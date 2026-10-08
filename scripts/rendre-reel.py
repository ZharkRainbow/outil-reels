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
formats = import_module("formats")
points = import_module("rendre-depuis-points")
captions = import_module("faire-captions")
incruster = import_module("incruster-captions")

SCRIPTS = Path(__file__).parent
SORTIE = reglages.SORTIE
SRC_W, SRC_H = 3840, 2160
ACCEL = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []
IPS = 24000 / 1001
# La geometrie, le dossier de rangement et les reperes d'habillage viennent de
# scripts/formats.json, comme pour la page et le rendu brut. Tant que ce script
# gardait sa propre table, il ne connaissait que quatre formats sur dix : la page
# proposait le 80/20 et le rendu par defaut sortait « KeyError: v8020 ». Il
# donnait aussi au carre une toile 1080x1920, quand la page, le rendu brut et le
# README disent 1080x1080.
# Un point de cadrage porte un cadre « camera » et un cadre « ecran » ; la table
# dit lequel alimente quelle zone, et depuis quel rush.
ZONE = {"a": "A", "b": "B"}
LUFS = -14.0
FONDU = 0.005            # 5 ms a chaque jointure : pas de clic, rien d'audible
# Vocabulaire : on passe par le dictionnaire commun, celui de
# corriger-transcript.py, et non par une poignee de regex locales. Deux regex
# ne rattrapaient que la marque ; tout le reste partait a l'ecran tel que whisper
# l'avait entendu, d'ou "de l'AMLIST" incruste a la place de "de lemlist".
vocabulaire = import_module("corriger-transcript")


def dire(texte):
    print(texte, flush=True)


def taille_source(chemin):
    """Largeur et hauteur de la piste image, lues par ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "json", str(chemin)],
                       capture_output=True, text=True, check=True)
    flux = json.loads(r.stdout)["streams"][0]
    return int(flux["width"]), int(flux["height"])


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
    """Cadrages de chaque zone du format, aux bonnes proportions, en pixels pairs.

    Les zones et leur source sont lues dans la table : le vertical consulting
    prend ainsi ses DEUX cadrages dans le rush du haut, et non un dans chaque.
    """
    # l'outil peut envoyer des tailles a virgule : ffmpeg veut des pixels pairs
    pair = lambda v: int(round(v / 2)) * 2
    cle = d.get("format", "vmc")
    zones = dict(formats.zones(cle))
    # Les cadres arrivent dans le repere de l'outil (d["source"], 3840 de large).
    # Sur un rush 1080p, les reprendre tels quels donne un crop plus grand que
    # l'image, et ffmpeg refuse. Le rendu brut applique deja ce facteur.
    reference = (d.get("source") or {}).get("w") or SRC_W
    srcA = taille_source(d["camera"])
    source = {"camera": srcA,
              "ecran": taille_source(d["ecran"]) if d.get("ecran") else srcA}

    def cadre(c, src):
        W, H = src
        k = W / reference
        q = {z: pair(c[z] * k) for z in ("x", "y", "w", "h")}
        q["w"], q["h"] = min(q["w"], W - W % 2), min(q["h"], H - H % 2)
        q["x"] = max(0, min(q["x"], W - q["w"]))
        q["y"] = max(0, min(q["y"], H - q["h"]))
        return q

    def aux_proportions(p, nom):
        """Le cadre du point pour cette zone, s'il a bien ses proportions."""
        z = zones[nom]
        c = p["camera"] if nom == "a" else p.get("ecran")
        if not c or abs(c["w"] / c["h"] - z["w"] / z["h"]) >= 0.03:
            return None
        return cadre(c, source[z["source"]])

    # l'outil garde les cadres de plusieurs formats : on prend ceux aux bonnes proportions
    pts = []
    for p in d.get("points", []):
        q = {ZONE[nom]: aux_proportions(p, nom) for nom in zones}
        if any(v is None for v in q.values()):
            continue
        q.setdefault("B", q["A"])      # format a une zone : rien a empiler
        pts.append({"t": p["t"], "glisse": p.get("glisse", False), **q})
    if not pts and formats.une_camera(cle):
        # une camera sans cadrage pose : le plan entier
        entier = {"x": 0, "y": 0, "w": pair(srcA[0]), "h": pair(srcA[1])}
        pts = [{"t": 0, "glisse": False, "A": entier, "B": entier}]
    if not pts:
        raise RuntimeError("aucun cadrage pose pour ce format")
    return pts


