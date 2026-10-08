# Brief : refonte UX de l'outil de reels

Brief rédigé le 08/10/2026 après une vraie session de production : 10 reels tirés
d'un podcast à deux caméras, validés et rendus avec cet outil. **L'outil marche et
reste l'outil principal des prochains jours** : c'est le plus rapide et le plus
simple. Le but n'est pas de le réécrire, mais de le rendre propre à utiliser.

À lire avant de toucher au code : `README.md`, puis ce fichier.

---

## 1. Ce qu'il faut garder tel quel

- **La simplicité.** Un fichier `outil/index.html` sans build, un `outil/serveur.py`
  en Python standard. Pas de framework, pas de dépendance ajoutée.
- **La timeline avec les mots transcrits** sous la piste, et les **blancs proposés
  en coupe** (rouge) qu'un clic garde ou retire. C'est la fonction la plus utile.
- **Le point de départ (« Début ici »)** qui se recale sur le début d'un mot.
- **« Sauter les coupes »** pour écouter le montage final.
- **Le rendu brut par lot** : quand `lots/reels.json` contient
  `"production": {"script": "produire-split.py", "sortie": "<dossier>"}`, le bouton
  d'enregistrement rend le reel sans habillage (cadre fixe, départ, fin, coupes) et le
  dépose dans le dossier. Sans cette clé, l'ancien rendu complet (`rendre-reel.py`)
  s'applique.
- **Pas de suivi de visage par défaut.** Le cadre est fixe. Un lot peut fixer ses cadres
  par défaut : `"cadres": {"vmc_haut": {...}, "vmc": {...}}`.

## 2. Ce qu'il faut corriger, par ordre de priorité

### 2.1 Colonne de droite : la vider de ce qui ne sert pas
Aujourd'hui, elle empile un texte d'aide de 4 lignes, « Titre du bandeau », « Exporter (un
fichier par début) », un bloc JSON brut, « Enregistrer le cadrage » et « ou copier le JSON ».

À la place :
- **Cadrages posés** : la liste, courte.
- **Un bouton principal unique** : « **Valider et envoyer en production** ». Il fait ce que fait
  aujourd'hui « Enregistrer le cadrage » (POST `/enregistrer`, qui lance le rendu). Le libellé doit
  dire clairement que le reel part en production. Ensuite, afficher l'état du rendu sous le bouton
  (en file, en cours, prêt) avec le nom du fichier produit.
