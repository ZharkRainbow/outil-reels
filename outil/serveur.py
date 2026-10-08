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
from urllib.parse import parse_qs, urlparse

RACINE = Path(__file__).parent
sys.path.insert(0, str(RACINE.parent / "scripts"))
import reglages

DEPOT = RACINE / "cadrages"
RENDU = RACINE.parent / "scripts" / "rendre-reel.py"
TAILLE_BLOC = 1 << 20
# Les exports passent un par un : on peut en lancer dix d'affilee sans que
# dix rendus 4K se disputent la machine.
FILE = queue.Queue()
ETATS = {}            # nom -> "attente", "cours", ou code de sortie du rendu


def ouvrier():
    while True:
        nom, fichier = FILE.get()
        ETATS[nom] = "cours"
        # un lot peut demander un rendu brut sans habillage, deposant le reel dans
        # un dossier : "production": {"script": "produire-split.py", "sortie": "..."}
        manifeste = Path(reglages.LOTS) / "reels.json"
        prod = json.loads(manifeste.read_text(encoding="utf-8")).get("production") \
            if manifeste.exists() else None
        cmd = [sys.executable, "-u", str(RACINE.parent / "scripts" / prod["script"]),
               str(fichier), prod["sortie"]] if prod else [sys.executable, "-u", str(RENDU), str(fichier)]
        with open(DEPOT / f"{nom}.log", "w", encoding="utf-8") as journal:
            code = subprocess.run(cmd, stdout=journal, stderr=subprocess.STDOUT).returncode
        ETATS[nom] = code
        print(f"[{datetime.now():%H:%M:%S}] export {'ok' if code == 0 else 'ECHEC'} : {nom}",
              flush=True)


class H(SimpleHTTPRequestHandler):

    def repondre(self, donnees, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
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

    def do_POST(self):
        if not self.hote_local():
            return
        if self.path not in ("/enregistrer", "/exporter"):
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            d = json.loads(self.rfile.read(n))
        except Exception:
            return self.send_error(400)
        DEPOT.mkdir(exist_ok=True)
        reel = "reel" in d and "debuts" in d
        if reel:
            # le nom porte le format, quelle que soit la version de la page qui envoie :
            # sinon le vertical et l'horizontal d'un meme reel s'ecrasent
            format_ = {"vmc": "vertical", "hmc": "horizontal", "hsolo": "horizontal",
                       "carre": "carre"}.get(d.get("format"), d.get("format"))
            d["passage"] = f"{d.get('lot') or 'Reel'} {d['reel']} - {format_}"
        nom = (d.get("passage") or "sans-passage").replace("/", "-")[:60]
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

        if ETATS.get(nom) in ("attente", "cours"):
            return self.repondre({"ok": False, "erreur": "cet export est deja dans la file"})
        ETATS[nom] = "attente"
        (DEPOT / f"{nom}.log").write_text("", encoding="utf-8")
        FILE.put((nom, f))
        print(f"[{datetime.now():%H:%M:%S}] export en file : {nom}", flush=True)
        self.repondre({"ok": True, "nom": nom, "fichier": f"{nom}.json (export en file)"})

    def do_GET(self):
        if not self.hote_local():
            return
        url = urlparse(self.path)
        if url.path != "/export-etat":
            return super().do_GET()
        nom = parse_qs(url.query).get("nom", [""])[0]
        etat, journal = ETATS.get(nom), DEPOT / f"{nom}.log"
        if etat == "attente":
            devant = [n for n, _ in list(FILE.queue)].index(nom) if nom in [n for n, _ in list(FILE.queue)] else 0
            en_cours = sum(1 for e in ETATS.values() if e == "cours")
            return self.repondre({"texte": f"{nom} : en file d'attente, {devant + en_cours} export(s) avant",
                                  "fini": False})
        lignes = [l for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()] \
            if journal.exists() else []
        texte = lignes[-1] if lignes else "Export en préparation..."
        if etat == "cours":
            texte = f"En cours — {nom} : {texte}"
        elif etat == 0:
            texte = f"Prêt — {texte}"
        fini = etat not in ("cours",)
        if isinstance(etat, int) and etat:
            texte = f"Echec de l'export ({journal.name}) : {texte}"
        self.repondre({"texte": texte, "fini": fini})

    def send_head(self):
        """Ajoute le support des requetes Range, indispensable pour le seek."""
        chemin = self.translate_path(self.path)
        if os.path.isdir(chemin):
            return super().send_head()
        plage = self.headers.get("Range")
        if not plage:
            self.send_header_accept_ranges = True
            f = super().send_head()
            return f
        m = re.match(r"bytes=(\d*)-(\d*)", plage)
        if not m or not os.path.isfile(chemin):
            return super().send_head()

        taille = os.path.getsize(chemin)
        debut = int(m.group(1)) if m.group(1) else 0
        fin = int(m.group(2)) if m.group(2) else taille - 1
        fin = min(fin, taille - 1)
        if debut > fin:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{taille}")
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
    DEPOT.mkdir(exist_ok=True)
    threading.Thread(target=ouvrier, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", reglages.PORT), H).serve_forever()
