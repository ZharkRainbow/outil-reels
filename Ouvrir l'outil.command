#!/bin/bash
# Double-clique ce fichier pour lancer l'outil et ouvrir le navigateur.
cd "$(dirname "$0")"
PORT="${REELS_PORT:-8765}"
( sleep 1; open "http://localhost:$PORT" ) &
python3 outil/serveur.py
