#!/usr/bin/env python3
"""L'etalonnage d'un rush : quelle LUT, et laquelle proposer.

Trois choix et pas un de plus (brief V3) : aucun, le rendu Cinestyle pour un
rush deja en Rec.709, et le delog pour un rush tourne en Log M. La table vit
dans scripts/etalonnages.json, lue par la page comme par le rendu : le choix
fait dans l'outil est exactement la LUT que ffmpeg applique.

Les fichiers .cube NE SONT PAS dans le depot, qui est public. Ils vivent dans
le dossier REELS_LUTS (voir reglages.py). Quand un fichier manque, on le dit
en toutes lettres plutot que de rendre l'image brute en silence.

La detection reprend celle de l'Atelier, mesuree la-bas sur de vrais rushes :
signalstats sur cinq images, mediane, et trois seuils. Elle n'est pas devinee,
elle est etalonnee.
"""
import json
import re
import subprocess
from pathlib import Path

try:
    import reglages
except ImportError:                                  # importe depuis ailleurs
    from importlib import import_module
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    reglages = import_module("reglages")

FICHIER = Path(__file__).resolve().parent / "etalonnages.json"
_TABLE = json.loads(FICHIER.read_text(encoding="utf-8"))
ORDRE = _TABLE["ordre"]
ETALONNAGES = _TABLE["etalonnages"]

# Ou ffmpeg prend ses images pour mesurer, en fraction de la duree. Cinq, et
# reparties : une seule image tombe une fois sur deux sur un fondu ou un plan
# de coupe, et le rush entier passe alors pour du Log.
ECHANTILLONS = (0.05, 0.275, 0.5, 0.725, 0.95)
MARGE_FIN = 0.04
# Les seuils, mesures sur de vrais rushes (D-Log M : saturation 2,2 a 3,4,
# noirs 51 a 68, blancs 121 a 140 ; Rec.709 deja monte : saturation >= 6,3).
SAT_DESATUREE = 5.0
SAT_LAITEUSE = 8.0
NOIR_LEVE = 35.0
NOIR_LAITEUX = 45.0
BLANC_PLAFONNE = 190.0
BLANC_LAITEUX = 175.0
IMAGE_NOIRE = 30.0        # en dessous, l'image est un fondu : elle ne compte pas
DELAI = 45


def trouver(cle):
    """L'etalonnage demande, ou une erreur qui dit lesquels existent."""
    if cle not in ETALONNAGES:
        raise ValueError(f"Étalonnage inconnu : « {cle} ». Les étalonnages connus sont : "
                         + ", ".join(ORDRE))
    return ETALONNAGES[cle]


def dossier_luts():
    return Path(reglages.LUTS)


def chemin_lut(cle):
    """Le .cube de cet etalonnage, ou None si l'etalonnage n'en demande pas."""
    nom = trouver(cle)["fichier"]
    return dossier_luts() / nom if nom else None


def catalogue():
    """Les trois choix, avec ce qui est reellement sur le disque. La page a
    besoin de savoir qu'un fichier manque AVANT qu'on lance un rendu de dix
    minutes qui finira par une phrase d'erreur."""
    sortie = []
    for cle in ORDRE:
        e = ETALONNAGES[cle]
        chemin = chemin_lut(cle)
        sortie.append({"cle": cle, "nom": e["nom"], "detail": e["detail"],
                       "fichier": e["fichier"],
                       "present": True if chemin is None else chemin.is_file(),
                       "taille": chemin.stat().st_size if chemin and chemin.is_file() else None})
    return {"ordre": ORDRE, "dossier": str(dossier_luts()), "etalonnages": sortie}


def verifier_present(cle):
    """Leve une phrase lisible si le .cube manque. Appele avant tout rendu."""
    chemin = chemin_lut(cle)
    if chemin is None or chemin.is_file():
        return chemin
    raise ValueError(
        f"La LUT « {trouver(cle)['nom']} » est absente du dossier {dossier_luts()} : "
        f"il y manque le fichier « {trouver(cle)['fichier']} ». Copie-le, ou pointe "
        f"REELS_LUTS sur le bon dossier, ou choisis « Aucun ».")


# --- Ce que ffmpeg doit faire -------------------------------------------

def _echapper(chemin):
    """Un chemin dans une option de filtre ffmpeg. Pas de guillemets : une
    apostrophe ne s'echappe pas a l'interieur. Deux passes, comme l'Atelier :
    la valeur d'option, puis le graphe."""
    valeur = str(chemin)
    for c in ("\\", "'", ":"):
        valeur = valeur.replace(c, "\\" + c)
    for c in ("\\", "'", "[", "]", ",", ";"):
        valeur = valeur.replace(c, "\\" + c)
    return valeur


def filtre(cle, profondeur=8):
    """Le bout de chaine ffmpeg qui applique la LUT, ou '' pour « Aucun ».

    L'interpolation tetraedrique et non trilineaire : sur un delog, la
    trilineaire laisse des marches visibles dans les degrades de peau.
    """
    chemin = verifier_present(cle)
    if chemin is None:
        return ""
    avant = "format=gbrp10le," if profondeur > 8 else ""
    return f"{avant}lut3d=file={_echapper(chemin)}:interp=tetrahedral"


