#!/usr/bin/env python3
"""Prepare un lot de reels split screen pour l'outil de recadrage.

Chaque reel est une prise filmee par deux cameras : la face cam (reference du
temps et du son) et la camera sur la tablette. Pour chaque paire :

1. mesure le decalage entre les deux cameras par le son (caler-flux.py) ;
2. fabrique le proxy de l'outil : les deux flux cote a cote en 1280x360,
   cales, avec le son de la face cam, une image-cle toutes les 10 images ;
3. detecte les blancs par le niveau sonore moyen, par tranches de 10 ms ;
4. transcrit la face cam mot a mot (whisper, -ml 1) sur un son dont les longs
   blancs ont ete raccourcis, puis recale chaque mot sur le temps reel ;
5. propose les coupes : les blancs, plus les reprises et faux departs notes a
   la main dans reels/decisions.json (reperes par le texte, pas par le temps).

Chaque etape est sautee si son fichier existe deja, sauf les coupes, toujours
recalculees.

Pourquoi raccourcir les blancs avant whisper : pendant qu'il dessine sur la
tablette, la personne se tait parfois 20 s. Whisper invente alors des phrases
repetees dans le silence et etire les mots voisins sur plusieurs secondes.

    python3 preparer-reels.py "<dossier face cam>" "<dossier ecran>" [numeros...] [--retourner-ecran]
    python3 preparer-reels.py "<dossier face cam>" - --lot Matin --sortie "Mes reels"

Avec "-" a la place du dossier ecran, les prises n'ont qu'une camera : pas de
calage, et le proxy garde le format de l'outil (camera a gauche, noir a droite).
Les prises sont alors numerotees 1, 2, 3... dans l'ordre des fichiers.
--lot prefixe le nom des reels (et de leurs fichiers de reglages), --sortie
donne le dossier d'export (voir REELS_SORTIE dans scripts/reglages.py).

--retourner-ecran : la camera de la tablette a filme a l'envers. L'image est
tournee de 180 degres dans le proxy, et le reglage est note dans reels.json
pour que l'export fasse la meme rotation avant d'appliquer les cadrages.
"""
import json
import math
import re
import subprocess
import sys
import tempfile
import wave
from array import array
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
caler = import_module("caler-flux")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reglages

RACINE = reglages.RACINE
DEPOT = reglages.LOTS
MODELE = reglages.MODELE_WHISPER
VISAGE = reglages.REPERER_VISAGE     # compile depuis outils/reperer-visage.swift
FPS = 25
SEUIL_BLANC = -37.0      # dBFS RMS : voix vers -20, plancher de bruit vers -57
BLANC_MIN = 0.25          # en dessous, c'est une respiration de phrase
BLANC_COUPE = 0.45        # un blanc plus long est resserre...
PAUSE_AVANT = 0.12        # ... en gardant 0,12 s apres la fin du son
PAUSE_APRES = 0.10        # ... et 0,10 s avant la reprise de parole


def duree(chemin):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(chemin)], capture_output=True, text=True, check=True).stdout)


