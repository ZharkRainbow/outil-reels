#!/usr/bin/env python3
"""Rend un reel split screen depuis le JSON exporte par l'outil de recadrage.

Un fichier par debut pose dans l'outil : meme fin, memes coupes, memes
cadrages, seul le point de depart change. Pour chaque debut :

1. montage : face cam en haut, tablette en bas (1080x960 chacune), cadrages
   de l'outil, coupes retirees, son de la face cam ramene a -14 LUFS ;
2. sous-titres : whisper relance sur le montage (faire-captions.py), pour
   qu'ils soient cales sur le fichier final et non sur la prise ;
3. incrustation des sous-titres et du bandeau titre (incruster-captions.py).

Les coupes sont calees sur la grille des images (23,976 i/s, la cadence de la
face cam) : la video retire des images entieres et le son exactement la meme
duree, sinon chaque coupe decale un peu la synchro labiale.

    python3 rendre-reel.py "outil-recadrage/cadrages/Reel 1.json"
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
reglages = import_module("reglages")
points = import_module("rendre-depuis-points")
captions = import_module("faire-captions")
incruster = import_module("incruster-captions")

SCRIPTS = Path(__file__).parent
SORTIE = reglages.SORTIE
SRC_W, SRC_H = 3840, 2160
ACCEL = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []
IPS = 24000 / 1001
# format -> taille finale, taille de chaque moitie, sens de l'assemblage
# (hsolo et carre : une seule camera, pas de tablette)
FORMATS = {"vmc": dict(a=(1080, 960), b=(1080, 960), pile="vstack"),
           "hmc": dict(a=(720, 1080), b=(1200, 1080), pile="hstack"),
           "hsolo": dict(a=(1920, 1080), b=None, pile=None),
           # carre (nom historique) : la video 16:9 d'origine au centre d'une toile
           # verticale 1080x1920, bandes noires dessus et dessous
           "carre": dict(a=(1080, 608), b=None, pile=None, toile=(1080, 1920, 0, 656))}
DOSSIERS = {"vmc": "Vertical", "hmc": "Horizontal", "hsolo": "Horizontal", "carre": "Vertical"}
# Habillage des formats a une camera.
# Horizontal : sous-titres a mi-hauteur, du cote libre de la personne, fixes pour
# toute la prise (a gauche s'il est a droite, a droite s'il est a gauche, coupes
# en deux autour de lui s'il est au centre). Vertical : video d'origine entre deux
# bandes noires, titre au-dessus pendant toute la video, sous-titres en dessous.
HABILLAGE_SEUL = {"hsolo": dict(cap_y=0.50, cap_taille=0.042, titre_y=0.09, cote_libre=True),
                  "carre": dict(cap_y=0.695, cap_taille=0.024, titre_y=0.25,
                                titre_taille=0.032, titre_duree=0, titre_deux_lignes=True)}
LUFS = -14.0
FONDU = 0.005            # 5 ms a chaque jointure : pas de clic, rien d'audible
# Vocabulaire : on passe par le dictionnaire commun, celui de
# corriger-transcript.py, et non par une poignee de regex locales. Deux regex
# ne rattrapaient que la marque ; tout le reste partait a l'ecran tel que whisper
# l'avait entendu, d'ou "de l'AMLIST" incruste a la place de "de lemlist".
vocabulaire = import_module("corriger-transcript")


def dire(texte):
    print(texte, flush=True)


def grille(t):
    return round(t * IPS) / IPS


def morceaux(debut, fin, coupes):
    """Parties gardees entre debut et fin, en temps du fichier monte (0 = debut)."""
    fusion = []
    for a, b in sorted((max(a, debut), min(b, fin)) for a, b in coupes):
        if b <= a:
            continue
        if fusion and a <= fusion[-1][1] + 0.02:
            fusion[-1][1] = max(fusion[-1][1], b)
        else:
            fusion.append([a, b])
    gardes, pos = [], debut
    for a, b in fusion:
        gardes.append((pos, a))
        pos = b
    gardes.append((pos, fin))
    res = []
    for a, b in gardes:
        a, b = grille(a - debut), grille(b - debut)
        if b - a >= 2 / IPS:
            res.append((a, b))
    return res


def sonie(camera, debut, duree):
    err = subprocess.run(["ffmpeg", "-nostats", "-ss", f"{debut:.3f}", "-t", f"{duree:.3f}",
                          "-i", camera, "-map", "0:a:0", "-af", "ebur128=framelog=quiet",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    valeurs = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    if not valeurs:
        raise RuntimeError("mesure de sonie impossible")
    return float(valeurs[-1])


def visage_median(d):
    piste = d.get("visage") or []
    if not piste:
        return 0.5, 0.35, 0.22, 0.4
    med = lambda i: sorted(v[i] for v in piste)[len(piste) // 2]
    return med(1) + med(3) / 2, med(2), med(3), med(4)


def cadrages(d):
    """Cadrages camera (et ecran) aux proportions du format, en pixels pairs."""
    # l'outil peut envoyer des tailles a virgule : ffmpeg veut des pixels pairs
    pair = lambda v: int(round(v / 2)) * 2
    lay = FORMATS[d.get("format", "vmc")]
    aW, aH = lay["a"]
    # l'outil garde les cadres de plusieurs formats : on prend ceux aux bonnes proportions
    pts = []
    for p in d.get("points", []):
        if abs(p["camera"]["w"] / p["camera"]["h"] - aW / aH) >= 0.03:
            continue
        if lay["b"]:
            bW, bH = lay["b"]
            if not p.get("ecran") or abs(p["ecran"]["w"] / p["ecran"]["h"] - bW / bH) >= 0.03:
                continue
        pts.append({"t": p["t"], "glisse": p.get("glisse", False),
                    "A": {k: pair(v) for k, v in p["camera"].items()},
                    "B": {k: pair(v) for k, v in (p.get("ecran") or p["camera"]).items()}})
    if not pts and not lay["b"]:
        # une camera sans cadrage pose : le plan entier, dans les deux formats
        cadre = {"x": 0, "y": 0, "w": SRC_W, "h": SRC_H}
        pts = [{"t": 0, "glisse": False, "A": cadre, "B": cadre}]
    if not pts:
        raise RuntimeError("aucun cadrage pose pour ce format")
    return pts


def monter(d, debut, dst):
    fin = d["fin"]
    parts = morceaux(debut, fin, d.get("coupes", []))
    if not parts:
        raise RuntimeError("tout est coupe entre ce debut et la fin")
    lay = FORMATS[d.get("format", "vmc")]
    aW, aH = lay["a"]
    bW, bH = lay["b"] or lay["a"]
    pts = cadrages(d)
    aw, ah = points.taille(pts, "A")
    bw, bh = points.taille(pts, "B")
    ax, ay = (points.expression(pts, "A", k, debut) for k in ("x", "y"))
    bx, by = (points.expression(pts, "B", k, debut) for k in ("x", "y"))

    duree = fin - debut
    depart_ecran = debut + d.get("decalage", 0.0)
    retard = ""
    rotation = "hflip,vflip," if d.get("retourner_ecran") else ""   # tablette filmee a l'envers
    if depart_ecran < 0:
        retard = f",tpad=start_duration={-depart_ecran:.3f}:start_mode=clone"
        depart_ecran = 0.0
    gain = LUFS - sonie(d.get("audio") or d["camera"], debut, duree)

    # Chaque image est reperee par son rang sur la grille du temps d'origine
    # (round(T*ips)), jamais par un compteur : apres le seek, la premiere image
    # decodee arrive parfois a 42 ms, et un renumerotage (N) avancerait alors
    # toute la video d'une image sur le son. Le nouvel horodatage est calcule
    # depuis ce rang, moins les images coupees avant lui, et arrondi : sans
    # round, 3.0 calcule en flottant devient 2 et deux images se superposent.
    rang = "round(T*24000/1001)"
    garde = "+".join(f"between(round(t*24000/1001),{round(a * IPS)},{round(b * IPS) - 1})"
                     for a, b in parts)
    horodatage, deja = "0", 0
    bornes = []
    for a, b in parts:
        na, nb = round(a * IPS), round(b * IPS)
        bornes.append((nb, f"{rang}-{na - deja}"))
        deja += nb - na
    for nb, valeur in reversed(bornes):
        horodatage = f"if(lt({rang},{nb}),{valeur},{horodatage})"
    son = [f"[0:a:0]asplit={len(parts)}" + "".join(f"[s{i}]" for i in range(len(parts)))
           if len(parts) > 1 else "[0:a:0]anull[s0]"]
    for i, (a, b) in enumerate(parts):
        son.append(f"[s{i}]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,"
                   f"afade=t=in:d={FONDU},afade=t=out:st={b - a - FONDU:.4f}:d={FONDU}[p{i}]")
    son.append("".join(f"[p{i}]" for i in range(len(parts)))
               + f"concat=n={len(parts)}:v=0:a=1,volume={gain:.2f}dB,alimiter=limit=0.89[son]")
    selection = f"select='{garde}',setpts='round(({horodatage})*1001/24000/TB)'[v]"
    camera = (f"[0:v:0]fps=24000/1001,crop={aw}:{ah}:'{ax}':'{ay}':exact=1,"
              f"scale={aW}:{aH}:flags=lanczos,setsar=1")
    if lay.get("toile"):
        tW, tH, tx, ty = lay["toile"]
        camera += f",pad={tW}:{tH}:{tx}:{ty}:black"
    entrees = [*ACCEL, "-ss", f"{debut:.3f}", "-t", f"{duree + 0.5:.3f}",
               "-i", d["camera"]]
    if lay["b"]:
        chaine = ";".join([
            camera + "[cam]",
            f"[1:v:0]{rotation}fps=24000/1001{retard},crop={bw}:{bh}:'{bx}':'{by}':exact=1,"
            f"scale={bW}:{bH}:flags=lanczos,setsar=1[scr]",
            f"[cam][scr]{lay['pile']}=inputs=2," + selection, *son])
        entrees += [*ACCEL, "-ss", f"{depart_ecran:.3f}",
                    "-t", f"{duree + 0.5:.3f}", "-i", d["ecran"]]
    else:
        chaine = ";".join([camera + "," + selection, *son])
    if d.get("audio"):
        index_audio = 2 if lay["b"] else 1
        entrees += ["-ss", f"{debut:.3f}", "-i", d["audio"]]
        chaine = chaine.replace("[0:a:0]", f"[{index_audio}:a:0]")
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-y", *entrees,
        "-filter_complex", chaine, "-map", "[v]", "-map", "[son]",
        "-r", "24000/1001", "-fps_mode", "cfr", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", str(dst)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-600:])
    return sum(b - a for a, b in parts), len(parts) - 1


def cote_libre(d, subs):
    """Zones des sous-titres en horizontal, les memes pour toute la prise.

    Le cote se decide une fois, sur la position mediane du visage : les
    sous-titres ne bougent pas d'une phrase a l'autre. Au centre, chaque
    sous-titre est coupe en deux de part et d'autre du visage.
    """
    cx, _, l, _ = visage_median(d)
    x0 = cx - l / 2 - 0.25 * l - 0.03          # visage elargi aux cheveux, plus un ecart
    x1 = cx + l / 2 + 0.25 * l + 0.03
    gauche, droite = [0.04, min(0.40, x0)], [max(0.60, x1), 0.96]
    mode = "gauche" if cx >= 0.58 else "droite" if cx <= 0.42 else "coupe"
    res = []
    for _, _, texte in subs:
        mots = texte.split()
        if mode == "coupe" and len(mots) > 1:
            k = min(range(1, len(mots)),
                    key=lambda i: abs(len(" ".join(mots[:i])) - len(" ".join(mots[i:]))))
            boites = [[" ".join(mots[:k]), *gauche], [" ".join(mots[k:]), *droite]]
        else:
            boites = [[texte, *(droite if mode == "droite" else gauche)]]
        res.append({"boites": boites})
    return res


def majuscule(texte):
    return texte[:1].upper() + texte[1:]


# phrases que whisper invente sur du silence ou un bruit : jamais prononcees
FANTOMES = re.compile(r"sous-titr|amara\.org|merci d'avoir regard|abonnez-vous", re.IGNORECASE)


def retirer_fantomes(srt):
    """Retire les captions inventees, et un « Merci » isole en toute fin."""
    blocs = [b for b in srt.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    garde = []
    for i, b in enumerate(blocs):
        texte = " ".join(b.strip().split("\n")[2:]).strip()
        if FANTOMES.search(texte):
            continue
        if i >= len(blocs) - 2 and re.fullmatch(r"merci[.!]?", texte, re.IGNORECASE):
            continue
        garde.append(b.strip().split("\n"))
    srt.write_text("\n\n".join("\n".join([str(k), *l[1:]]) for k, l in enumerate(garde, 1)) + "\n",
                   encoding="utf-8")


def corriger(srt):
    retirer_fantomes(srt)
    blocs = srt.read_text(encoding="utf-8").strip().split("\n\n")
    sortie = []
    for b in blocs:
        L = b.strip().split("\n")
        if len(L) < 3:
            continue
        num, tc = L[0], L[1]
        # whisper met des guillemets autour des phrases citees : coupes en
        # morceaux de 3 mots, ils restent orphelins a l'ecran
        texte = re.sub(r'["«»“”]', "", " ".join(L[2:])).strip()
        mots = texte.split()
        corr = vocabulaire.corriger([(0.0, 0.0, m) for m in mots])
        sortie.append(f"{num}\n{tc}\n" + " ".join(w for _, _, w in corr))
    srt.write_text("\n\n".join(sortie) + "\n", encoding="utf-8")


def relire(srt):
    """Controle orthographique du SRT corrige : signale ce qui reste douteux.

    Le dictionnaire ne rattrape que les fautes deja rencontrees. Whisper en
    invente de nouvelles a chaque marque, chaque prenom, chaque sigle. Ce
    controle ne corrige rien tout seul -- il n'y a personne pour arbitrer
    pendant un rendu -- mais il ecrit la liste a cote de la video, pour qu'une
    faute inconnue soit vue avant publication et non apres.
    """
    try:
        from spellchecker import SpellChecker
    except ImportError:
        return                      # pas de dictionnaire installe : on laisse passer
    texte = srt.read_text(encoding="utf-8")
    texte = "\n".join(l for l in texte.splitlines() if not re.match(r"^\d+$|-->", l))
    mots = [p for m in re.findall(r"[A-Za-zÀ-ÿ'’-]+", texte)
            for p in re.split(r"['’-]", m) if len(p) > 1]
    sp = SpellChecker(language="fr")
    doutes = sorted({m for m in mots if m.lower() not in JARGON and sp.unknown([m.lower()])},
                    key=str.lower)
    if doutes:
        srt.with_suffix(".relire.txt").write_text("\n".join(doutes) + "\n", encoding="utf-8")
        dire("  a relire : " + ", ".join(doutes))


# Mots justes que le dictionnaire francais ne connait pas : marques, jargon
# du metier, anglicismes employes tels quels. Ils vivent dans vocabulaire.json,
# cle "jargon", pas dans ce code. Ne jamais y mettre une faute pour faire taire
# le controle : une faute se corrige dans corriger-transcript.py.
JARGON = set(vocabulaire._D.get("jargon", []))
JARGON |= {vocabulaire.MARQUE.lower(), vocabulaire.MARQUE_GROUPE.lower(),
           vocabulaire.NOM.lower(), vocabulaire.PRENOM.lower()} - {""}
JARGON |= {v.lower() for v in vocabulaire.MOT_A_MOT.values()}


def main():
    d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    format_ = d.get("format", "vmc")
    if not d.get("points") and FORMATS[format_]["b"]:
        sys.exit("Aucun cadrage pose : pose au moins un cadrage avant d'exporter.")
    debuts = d.get("debuts") or [0.0]
    # rangement : <sortie>/Vertical/01 - <titre>.mp4
    racine = SORTIE
    if d.get("sortie") and "REELS_SORTIE" not in os.environ:
        # dans SORTIE, pas a cote : SORTIE.parent, c'est la racine du depot,
        # et "sortie": "Mes reels" y faisait apparaitre un dossier de rendus
        racine = SORTIE / d["sortie"]
    dossier = racine / DOSSIERS[format_]
    dossier.mkdir(parents=True, exist_ok=True)
    d["titre"] = majuscule(d.get("titre", "").strip())
    titre = re.sub(r'[/:\\]', "-", d["titre"])
    # "07 - Prenom Mon titre.mp4", ou simplement "07 - Mon titre.mp4"
    etiquettes = [reglages.PREFIXE, titre]
    reste = " ".join(x for x in etiquettes if x)
    ident = re.sub(r'[/:\\\x00-\x1f]', "-", str(d['reel']))
    nom = (ident.zfill(2) if ident.isdecimal() else ident) + (f" - {reste}" if reste else "")
    faits = []
    for i, debut in enumerate(debuts, 1):
        etiquette = f"{nom} (debut {i})" if len(debuts) > 1 else nom
        final = dossier / f"{etiquette}.mp4"
        with tempfile.TemporaryDirectory() as t:
            brut = Path(t) / f"{etiquette}.mp4"
            dire(f"{etiquette} : montage (1/3)...")
            duree, jointures = monter(d, debut, brut)
            dire(f"{etiquette} : sous-titres (2/3)...")
            srt = captions.captions(brut, long=format_ == "hmc")
            if srt is None:
                raise RuntimeError("transcription des sous-titres impossible")
            corriger(srt)
            relire(srt)
            dire(f"{etiquette} : incrustation (3/3)...")
            hab = HABILLAGE_SEUL.get(format_) or points.HABILLAGE[format_]
            cmd = ["python3", str(SCRIPTS / "incruster-captions.py"), str(brut), str(srt),
                   str(final), "--y", str(hab["cap_y"]), "--taille", str(hab["cap_taille"])]
            if "titre_taille" in hab:
                cmd += ["--accroche-taille", str(hab["titre_taille"])]
            if "titre_duree" in hab:
                cmd += ["--accroche-duree", str(hab["titre_duree"])]
            if hab.get("titre_deux_lignes"):
                cmd += ["--accroche-deux-lignes"]
            if hab.get("halo"):
                cmd += ["--halo"]
            if hab.get("cote_libre"):
                zones = Path(t) / "zones.json"
                zones.write_text(json.dumps(cote_libre(d, incruster.lire_srt(srt)),
                                            ensure_ascii=False), encoding="utf-8")
                cmd += ["--placements", str(zones)]
            if d.get("titre"):
                cmd += ["--accroche", d["titre"], "--accroche-y", str(hab["titre_y"])]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode or not final.exists():
                raise RuntimeError("incrustation : " + (r.stdout or r.stderr).strip()[-400:])
        faits.append(final.name)
        dire(f"{etiquette} : ok ({duree:.1f} s, {jointures} coupe(s))")
    dire(f"Termine : {', '.join(faits)} dans {dossier.parent.name}/{dossier.name}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"Echec : {e}")
