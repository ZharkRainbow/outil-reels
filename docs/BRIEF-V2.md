# Brief V2 : l outil de reels devient l outil de montage du quotidien

Rédigé le 08/10/2026 d après les retours de Lucas sur la refonte UX (branche refonte-ux).
Point de départ : la branche refonte-v2 (= refonte-ux). Lire d abord README.md,
docs/BRIEF-REFONTE-UX.md et docs/COMPTE-RENDU-REFONTE.md.

## Ce que Lucas valide et qu il faut garder
- La colonne de droite : « Cadrages posés » et « Ce qui part en production » (début, fin, durée,
  coupes, fichiers, dossier). « Très cool », à garder tel quel.
- L aperçu du rendu à côté des cadres, la barre du haut (lot, reels validés cochés, compteur).
- Le cadre fixe par défaut, sans suivi de visage. La production brute par lot (produire-split.py).
- Toutes les protections du serveur ajoutées par la revue Claude.

## 1. La timeline : reprendre celle de l Atelier
Lucas préfère nettement la timeline de l autre outil (l Atelier, gros studio local à plusieurs pages).
Référence complète, hors dépôt : ~/projets/references/atelier/
  - images/selection.png : la timeline à imiter ; images/*.png : l Atelier en entier
  - static/editor/selection/trimmer.js, trim-edit.js, rails.js, playback.js : son code de timeline
  - timeline.py : forme d onde et détection des blancs côté serveur
Ce qu il faut :
- une vraie timeline avec forme d onde, un CURSEUR de lecture qu on attrape et déplace à la souris,
  un clic n importe où sur la piste pour s y placer, un zoom à la molette / au trackpad ;
- les mots transcrits et les coupes sur la même piste (garder ce qui marche déjà) ;
- un bouton « Supprimer les blancs » qui coupe tous les blancs proposés en un clic, et son inverse
  « Tout garder » ; chaque blanc reste réglable un par un ;
- les départs (D1, D2…) et la fin restent visibles et déplaçables sur la piste.
Le code de l Atelier n est pas sous licence publique dans ce dépôt : le réécrire ici (même auteur,
Lucas), sans copier de dépendance ni de build.

## 2. « Reel suivant » = valider
Aujourd hui « Valider et envoyer en production » et « Reel suivant » font doublon.
- Un seul geste : « Reel suivant » enregistre le cadrage, envoie le reel en production et ouvre le
  reel suivant (raccourci N). Le reel passe en ✓ dans le menu.
- Garder un moyen de naviguer SANS valider (flèche discrète « passer sans valider ») et « reel
  précédent ».
- Le suivi de production reste visible dans la colonne de droite pour chaque reel envoyé.

## 3. Les formats : ne plus être bloqué en 50/50
Sélecteur de format toujours visible pour un lot à deux caméras, comme l ancienne version :
« Vertical 50/50 », « Vertical 80/20 » (à ajouter : haut 80 %, bas 20 %), « Vertical 70/30 »,
« Horizontal » (hmc), « Horizontal 50/50 » (h5050), « Vertical consulting » (vcons).
- Par défaut tous les formats deux caméras sont proposés ; le manifeste peut restreindre (« formats »).
- Chaque format garde ses propres cadres (un cadrage posé en 50/50 ne s applique pas en 80/20) ;
  les cadres par défaut du lot (« cadres ») restent appliqués à chaque format qu ils couvrent.
- scripts/produire-split.py doit rendre TOUS ces formats (géométrie lue dans une table partagée,
  pas dupliquée entre la page et le script) ; le nom du fichier porte le format.
- Un même reel peut être produit dans plusieurs formats.

## 4. Une interface plus agréable : s inspirer de HyperFrames Studio
HyperFrames (npm « hyperframes », Apache-2.0) a une belle interface locale de prévisualisation.
Installe-le hors du dépôt (~/outils-hf), lance son studio / preview sur une composition d exemple,
regarde-le dans Chrome headless (captures) et inspire-toi de sa mise en page : lecteur central,
timeline en bas, inspecteur à droite, typographie, densité, états. Inspiration visuelle uniquement,
pas de dépendance ajoutée à l outil. Sombre, sobre, lisible, en français.

## 5. Contraintes (inchangées)
Sans build, sans framework, Python standard. Dépôt public : aucune donnée réelle. Serveur local
uniquement. Fichiers lisibles. Vérification en conditions réelles : lot de test deux caméras
fabriqué avec ffmpeg dans /tmp, chaque format produit et contrôlé (dimensions, durée, son).
