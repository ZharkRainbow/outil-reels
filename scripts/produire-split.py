#!/usr/bin/env python3
"""Rendu brut d'un reel, sans habillage : le cadre fixe du premier point de
cadrage, le depart et la fin choisis dans l'outil, les coupes gardees. Ni
sous-titres, ni titre, ni traitement du son. C'est la version a valider avant
la finition.

    python3 produire-split.py "outil/cadrages/<nom>.json" "<dossier de sortie>"

Tous les formats de scripts/formats.json sont rendus par le meme chemin : un
fond de la taille demandee, puis une zone posee par-dessus. La geometrie n'est
ecrite nulle part ici — un cadre pose dans la page tombe donc exactement la ou
le rendu le met, sans avoir a encoder pour s'en apercevoir.

L'etalonnage choisi dans l'outil est applique AVANT le recadrage : une LUT
travaille sur l'image entiere, et la poser apres le crop donnerait un resultat
different de l'apercu.

Le son vient du mix préparé avec --mixer-son, sinon de la caméra du haut.
Les cadres de l'outil sont exprimes dans le repere de la source de l'outil :
chaque zone est remise a l'echelle de la source dont elle vient.
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
formats = import_module("formats")
etalonnage = import_module("etalonnage")


def flux_video(chemin):
    """Largeur et cadence de la piste image, lues par ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,r_frame_rate", "-of", "json", str(chemin)],
                       capture_output=True, text=True, check=True)
    flux = json.loads(r.stdout)["streams"][0]
    num, _, den = flux["r_frame_rate"].partition("/")
    return int(flux["width"]), int(num) / int(den or 1), flux["r_frame_rate"]


def verifier(d):
    """Mieux vaut une phrase que de sortir un reel qui n'est pas le bon, ou un
    traceback Python, puisque l'outil n'affiche que la derniere ligne du journal."""
    f = formats.trouver(d.get("format", "vmc"))
    if any(z["source"] == "ecran" for _, z in formats.zones(d.get("format", "vmc"))) \
            and not d.get("ecran"):
        raise ValueError(f"Le format « {f['nom']} » assemble deux caméras : "
                         f"ce reel n'en déclare qu'une")
    if not d.get("points"):
        raise ValueError("Aucun cadrage posé : pose un cadrage avant d'envoyer en production")
    if not d.get("debuts") or d.get("fin") is None:
        raise ValueError("Ce cadrage n'a pas de début ou pas de fin : rien à monter")
    for source, cle in (d.get("etalonnages") or {}).items():
        # autant le dire maintenant qu'au bout de dix minutes d'encodage
        etalonnage.verifier_present(cle)
    if len(d["points"]) > 1:
        print(f"{len(d['points'])} cadrages posés, le rendu brut ne garde que le premier "
              f"(cadre fixe)", flush=True)


