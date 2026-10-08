# Outil de reels

Transformer un rush long en reels verticaux, sans ouvrir de logiciel de montage.

Tu poses les coupes et les cadrages dans une petite interface web qui tourne sur
ta machine, tu cliques sur Exporter, et tu récupères des fichiers finis :
recadrés, sous-titrés, avec le son remis à niveau. Rien ne part sur Internet,
tout se calcule en local.

---

## Ce que ça fait

**Deux caméras, une seule timeline.** L'outil travaille sur un proxy léger qui
contient les deux rushes côte à côte, plus le son. Un seul élément vidéo : il ne
peut pas se désynchroniser d'avec lui-même. C'était la vraie cause des « bugs de
synchro » des versions précédentes.

**Une seule piste, avec la forme d'onde.** Les pics sont calculés à la
préparation et stockés dans le JSON de la prise : zoomer ne redemande rien au
serveur. Le curseur de lecture s'attrape à la souris, un clic n'importe où sur la
piste s'y place, la molette zoome autour du pointeur (deux doigts à l'horizontale
pour glisser, « Tout voir » pour revenir). Mots transcrits, coupes, départs et
fin sont sur cette même piste.

**Les silences sont détectés et proposés en coupe.** Ils s'affichent hachurés en
rouge. Un clic garde, un clic coupe, les deux bords se règlent à la souris.
« Supprimer les blancs » les coupe tous d'un geste, « Tout garder » remet le reel
en continu. Le bouton « Couper ici » ajoute une coupe manuelle, dont les bords se
collent au blanc le plus proche. La case « Sauter les coupes » lit le montage
final, pour entendre le résultat avant de rendre.

**Le point de départ se règle au mot près.** Les mots transcrits sont posés sous
la forme d'onde. Tu glisses un départ, il se recale tout seul juste avant la
reprise de parole. Tu peux en poser plusieurs : chacun produit un fichier, pour
tester deux accroches sur la même prise.

**Le cadrage est horodaté.** Deux cadres verrouillés aux proportions du format
choisi, un aperçu en direct du rendu final. Tu poses un point de cadrage à un
instant donné, il tient jusqu'au point suivant — ou glisse par interpolation si
tu coches la case. Le cadre du haut peut suivre le visage automatiquement.

**Le rendu enchaîne tout seul :** montage et coupes calées sur la grille d'images,
son ramené à −14 LUFS, transcription du montage final, correction du vocabulaire,
contrôle orthographique, incrustation des sous-titres et du bandeau titre.

---

## Installation

Sur un Mac, une seule commande :

```bash
bash installer.sh
```

Le script installe ffmpeg, ImageMagick et whisper.cpp par Homebrew, télécharge le
modèle de transcription (1,6 Go, une seule fois), compile le détecteur de visage,
et crée `vocabulaire.json` à partir de l'exemple.

Pour vérifier à tout moment que rien ne manque :

```bash
python3 scripts/reglages.py
```

### Les polices

Le style d'origine utilise **ZTNature**, une police sous licence qui n'est pas
distribuée ici. Si elle n'est pas installée, l'outil retombe sur une police
système : le rendu est moins beau, il n'est pas cassé. Pour retrouver le style
exact, pose `ZTNature-MediumItalic.otf` et `ZTNature-Bold.otf` dans
`~/Library/Fonts`, ou pointe les tiennes :

```bash
export REELS_POLICE="$HOME/Library/Fonts/MaPolice-Italic.otf"
export REELS_POLICE_TITRE="$HOME/Library/Fonts/MaPolice-Bold.otf"
```

---

## Utilisation

### 1. Préparer un lot

Un lot, c'est un tournage : plusieurs prises qui partagent les mêmes réglages.

```bash
python3 scripts/preparer-reels.py "<dossier face cam>" "<dossier second écran>" \
    --lot "Matin" --sortie "Mes reels"
```

Le script cale les deux caméras par le son, fabrique les proxys, détecte les
blancs, transcrit mot à mot, propose les coupes et écrit le manifeste
`lots/Matin/reels.json`. C'est long : compte le temps réel de la vidéo.

Pour un tournage à une seule caméra, mets `-` à la place du second dossier.

Le format du manifeste est documenté dans `exemple/reels.json`.

Pour deux pistes déjà synchronisées et deux micros à entendre :

```bash
python3 scripts/preparer-reels.py "<dossier haut>" "<dossier bas>" \
    --lot "Podcast" --deja-synchronisees --mixer-son
```

Chaque lot reste dans `lots/<nom>/`. Le mix alimente le proxy, la transcription
et les deux modes de rendu ; les rushes ne sont pas modifiés. Sans `--mixer-son`,
le son vient toujours de la caméra du haut.