def monter(d, debut, dst):
    fin = d["fin"]
    parts = morceaux(debut, fin, d.get("coupes", []))
    if not parts:
        raise RuntimeError("tout est coupe entre ce debut et la fin")
    cle = d.get("format", "vmc")
    f_ = formats.trouver(cle)
    zones = formats.zones(cle)
    pts = cadrages(d)

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
    # Une zone posee par zone de la table : le meme chemin sert les dix formats,
    # empiles, cote a cote ou a une seule camera. La premiere zone est agrandie
    # aux dimensions du format par « pad », les suivantes posees par-dessus.
    # On ne part PAS d'un fond « color » : les horodatages du montage doivent
    # rester ceux du rush, sinon le select ci-dessus decale tout d'une image.
    def etage(nom, z):
        """Le rush de cette zone, recadre et mis a l'echelle de la zone."""
        k = ZONE[nom]
        w, h = points.taille(pts, k)
        x, y = (points.expression(pts, k, axe, debut) for axe in ("x", "y"))
        # seul le second rush porte le retournement de la tablette et son calage
        devant = rotation if z["source"] == "ecran" else ""
        apres_fps = retard if z["source"] == "ecran" else ""
        return (f"[{flux[z['source']]}]{devant}fps=24000/1001{apres_fps},"
                f"crop={w}:{h}:'{x}':'{y}':exact=1,"
                f"scale={z['w']}:{z['h']}:flags=lanczos,setsar=1")

    entrees = [*ACCEL, "-ss", f"{debut:.3f}", "-t", f"{duree + 0.5:.3f}",
               "-i", d["camera"]]
    besoin_ecran = any(z["source"] == "ecran" for _, z in zones)
    if besoin_ecran:
        entrees += [*ACCEL, "-ss", f"{depart_ecran:.3f}",
                    "-t", f"{duree + 0.5:.3f}", "-i", d["ecran"]]
    flux = {"camera": "0:v:0", "ecran": "1:v:0"}
    (nom0, z0), autres = zones[0], zones[1:]
    fond = f"pad={f_['W']}:{f_['H']}:{z0['x']}:{z0['y']}:color={formats.fond(cle)}"
    branches, dessus = [etage(nom0, z0) + f",{fond}[mont0]"], "mont0"
    for n, (nom, z) in enumerate(autres, 1):
        branches.append(etage(nom, z) + f"[z{nom}]")
        branches.append(f"[{dessus}][z{nom}]overlay={z['x']}:{z['y']}[mont{n}]")
        dessus = f"mont{n}"
    chaine = ";".join([*branches, f"[{dessus}]" + selection, *son])
    if d.get("audio"):
        entrees += ["-ss", f"{debut:.3f}", "-i", d["audio"]]
        chaine = chaine.replace("[0:a:0]", f"[{2 if besoin_ecran else 1}:a:0]")
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
    try:
        formats.trouver(format_)
    except ValueError as pb:
        sys.exit(str(pb))
    if not d.get("points") and not formats.une_camera(format_):
        sys.exit("Aucun cadrage pose : pose au moins un cadrage avant d'exporter.")
    debuts = d.get("debuts") or [0.0]
    # rangement : <sortie>/Vertical/01 - <titre>.mp4
    racine = SORTIE
    if d.get("sortie") and "REELS_SORTIE" not in os.environ:
        # dans SORTIE, pas a cote : SORTIE.parent, c'est la racine du depot,
        # et "sortie": "Mes reels" y faisait apparaitre un dossier de rendus
        racine = SORTIE / d["sortie"]
    dossier = racine / formats.dossier(format_)
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
            hab = formats.habillage(format_)
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