def rendre(d, sortie):
    # un format a une seule camera n'ouvre pas de second rush : on reprend le
    # premier, ffmpeg ne lira simplement jamais son flux
    cam = RACINE / d["camera"]
    ecran = RACINE / d["ecran"] if d.get("ecran") else cam
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

    # Les cadres arrivent dans le repere de l'outil (d["source"]) : on les
    # ramene a l'echelle de chaque source. Le facteur est pris sur la largeur,
    # ce qui suppose des rushes 16:9 comme le proxy.
    cle = d.get("format", "vmc")
    f_ = formats.trouver(cle)
    p = d["points"][0]
    # le cadre "camera" du point alimente la zone a, le cadre "ecran" la zone b.
    # Quelle source les fournit, c'est la table qui le dit : le vertical
    # consulting prend ses DEUX zones dans le rush du haut.
    large = {"camera": large_cam, "ecran": flux_video(ecran)[0] if d.get("ecran") else large_cam}
    # la LUT de chaque source, calculee une fois : « Aucun » donne une chaine vide
    choix = d.get("etalonnages") or {}
    luts = {}
    for source, chemin in (("camera", cam), ("ecran", ecran)):
        f_lut = etalonnage.filtre(choix.get(source, "aucun"),
                                  etalonnage.profondeur_bits(chemin))
        luts[source] = f_lut + "," if f_lut else ""
    cadre = {"a": p["camera"], "b": p.get("ecran")}
    entree = {"camera": "0:v", "ecran": "1:v"}
    decoupes = []
    for nom_zone, z in formats.zones(cle):
        if cadre[nom_zone] is None:
            raise ValueError(f"Le format « {f_['nom']} » attend deux cadres, "
                             f"le cadrage n'en porte qu'un")
        k = large[z["source"]] / d["source"]["w"]
        decoupes.append((nom_zone, z, {c: round(cadre[nom_zone][c] * k)
                                       for c in ("x", "y", "w", "h")}))

    sortie.mkdir(parents=True, exist_ok=True)
    morceaux = []
    decal = d.get("decalage") or 0
    alignement = f"trim=start={decal},setpts=PTS-STARTPTS" if decal >= 0 else f"tpad=start_duration={-decal}:start_mode=clone"
    rotation = ",hflip,vflip" if d.get("retourner_ecran") else ""
    audio = "2:a" if d.get("audio") else "0:a"
    for i, (s, f) in enumerate(gardes):
        bout = ""
        for nom_zone, z, c in decoupes:
            # seul le second rush porte le decalage de calage et le retournement
            avant = f"{alignement}{rotation}," if z["source"] == "ecran" else ""
            bout += (f"[{entree[z['source']]}]{avant}trim={s}:{f},setpts=PTS-STARTPTS,"
                     f"fps={cadence},{luts[z['source']]}"
                     f"crop={c['w']}:{c['h']}:{c['x']}:{c['y']},"
                     f"scale={z['w']}:{z['h']},setsar=1[z{nom_zone}{i}];")
        # un fond aux dimensions du format, puis une zone posee par-dessus.
        # shortest=1 sur le premier overlay : sans lui, le fond de « color » est
        # infini et le rendu ne s'arrete jamais.
        bout += (f"color=c={formats.fond(cle)}:s={f_['W']}x{f_['H']}:r={cadence}[f{i}];")
        avant = f"f{i}"
        for n, (nom_zone, z, _) in enumerate(decoupes):
            apres = f"v{i}" if n == len(decoupes) - 1 else f"p{n}{i}"
            bout += (f"[{avant}][z{nom_zone}{i}]overlay={z['x']}:{z['y']}"
                     f"{':shortest=1' if n == 0 else ''}[{apres}];")
            avant = apres
        morceaux.append(bout + f"[{avant}]format=yuv420p[w{i}];"
                               f"[{audio}]atrim={s}:{f},asetpts=PTS-STARTPTS[a{i}];")
    filtre = "".join(morceaux) + "".join(f"[w{i}][a{i}]" for i in range(len(gardes))) \
        + f"concat=n={len(gardes)}:v=1:a=1[v][a]"

    titre = re.sub(r"[^\w\s'-]", "", d.get("titre", "")).strip()
    ident = re.sub(r'[/:\\\x00-\x1f]', '-', str(d['reel']))
    # le nom porte le format : deux formats du meme reel cohabitent dans le dossier
    suffixe = f" - {f_['fichier']}"
    nom = (f"{ident} - {titre}{suffixe}.mp4" if titre else f"{ident}{suffixe}.mp4")
    dits = [f"{s} {etalonnage.trouver(c)['nom']}" for s, c in sorted(choix.items())
            if c != "aucun"]
    print(f"{f_['nom']} — {len(gardes)} morceau(x), "
          f"{sum(f - s for s, f in gardes):.1f} s"
          + (" — étalonnage : " + ", ".join(dits) if dits else "")
          + f" -> {nom}", flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-i", str(ecran),
                    *(["-i", d["audio"]] if d.get("audio") else []),
                    # un seul thread de filtrage : sur deux coeurs, en paralleliser
                    # davantage ne gagne rien et prive l'encodeur de la machine
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
    verifier(d)
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
    # l'outil n'affiche que la derniere ligne du journal : une phrase, pas un
    # traceback. Les echecs ffmpeg gardent la leur, elle sert au diagnostic.
    try:
        main()
    except ValueError as pb:
        sys.exit(str(pb))
