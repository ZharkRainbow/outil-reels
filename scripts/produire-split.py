#!/usr/bin/env python3
"""Rendu brut d'un reel deux cameras, sans habillage : le cadre fixe du premier
point de cadrage, le depart et la fin choisis dans l'outil, les coupes gardees.
Ni sous-titres, ni titre, ni traitement du son. C'est la version a valider avant
la finition.

    python3 produire-split.py "outil/cadrages/<nom>.json" "<dossier de sortie>"

Le son vient de la camera du haut (y mixer les deux micros a la preparation).
Les cadres de l'outil sont exprimes dans le repere de la camera du haut : le
cadre du bas est remis a l'echelle de sa propre source.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def largeur(chemin):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width", "-of", "csv=p=0", str(chemin)],
                       capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def main():
    d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sortie = Path(sys.argv[2])
    sortie.mkdir(parents=True, exist_ok=True)
    cam, ecran = RACINE / d["camera"], RACINE / d["ecran"]
    a, b = d["debuts"][0], d["fin"]

    gardes, t = [], a
    for x, y in sorted(c for c in d.get("coupes", []) if c[1] > a and c[0] < b):
        if x > t:
            gardes.append((t, min(x, b)))
        t = max(t, y)
    if t < b:
        gardes.append((t, b))

    p = d["points"][0]
    h = p["camera"]
    k = largeur(ecran) / d["source"]["w"]
    e = {z: round(p["ecran"][z] * k) for z in ("x", "y", "w", "h")}
    morceaux = []
    for i, (s, f) in enumerate(gardes):
        morceaux.append(
            f"[0:v]trim={s}:{f},setpts=PTS-STARTPTS,crop={h['w']}:{h['h']}:{h['x']}:{h['y']},"
            f"scale=1080:960,setsar=1[h{i}];"
            f"[1:v]trim={s}:{f},setpts=PTS-STARTPTS,crop={e['w']}:{e['h']}:{e['x']}:{e['y']},"
            f"scale=1080:960,setsar=1[b{i}];"
            f"[h{i}][b{i}]vstack,fps=30,format=yuv420p[v{i}];"
            f"[0:a]atrim={s}:{f},asetpts=PTS-STARTPTS[a{i}];")
    filtre = "".join(morceaux) + "".join(f"[v{i}][a{i}]" for i in range(len(gardes))) \
        + f"concat=n={len(gardes)}:v=1:a=1[v][a]"

    titre = re.sub(r"[^\w\s'-]", "", d.get("titre", "")).strip()
    nom = f"{d['reel']} - {titre}.mp4" if titre else f"{d['reel']}.mp4"
    for vieux in sortie.glob(f"{d['reel']} - *.mp4"):
        vieux.unlink()
    print(f"{len(gardes)} morceau(x), {sum(f - s for s, f in gardes):.1f} s -> {nom}", flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-i", str(ecran),
                    "-filter_complex", filtre, "-map", "[v]", "-map", "[a]",
                    "-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(sortie / nom)], check=True)
    print(f"Reel pret : {sortie / nom}", flush=True)


if __name__ == "__main__":
    main()
