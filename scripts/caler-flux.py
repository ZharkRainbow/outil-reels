#!/usr/bin/env python3
"""Mesure le decalage entre deux enregistrements d'une meme prise, par le son.

Les deux cameras recoivent le meme micro sans fil : leurs pistes audio sont
quasi identiques, a un decalage pres. On correle leur enveloppe (voir
decalage()).

    python3 caler-flux.py reference.mp4 autre.mp4
    -> temps_autre = temps_reference + decalage (secondes)
"""
import subprocess
import sys
from array import array

TAUX = 2000
DUREE = 60
LAG_MAX = 8.0


def signal(chemin):
    brut = subprocess.run(
        ["ffmpeg", "-v", "error", "-t", str(DUREE), "-i", chemin, "-map", "0:a:0",
         "-ac", "1", "-ar", str(TAUX), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    s = array("h")
    s.frombytes(brut[: len(brut) // 2 * 2])
    return s


def enveloppe(s, pas=20):
    env = [sum(abs(v) for v in s[i:i + pas]) / pas for i in range(0, len(s) - pas, pas)]
    m = sum(env) / len(env)
    return [v - m for v in env]


def meilleur(ref, oth, lags, debut, fin):
    best, best_lag = None, 0
    for lag in lags:
        c = 0.0
        for i in range(debut, fin):
            j = i + lag
            if 0 <= j < len(oth):
                c += ref[i] * oth[j]
        if best is None or c > best:
            best, best_lag = c, lag
    return best_lag, best


def normalise(ref, oth, lag, debut, fin):
    a = [ref[i] for i in range(debut, fin) if 0 <= i + lag < len(oth)]
    b = [oth[i + lag] for i in range(debut, fin) if 0 <= i + lag < len(oth)]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def decalage(reference, autre):
    """Correlation d'enveloppe a 100 Hz, affinee par interpolation parabolique.

    Le signal brut des deux recepteurs du micro n'est pas en phase (codecs et
    filtres differents) : sa correlation est faible et trompeuse. L'enveloppe,
    elle, correle a plus de 0,9. Une precision de 10 ms suffit largement : une
    image dure 40 ms.
    """
    r, o = signal(reference), signal(autre)
    er, eo = enveloppe(r), enveloppe(o)
    k = int(LAG_MAX * 100)
    lag, _ = meilleur(er, eo, range(-k, k + 1), k, len(er) - k)
    c = [normalise(er, eo, lag + d, k, len(er) - k) for d in (-1, 0, 1)]
    den = c[0] - 2 * c[1] + c[2]
    fin = 0.5 * (c[0] - c[2]) / den if den else 0.0
    return (lag + max(-0.5, min(0.5, fin))) / 100, c[1]


if __name__ == "__main__":
    d, c = decalage(sys.argv[1], sys.argv[2])
    print(f"{d:.4f} {c:.3f}")
