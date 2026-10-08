# Compte rendu — brief V2, 8 octobre 2026

Branche `refonte-v2`. Points 1 à 4 du brief V2, un commit par sujet, puis ce
compte rendu. Aucun push. Aucun média, lot, rendu ou cadrage de test dans le
dépôt : tout le matériel de vérification vit dans `/tmp`. Aucune dépendance
ajoutée, aucun build, Python standard.

| commit    | sujet                                                      |
|-----------|------------------------------------------------------------|
| `5347dfc` | 1 — Timeline : forme d'onde, curseur attrapable, zoom molette |
| `98552b1` | 3 — Formats : une table partagée, le 80/20, un cadre par format |
| `f8519ba` | 2 — Reel suivant vaut validation, et le suivi tient par reel |
| `d3d8dba` | 4 — Interface : gris chauds, un seul accent, commandes à la même hauteur |

## Ce qui a changé

### 1. La timeline de l'Atelier, réécrite ici

La piste est maintenant une vraie timeline, écrite de zéro dans
`outil/index.html` d'après la référence hors dépôt `~/projets/references/atelier`
(même auteur, Lucas). Rien n'en a été copié : ni code, ni dépendance, ni build.

- **Forme d'onde** dessinée dans un canvas, un pic par colonne de pixels,
  `devicePixelRatio` plafonné à 2. L'amplitude est compressée (puissance 0,75)
  et normalisée avec un plancher, sinon une prise silencieuse affiche un trait.
- **Curseur attrapable** : on le prend à la souris et on le déplace, et un clic
  n'importe où sur la piste s'y place. Les deux passent par les mêmes
  Pointer Events avec `setPointerCapture`, et un seuil de 2 px sépare le clic du
  glisser — sans lui, tout clic devenait un micro-déplacement.
- **Zoom à la molette et au trackpad**, ancré sous le curseur de la souris,
  avec `deltaMode` normalisé et le pincement (`ctrlKey`) traité comme un zoom.
  Deux doigts font glisser la fenêtre.
- Les **mots transcrits** et les **coupes** restent sur cette même piste, les
  coupes gardant leurs deux bords attrapables.
- **« Supprimer les blancs »** coupe tous les blancs proposés d'un clic,
  **« Tout garder »** les rend tous, et chaque blanc reste réglable un par un.
- Les **départs** (D1, D2…) et la **fin** sont des poignées en capsule,
  visibles et déplaçables.

### 2. « Reel suivant » vaut validation

Un seul geste. Le bouton de la colonne de droite enregistre le cadrage, envoie
le reel en production et ouvre le suivant ; raccourci `N`. Le reel passe en ✓
dans le menu. Sur le dernier reel, le bouton dit « Valider et envoyer en
production » et ne bascule nulle part.

Pour naviguer sans rien envoyer, deux commandes discrètes sous la piste :
« ‹ Reel précédent » et « passer sans valider › ».

Le **suivi de production** est devenu une liste, une ligne par reel envoyé,
avec une pastille d'état (en file, en cours, prêt, raté). Un seul paragraphe ne
suffisait plus : dès qu'on passait au reel suivant, le rendu en cours
disparaissait de l'écran alors qu'il tournait encore.

Le corps de la requête est figé **avant** l'attente réseau : changer de reel
pendant un envoi ne peut plus corrompre ce qui part. Si l'envoi échoue, on
reste sur le reel.

### 3. Les formats, et une seule table de géométrie

La géométrie vit désormais dans **`scripts/formats.json`**, un seul fichier lu
par les trois côtés : la page (servie telle quelle sur `/formats.json`),
`scripts/produire-split.py` et `scripts/rendre-depuis-points.py`, via le petit
module `scripts/formats.py`. Tant que la géométrie était recopiée des deux
côtés, un cadre posé dans l'outil ne tombait pas exactement là où le rendu le
mettait, et il fallait encoder pour s'en apercevoir.

Dix formats, dont le **Vertical 80/20** demandé :

