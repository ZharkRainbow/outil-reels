#!/usr/bin/env python3
"""Genere un SRT de captions courtes (3 a 5 mots) pour chaque clip d'un lot.

On re-transcrit le clip plutot que de decouper le SRT du long format : les
segments d'un long format font 2 a 5 s, illisibles en reel, et un decoupage
reintroduit une derive de calage. Whisper relance sur le clip donne des
timecodes cales a la frame sur ce clip precis.

    python3 faire-captions.py <dossier> [<dossier> ...]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reglages

MODELE = reglages.MODELE_WHISPER
MAX_CAR = 19          # vertical : 3 a 4 mots par caption
MAX_CAR_LONG = 46     # horizontal : 7 a 8 mots. Au-dela, la contrainte 'une seule ligne' force une reduction qui rend le texte illisible.


def captions(src: Path, long=False) -> Path | None:
    dossier = "_captions-long" if long else "_captions"
    dst = src.parent / dossier / (src.stem + ".srt")
    dst.parent.mkdir(exist_ok=True)
    if dst.exists():
        return dst
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ar", "16000",
                        "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                       capture_output=True)
        if not wav.exists():
            return None
        subprocess.run(["whisper-cli", "-m", str(MODELE), "-f", str(wav),
                        "-l", "fr", "-osrt", "-ml", str(MAX_CAR_LONG if long else MAX_CAR), "-sow",
                        "-of", str(Path(tmp) / "c")], capture_output=True)
        srt = Path(tmp) / "c.srt"
        if not srt.exists():
            return None
        dst.write_text(srt.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


if __name__ == "__main__":
    cibles = []
    for a in sys.argv[1:]:
        if a.startswith("--"):
            continue
        p = Path(a)
        cibles += sorted(x for x in p.rglob("*.mp4")) if p.is_dir() else [p]
    long = "--long" in sys.argv
    for f in cibles:
        r = captions(f, long)
        n = len(r.read_text(encoding="utf-8").strip().split("\n\n")) if r else 0
        print(f"{f.name[:60]:62s} {n:4d} captions", flush=True)
    print("TERMINE")