def profondeur_bits(source):
    """Profondeur de la source, pour ne pas ecraser un rush 10 bits en 8."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=pix_fmt,bits_per_raw_sample",
                            "-of", "json", str(source)],
                           capture_output=True, text=True, timeout=DELAI, check=True)
        flux = json.loads(r.stdout)["streams"][0]
    except (subprocess.SubprocessError, ValueError, KeyError, IndexError, OSError):
        return 8
    brut = flux.get("bits_per_raw_sample")
    if brut and str(brut).isdigit() and int(brut) > 8:
        return int(brut)
    m = re.search(r"p(10|12|14|16)(le|be)?$", str(flux.get("pix_fmt") or ""))
    return int(m.group(1)) if m else 8


# --- La mesure -----------------------------------------------------------

def duree(source):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(source)],
                       capture_output=True, text=True, timeout=DELAI, check=True)
    return float(r.stdout.strip() or 0)


def _mediane(valeurs):
    v = sorted(valeurs)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def mesurer(source):
    """{ylow, yhigh, sat} : noirs, blancs et saturation moyenne de la source.

    Une image par echantillon, pas un passage complet : lire un rush de dix
    minutes pour trois nombres couterait plus cher que le rendu lui-meme.
    """
    total = duree(source)
    facteur = 255 / ((1 << profondeur_bits(source)) - 1)
    brutes = []
    for part in ECHANTILLONS:
        t = min(max(0.0, total * part), max(0.0, total - MARGE_FIN))
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{t:.6f}",
             "-i", str(source), "-frames:v", "1", "-vf",
             "scale=640:-2:flags=bilinear,signalstats,metadata=print:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=DELAI)
        texte = (r.stdout or "") + (r.stderr or "")
        image = {}
        for cle, etiquette in (("ylow", "YLOW"), ("yhigh", "YHIGH"), ("sat", "SATAVG")):
            # la derniere occurrence : le vidage du decodeur reimprime la meme image
            trouves = re.findall(rf"lavfi\.signalstats\.{etiquette}=(-?[0-9.]+)", texte)
            if trouves:
                image[cle] = float(trouves[-1]) * facteur
        if len(image) == 3:
            brutes.append(image)
    if not brutes:
        raise ValueError("ffmpeg n'a produit aucune mesure sur ce rush.")
    # on ecarte les fondus au noir, sauf s'il ne reste plus rien a mesurer
    eclairees = [i for i in brutes if i["yhigh"] >= IMAGE_NOIRE] or brutes
    return {c: round(_mediane([i[c] for i in eclairees]), 1) for c in ("ylow", "yhigh", "sat")}


def diagnostiquer(mesure):
    """La famille detectee, l'etalonnage a proposer, et la phrase a afficher.

    Un rush en Log se reconnait a trois choses a la fois : une saturation au
    plancher, des noirs leves et des blancs rentres. Prise seule, chacune se
    trompe — une scene de nuit a les noirs bas, un mur blanc a la saturation
    basse. C'est leur conjonction qui tranche.
    """
    sat, bas, haut = mesure["sat"], mesure["ylow"], mesure["yhigh"]
    desaturee = sat < SAT_DESATUREE
    laiteuse = sat < SAT_LAITEUSE and bas >= NOIR_LAITEUX and haut <= BLANC_LAITEUX
    log = laiteuse or (desaturee and bas >= NOIR_LEVE and haut <= BLANC_PLAFONNE)
    douteux = ((desaturee and not log)
               or (not log and SAT_DESATUREE <= sat < SAT_LAITEUSE and bas >= IMAGE_NOIRE)
               or (log and (sat >= 4.5 or bas < NOIR_LAITEUX or haut > BLANC_LAITEUX)))
    famille = "log" if log else "709"
    propose = next((c for c in ORDRE if ETALONNAGES[c]["pour"] == famille), "aucun")
    phrase = (f"{'Log' if log else 'Rec.709'} détecté · blancs {round(haut)} · "
              f"saturation {sat:.1f}" + (" · à vérifier" if douteux else ""))
    return {"famille": famille, "propose": propose, "sur": not douteux,
            "mesure": mesure, "phrase": phrase}


def examiner(source):
    """Mesure + diagnostic. Une erreur ne bloque jamais : on le dit, c'est tout."""
    try:
        return diagnostiquer(mesurer(source))
    except (ValueError, OSError, subprocess.SubprocessError) as pb:
        return {"famille": None, "propose": "aucun", "sur": False, "mesure": None,
                "phrase": f"Mesure impossible : {pb}"[:400]}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        cat = catalogue()
        print("dossier des LUT :", cat["dossier"])
        for e in cat["etalonnages"]:
            print(f"  {e['cle']:10} {e['nom']:28} "
                  + ("—" if e["fichier"] is None
                     else ("présente" if e["present"] else "ABSENTE") + f"  {e['fichier']}"))
    else:
        for src in sys.argv[1:]:
            d = examiner(src)
            print(f"{src}\n  {d['phrase']}\n  proposé : {d['propose']}  mesure : {d['mesure']}")
