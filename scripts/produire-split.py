#!/usr/bin/env python3
"""Rendu brut d'un reel deux cameras, sans habillage : le cadre fixe du premier
point de cadrage, le depart et la fin choisis dans l'outil, les coupes gardees.
Ni sous-titres, ni titre, ni traitement du son. C'est la version a valider avant
la finition.

    python3 produire-split.py "outil/cadrages/<nom>.json" "<dossier de sortie>"

Le son vient du mix préparé avec --mixer-son, sinon de la caméra du haut.
Les cadres de l'outil sont exprimes dans le repere de la camera du haut : le
cadre du bas est remis a l'echelle de sa propre source.
"""
import json
import platform
import re
import subprocess
import sys
from importlib import import_module
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
reglages = import_module("reglages")


def flux_video(chemin):
    """Largeur et cadence de la piste image, lues par ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,r_frame_rate", "-of", "json", str(chemin)],
                       capture_output=True, text=True, check=True)
    flux = json.loads(r.stdout)["streams"][0]
    num, _, den = flux["r_frame_rate"].partition("/")
    return int(flux["width"]), int(num) / int(den or 1), flux["r_frame_rate"]


def rendre(d, sortie):
    cam, ecran = RACINE / d["camera"], RACINE / d["ecran"]
    large_cam, ips, cadence = flux_video(cam)

    # Les bornes sont calees sur la grille d'images de la camera du haut.
    # trim ne retient que des images entieres alors que atrim coupe le son a
    # l'echantillon : sans ce calage, concat etire chaque morceau jusqu'a sa
    # piste la plus longue et l'ecart s'accumule a chaque coupe. Sur neuf
    # morceaux le reel sortait 0,3 s trop long, l'image en retard sur le son.
    grille = lambda t: round(t * ips) / ips
    a, b = grille(d["debuts"][0]), grille(d["fin"])

    gardes, t = [], a
    for x, y in sorted((grille(c[0]), grille(c[1]))
                       for c in d.get("coupes", []) if c[1] > a and c[0] < b):
        if x > t:
            gardes.append((t, min(x, b)))
        t = max(t, y)
    if t < b:
        gardes.append((t, b))
    # un morceau de moins de deux images ne survit pas au trim : concat
    # recevrait un segment vide
    gardes = [(s, f) for s, f in gardes if f - s >= 2 / ips]
    if not gardes:
        raise ValueError("Le montage est vide : vérifier début, fin et coupes")

    p = d["points"][0]
    k = large_cam / d["source"]["w"]
    h = {z: round(p["camera"][z] * k) for z in ("x", "y", "w", "h")}
    k = flux_video(ecran)[0] / d["source"]["w"]
    e = {z: round(p["ecran"][z] * k) for z in ("x", "y", "w", "h")}
    sortie.mkdir(parents=True, exist_ok=True)
    morceaux = []
    decal = d.get("decalage") or 0
    alignement = f"trim=start={decal},setpts=PTS-STARTPTS" if decal >= 0 else f"tpad=start_duration={-decal}:start_mode=clone"
    rotation = ",hflip,vflip" if d.get("retourner_ecran") else ""
    audio = "2:a" if d.get("audio") else "0:a"
    for i, (s, f) in enumerate(gardes):
        morceaux.append(
            f"[0:v]trim={s}:{f},setpts=PTS-STARTPTS,fps={cadence},crop={h['w']}:{h['h']}:{h['x']}:{h['y']},"
            f"scale=1080:960,setsar=1[h{i}];"
            f"[1:v]{alignement}{rotation},trim={s}:{f},setpts=PTS-STARTPTS,fps={cadence},"
            f"crop={e['w']}:{e['h']}:{e['x']}:{e['y']},"
            f"scale=1080:960,setsar=1[b{i}];"
            f"[h{i}][b{i}]vstack,fps=30,format=yuv420p[v{i}];"
            f"[{audio}]atrim={s}:{f},asetpts=PTS-STARTPTS[a{i}];")
    filtre = "".join(morceaux) + "".join(f"[v{i}][a{i}]" for i in range(len(gardes))) \
        + f"concat=n={len(gardes)}:v=1:a=1[v][a]"

    titre = re.sub(r"[^\w\s'-]", "", d.get("titre", "")).strip()
    ident = re.sub(r'[/:\\\x00-\x1f]', '-', str(d['reel']))
    nom = f"{ident} - {titre}.mp4" if titre else f"{ident}.mp4"
    print(f"{len(gardes)} morceau(x), {sum(f - s for s, f in gardes):.1f} s -> {nom}", flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-i", str(ecran),
                    *(["-i", d["audio"]] if d.get("audio") else []),
                    "-filter_complex_threads", "1", "-filter_complex", filtre, "-map", "[v]", "-map", "[a]",
                    "-c:v", "h264_videotoolbox" if platform.system() == "Darwin" else "libx264", "-b:v", "12M", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(sortie / nom)], check=True)
    print(f"Reel pret : {sortie / nom}", flush=True)
    return sortie / nom


def dossier_de_sortie(valeur):
    """Un dossier relatif est resolu depuis REELS_SORTIE, jamais depuis le
    repertoire courant : le serveur est lance a la racine du depot public,
    et les reels finis y atterrissaient."""
    if not valeur:
        return reglages.SORTIE
    chemin = Path(valeur).expanduser()
    return chemin if chemin.is_absolute() else reglages.SORTIE / chemin


def main():
    d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sortie = dossier_de_sortie(sys.argv[2] if len(sys.argv) > 2 else None)
    debuts = d["debuts"]
    faits = []
    for i, debut in enumerate(debuts, 1):
        version = dict(d, debuts=[debut])
        if len(debuts) > 1:
            version["reel"] = f"{d['reel']} (debut {i})"
        faits.append(rendre(version, sortie))
    print("Reels prêts : " + ", ".join(str(p) for p in faits), flush=True)


if __name__ == "__main__":
    main()
