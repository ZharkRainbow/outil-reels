#!/usr/bin/env python3
"""Rend un extrait en appliquant les cadrages poses dans l'outil de recadrage.

Entre deux points, le cadrage GLISSE : on construit une expression ffmpeg
par morceaux evaluee a chaque frame, plutot que de decouper en segments, ce
qui donnerait des sauts secs.

Contrainte de ffmpeg : dans le filtre crop, w et h sont evalues une seule fois,
seuls x et y peuvent dependre du temps. Si les tailles varient entre deux
points, le script le signale et prend la plus grande.

    python3 rendre-depuis-points.py points.json --in 0 --out 63.5 --sortie clip.mp4
    ... [--srt fichier.srt] [--titre "..."]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import formats

CAM = Path("camera.mp4")   # surcharge par les arguments de la ligne de commande
SCR = Path("ecran.mp4")    # idem
SCRIPTS = Path(__file__).parent


def layout(cle):
    """La geometrie du format, lue dans scripts/formats.json comme la page et
    le rendu brut. Ce script habille deux zones ; un format a une seule camera
    n'a rien a habiller ici."""
    f = formats.trouver(cle)
    z = f["zones"]
    if "b" not in z:
        sys.exit(f"Le rendu habille attend deux zones, « {f['nom']} » n'en a qu'une.")
    coins = lambda n: (z[n]["x"], z[n]["y"], z[n]["w"], z[n]["h"])
    return dict(W=f["W"], H=f["H"], a=coins("a"), b=coins("b"), fond=formats.fond(cle))


def expression(pts, zone, axe, t0):
    """x(t) ou y(t) : interpolation lineaire par morceaux, temps relatif a t0."""
    p = sorted(pts, key=lambda q: q["t"])
    if len(p) == 1:
        return str(p[0][zone][axe])
    e = str(p[-1][zone][axe])                      # apres le dernier point
    for i in range(len(p) - 2, -1, -1):
        ta, tb = p[i]["t"] - t0, p[i + 1]["t"] - t0
        va, vb = p[i][zone][axe], p[i + 1][zone][axe]
        # palier par defaut : la valeur TIENT jusqu'au point suivant.
        # Le glissement n'a lieu que si le point le demande explicitement.
        seg = (str(va) if (va == vb or not p[i].get("glisse")) else
               f"({va}+({vb - va})*(t-{ta:.3f})/{tb - ta:.3f})")
        e = f"if(lt(t,{tb:.3f}),{seg},{e})"
    return f"if(lt(t,{p[0]['t'] - t0:.3f}),{p[0][zone][axe]},{e})"


def taille(pts, zone):
    ws = {q[zone]["w"] for q in pts}
    hs = {q[zone]["h"] for q in pts}
    if len(ws) > 1:
        print(f"  ! la taille du cadre {zone} varie ({sorted(ws)}) : ffmpeg ne sait pas "
              f"animer w/h, je prends {max(ws)}")
    return max(ws), max(hs)


def main():
    a = sys.argv[1:]
    data = json.loads(Path(a[0]).read_text(encoding="utf-8"))
    opt = {a[i]: a[i + 1] for i in range(1, len(a) - 1) if a[i].startswith("--")}
    t0, t1 = float(opt.get("--in", 0)), float(opt.get("--out", 0))
    dst = Path(opt["--sortie"])
    lay = layout(data.get("format", "vmc"))

    pts = [{"t": p["t"], "glisse": p.get("glisse", False),
             "A": p["camera"], "B": p["ecran"]} for p in data["points"]]
    if not pts:
        sys.exit(f"Le fichier de cadrage est vide : aucun point enregistre.\n"
                 f"Dans l'outil, verifie que le menu deroulant est bien sur le bon\n"
                 f"passage AVANT de poser les cadrages, puis clique 'Poser un cadrage\n"
                 f"ici' pour chacun avant d'envoyer.")
    dedans = [p for p in pts if t0 - 0.01 <= p["t"] <= t1 + 0.01]
    if not dedans:
        hors = ", ".join(f"{q['t']:.1f}s" for q in pts[:6])
        sys.exit(f"Aucun point dans la plage {t0:.1f} -> {t1:.1f}s.\n"
                 f"Les points recus sont a : {hors}\n"
                 f"Ils appartiennent a un autre passage : reselectionne le bon dans\n"
                 f"le menu deroulant, repose les cadrages, et renvoie.")
    print(f"{len(dedans)} point(s) de cadrage dans {t0:.1f} -> {t1:.1f}s")

    aw, ah = taille(dedans, "A")
    bw, bh = taille(dedans, "B")
    ax, ay = expression(dedans, "A", "x", t0), expression(dedans, "A", "y", t0)
    bx, by = expression(dedans, "B", "x", t0), expression(dedans, "B", "y", t0)
    # quelle source alimente la zone du bas : c'est la table qui le dit
    srcB = (CAM if formats.trouver(data.get("format", "vmc"))["zones"]["b"]["source"] == "camera"
            else SCR)
    aX, aY, aW, aH = lay["a"]
    bX, bY, bW, bH = lay["b"]

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        brut = tmp / "b.mp4"
        chaine = (
            f"[0:v]crop={aw}:{ah}:'{ax}':'{ay}':exact=1,scale={aW}:{aH}:flags=lanczos[cam];"
            f"[1:v]crop={bw}:{bh}:'{bx}':'{by}':exact=1,scale={bW}:{bH}:flags=lanczos[scr];"
            f"color=c={lay['fond']}:s={lay['W']}x{lay['H']}:d={t1-t0:.3f}[bg];"
            f"[bg][cam]overlay={aX}:{aY}[x];[x][scr]overlay={bX}:{bY}[v]"
        )
        r = subprocess.run([
            "ffmpeg", "-y", "-ss", f"{t0:.3f}", "-i", str(CAM),
            "-ss", f"{t0:.3f}", "-i", str(srcB), "-t", f"{t1-t0:.3f}",
            "-filter_complex", chaine, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(brut)
        ], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stderr[-1800:])
        subprocess.run(["python3", str(SCRIPTS / "masteriser-audio.py"), str(brut)],
                       capture_output=True)
        srt = opt.get("--srt")
        if srt and Path(srt).exists():
            # les reperes de l'habillage viennent de la table, comme la geometrie :
            # sur un format empile, le titre tombe sur la couture entre les deux
            # zones, et la couture n'est pas au meme endroit en 50/50 et en 80/20
            hab = formats.habillage(data.get("format", "vmc"))
            cmd = ["python3", str(SCRIPTS / "incruster-captions.py"), str(brut), srt,
                   str(dst), "--y", str(hab["cap_y"]),
                   "--taille", str(hab["cap_taille"])]
            if hab.get("halo"):
                cmd += ["--halo"]
            if opt.get("--titre"):
                cmd += ["--accroche", opt["--titre"],
                        "--accroche-y", str(hab["titre_y"])]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode:
                sys.exit((r.stdout or r.stderr)[-800:])
        else:
            brut.replace(dst)
    print(f"OK -> {dst}")


if __name__ == "__main__":
    main()