| clé | nom | image | zones |
|-----|-----|-------|-------|
| `vmc` | Vertical 50/50 | 1080 × 1920 | 960 / 960 |
| `v8020` | Vertical 80/20 | 1080 × 1920 | 1536 / 384 |
| `v7030` | Vertical 70/30 | 1080 × 1920 | 1344 / 576 |
| `hmc` | Horizontal | 1920 × 1080 | 720 à gauche / 1200 à droite |
| `h5050` | Horizontal 50/50 | 1920 × 1080 | 960 / 960 côte à côte |
| `vcons` | Vertical consulting | 1080 × 1920 | deux cadrages du **même** rush |
| `v6535` | Vertical 65/35 | 1080 × 1920 | 1248 / 672 |
| `v6040` | Vertical 60/40 | 1080 × 1920 | 1152 / 768 |
| `hsolo` | Horizontal une caméra | 1920 × 1080 | une seule zone |
| `carre` | Carré 1:1 | 1080 × 1080 | une zone entre deux bandes |

- Le sélecteur est **toujours visible** sur un lot à deux caméras. Par défaut
  tous les formats à deux caméras sont proposés ; le manifeste du lot peut
  restreindre la liste avec sa clé `"formats"`.
- **Chaque format garde ses propres cadres.** Un point de cadrage porte sa clé
  de format : un cadrage posé en 50/50 ne s'applique pas en 80/20. Les cadres
  par défaut du lot (`"cadres"`) restent appliqués à chaque format qu'ils
  couvrent.
- `produire-split.py` rend **tous** ces formats par le même chemin : un fond aux
  dimensions du format, puis une zone posée par-dessus, autant de fois qu'il y a
  de zones. Le fichier porte le nom du format, donc deux formats du même reel
  cohabitent dans le dossier de sortie.

### 4. L'interface

La mise en page était déjà la bonne — lecteur au centre, piste en bas,
inspecteur à droite — donc le travail a porté sur la typographie, la densité et
les états. Quatre habitudes reprises de **HyperFrames Studio** (npm
`hyperframes`, Apache-2.0), installé hors dépôt dans `~/outils-hf` et regardé
dans Chrome. Rien n'en est copié : ni code, ni dépendance, ni couleur de marque.

- **Trois niveaux de fond seulement**, en gris chauds, et pas un de plus.
- **Les liserés ne sont plus une couleur** mais du blanc transparent : le même
  liseré tient sur les trois niveaux.
- **Un seul accent**, l'ambre de la forme d'onde. Le bleu et le cyan
  disparaissent ; le vert et le rouge ne disent plus qu'un état. Un seul aplat
  plein par écran, le bouton de validation ; l'action principale de la barre de
  commandes prend un ambre sourd.
- **Densité** : titres de section à 9 px très espacés, nombres en chasse fixe et
  alignés, lignes de valeurs réduites à un filet, toutes les commandes à 28 px,
  anneau de mise au point à l'intérieur, transitions courtes limitées à la
  couleur et à l'échelle. `prefers-reduced-motion` les coupe.

## Comment c'est vérifié

### Le lot de test

Fabriqué avec ffmpeg dans `/tmp/lot-v2` : deux caméras distinctes (mires
différentes), trois prises de 20 s, 1920 × 1080, 24 ips, avec son. Un second lot
`Restreint` porte `"formats": ["vmc", "v8020"]` pour contrôler la restriction.
Rien de tout cela n'entre dans le dépôt.

### PASS — compilation et tests

```
python3 -m py_compile outil/*.py scripts/*.py tests/*.py
python3 -m unittest discover -s tests     → 9 tests, OK
git diff --check                          → rien
```

### PASS — les dix formats produits et contrôlés

Les dix cadrages de test (un par format, cadres centrés au ratio de chaque
zone) ont été rendus pour de bon par `produire-split.py`, puis contrôlés à
ffprobe. Durée attendue d'après le cadrage : début 0,41 s, fin 19,28 s, quatre
coupes → **15,71 s**.

| clé | image obtenue | attendue | durée image | durée son | ips |
|-----|---------------|----------|-------------|-----------|-----|
| `vmc` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `v8020` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `v7030` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `hmc` | 1920 × 1080 | 1920 × 1080 | 15,71 s | 15,71 s | 24 |
| `h5050` | 1920 × 1080 | 1920 × 1080 | 15,71 s | 15,71 s | 24 |
| `vcons` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `v6535` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `v6040` | 1080 × 1920 | 1080 × 1920 | 15,71 s | 15,71 s | 24 |
| `hsolo` | 1920 × 1080 | 1920 × 1080 | 15,71 s | 15,71 s | 24 |
| `carre` | 1080 × 1080 | 1080 × 1080 | 15,71 s | 15,71 s | 24 |

