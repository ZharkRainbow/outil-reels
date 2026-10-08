# Compte rendu — brief V3, 8 octobre 2026

Branche `refonte-v3`, partie de `refonte-v2`. Points 1 à 3 du brief V3, un
commit par sujet, puis ce compte rendu. **Aucun push.** Aucun média, lot, rendu,
cadrage ni `.cube` dans le dépôt : tout le matériel de vérification vit dans
`/tmp` et dans `~/projets/references`. Aucune dépendance ajoutée, aucun build,
Python standard.

| commit    | sujet                                                          |
|-----------|-----------------------------------------------------------------|
| `15994dd` | Brief V3 : le document de référence                              |
| `fa3ad2d` | 2 — Étalonnage : la table des trois choix, la détection, la LUT au rendu |
| `95ed48e` | 2 — Étalonnage : les routes que la page interroge                |
| `1d3b7a0` | 1·2·3 — La timeline de l'Atelier, l'étalonnage et le titre dans la page |
| `20f730f` | Mode d'emploi                                                    |

Les points 1, 2 et 3 tombent tous les trois dans `outil/index.html`, d'où un
seul commit pour la page. Le reste est découpé par sujet.

---

## 1. La timeline

Modèle : `~/projets/references/atelier/images/selection-lucas-2026-10-08.png`.
Ce qui changeait tout, et qui est fait : **la piste passe de 104 à 64 px et la
forme d'onde la remplit d'un bord à l'autre**. La V2 réservait 15 px en haut
pour la règle du temps et 27 px en bas pour les mots ; ces 42 px étaient le vrai
écart avec le modèle, plus que les couleurs.

- **Les mots quittent la piste** pour un onglet **Transcript**, à côté de
  **Aperçu**, comme dans l'Atelier. Un clic sur un mot s'y place, le mot en
  cours de lecture se surligne, et ceux que le montage retire sont barrés.
- **La règle du temps ne sort qu'une fois zoomé**, posée par-dessus l'onde en
  traits fins avec une pastille d'heure. Au repos, la piste est nue. Le zoom à
  la molette est une invention de la V2 que l'Atelier n'a pas ; il reste, mais
  il ne coûte plus rien à l'état de repos.
- **Deux poignées en capsule ambre de 16 px**, posées *de part et d'autre* de
  la borne et jamais dessus : viser un trait de 2 px est injouable, viser
  16 × 68 px ne demande rien. Le vert et le rouge de la V2 disparaissent — les
  libellés **DÉBUT** et **FIN** sous la piste disent déjà lequel est lequel, et
  la page n'a qu'un seul accent. La valeur n'est plus écrite sur la poignée :
  un seul endroit par valeur, le pied de la piste.
- **Hors bornes, plus de hachure** : la forme d'onde descend à 23 % de son
  intensité, exactement comme l'Atelier. On voit le rush avant et après, on voit
  qu'il ne sortira pas, et la piste reste lisible. La hachure sombre de la V2
  noyait tout ce qui dépassait.
- **Les blancs supprimés** restent hachurés de rouge dans la piste, chacun
  réglable par ses deux bords, un clic pour le garder ou le couper.