### 2. Cadrer

```bash
python3 outil/serveur.py
```

Puis ouvre **http://localhost:8765/?lot=Matin** — ou double-clique
`Ouvrir l'outil.command`.

Tu passes d'une prise à l'autre avec le menu en haut. Ton travail est gardé dans
le navigateur au fur et à mesure : tu peux fermer et revenir.

### 3. Exporter

Le bouton **Valider et envoyer en production** met le rendu dans une file. Les exports passent un par un,
pour que dix rendus ne se disputent pas la machine. L'avancement s'affiche dans
la page, et le détail va dans `outil/cadrages/<nom>.log`.

Les fichiers finis arrivent dans `rendus/<sortie>/Vertical/` ou `Horizontal/`.

---

## Les formats

| Clé | Rendu |
|---|---|
| `vmc` | 1080×1920, deux caméras empilées 50/50 |
| `hmc` | 1920×1080, caméra à gauche, écran à droite |
| `hsolo` | 1920×1080, une caméra, sous-titres du côté libre du visage |
| `carre` | 1080×1080, la vidéo d'origine entre deux bandes noires |
| `v7030` `v6535` `v6040` | 1080×1920, deux caméras, proportions à comparer |
| `h5050` | 1920×1080, deux caméras côte à côte |

Un lot ne propose que les formats listés dans son manifeste.

---

## Le vocabulaire

Whisper ne connaît ni ta marque, ni ton jargon, ni les prénoms de ton équipe. Il
remplace ce qu'il n'entend pas par le mot le plus proche statistiquement, et la
faute se retrouve **incrustée dans l'image**. Une marque devient un sigle, un nom
de famille perd sa première lettre.

`vocabulaire.json` règle ça. Copie `vocabulaire.exemple.json`, remplis-le :

- `mot_a_mot` : un mot pour un mot. **Les clés s'écrivent sans accent et sans
  majuscule**, la comparaison les retire. Écrire `"leborgne"`, jamais `"Lebôrgne"`,
  sinon la règle ne s'applique jamais.