Son présent partout, aac 48 kHz, et **l'image et le son ont exactement la même
durée** : le calage des bornes sur la grille d'images tient sur les dix.

La géométrie a aussi été regardée à l'œil, en extrayant une image de quatre
rendus : le 80/20 a bien une grande zone en haut et une bande étroite en bas, le
vertical consulting montre deux fois le même rush, l'horizontal pose la caméra à
gauche sur 720, le carré encadre l'image entre deux bandes.

### PASS — la timeline dans un vrai navigateur

Chrome (service `chrome-dev`, protocole de débogage), page ouverte sur le lot de
test :

| geste | résultat |
|-------|----------|
| clic à 60 % d'une prise de 20 s | lecture à 12,00 s |
| curseur attrapé et glissé à 25 % | lecture à 5,00 s |
| molette vers le haut, souris au milieu | fenêtre 0–20 s → 6,32–13,68 s, centrée sur le curseur |
| « Tout garder » | 0 coupe active, durée finale 0:15.2 |
| « Supprimer les blancs » | 5 coupes actives, durée finale 0:12.2 |

Aucune erreur JavaScript.

### PASS — un geste vaut validation

Toujours dans Chrome, sur le lot de test, mémoire du navigateur vidée :

1. menu au départ : `○ Test 1`, `○ Test 2`, `○ Test 3` ;
2. un cadrage posé, puis le bouton de validation ;
3. le reel courant passe à `Test 2`, le menu affiche `✓ Test 1`, le compteur
   passe à 1/3 ;
4. le bloc « Suivi de production » montre `Test 1 — Prêt`, pastille verte ;
5. le fichier est bien sur le disque :
   `/tmp/lot-v2/rendus/1 - La timeline qu on attrape a la souris - vertical 50-50.mp4`.

Aucune erreur JavaScript.

### PASS — les formats dans la page

- Lot à deux caméras sans clé `"formats"` : les huit formats à deux caméras sont
  proposés, le premier est marqué actif.
- Lot `Restreint` : seuls « Vertical 50/50 » et « Vertical 80/20 » apparaissent.
- Passage de 50/50 à 80/20 : l'aperçu change de découpe, le cadre du haut passe
  à « toute la hauteur », et « Cadrages posés » repasse à « aucun » — le point
  posé en 50/50 ne suit pas, c'est le comportement demandé.

### PASS — la mise en forme

Captures avant/après à 1440 × 900 sur le lot de test, et une capture à
1000 × 820 : la barre du haut passe à la ligne sans déborder (78 px de haut,
pas de défilement horizontal), les 19 boutons de commande mesurent tous 28 px
sauf le bouton de validation à 36 px, aucune erreur de console.

## Ce qui reste

- **Le rendu habillé** (`rendre-depuis-points.py`) lit maintenant la table
  partagée, mais son habillage — titre, sous-titres, marges — n'est prévu que
  pour deux zones et retombe sur un gabarit choisi d'après l'orientation. Les
  formats à une caméra (`hsolo`, `carre`) sortent donc en rendu brut seulement.
  Les habiller demande un gabarit par format, ce qui n'est pas dans ce brief.
- **La transcription du lot de test est factice.** Les mots affichés sur la
  piste viennent d'un fichier écrit à la main : le calage mot à mot sur une
  vraie prise n'est pas vérifié ici.
- **Le zoom ne tient pas entre deux reels.** Changer de reel remet la fenêtre à
  la prise entière. C'est volontaire pour l'instant, mais sur une longue
  session de montage on voudra sans doute la garder.
- **Les ✓ du menu vivent dans ce navigateur**, pas sur le serveur. Ils disent
  « envoyé », pas « rendu réussi » — le suivi de production, lui, dit l'état
  réel, mais il disparaît au rechargement de la page.
- **Un reel produit dans plusieurs formats n'est pas suivi comme tel** : les
  fichiers cohabitent bien dans le dossier, mais le menu ne montre qu'un seul ✓
  et ne dit pas dans quels formats le reel est déjà sorti.
- **Les cadres par défaut du lot** (`"cadres"`) ne couvrent que les formats pour
  lesquels le manifeste les déclare. Pour les autres, le cadre de départ est
  calculé au ratio de la zone, centré. C'est utilisable, mais un lot régulier
  gagnerait à déclarer ses cadres pour chaque format qu'il utilise.