- **La ligne de transport** : bouton rond, `00:00.0 / 00:21.4` (deux chiffres
  aux minutes, comme l'Atelier), l'aide « Espace lecture · I / O fixer début /
  fin », puis à droite le segment **Léger · Normal · Serré**,
  **✂ Supprimer les blancs**, et le lien **Rétablir** — qui ne s'affiche que
  s'il a quelque chose à remettre.
- **Sous la piste** : `DÉBUT « ‹ 00:00.3 › »` à gauche, `Rush 00:00 → 00:21` au
  centre, `FIN « ‹ 00:17.1 › »` à droite. Sauts de 0,1 s (`‹ ›`) et 0,5 s
  (`« »`).
- **Les départs multiples restent là.** `D1`, `D2` n'apparaissent sur les
  poignées que s'il y en a plusieurs, et la ligne de pastilles sous la piste ne
  revient qu'alors : avec un seul départ, elle répétait ce que le pied dit déjà.

Les commandes que la ligne de transport a rendues (−10 s, −1 s, +1 s, +10 s,
« Tout voir », « Sauter les coupes ») sont descendues dans le groupe
**Navigation**, en bas. L'Atelier n'en a aucune ; elles servent, mais pas sur
cette ligne-là.

**La sensibilité.** Dans l'Atelier, Léger / Normal / Serré ne change qu'une
chose : la durée minimale d'une pause coupée. Le seuil en décibels, lui, est
commun et déjà appliqué en amont. C'est repris tel quel — 0,50 / 0,35 / 0,25 s
— et appliqué côté page sur la liste `blancs` que `preparer-reels.py` écrit déjà
(toute pause ≥ 0,25 s), avec les mêmes marges que le script : 0,12 s après le
dernier mot, 0,10 s avant le suivant. `BLANC_COUPE` ne sert donc plus à la page.

## 2. L'étalonnage

Trois choix sous chaque caméra, pas un de plus, nourris par
`scripts/etalonnages.json` — la même table que lit `produire-split.py`, servie
telle quelle sur `/etalonnages.json`. Un fichier absent est annoncé **dans le
menu**, au chargement de la page.

Sous le menu, la mesure du rush et l'image de contrôle :

- `scripts/etalonnage.py` prend cinq images réparties dans le rush, les passe à
  `signalstats`, prend la médiane de `YLOW` / `YHIGH` / `SATAVG`, normalise selon
  la profondeur de bits, et écarte les images noires. Les seuils viennent de
  `grading.py` de l'Atelier, mesurés sur de vrais rushes.
- La phrase est celle de l'Atelier : « Log détecté · blancs 134 · saturation
  2.9 », avec « · à vérifier » quand la mesure est en bordure.
- La suggestion suit : Log → *Délog*, Rec.709 → *Aucun*. **Elle ne s'impose
  jamais à un choix déjà enregistré.** Quand la mesure échoue, on ne devine
  pas : *Aucun*, et la phrase le dit.
- L'image de contrôle est une image fixe calculée par `ffmpeg lut3d`, prise à un
  cinquième du rush — le tout début est souvent un claquement de mains ou une
  mire, qui ne dit rien de l'étalonnage de la scène. On appuie dessus pour voir
  le rush sans la LUT.

Au rendu, `produire-split.py` pose la LUT **avant le recadrage** : une LUT
travaille sur l'image entière, et la poser après le crop donnerait un résultat
différent de l'aperçu. En 10 bits, un `format=gbrp10le` passe devant.

**Deux choses coûteuses, donc mises en cache.** Une mesure vaut cinq appels à
ffmpeg, une image un seul. Sur deux cœurs, changer de reel et revenir relancerait
tout. La clé du cache porte le chemin, la date et la taille du fichier : un rush
remplacé est remesuré.

**Deux points de sécurité**, sur le modèle de ce qui protège déjà
l'enregistrement. Le chemin du rush ne vient **jamais** de la requête : la page
nomme un lot, un reel et une caméra, et `rush_du_reel()` va chercher le fichier
dans le manifeste. Et l'étalonnage ne voyage qu'en **clé de la table**, vérifiée
à l'entrée du POST comme de la requête : un nom de `.cube` venu du réseau n'a
rien à faire dans une ligne de commande ffmpeg.

**Les LUT ne sont pas dans le dépôt**, qui est public. `REELS_LUTS` dans
`reglages.py`, défaut `~/luts` ; pour les essais, `~/projets/references/luts`.
`reglages.manquants()` signale le dossier absent et chaque `.cube` manquant.

## 3. Le titre

Champ **Titre** éditable en tête de la colonne de droite, pré-rempli par le
titre proposé dans le manifeste du lot. Il part avec le cadrage et nomme le
fichier produit — c'était déjà le cas, mais le champ était `type="hidden"` et
personne ne pouvait le corriger.

Dessous, **position du titre** : haut / milieu / aucune. Enregistrée avec le
cadrage et transmise au rendu, **rien n'est incrusté** : c'est pour l'habillage
à venir. Le serveur refuse toute autre valeur.

---

## Comment c'est vérifié

### Le lot de test

`/tmp/lot-v3`, fabriqué par deux scripts jetables (`faire-sources.py`,
`faire-lot.py`) : trois prises de 21 s, deux caméras chacune, 1920 × 1080,
mire + bruit modulé, assemblées en proxys côte à côte par les vraies fonctions
de `preparer-reels.py`. **La prise 2 est tournée « en Log »** : saturation 0,07,
contraste 0,90, niveaux de sortie ramenés entre 0,22 et 0,60 — il faut aller
aussi loin, sinon la détection a raison de répondre Rec.709 (voir plus bas).

Les mots du lot sont **synthétisés**, pas transcrits. Ce n'est pas que
`whisper-cli` manque — il est installé, modèle compris — c'est que l'audio du
lot est du bruit modulé : whisper n'en tirerait rien d'utilisable. Les mots
`mot1`, `mot2`… suffisent pour vérifier l'onglet Transcript, le calage des
départs et le barré des mots coupés.

### PASS — compilation et tests

```
python3 -c "import ast; ast.parse(open('outil/serveur.py').read())"   ok
node --check  (bloc <script> de index.html extrait)                   ok
python3 -m pytest tests/ -q                                           17 passed
```

Cinq règles pures s'ajoutent au bloc `REGLES` de la page, rejouées **sans
navigateur** par `tests/test_refonte.py` : les trois niveaux de blancs et leurs
marges, l'étalonnage proposé, et le seuil au-delà duquel la règle de temps sort.

**Une s'est fait prendre à l'essai.** `10.6 - 10.25` vaut `0.34999999999999964`,
et une pause de 0,35 s échappait au niveau qui la vise : Léger et Normal
donnaient exactement la même liste. Les durées se comparent maintenant en
millisecondes entières. Sans le passage en navigateur, le bogue serait passé.

### PASS — la détection sur le lot de test

| rush       | mesure                                        | proposé |
|------------|-----------------------------------------------|---------|
| camera-1   | Rec.709 détecté · blancs 219 · saturation 131.1 | Aucun   |
| ecran-1    | Rec.709 détecté · blancs 185 · saturation 69.2  | Aucun   |
| camera-2   | Log détecté · blancs 134 · saturation 2.9       | Délog   |
| ecran-2    | Log détecté · blancs 123 · saturation 1.8       | Délog   |

Au premier essai, les six rushes répondaient Rec.709, **y compris celui qui
était censé être en Log** : la prise « log » du lot sortait à saturation 24,9,
là où de vrais rushes D-Log M mesurent 2 à 3,5. La détection avait raison, c'est
le matériel d'essai qui était faux. Prise 2 refabriquée, 24 s d'encodage, et les
quatre lignes ci-dessus.

### PASS — la timeline dans un vrai navigateur

Chrome headless via `dev-browser`, sur `http://localhost:8793/?lot=V3`.

- piste : **64 px**, 0 mot dessus, 0 graduation au repos, 2 poignées ;
- horloge `00:00.0 / 00:21.4`, pied `00:00.0` / `Rush 00:00 → 00:21` / `00:21.4` ;
- **glisser la poignée de début** à 25 % de la piste → `00:05.3` ;
  **glisser celle de fin** à 80 % → `00:17.1`. Capture faite : la zone gardée
  est encadrée d'ambre, l'onde hors bornes reste visible et atténuée ;
- **Léger 6 blancs · Normal 7 · Serré 9** — trois états visiblement différents ;
- **✂ Supprimer les blancs** → 7 actives, « 00:09.2 à l'arrivée », le lien
  **Rétablir** apparaît ; **Rétablir** → 0 active, le lien disparaît ;
- onglet **Transcript** : 41 mots, 17 barrés, clic sur un mot → la tête de
  lecture passe à `00:07.0` ; retour sur **Aperçu**, l'image revient.
- aucune erreur JavaScript, aucune requête en échec.

Un défaut trouvé là et nulle part ailleurs : `display:flex` sur `.stage` bat
l'attribut `hidden`, et l'onglet Transcript s'ouvrait **par-dessus** l'aperçu au
lieu de prendre sa place. Une ligne de CSS.

### PASS — l'étalonnage dans la page

Reel 2 ouvert : les deux menus passent d'eux-mêmes sur **Délog · Log M →
Rec.709**, les deux lignes de diagnostic s'affichent, les deux images de
contrôle sont calculées. Le choix forcé à la main sur un autre reel est
retrouvé après rechargement de la page, et la suggestion ne l'écrase pas.

Effet mesuré de la LUT sur une image extraite par le serveur (camera-2) :

| choix    | YAVG  | YHIGH | saturation |
|----------|-------|-------|------------|
| Aucun    | 106.4 | 138   | 3.9        |
| Cinestyle| 85.1  | 119   | 5.0        |
| Délog    | 93.9  | 138   | **12.1**   |

### PASS — les reels réellement produits

Quatre rendus lancés par `produire-split.py`, un par étalonnage, sur le lot de
test, depuis des cadrages **exportés par la page** (donc avec leur titre, leur
position de titre, leurs coupes et leur étalonnage) :

```
1 - Pourquoi personne ne clique - sans LUT - vertical 50-50.mp4    6 morceaux,  9.2 s  — 10 s
1 - Pourquoi personne ne clique - Cinestyle - vertical 50-50.mp4   6 morceaux,  9.2 s  — 21 s
2 - La seule metrique - sans LUT - vertical 50-50.mp4              8 morceaux, 15.7 s  — 13 s
2 - La seule metrique - delog - vertical 50-50.mp4                 8 morceaux, 15.7 s  — 47 s
```

Tous en 1080 × 1920. Le nom du fichier porte le titre saisi dans la page. La
ligne de journal dit l'étalonnage appliqué, par source.

Contrôle visuel sur une image extraite du reel 2, sans LUT puis délogué :
la version sans LUT est presque monochrome, la version déloguée a des couleurs
et des noirs plus bas.

| reel 2  | YAVG  | YLOW | YHIGH | saturation |
|---------|-------|------|-------|------------|
| Aucun   | 102.6 | 75   | 133   | 2.5        |
| Délog   | 89.8  | 56   | 133   | **8.7**    |

La LUT va donc de bout en bout : détection → menu → image de contrôle → rendu.

---

## Ce qui reste, et ce qui est volontairement laissé de côté

- **Le titre n'est pas incrusté.** Le brief le demande explicitement : le champ
  *position* est là, enregistré et transmis, l'incrustation viendra avec
  l'habillage.
- **Pas de règle pure pour le nom de fichier.** `produire-split.py` nettoie le
  titre avec `re.sub(r"[^\w\s'-]", "", …)` ; le `\w` de Python connaît les
  accents, celui de JavaScript non. Une règle « partagée » aurait divergé sur le
  premier titre accentué. Le nettoyage reste côté Python, seul.
- **La prise 3 du lot de test n'a pas été rendue.** Elle est en Rec.709 comme la
  prise 1 et n'aurait rien montré de plus.
- **Les mots du lot sont synthétiques** (voir plus haut). L'onglet Transcript
  n'a donc pas été vu sur de la vraie parole.
- **L'onglet Transcript ne montre pas les propositions de passages** que
  l'Atelier affiche dans sa colonne de gauche : hors brief.
- `reperer-visage` n'est toujours pas compilé sur cette machine ;
  `reglages.manquants()` le signale, comme avant.

## Pour rejouer la vérification

```bash
export REELS_LOTS=/tmp/lot-v3/lots
export REELS_SORTIE=/tmp/lot-v3/rendus
export REELS_LUTS="$HOME/projets/references/luts"
python3 outil/serveur.py           # puis http://localhost:8765/?lot=V3
```

Le lot de test se refabrique avec `/tmp/lot-v3/faire-sources.py` puis
`/tmp/lot-v3/faire-lot.py` — environ deux minutes sur cette machine. Les deux
scripts sont volontairement hors dépôt : ils ne servent qu'à l'essai.
