#!/usr/bin/env python3
"""Sert l'outil de recadrage et recoit les cadrages.

POINT CRITIQUE : SimpleHTTPRequestHandler ne gere PAS les requetes Range HTTP.
Il repond 200 avec le fichier entier au lieu de 206 avec la plage demandee.
Pour une video de 146 Mo, le navigateur doit donc tout telecharger avant de
lire, et surtout il ne peut pas se deplacer dans la timeline : chaque seek
redemande le fichier depuis le debut, le decodeur repart de zero et l'image
reste figee sur les premieres frames.

C'etait la cause reelle des "bugs de synchronisation" de l'outil. On implemente
donc Range ici.
"""
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

RACINE = Path(__file__).parent
sys.path.insert(0, str(RACINE.parent / "scripts"))
import reglages
import formats
import etalonnage

DEPOT = Path(os.environ.get("REELS_CADRAGES", RACINE / "cadrages"))
RENDU = RACINE.parent / "scripts" / "rendre-reel.py"
TAILLE_BLOC = 1 << 20
# Les exports passent un par un : on peut en lancer dix d'affilee sans que
# dix rendus 4K se disputent la machine.
FILE = queue.Queue()
ETATS = {}            # nom -> "attente", "cours", ou code de sortie du rendu
# Mesures et images de controle de l'etalonnage. Une mesure coute cinq appels
# a ffmpeg, une image un : sans ce cache, changer de reel et revenir relancerait
# tout, et la machine n'a que deux coeurs. La cle porte la date et la taille du
# fichier : un rush remplace est remesure.
DIAGS = {}
APERCUS = {}
APERCUS_MAX = 40
LARGE_APERCU = 384


def ouvrier():
    """Un seul export a la fois. Quoi qu'il arrive, la boucle survit : si ce
    thread meurt, la file se bloque sans que rien ne l'annonce a l'ecran."""
    while True:
        nom, fichier = FILE.get()
        code = 1
        try:
            ETATS[nom] = "cours"
            code = lancer_export(nom, fichier)
        except Exception as exc:
            try:
                (DEPOT / f"{nom}.log").write_text(str(exc), encoding="utf-8")
            except OSError:
                pass
            print(f"[{datetime.now():%H:%M:%S}] export impossible : {nom} : {exc}", flush=True)
        finally:
            ETATS[nom] = code
            # ETATS vit en memoire : apres un redemarrage, un export reussi
            # repassait pour un echec dans la colonne de suivi de la page.
            # L'issue est donc aussi posee a cote du journal.
            try:
                (DEPOT / f"{nom}.etat").write_text(str(code), encoding="utf-8")
            except OSError:
                pass
            FILE.task_done()
        print(f"[{datetime.now():%H:%M:%S}] export {'ok' if code == 0 else 'ECHEC'} : {nom}",
              flush=True)


def nom_interne(passage):
    """Nom de travail d'un export : court, sans separateur de chemin, et unique.

    La coupe a soixante caracteres se faisait APRES avoir collé le format. Sur un
    identifiant de reel un peu long, « ... - vertical 50-50 » et « ... - horizontal »
    tombaient donc sur le meme nom : meme fichier de cadrage, meme journal, et le
    second export refuse comme « deja dans la file ». On garde maintenant le debut
    du libelle (il situe le lot) ET sa fin (elle porte le format), et on ajoute une
    empreinte du libelle entier, qui separe deux passages que la coupe confondrait.
    """
    propre = re.sub(r'[\\/:\x00-\x1f]', '-', str(passage or "sans-passage"))
    if len(propre) <= 60:
        return propre
    empreinte = hashlib.sha1(propre.encode("utf-8")).hexdigest()[:8]
    return f"{propre[:28]}--{propre[-20:]} {empreinte}"