- **« Copier le JSON »** en lien secondaire discret.
- **À supprimer de l'écran** : le texte d'aide (le passer en infobulle « ? »), le champ « Titre du
  bandeau » (inutile tant qu'il n'y a pas d'habillage) et le bloc JSON affiché.
- « Exporter (un fichier par début) » : à garder seulement si le reel a plusieurs départs.

### 2.2 Les deux zones de cadrage : supprimer le noir perdu
Les deux panneaux « Haut » et « Bas » prennent toute la largeur, alors que l'image n'en occupe
qu'un tiers à gauche. Les deux tiers de droite sont noirs.
- Mettre l'**aperçu du rendu final (9:16)** à droite des deux panneaux, en grand.
- Ou dimensionner les panneaux à la taille réelle de l'image.
- Objectif : l'écran sert à voir l'image, pas du noir.

### 2.3 Barre du bas : deux rangées peu lisibles
Ce qu'il y a aujourd'hui :
- deux pistes empilées (coupes, puis mots) ;
- la ligne « Débuts » ;
- les boutons `Lecture`, `-10s`, `-1s`, `+1s`, `+10s` et « Sauter les coupes » ;
- à droite, « + Début ici », « Fin ici », « Couper ici », « Poser un cadrage ici », « Corriger ce
  point », « point précédent / suivant », puis (ajouté le 08/10) « ‹ reel précédent » et
  « Reel suivant › ».

Ce qu'il faut :
- **Grouper par intention** : lecture, bornes (début, fin, couper), cadrage, navigation.
- **Une seule piste** plus haute, avec les mots et les coupes superposés.
- **Les raccourcis clavier affichés** : `Espace`, `←` `→`, `I` début, `O` fin, `C` couper, `N` reel suivant.
- **« Reel suivant » toujours visible et en évidence** : c'est l'action la plus fréquente une fois
  un reel validé. Idéalement, valider un reel passe automatiquement au suivant.

### 2.4 Barre du haut
Elle contient un bouton bleu vide (le sélecteur de lot, qui n'affiche pas son nom), « Vertical
50/50 » (seul format du lot) et le menu des reels.
- Afficher le **nom du lot** dans le sélecteur.
- Masquer le choix de format quand le lot n'en propose qu'un.
- Dans le menu des reels, **marquer ceux déjà validés** (✓) et ceux qui restent.

### 2.5 Ouvrir ses fichiers depuis l'interface
Aujourd'hui, il faut préparer un lot en ligne de commande (`scripts/preparer-reels.py`) avant de
pouvoir travailler. Il faut un bouton « **Nouveau lot** » qui :
1. demande les deux dossiers ou fichiers (caméra du haut, caméra du bas), avec un sélecteur de
   fichiers macOS lancé côté serveur via `osascript` ;
2. lance `preparer-reels.py` en tâche de fond et affiche l'avancement ;
3. ouvre le lot quand il est prêt.

### 2.6 Bugs et dettes relevés pendant la session
- **Identifiants non numériques** : `rendre-reel.py` fait `int(d['reel'])` et plante sur un
  identifiant comme `P1-03`. Accepter n'importe quel identifiant.
- **Chemins du lot** : la page charge `<lot>/reels.json`, puis les données par un chemin relatif
  `reels/<id>.json`. Il a fallu créer un lien `outil/reels -> ../lots` pour que ça marche. Le
  lien ouvert par `Ouvrir l'outil.command` (`http://localhost:8765`) tombe sur une liste de
  fichiers, pas sur l'outil. Unifier : un seul point d'entrée, `/?lot=<nom>`, un sous-dossier
  par lot dans `lots/` (comme le prévoit `exemple/reels.json`).
- **Un seul manifeste** : `preparer-reels.py` écrit `lots/reels.json` pour tous les lots.
  Préparer un deuxième lot écrase le premier. Il faut un dossier par lot.
- **Son à deux micros** : la transcription et le son du rendu viennent uniquement de la caméra du
  haut. Sur un podcast, la voix de l'invité était muette tant qu'on n'avait pas mixé les deux micros
  dans la piste du haut à la préparation. À faire dans `preparer-reels.py` (option `--mixer-son`).
- **Calage audio** : `caler-flux.py` cale les deux caméras par corrélation du son. Sur deux micros
  différents, il peut se tromper. Prévoir une option « déjà synchronisées » (décalage 0).
- **Cache** : réglé le 08/10 (`no-store` sur tout `.html` et `.json`), à garder.

## 3. Contraintes

- Rester sans build, en HTML/JS/Python standard, avec des fichiers lisibles.
- Rien ne sort de la machine. Le serveur n'écoute que `127.0.0.1` et refuse tout `Host` qui n'est
  pas `localhost` ou `127.0.0.1` (protection contre le DNS rebinding, ajoutée le 08/10).
- Le dépôt GitHub est **public** : ne jamais y mettre de rushes, de lots, de rendus, de cadrages
  ni de vocabulaire (voir `.gitignore`).
- Toute modification se vérifie en conditions réelles : préparer un lot à deux caméras, valider
  un reel, contrôler le fichier rendu (durée, 1080×1920, début et fin sur des mots entiers).

## 4. Livrable attendu

Une branche avec les points 2.1 à 2.4 et 2.6, testés. Le point 2.5 peut venir dans un second temps.
Un court compte rendu : ce qui a changé, ce qui a été testé, ce qui reste.
