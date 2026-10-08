#!/usr/bin/env python3
"""Tous les chemins et reglages de l'outil, au meme endroit.

C'est le seul fichier a regarder pour adapter l'outil a une autre machine, et
meme ca n'est en principe pas necessaire : chaque valeur se surcharge par une
variable d'environnement, donc sans toucher au code.

    export REELS_SORTIE="$HOME/Movies/CapCut/Mes reels"
    python3 outil/serveur.py

Les valeurs par defaut restent a l'interieur du depot, pour qu'une premiere
installation fonctionne sans rien configurer du tout.
"""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _chemin(variable, defaut):
    return Path(os.environ.get(variable) or defaut).expanduser()


# Ou l'outil va chercher les lots prepares par preparer-reels.py.
# Un lot = un sous-dossier contenant reels.json, les proxys et les donnees.
LOTS = _chemin("REELS_LOTS", RACINE / "lots")

# Ou les videos finies sont ecrites. Un sous-dossier Vertical/ ou Horizontal/
# y est cree selon le format.
SORTIE = _chemin("REELS_SORTIE", RACINE / "rendus")

# Prefixe du nom de fichier rendu : "07 - <prefixe> <titre>.mp4".
# Vide par defaut, ce qui donne "07 - <titre>.mp4".
PREFIXE = os.environ.get("REELS_PREFIXE", "").strip()

# Modele whisper.cpp, installe par installer.sh.
MODELE_WHISPER = _chemin("REELS_MODELE",
                         "~/.cache/whisper-cpp/ggml-large-v3-turbo.bin")

# Langue passee a whisper.
LANGUE = os.environ.get("REELS_LANGUE", "fr")

# Dictionnaire de correction du vocabulaire (marques, prenoms, jargon).
# Voir vocabulaire.exemple.json pour le format.
VOCABULAIRE = _chemin("REELS_VOCABULAIRE", RACINE / "vocabulaire.json")

# Ou sont les LUT .cube de l'etalonnage. Elles ne sont PAS dans le depot, qui
# est public : ce sont des fichiers sous licence. Pour les essais du depot,
# pointer sur ~/projets/references/luts.
LUTS = _chemin("REELS_LUTS", "~/luts")

# Port du serveur local.
PORT = int(os.environ.get("REELS_PORT", "8765"))

# Binaire de detection de visage, compile depuis outils/reperer-visage.swift.
REPERER_VISAGE = _chemin("REELS_VISAGE", RACINE / "outils" / "reperer-visage")


# --- Polices des sous-titres --------------------------------------------
#
# Le style d'origine utilise ZTNature, une police sous licence qui n'est pas
# distribuee avec l'outil. Si elle n'est pas installee, on retombe sur une
# police systeme plutot que d'echouer : le rendu est moins beau, il n'est pas
# casse. Pour retrouver le style exact, poser les deux .otf dans ~/Library/Fonts.

_SECOURS = [
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/System/Library/Fonts/Supplemental/Avenir Next.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _police(variable, defaut, gras=False):
    demande = os.environ.get(variable)
    if demande:
        return Path(demande).expanduser()
    p = Path(defaut).expanduser()
    if p.exists():
        return p
    for s in _SECOURS:
        if Path(s).exists():
            return Path(s)
    return p            # laisse echouer avec un message clair


POLICE = _police("REELS_POLICE", "~/Library/Fonts/ZTNature-MediumItalic.otf")
POLICE_TITRE = _police("REELS_POLICE_TITRE", "~/Library/Fonts/ZTNature-Bold.otf",
                       gras=True)

# Couleurs de l'habillage.
COULEUR_CAPTIONS = os.environ.get("REELS_COULEUR_CAPTIONS", "#FAD400")
COULEUR_TITRE = os.environ.get("REELS_COULEUR_TITRE", "#2322E0")


def manquants():
    """Liste ce qui manque pour que la chaine tourne. Utilise par verifier.sh."""
    import shutil
    trous = []
    for outil in ("ffmpeg", "ffprobe", "magick", "whisper-cli"):
        if not shutil.which(outil):
            trous.append(f"binaire absent : {outil}")
    if not MODELE_WHISPER.exists():
        trous.append(f"modele whisper absent : {MODELE_WHISPER}")
    if not REPERER_VISAGE.exists():
        trous.append(f"detecteur de visage non compile : {REPERER_VISAGE}")
    if not POLICE.exists():
        trous.append(f"police absente : {POLICE}")
    if not LUTS.is_dir():
        trous.append(f"dossier des LUT absent : {LUTS} (voir REELS_LUTS)")
    else:
        import json
        table = json.loads((RACINE / "scripts" / "etalonnages.json")
                           .read_text(encoding="utf-8"))
        for cle, e in table["etalonnages"].items():
            if e["fichier"] and not (LUTS / e["fichier"]).is_file():
                trous.append(f"LUT absente : {LUTS / e['fichier']}")
    return trous


if __name__ == "__main__":
    for nom in ("RACINE", "LOTS", "SORTIE", "LUTS", "MODELE_WHISPER",
                "VOCABULAIRE", "REPERER_VISAGE", "POLICE", "POLICE_TITRE"):
        print(f"{nom:16} {globals()[nom]}")
    print(f"{'PREFIXE':16} {PREFIXE or '(aucun)'}")
    print(f"{'PORT':16} {PORT}")
    for t in manquants():
        print("  MANQUE :", t)
