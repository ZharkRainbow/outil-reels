#!/bin/bash
# Installe tout ce dont l'outil a besoin, sur un Mac.
# A lancer une seule fois :  bash installer.sh
set -e
cd "$(dirname "$0")"
RACINE="$(pwd)"

dire() { printf "\n\033[1m%s\033[0m\n" "$1"; }

dire "1/5  Homebrew"
if ! command -v brew >/dev/null; then
  echo "Homebrew n'est pas installe. Installe-le d'abord :"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi
echo "ok"

dire "2/5  ffmpeg et ImageMagick"
for p in ffmpeg imagemagick; do
  if brew list --formula "$p" >/dev/null 2>&1; then echo "$p : deja la"
  else brew install "$p"; fi
done

dire "3/5  whisper.cpp et son modele"
if ! command -v whisper-cli >/dev/null; then
  brew install whisper-cpp
else
  echo "whisper-cli : deja la"
fi
MODELE="$HOME/.cache/whisper-cpp/ggml-large-v3-turbo.bin"
if [ -f "$MODELE" ]; then
  echo "modele : deja la"
else
  echo "telechargement du modele (environ 1,6 Go, une seule fois)..."
  mkdir -p "$(dirname "$MODELE")"
  curl -L --progress-bar -o "$MODELE" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
fi

dire "4/5  detecteur de visage"
# Petit binaire Swift qui utilise Vision, le framework de reconnaissance
# d'Apple. Il repere le plus grand visage de chaque image : c'est ce qui
# permet au cadre du haut de suivre la personne toute seule.
if [ -f outils/reperer-visage ]; then
  echo "deja compile"
elif command -v swiftc >/dev/null; then
  swiftc -O -o outils/reperer-visage outils/reperer-visage.swift
  echo "compile"
else
  echo "swiftc absent : installe les outils Xcode avec  xcode-select --install"
  echo "puis relance ce script. Sans lui, le suivi automatique du visage"
  echo "ne marchera pas, le reste fonctionne."
fi

dire "5/5  verificateur d'orthographe (optionnel)"
python3 -m pip install --quiet --user pyspellchecker 2>/dev/null \
  && echo "installe" \
  || echo "non installe : le controle des sous-titres sera simplement saute"

dire "Vocabulaire"
if [ -f vocabulaire.json ]; then
  echo "vocabulaire.json : deja la"
else
  cp vocabulaire.exemple.json vocabulaire.json
  echo "vocabulaire.json cree depuis l'exemple. Ouvre-le pour y mettre tes"
  echo "marques, tes prenoms et ton jargon : c'est ce qui evite les fautes"
  echo "incrustees dans les sous-titres."
fi

mkdir -p lots rendus outil/cadrages
[ -d lots/exemple ] || cp -R exemple lots/exemple

dire "Verification"
python3 scripts/reglages.py

dire "C'est pret."
echo "Lance l'outil en double-cliquant sur \"Ouvrir l'outil.command\","
echo "ou avec :  python3 outil/serveur.py"