def proxy_seul(camera, dst):
    """Une seule camera : a gauche, comme dans le proxy a deux flux."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-i", str(camera),
        "-vf", f"fps={FPS},scale=640:360,pad=1280:360:0:0:black",
        "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
        "-g", "10", "-keyint_min", "10", "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], check=True)


def proxy(camera, ecran, decal, retourner, dst):
    """Les deux flux cote a cote. Ecran en retard : on fige sa premiere image."""
    entree_ecran = ["-ss", f"{decal:.3f}"] if decal > 0 else []
    retard = f",tpad=start_duration={-decal:.3f}:start_mode=clone" if decal < 0 else ""
    rotation = "hflip,vflip," if retourner else ""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-hwaccel", "videotoolbox", "-i", str(camera),
        "-hwaccel", "videotoolbox", *entree_ecran, "-i", str(ecran),
        "-filter_complex",
        f"[0:v:0]fps={FPS},scale=640:360[a];"
        f"[1:v:0]{rotation}fps={FPS},scale=640:360{retard}[b];[a][b]hstack=inputs=2[v]",
        "-map", "[v]", "-map", "0:a:0", "-t", f"{duree(camera):.3f}",
        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
        "-g", "10", "-keyint_min", "10", "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], check=True)


def visages(proxy_, tmp):
    """Position du visage une fois par seconde, lue sur la moitie camera du proxy.

    Detection par Vision (outils/reperer-visage), en fractions de l'image
    camera, origine en haut a gauche : [[t, x, y, largeur, hauteur], ...].
    """
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(proxy_), "-vf",
                    "fps=1,crop=640:360:0:0", str(tmp / "v%04d.png")], check=True)
    images = sorted(tmp.glob("v*.png"))
    sortie = subprocess.run([str(VISAGE)] + [str(i) for i in images],
                            capture_output=True, text=True, check=True).stdout
    piste = []
    for ligne in sortie.splitlines():
        chemin, *valeurs = ligne.rsplit(" ", 4)
        if len(valeurs) == 4:
            t = int(Path(chemin).stem[1:]) - 1
            piste.append([t, *(round(float(v), 4) for v in valeurs)])
    return piste


def wav(camera, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(camera), "-map", "0:a:0",
                    "-ac", "1", "-ar", "16000", str(dst)], check=True)


def niveaux(wav_):
    """Niveau moyen (RMS, dBFS) par tranche de 10 ms."""
    with wave.open(str(wav_)) as w:
        taux, brut = w.getframerate(), w.readframes(w.getnframes())
    s, k = array("h"), taux // 100
    s.frombytes(brut)
    res = []
    for i in range(0, len(s) - k, k):
        e = sum(v * v for v in s[i:i + k]) / k
        res.append(10 * math.log10(e / 32768 ** 2) if e else -99.0)
    return res


def blancs(db, minimum=BLANC_MIN):
    """Intervalles sous le seuil, en secondes.

    Mesure au niveau moyen et non au pic (silencedetect) : un seul clic de
    stylet sur la tablette suffisait a couper un blanc de 0,8 s en deux
    morceaux trop courts, et la pause passait inapercue. Un son de moins de
    20 ms n'interrompt donc pas un blanc ; un vrai mot dure plus longtemps.
    """
    res, debut, son = [], None, 0
    for i, v in enumerate(db + [0.0]):
        if v < SEUIL_BLANC:
            if debut is None:
                debut = i
            son = 0
            continue
        son += 1
        if debut is not None and (son >= 2 or i == len(db)):
            fin = i - son + 1
            if (fin - debut) / 100 >= minimum:
                res.append([round(debut / 100, 3), round(fin / 100, 3)])
            debut = None
    return res


def transcrire(wav_, base, longs):
    """Transcrit un son dont les blancs de plus de 0,8 s sont ramenes a 0,4 s."""
    with wave.open(str(wav_)) as w:
        taux, brut = w.getframerate(), w.readframes(w.getnframes())
    octets = 2
    garde, curseur = [], 0.0
    for a, b in longs:
        if b - a >= 0.8:
            garde.append((curseur, a + 0.2))
            curseur = b - 0.2
    garde.append((curseur, len(brut) / octets / taux))
    table, sortie, t = [], bytearray(), 0.0
    for a, b in garde:
        morceau = brut[int(a * taux) * octets:int(b * taux) * octets]
        table.append((t, a, len(morceau) / octets / taux))
        sortie += morceau
        t += len(morceau) / octets / taux
    compact = Path(f"{base}.compact.wav")
    with wave.open(str(compact), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(octets)
        w.setframerate(taux)
        w.writeframes(bytes(sortie))
    subprocess.run(["whisper-cli", "-m", str(MODELE), "-l", reglages.LANGUE, "-f", str(compact),
                    "-ml", "1", "-sow", "-oj", "-of", str(base)],
                   check=True, capture_output=True)
    compact.unlink()

    def reel(tc):
        for debut_c, debut_r, longueur in reversed(table):
            if tc >= debut_c:
                return debut_r + min(tc - debut_c, longueur)
        return tc

    sortie_whisper = Path(f"{base}.json")
    d = json.loads(sortie_whisper.read_text(encoding="utf-8"))
    mots_ = []
    for seg in d["transcription"]:
        texte = seg["text"].strip()
        if texte:
            mots_.append([round(reel(seg["offsets"]["from"] / 1000), 3),
                          round(reel(seg["offsets"]["to"] / 1000), 3), texte])
    sortie_whisper.write_text(json.dumps(mots_, ensure_ascii=False), encoding="utf-8")


def norme(texte):
    return re.sub(r"[^\w%]+", " ", texte.lower()).split()


def trouver(mots_, phrase, occurrence=1, apres=-1.0):
    """Temps du premier mot de la n-ieme occurrence de la phrase apres 'apres'."""
    cible = norme(phrase)
    flux = []                      # (jeton normalise, indice du mot)
    for i, m in enumerate(mots_):
        flux += [(j, i) for j in norme(m[2])]
    vus = 0
    for k in range(len(flux) - len(cible) + 1):
        if [j for j, _ in flux[k:k + len(cible)]] == cible and mots_[flux[k][1]][0] > apres:
            vus += 1
            if vus == occurrence:
                return mots_[flux[k][1]][0]
    raise ValueError(f"phrase introuvable : {phrase!r}")


def reprise_de_parole(t, fins_blancs, marge=0.4):
    """Fin du blanc qui precede le mot a t : le vrai debut du son, a 10 ms pres."""
    proches = [b for b in fins_blancs if abs(b - t) < marge]
    return min(proches, key=lambda b: abs(b - t)) if proches else t


def premiere_parole(longs):
    """Debut du premier son qui dure plus de 0,3 s : on ignore clics et souffles."""
    for c in [0.0] + [b for _, b in longs]:
        suivant = next((a for a, _ in longs if a >= c), None)
        if suivant is None or suivant - c >= 0.3:
            return c
    return 0.0


def coupes(n, mots_, longs, fins, duree_reel, decisions):
    """Blancs a resserrer, puis reprises et faux departs decides a la lecture.

    Dans decisions.json, une borne se donne par une phrase ("depuis" : la
    premiere phrase jetee, "jusqua" : la premiere phrase gardee), recalee sur
    la reprise de parole mesuree dans le son, ou en secondes ("de_s", "a_s")
    quand whisper a fusionne deux prises et ne donne pas de temps fiable.
    """
    res = []
    for a, b in longs:
        if b - a >= BLANC_COUPE:
            res.append({"a": round(a + PAUSE_AVANT, 3), "b": round(b - PAUSE_APRES, 3),
                        "type": "blanc"})
    dec = decisions.get(n, {})
    for c in dec.get("coupes", []):
        if "de_s" in c:
            a = c["de_s"]
        else:
            a = reprise_de_parole(trouver(mots_, c["depuis"], c.get("occurrence", 1)), fins) \
                - PAUSE_APRES
        if "a_s" in c:
            b = c["a_s"]
        else:
            b = reprise_de_parole(trouver(mots_, c["jusqua"], 1, apres=a + 0.2), fins) - PAUSE_APRES
        res.append({"a": round(max(0.0, a), 3), "b": round(b, 3), "type": "reprise",
                    "texte": c.get("pourquoi", ""), "on": c.get("on", True)})
    debuts = []
    for d in dec.get("debuts", [{}]):
        if "s" in d:
            t = d["s"]
        elif "phrase" in d:
            t = reprise_de_parole(trouver(mots_, d["phrase"], d.get("occurrence", 1)), fins) \
                - PAUSE_APRES
        else:
            t = premiere_parole(longs) - PAUSE_APRES
        debuts.append(round(max(0.0, t), 3))
    dernier = longs[-1] if longs else None
    fin = round(dernier[0] + 0.25, 3) if dernier and dernier[1] >= duree_reel - 0.1 else duree_reel
    fin = dec.get("fin_s", fin)       # quand un bruit final passe pour de la parole
    return res, debuts, fin


def main():
    dossier_cam, seul = Path(sys.argv[1]), sys.argv[2] == "-"
    dossier_ecran = None if seul else Path(sys.argv[2])
    retourner = "--retourner-ecran" in sys.argv
    options = {sys.argv[i]: sys.argv[i + 1] for i in range(3, len(sys.argv) - 1)
               if sys.argv[i] in ("--lot", "--sortie")}
    valeurs = set(options.values())
    voulus = [a for a in sys.argv[3:] if not a.startswith("--") and a not in valeurs]
    DEPOT.mkdir(parents=True, exist_ok=True)
    manifeste = DEPOT / "reels.json"
    lot = json.loads(manifeste.read_text()) if manifeste.exists() else {"reels": []}
    if "--lot" in options:
        lot["lot"] = options["--lot"]
    if "--sortie" in options:
        lot["sortie"] = options["--sortie"]
    par_id = {r["id"]: r for r in lot["reels"]}
    fichier_decisions = DEPOT / "decisions.json"
    decisions = json.loads(fichier_decisions.read_text(encoding="utf-8")) \
        if fichier_decisions.exists() else {}

    for rang, camera in enumerate(sorted(dossier_cam.glob("*.MP4")), 1):
        n = str(rang) if seul else camera.stem
        ecran = None if seul else dossier_ecran / camera.name
        if (ecran is not None and not ecran.exists()) or (voulus and n not in voulus):
            continue
        if n not in par_id:
            par_id[n] = {"id": n}
            lot["reels"].append(par_id[n])
        r = par_id[n]
        r.update(nom=f"{lot.get('lot', 'Reel')} {n}", camera=str(camera),
                 ecran=str(ecran) if ecran else None, fichier=camera.name,
                 duree=round(duree(camera), 3), donnees=f"reels/{n}.json")
        if seul:
            r["decalage"], r["confiance_calage"] = 0.0, None
        elif "decalage" not in r:
            d, conf = caler.decalage(str(camera), str(ecran))
            r["decalage"], r["confiance_calage"] = round(d, 3), round(conf, 3)
        if not seul:
            print(f"[{n}] decalage ecran {r['decalage']:+.3f} s "
                  f"(correlation {r['confiance_calage']})", flush=True)
        manifeste.write_text(json.dumps(lot, ensure_ascii=False, indent=1), encoding="utf-8")

        fichier_proxy = DEPOT / f"{n}.mp4"
        if seul:
            if not fichier_proxy.exists():
                proxy_seul(camera, fichier_proxy)
                print(f"[{n}] proxy ok ({camera.name})", flush=True)
        elif not fichier_proxy.exists() or r.get("retourner_ecran", False) != retourner:
            proxy(camera, ecran, r["decalage"], retourner, fichier_proxy)
            r["retourner_ecran"] = retourner
            print(f"[{n}] proxy ok" + (" (ecran tourne de 180 degres)" if retourner else ""), flush=True)
        # la version dans l'adresse oblige le navigateur a recharger un proxy refait
        r["proxy"] = f"reels/{n}.mp4?v={int(fichier_proxy.stat().st_mtime)}"
        manifeste.write_text(json.dumps(lot, ensure_ascii=False, indent=1), encoding="utf-8")
        w = DEPOT / f"{n}.wav"
        if not w.exists():
            wav(camera, w)
        db = niveaux(w)
        longs, fins = blancs(db), [b for _, b in blancs(db, 0.06)]
        if not (DEPOT / f"{n}.mots.json").exists():
            transcrire(w, DEPOT / f"{n}.mots", longs)
            print(f"[{n}] transcription ok", flush=True)
        mots_ = json.loads((DEPOT / f"{n}.mots.json").read_text(encoding="utf-8"))
        propositions, debuts, fin = coupes(n, mots_, longs, fins, r["duree"], decisions)
        donnees = DEPOT / f"{n}.json"
        ancien = json.loads(donnees.read_text(encoding="utf-8")) if donnees.exists() else {}
        piste = ancien.get("visage")
        if seul and piste is None:
            with tempfile.TemporaryDirectory() as t:
                piste = visages(fichier_proxy, Path(t))
            print(f"[{n}] visage repere sur {len(piste)} images", flush=True)
        contenu = {"mots": mots_, "blancs": longs, "coupes": propositions,
                   "debuts": debuts, "debut": debuts[0], "fin": fin,
                   "titre": decisions.get(n, {}).get("titre", "")}
        if piste is not None:
            contenu["visage"] = piste
        donnees.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
        print(f"[{n}] {len(mots_)} mots, {len(propositions)} coupes proposees, "
              f"debut(s) {debuts}, fin {fin}", flush=True)

    lot["reels"].sort(key=lambda r: (len(r["id"]), r["id"]))
    manifeste.write_text(json.dumps(lot, ensure_ascii=False, indent=1), encoding="utf-8")
    print("TERMINE")


if __name__ == "__main__":
    main()