- `suites` : des groupes de mots, les plus longs d'abord.
- `hallucinations` : les phrases que whisper invente sur du silence (« sous-titrage
  par… », « merci d'avoir regardé »). Elles sont supprimées.
- `marque` : plutôt qu'une liste de graphies, une règle de forme. Whisper en invente
  une nouvelle à chaque passe et coupe parfois le mot en deux. On déclare les débuts
  et les fins possibles, plus une liste blanche de vrais mots à ne pas toucher.
- `nom_de_famille` : même logique. Après le prénom, tout mot commençant par
  l'initiale du nom et qui n'est pas un mot courant est remplacé.
- `jargon` : les mots justes que le dictionnaire français ignore, pour que le
  contrôle orthographique ne les signale pas.

Chaque correction devrait être vérifiée à l'oreille avant d'être ajoutée.

**Le contrôle orthographique.** Le dictionnaire ne rattrape que les fautes déjà
rencontrées. Après correction, les sous-titres passent au dictionnaire français et
tout mot douteux est écrit dans un fichier `.relire.txt` à côté de la vidéo. Il ne
corrige rien tout seul — personne n'arbitre pendant un rendu — mais une faute
inconnue se voit **avant** publication, pas après.

---

## Réglages

Tout se surcharge par variable d'environnement, sans toucher au code. Les valeurs
par défaut restent à l'intérieur du dépôt : une première installation marche sans
rien configurer.

| Variable | Défaut | Rôle |
|---|---|---|
| `REELS_LOTS` | `lots/` | où l'outil cherche les lots préparés |
| `REELS_SORTIE` | `rendus/` | où atterrissent les vidéos finies |
| `REELS_PREFIXE` | vide | préfixe du nom de fichier : `07 - <préfixe> <titre>.mp4` |
| `REELS_MODELE` | `~/.cache/whisper-cpp/ggml-large-v3-turbo.bin` | modèle de transcription |
| `REELS_LANGUE` | `fr` | langue passée à whisper |
| `REELS_VOCABULAIRE` | `vocabulaire.json` | dictionnaire de correction |
| `REELS_POLICE` / `REELS_POLICE_TITRE` | ZTNature | polices des sous-titres |
| `REELS_COULEUR_CAPTIONS` / `REELS_COULEUR_TITRE` | `#FAD400` / `#2322E0` | couleurs |
| `REELS_CADRAGES` | `outil/cadrages/` | cadrages enregistrés et journaux |
| `REELS_PORT` | `8765` | port du serveur local |

`python3 scripts/reglages.py` affiche les valeurs actives et ce qui manque.

---

## Ce qu'il y a dans le dépôt

```
outil/serveur.py              serveur local, file d'export, support des requêtes Range
outil/index.html              toute l'interface, sans dépendance externe
scripts/reglages.py           chemins et réglages, le seul fichier à regarder
scripts/preparer-reels.py     calage, proxys, blancs, transcription, manifeste
scripts/caler-flux.py         mesure le décalage entre les deux caméras
scripts/rendre-reel.py        le rendu, de bout en bout
scripts/rendre-depuis-points.py  interpolation des cadrages, habillage par format
scripts/faire-captions.py     sous-titres courts calés sur le montage final
scripts/incruster-captions.py rend les sous-titres en PNG puis les incruste
scripts/corriger-transcript.py applique le vocabulaire, timecodes préservés
outils/reperer-visage.swift   détection de visage par Vision, compilée à l'installation
exemple/reels.json            le format d'un manifeste, commenté
```

---

## Détails qui ont coûté cher

Quelques pièges rencontrés en construisant l'outil, notés pour qui voudrait le
modifier.

**Les requêtes Range.** `SimpleHTTPRequestHandler` ne les gère pas : il répond 200
avec le fichier entier au lieu de 206 avec la plage demandée. Pour une vidéo de
146 Mo, le navigateur doit tout télécharger avant de lire, et surtout il ne peut
pas se déplacer dans la timeline. C'était la cause réelle des blocages. Le support
Range est implémenté dans `serveur.py`.

**Le proxy a besoin de `-g 10`.** Sans image-clé rapprochée, il y en a une toutes
les 8 secondes et le déplacement dans la timeline devient inutilisable :

```bash
ffmpeg -i RUSH.mp4 -vf scale=640:360 -c:v libx264 -crf 28 -preset veryfast \
  -g 10 -keyint_min 10 -sc_threshold 0 -an proxy.mp4
```

**Les coupes sont calées sur la grille d'images** (23,976 i/s). La vidéo retire des
images entières et le son exactement la même durée, sinon chaque coupe décale un
peu la synchro labiale.

**Les sous-titres sont re-transcrits sur le montage**, pas découpés depuis le SRT
du rush. Les segments d'un long format font 2 à 5 secondes, illisibles en reel, et
un découpage réintroduit une dérive de calage.

**Les sous-titres passent par ImageMagick**, pas par `drawtext` : beaucoup de
builds de ffmpeg n'ont ni `drawtext` ni `subtitles`.

---

## Licence

MIT. Voir `LICENCE`.

---

## Mode podcast : deux caméras déjà synchronisées, rendu brut

Pour des pistes Riverside (ou toute paire déjà alignée) qu'on veut juste couper et
cadrer, sans sous-titres ni habillage :

1. Découper les mêmes passages dans deux dossiers, avec les mêmes noms `.MP4`.
2. Préparer avec `--lot Podcast --deja-synchronisees --mixer-son` (commande ci-dessus).
3. Ajouter à `lots/Podcast/reels.json` :
   - `"formats": ["vmc"]` ;
   - `"cadres": {"vmc_haut": {...}, "vmc": {...}}` pour les cadres fixes par défaut ;
   - `"production": {"script": "produire-split.py", "sortie": "<dossier>"}`.
4. Lancer `python3 outil/serveur.py`, puis ouvrir `http://localhost:8765/?lot=Podcast`.
5. Régler début, fin et coupes, puis **Valider et envoyer en production**.
   L'état du rendu apparaît sous le bouton ; **Reel suivant** (raccourci `N`)
   permet de poursuivre. Les ✓ du menu indiquent les validations envoyées depuis
   ce navigateur, pas une garantie de réussite du rendu.

L'ancien `lots/reels.json` reste accessible avec `/?lot=reels`, sans lien symbolique.
Une nouvelle préparation avec `--lot reels` reprend ses réglages dans `lots/reels/`.
Le bouton secondaire **Exporter (un fichier par début)** apparaît dès qu'il y a
plusieurs départs ; les deux modes de rendu produisent alors toutes les variantes.

Sur la piste, la molette zoome autour du pointeur pour lire les mots et poser les
départs au bon endroit. `Espace` lance la lecture, `←`/`→` déplacent d'une seconde (`Maj` : dix secondes),
`I` ajoute un début, `O` pose la fin, `C` commence/termine une coupe.
`Alt` + flèches déplace le cadre sélectionné.

Les améliorations sont décrites dans `docs/BRIEF-REFONTE-UX.md` et leur vérification
dans `docs/COMPTE-RENDU-REFONTE.md`.
