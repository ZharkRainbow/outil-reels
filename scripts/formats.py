#!/usr/bin/env python3
"""La table des formats, lue une fois depuis scripts/formats.json.

Un seul endroit decrit ou chaque camera est posee dans l'image finale : la page
(qui recoit le fichier tel quel sur /formats.json), le rendu brut et le rendu
habille. Tant que la geometrie etait recopiee des deux cotes, un cadre pose dans
l'outil ne tombait pas exactement la ou le rendu le mettait, et il fallait
encoder pour s'en apercevoir.
"""
import json
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "formats.json"
_TABLE = json.loads(FICHIER.read_text(encoding="utf-8"))

ORDRE = _TABLE["ordre"]
FORMATS = _TABLE["formats"]


def trouver(cle):
    """Le format demande, ou une erreur qui dit lesquels existent."""
    if cle not in FORMATS:
        raise ValueError(f"Format inconnu : « {cle} ». Les formats connus sont : "
                         + ", ".join(ORDRE))
    return FORMATS[cle]


def zones(cle):
    """[(nom de zone, geometrie)] dans l'ordre d'empilement : a puis b."""
    z = trouver(cle)["zones"]
    return [(n, z[n]) for n in ("a", "b") if n in z]


def deux_cameras():
    """Les formats proposes par defaut sur un lot a deux cameras."""
    return [c for c in ORDRE if FORMATS[c].get("deux_cameras")]


def fond(cle):
    """La couleur de fond au format que ffmpeg attend. La table l'ecrit en
    #RRGGBB, lisible par la page ; ffmpeg prefere 0xRRGGBB."""
    return "0x" + trouver(cle)["fond"].lstrip("#")


def nom_fichier(cle):
    """Ce que le nom du reel rendu porte, pour que deux formats du meme reel
    ne s'ecrasent pas dans le meme dossier."""
    return trouver(cle)["fichier"]
