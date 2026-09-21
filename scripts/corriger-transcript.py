#!/usr/bin/env python3
"""Corrige le vocabulaire propre a une marque dans une transcription whisper.

Whisper ne connait ni ta marque, ni ton jargon, ni les prenoms de ton equipe.
Il remplace ce qu'il ne reconnait pas par le mot statistiquement le plus
proche, ce qui produit des sous-titres faux a l'ecran. Un nom de marque devient un sigle,
un nom de famille perd sa premiere lettre.

Les corrections vivent dans un fichier de donnees, pas dans ce code : voir
vocabulaire.exemple.json, a copier en vocabulaire.json et a remplir. Chaque
correction devrait etre verifiee a l'oreille sur une fenetre courte, la ou
whisper est fiable.

Les corrections s'appliquent sur la SUITE DE MOTS, pas sur un texte recolle :
chaque mot porte son propre timecode et il faut les preserver.

    python3 corriger-transcript.py "de l'AMLIST"   -> essai rapide
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reglages


def _charger():
    f = reglages.VOCABULAIRE
    if not f.exists():
        f = reglages.RACINE / "vocabulaire.exemple.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


_D = _charger()

# Un mot pour un mot. Cle comparee sans accent ni casse ni ponctuation :
# ecrire "leborgne", jamais "Lebôrgne", sinon la cle ne matche jamais.
MOT_A_MOT = _D.get("mot_a_mot", {})

# Suites de mots, les plus longues d'abord. [[mots cherches], [remplacement]]
SUITES = [(list(a), list(b)) for a, b in _D.get("suites", [])]

# Whisper comble les silences avec des formules de generique apprises sur des
# sous-titres de television. Elles n'ont jamais ete prononcees et se retrouvent
# incrustees a l'ecran en fin de reel. On les supprime purement.
HALLUCINATIONS = [list(h) for h in _D.get("hallucinations", [])]

# Le nom de la marque, par regle plutot que par liste.
#
# Lister les graphies ne suffit pas : whisper en invente une nouvelle a chaque
# passe, et il lui arrive de couper le mot en deux, ce qu'un dictionnaire a un
# mot ne voit jamais. On raisonne donc sur la forme : tout ce qui commence par
# un des debuts et se termine par une des fins est la marque. Les vrais mots
# de la langue sont proteges par la liste blanche "mots_vrais".
_M = _D.get("marque", {})
MARQUE = _M.get("nom", "")
MARQUE_GROUPE = _M.get("nom_groupe", "")
OFF_DEBUTS = tuple(_M.get("debuts", []))
OFF_FINS_GROUPE = set(_M.get("fins_groupe", []))
OFF_FINS_MARQUE = set(_M.get("fins", []))
OFF_MOTS_VRAIS = set(_M.get("mots_vrais", []))

# Whisper invente une graphie differente a chaque passe pour un nom de famille
# inhabituel. Lister les variantes ne suffit pas. On prend donc la regle
# inverse : apres le prenom, tout mot commencant par l'initiale du nom et qui
# n'est pas un mot courant est le nom de famille.
_N = _D.get("nom_de_famille", {})
PRENOM = _N.get("prenom", "")
NOM = _N.get("nom", "")
INITIALE = _N.get("initiale", "")
LONGUEUR_MIN = int(_N.get("longueur_min", 4))
APRES_PRENOM_OK = set(_N.get("exceptions", []))


def _decoupe_marque(k):
    """Renvoie 'groupe', 'marque' ou None pour une cle donnee."""
    if not OFF_DEBUTS:
        return None
    n = k.replace("-", "").replace("'", "").replace(" ", "")
    if k in OFF_MOTS_VRAIS or n in OFF_MOTS_VRAIS:
        return None
    for d in sorted(OFF_DEBUTS, key=len, reverse=True):
        if n.startswith(d):
            reste = n[len(d):]
            if reste in OFF_FINS_GROUPE:
                return "groupe"
            if reste in OFF_FINS_MARQUE:
                return "marque"
    return None


def cle(mot):
    m = unicodedata.normalize("NFD", mot.lower())
    m = "".join(c for c in m if unicodedata.category(c) != "Mn")
    return m.strip(" ,.;:!?»«…\"")


def _ponctuation(origine):
    """Recupere la ponctuation finale du mot remplace."""
    m = re.search(r"[,.;:!?…»]+$", origine)
    return m.group(0) if m else ""


def corriger(mots):
    """mots = [(t0, t1, texte)] -> meme forme, vocabulaire corrige."""
    out = list(mots)

    # suites d'abord : elles peuvent changer le nombre de mots
    i, res = 0, []
    while i < len(out):
        remplace = None
        for source, cible in SUITES:
            n = len(source)
            if i + n > len(out):
                continue
            if [cle(out[i + k][2]) for k in range(n)] == source:
                remplace = (n, cible)
                break
        if remplace:
            n, cible = remplace
            t0, t1 = out[i][0], out[i + n - 1][1]
            fin = _ponctuation(out[i + n - 1][2])
            pas = (t1 - t0) / max(len(cible), 1)
            for j, mot in enumerate(cible):
                res.append((t0 + j * pas, t0 + (j + 1) * pas,
                            mot + (fin if j == len(cible) - 1 else "")))
            i += n
        else:
            res.append(out[i])
            i += 1

    # la marque : d'abord les paires, car whisper coupe parfois le mot en deux
    if MARQUE:
        fus, i = [], 0
        while i < len(res):
            if i + 1 < len(res) and cle(res[i][2]) in OFF_DEBUTS:
                genre = _decoupe_marque(cle(res[i][2]) + cle(res[i + 1][2]))
                if genre:
                    nom = MARQUE_GROUPE if genre == "groupe" else MARQUE
                    fus.append((res[i][0], res[i + 1][1],
                                nom + _ponctuation(res[i + 1][2])))
                    i += 2
                    continue
            genre = _decoupe_marque(cle(res[i][2]))
            if genre:
                nom = MARQUE_GROUPE if genre == "groupe" else MARQUE
                fus.append((res[i][0], res[i][1], nom + _ponctuation(res[i][2])))
            else:
                fus.append(res[i])
            i += 1
        res = fus

    # hallucinations : on retire les suites entieres
    net, i = [], 0
    while i < len(res):
        saute = 0
        for h in HALLUCINATIONS:
            n = len(h)
            if i + n <= len(res) and [cle(res[i + k][2]) for k in range(n)] == h:
                saute = n
                break
        if saute:
            i += saute
        else:
            net.append(res[i])
            i += 1
    res = net

    # nom de famille : regle par position, pas par liste
    if PRENOM and NOM and INITIALE:
        for i in range(len(res) - 1):
            if cle(res[i][2]) != PRENOM:
                continue
            t0, t1, w = res[i + 1]
            k = cle(w)
            if k.startswith(INITIALE) and k not in APRES_PRENOM_OK and len(k) >= LONGUEUR_MIN:
                res[i + 1] = (t0, t1, NOM + _ponctuation(w))

    # puis mot a mot
    final = []
    for t0, t1, w in res:
        k = cle(w)
        final.append((t0, t1, MOT_A_MOT[k] + _ponctuation(w)) if k in MOT_A_MOT
                     else (t0, t1, w))
    return final


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"dictionnaire : {reglages.VOCABULAIRE}")
        print(f"  {len(MOT_A_MOT)} mots, {len(SUITES)} suites, "
              f"{len(HALLUCINATIONS)} hallucinations")
        print(f"  marque : {MARQUE or '(aucune)'} | nom de famille : "
              f"{(PRENOM + ' ' + NOM).strip() or '(aucun)'}")
        sys.exit()
    for phrase in sys.argv[1:]:
        mots = [(0.0, 1.0, m) for m in phrase.split()]
        print(" ".join(w for _, _, w in corriger(mots)))