def issue_sur_disque(nom):
    """Code de sortie d'un export termine avant le redemarrage, ou None."""
    try:
        return int((DEPOT / f"{nom}.etat").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def lancer_export(nom, fichier):
    # un lot peut demander un rendu brut sans habillage, deposant le reel dans
    # un dossier : "production": {"script": "produire-split.py", "sortie": "..."}
    d = json.loads(fichier.read_text(encoding="utf-8"))
    manifeste = manifeste_lot(d.get("lot_id", "reels"))
    prod = json.loads(manifeste.read_text(encoding="utf-8")).get("production") if manifeste.exists() else None
    if prod is not None:
        if not isinstance(prod, dict) or prod.get("script") != "produire-split.py":
            raise ValueError("Script de production non autorisé")
        cmd = [sys.executable, "-u", str(RACINE.parent / "scripts" / prod["script"]),
               str(fichier), str(prod.get("sortie") or "")]
    else:
        cmd = [sys.executable, "-u", str(RENDU), str(fichier)]
    with open(DEPOT / f"{nom}.log", "w", encoding="utf-8") as journal:
        return subprocess.run(cmd, stdout=journal, stderr=subprocess.STDOUT).returncode


# Champs que le rendu transforme en chemins ou en decalages. Ils ne doivent
# jamais venir du corps de la requete : une page tierce pourrait y glisser
# "/etc/shadow" ou une URL distante, que ffmpeg ouvrirait sans discuter.
CHAMPS_DU_LOT = ("camera", "ecran", "audio", "decalage", "retourner_ecran", "base", "public")


def fiche_du_lot(lot_id, reel_id):
    """Manifeste du lot et fiche du reel demande, lus sur le disque."""
    manifeste = manifeste_lot(lot_id)
    lot = json.loads(manifeste.read_text(encoding="utf-8"))
    for fiche in lot.get("reels", []):
        if str(fiche.get("id")) == str(reel_id):
            return lot, fiche
    return lot, None


def rush_du_reel(lot_id, reel_id, source):
    """Le chemin du rush, pris dans le MANIFESTE et jamais dans la requete.
    Meme principe que CHAMPS_DU_LOT a l'enregistrement : la page choisit un
    reel et une camera, pas un fichier."""
    if source not in ("camera", "ecran"):
        raise ValueError("Source inconnue")
    lot, fiche = fiche_du_lot(lot_id, reel_id)
    if fiche is None or not fiche.get(source):
        raise ValueError("Reel absent du manifeste, ou sans ce rush")
    chemin = (RACINE.parent / fiche[source]).resolve()
    if not chemin.is_file():
        raise ValueError(f"Rush introuvable : {fiche[source]}")
    return chemin


def _cle(chemin):
    s = chemin.stat()
    return (str(chemin), int(s.st_mtime), s.st_size)


def manifeste_lot(nom):
    if not nom or nom in (".", "..") or "/" in nom or "\\" in nom:
        raise ValueError("Nom de lot invalide")
    chemin = Path(reglages.LOTS) / nom / "reels.json"
    if nom == "exemple" and not chemin.exists():
        return RACINE.parent / "exemple" / "reels.json"
    if nom == "reels" and not chemin.exists():
        return Path(reglages.LOTS) / "reels.json"  # ancien lot podcast
    return chemin


def image_de_controle(rush, filtre):
    """Une image fixe du rush, LUT posee, pour juger l'etalonnage sans encoder.

    Prise a un cinquieme du rush : le tout debut est souvent un claquement de
    mains ou une mire, qui ne dit rien de l'etalonnage de la scene.
    """
    total = etalonnage.duree(rush)
    t = min(max(0.0, total * 0.2), max(0.0, total - 0.04))
    chaine = (filtre + "," if filtre else "") + f"scale={LARGE_APERCU}:-2:flags=lanczos"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error",
                        "-ss", f"{t:.3f}", "-i", str(rush), "-frames:v", "1",
                        "-vf", chaine, "-q:v", "3", "-f", "mjpeg", "-"],
                       capture_output=True, timeout=90)
    if r.returncode or not r.stdout:
        raise ValueError((r.stderr or b"").decode("utf-8", "replace").strip()
                         or "ffmpeg n'a pas produit d'image")
    return r.stdout


class H(SimpleHTTPRequestHandler):

    def translate_path(self, path):
        url = unquote(urlparse(path).path)
        if url in ("/", "/index.html", "/outil/index.html"):
            return str(RACINE / "index.html")
        if url.startswith("/lots/"):
            try:
                nom, relatif = url[len("/lots/"):].split("/", 1)
                base = manifeste_lot(nom).parent.resolve()
                # l'ancien lot pose ses fichiers a plat dans LOTS, a cote des
                # autres lots : sans ca, /lots/reels/<autre lot>/ les servirait
                if base == Path(reglages.LOTS).resolve() and "/" in relatif:
                    raise ValueError("Chemin hors du lot")
                cible = (base / relatif).resolve()
                if not cible.is_relative_to(base) or cible.is_dir():
                    raise ValueError("Chemin hors du lot")
                return str(cible)
            except ValueError:
                return str(RACINE / "introuvable")
        return str(RACINE / "introuvable")

    def repondre(self, donnees, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(donnees, ensure_ascii=False).encode())

    def hote_local(self):
        """Refuse les requetes d'un autre site (DNS rebinding) : le serveur rend
        des fichiers et lance des exports, il ne doit repondre qu'a localhost."""
        hote = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if hote in ("localhost", "127.0.0.1"):
            return True
        self.send_error(403)
        return False

    def meme_origine(self):
        """Refuse une requete fabriquee par un autre site. Le controle du Host
        arrete le DNS rebinding ; celui-ci arrete la CSRF ordinaire, qui passe
        sans pre-vol CORS avec un Content-Type simple."""
        # on se compare au Host, deja restreint a localhost : le port peut
        # changer (REELS_PORT, second serveur de test) sans casser l'envoi
        attendues = {f"http://{self.headers.get('Host')}"}
        origine = self.headers.get("Origin")
        depuis = self.headers.get("Sec-Fetch-Site")
        if (origine and origine not in attendues) or (depuis and depuis != "same-origin"):
            self.send_error(403)
            return False
        return True

    def do_HEAD(self):
        if self.hote_local():
            super().do_HEAD()

    def do_POST(self):
        if not self.hote_local() or not self.meme_origine():
            return
        if self.path not in ("/enregistrer", "/exporter"):
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise ValueError("Objet attendu")
        except Exception:
            return self.send_error(400)
        # l'etalonnage n'arrive jamais comme un chemin, seulement comme une
        # cle de la table : un nom de .cube venu du reseau n'a rien a faire
        # dans une ligne de commande ffmpeg. On verifie d'abord la FORME : sur
        # {"etalonnages": ["x"]}, .items() levait une AttributeError hors de
        # tout filet et le serveur coupait la connexion au lieu de repondre 400.
        etals = d.get("etalonnages")
        if etals is not None and not isinstance(etals, dict):
            return self.send_error(400, "Étalonnages : objet attendu")
        for source, cle in (etals or {}).items():
            if source not in ("camera", "ecran") or not isinstance(cle, str) \
                    or cle not in etalonnage.ETALONNAGES:
                return self.send_error(400, "Étalonnage inconnu")
        # meme raison : la page compte ses points pour le journal, et un
        # "points": 17 venu du reseau cassait la reponse plutot que la refuser
        if not isinstance(d.get("points", []), list):
            return self.send_error(400, "Points : liste attendue")
        if "debuts" in d and not isinstance(d["debuts"], list):
            return self.send_error(400, "Débuts : liste attendue")
        if d.get("titre_position") not in (None, "haut", "milieu", "aucun"):
            return self.send_error(400, "Position de titre inconnue")
        DEPOT.mkdir(parents=True, exist_ok=True)
        reel = "reel" in d and "debuts" in d
        if reel:
            # on reprend du manifeste tout ce qui devient un chemin a l'export
            try:
                lot, fiche = fiche_du_lot(d.get("lot_id") or "reels", d["reel"])
            except (ValueError, OSError, json.JSONDecodeError):
                return self.send_error(400, "Lot introuvable")
            if fiche is None:
                return self.send_error(400, "Reel absent du manifeste")
            for cle in CHAMPS_DU_LOT:
                d.pop(cle, None)
                if cle in fiche:
                    d[cle] = fiche[cle]
            d["lot"], d["sortie"], d["rendu"] = lot.get("lot"), lot.get("sortie"), lot.get("rendu")
            # le nom porte le format, quelle que soit la version de la page qui envoie :
            # sinon deux formats du meme reel s'ecrasent. Le libelle vient de la
            # table partagee, pas d'une liste recopiee ici.
            try:
                format_ = formats.nom_fichier(d.get("format") or "vmc")
            except ValueError:
                return self.send_error(400, "Format inconnu")
            d["passage"] = f"{d.get('lot_id') or d.get('lot') or 'Reel'} {d['reel']} - {format_}"
        nom = nom_interne(d.get("passage"))
        if ETATS.get(nom) in ("attente", "cours"):
            return self.repondre({"ok": False, "erreur": "cet export est déjà dans la file"}, 409)
        f = DEPOT / f"{nom}.json"
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{datetime.now():%H:%M:%S}] recu : {f.name} "
              f"({len(d.get('points', []))} point(s))", flush=True)
        # un lot peut demander qu'on garde le cadrage sans rendre : "rendu": false
        # dans son reels.json, quand le rendu se fait ailleurs.
        if reel and d.get("rendu") is False:
            return self.repondre({"ok": True, "garde": True, "fichier": f.name})
        # un reel envoye est un reel a exporter, quel que soit le bouton clique
        if self.path == "/enregistrer" and not reel:
            return self.repondre({"ok": True, "fichier": f.name})

        ETATS[nom] = "attente"
        (DEPOT / f"{nom}.log").write_text("", encoding="utf-8")
        (DEPOT / f"{nom}.etat").unlink(missing_ok=True)   # l'issue precedente ne vaut plus
        FILE.put((nom, f))
        print(f"[{datetime.now():%H:%M:%S}] export en file : {nom}", flush=True)
        self.repondre({"ok": True, "nom": nom, "fichier": f"{nom}.json (export en file)"})

    def etalonner(self, url):
        """Mesure d'un rush, ou son image de controle avec la LUT posee."""
        q = parse_qs(url.query)
        try:
            rush = rush_du_reel(q.get("lot", ["reels"])[0], q.get("reel", [""])[0],
                               q.get("source", [""])[0])
        except (ValueError, OSError, json.JSONDecodeError) as pb:
            return self.send_error(400, str(pb))
        if url.path == "/etalonnage":
            cle = _cle(rush)
            if cle not in DIAGS:
                DIAGS[cle] = etalonnage.examiner(rush)
            return self.repondre(DIAGS[cle])
        choix = q.get("choix", ["aucun"])[0]
        try:
            filtre = etalonnage.filtre(choix, etalonnage.profondeur_bits(rush))
        except ValueError as pb:
            return self.send_error(409, str(pb))
        cle = _cle(rush) + (choix,)
        if cle not in APERCUS:
            try:
                APERCUS[cle] = image_de_controle(rush, filtre)
            except (ValueError, OSError, subprocess.SubprocessError) as pb:
                return self.send_error(500, str(pb)[:200])
            # on ne garde pas le journal de toute la session en memoire
            for vieille in list(APERCUS)[:-APERCUS_MAX]:
                APERCUS.pop(vieille, None)
        donnees = APERCUS[cle]
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        if not self.hote_local():
            return
        url = urlparse(self.path)
        if url.path == "/formats.json":
            # la page lit la meme table que les scripts de rendu
            return self.repondre(json.loads(formats.FICHIER.read_text(encoding="utf-8")))
        if url.path == "/etalonnages.json":
            # la page lit la meme table que produire-split.py, et sait des le
            # chargement quelle LUT manque sur le disque
            return self.repondre(etalonnage.catalogue())
        if url.path in ("/etalonnage", "/etalonnage-apercu"):
            return self.etalonner(url)
        if url.path == "/lots":
            lots = [] if (Path(reglages.LOTS) / "exemple" / "reels.json").exists() else [{"id": "exemple", "nom": "Exemple"}]
            chemins = list(Path(reglages.LOTS).glob("*/reels.json"))
            ancien = Path(reglages.LOTS) / "reels.json"
            if ancien.exists() and not (Path(reglages.LOTS) / "reels" / "reels.json").exists():
                chemins.append(ancien)
            for chemin in chemins:
                try:
                    d = json.loads(chemin.read_text(encoding="utf-8"))
                    ident = "reels" if chemin == ancien else chemin.parent.name
                    lots.append({"id": ident, "nom": d.get("lot", ident)})
                except (ValueError, OSError):
                    continue
            return self.repondre(lots)
        if url.path != "/export-etat":
            return super().do_GET()
        nom = parse_qs(url.query).get("nom", [""])[0]
        if not nom or "/" in nom or "\\" in nom:
            return self.send_error(400)
        etat, journal = ETATS.get(nom), DEPOT / f"{nom}.log"
        if etat is None:
            etat = issue_sur_disque(nom)      # export d'avant le redemarrage
        if etat == "attente":
            devant = [n for n, _ in list(FILE.queue)].index(nom) if nom in [n for n, _ in list(FILE.queue)] else 0
            en_cours = sum(1 for e in ETATS.values() if e == "cours")
            return self.repondre({"texte": f"{nom} : en file d'attente, {devant + en_cours} export(s) avant",
                                  "fini": False})
        # ffmpeg et whisper ecrivent directement dans ce journal : il peut
        # contenir des octets qui ne sont pas de l'UTF-8.
        lignes = [l for l in journal.read_text(encoding="utf-8", errors="replace").splitlines()
                  if l.strip()] if journal.exists() else []
        if etat is None and not lignes:
            return self.repondre({"texte": f"Export inconnu : {nom}", "fini": True, "ok": False})
        texte = lignes[-1] if lignes else "Export en préparation..."
        if etat == "cours":
            texte = f"En cours — {nom} : {texte}"
        elif etat == 0:
            texte = f"Prêt — {texte}"
        fini = etat not in ("cours",)
        if isinstance(etat, int) and etat:
            texte = f"Echec de l'export ({journal.name}) : {texte}"
        self.repondre({"texte": texte, "fini": fini, "ok": etat == 0})

    def send_head(self):
        """Ajoute le support des requetes Range, indispensable pour le seek."""
        chemin = self.translate_path(self.path)
        if os.path.isdir(chemin):
            return super().send_head()
        plage = self.headers.get("Range")
        self._reste = None
        if not plage:
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", plage)
        if not m or not os.path.isfile(chemin):
            return super().send_head()

        taille = os.path.getsize(chemin)
        if m.group(1):
            debut = int(m.group(1))
            fin = min(int(m.group(2)), taille - 1) if m.group(2) else taille - 1
        else:   # "bytes=-500" : les 500 derniers octets
            debut, fin = max(0, taille - int(m.group(2) or 0)), taille - 1
        if debut > fin or debut >= taille:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{taille}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        f = open(chemin, "rb")
        f.seek(debut)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(chemin))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        self.send_header("Content-Length", str(fin - debut + 1))
        self.end_headers()
        self._reste = fin - debut + 1
        return f

    def copyfile(self, source, sortie):
        """Ne copie que la plage demandee."""
        reste = getattr(self, "_reste", None)
        if reste is None:
            return super().copyfile(source, sortie)
        self._reste = None
        while reste > 0:
            bloc = source.read(min(TAILLE_BLOC, reste))
            if not bloc:
                break
            sortie.write(bloc)
            reste -= len(bloc)

    def end_headers(self):
        # la page et les manifestes changent souvent : jamais de version gardee en cache
        chemin = urlparse(self.path).path
        if chemin == "/" or chemin.endswith((".html", ".json")):
            self.send_header("Cache-Control", "no-store")
        if not self.path.endswith(".json"):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        # le navigateur annule ses requetes video a chaque seek : c'est normal
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


if __name__ == "__main__":
    print(f"Outil de reels : http://localhost:{reglages.PORT}")
    print(f"Les cadrages arrivent dans {DEPOT}/")
    DEPOT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=ouvrier, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", reglages.PORT), H).serve_forever()
