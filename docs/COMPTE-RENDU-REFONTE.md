# Compte rendu — refonte UX, 8 octobre 2026

Branche `refonte-ux`. Points réalisés dans l'ordre 2.1, 2.2, 2.3, 2.4, 2.6,
avec un commit par point, puis ce compte rendu. Aucun push. Aucun média, lot,
rendu ou cadrage de test créé dans le dépôt ; aucune dépendance ajoutée.

## Changements

- **2.1** — Une action principale « Valider et envoyer en production », via
  `/enregistrer`, avec état en file/en cours/prêt ou erreur et noms des sorties.
  Aide en infobulle, JSON et titre masqués, copie secondaire. L'export des
  variantes n'apparaît que pour plusieurs départs.
- **2.2** — Sources ajustées à leurs images, grand aperçu à leur droite,
  panneau de validation séparé. Disposition adaptable aux fenêtres réduites.
- **2.3** — Piste unique avec mots et coupes superposés, zoom et défilement,
  départs toujours déplaçables. Commandes regroupées par intention ; raccourcis
  affichés et actifs. Début et fin se calent près des bornes des mots. Navigation
  suivante visible ; passage au suivant manuel (`N`), sans changement automatique.
- **2.4** — Nom du lot, liste des lots du serveur, format masqué s'il est unique,
  ✓ pour les validations envoyées, ○ pour les autres. Ces marques sont conservées
  dans ce navigateur ; elles n'indiquent pas la réussite du rendu.
- **2.6** — Identifiants libres dans le rendu complet, identifiants numériques
  du manifeste acceptés dans le menu. Entrée `/?lot=<nom>`, ressources résolues
  depuis le manifeste, préparation dans `lots/<nom>/`. Compatibilité avec
  `lots/reels.json` et sa clé `production`, sans lien symbolique.
  Options `--mixer-son` et `--deja-synchronisees` : mix utilisé par le proxy,
  la transcription et les deux moteurs de rendu. Cache de préparation invalidé
  si les sources/options changent. Cadres fixes par défaut conservés ; un cadre
  ajusté dans le navigateur est repris. Suivi automatique uniquement sur demande
  explicite du lot (`suivi: true`).

Le rendu brut gère aussi plusieurs départs et remet les cadres à l'échelle des
sources. Le décodage matériel macOS est conservé ; Linux utilise le décodage
logiciel et libx264 pour le rendu brut. `REELS_CADRAGES` permet de placer les
cadrages/journaux hors du dépôt. README actualisé.

## Vérifications effectuées

**PASS — compilation et ouverture après chaque point.**

```bash
python3 -m py_compile outil/*.py scripts/*.py tests/*.py
python3 -m unittest discover -s tests -v
git diff --check
```

Les six tests standard Python passent : entrée et cache, Host GET/HEAD/POST,
Range, chemins hors lot, manifeste historique/liste des lots, sauvegarde sans
rendu et noms du rendu complet. Le test des noms intercepte le montage après
le choix du fichier : ce n'est pas un test de l'habillage.

Chrome headless a ouvert la page avec `exemple/reels.json` après chaque point.
Avant 2.6 : `/outil/index.html?lot=/exemple` ; après : `/?lot=exemple`.
Ce manifeste ne contient pas de médias distribués : son menu et ses formats sont
vérifiés, sa lecture vidéo ne peut pas l'être. Aucune erreur JavaScript lors du
contrôle final via le protocole de débogage Chrome.

**PASS — préparation et rendu brut de bout en bout.**

Deux vidéos de cinq secondes, 640×360, ont été créées avec ffmpeg : `testsrc`
avec sinus 440 Hz et `testsrc2` avec sinus 880 Hz. Toutes les données se trouvent
sous `/tmp/reels-ux-test`, y compris les serveurs de test sur 8876–8878.
Le serveur existant sur 8765 n'a pas été modifié.

```bash
REELS_LOTS=/tmp/reels-ux-test/lots python3 scripts/preparer-reels.py \
  /tmp/reels-ux-test/haut /tmp/reels-ux-test/bas \
  --lot Test --mixer-son --deja-synchronisees
# Même commande avec --lot Second : les deux manifestes coexistent.
```

La préparation, y compris whisper-cli réellement installé, a terminé pour les
deux lots. Le sinus n'étant pas de la parole, les données de timeline du lot Test
ont ensuite été remplacées, hors dépôt, par quatre mots horodatés contrôlés et
un blanc proposé en coupe, afin de vérifier les interactions sans dépendre
d'hallucinations de transcription.

Dans Chrome : proxy lisible, cadres du lot, clic pour garder/recouper le blanc,
`I`, `O`, flèche de lecture, « Sauter les coupes », validation réelle par POST,
marque ✓ et navigation `N` vérifiés. Début 0,44 s, fin 4,06 s, coupe 1,60–2,40 s.
Le serveur a successivement indiqué en cours puis prêt avec le fichier produit.

`ffprobe` confirme **1080×1920**, vidéo **2,833333 s**, audio **2,820000 s**
(attendu 2,82 s, écart vidéo inférieur à une image). Une analyse du son extrait
retrouve 440 et 880 Hz avec des amplitudes comparables, très au-dessus de la
fréquence témoin 1200 Hz : les deux micros sont présents.
Deux variantes réelles sont également produites : **2,833333 s** et **2,266667 s**,
avec les deux noms affichés dans l'état final. Une production via le manifeste
historique `lots/reels.json` a aussi produit son fichier dans son propre dossier.

**PASS — contrôles complémentaires.** Host étranger : 403 en GET, HEAD et POST.
Range `bytes=100-199` : 206 et exactement 100 octets. HTML/JSON : `no-store`.
Tentative de remontée hors du lot : 404. `rendu: false` : sauvegarde sans export.
La phase `monter()` du rendu complet a produit un montage avec mix audio ; pour
ce test unitaire de phase, les cadres ont été exprimés à l'échelle 640×360 des
sources synthétiques. Les noms `P1-03`, `7` et `A/B` sont acceptés et sécurisés.

Captures à 1440×1000, 1280×800 et 768×900 ; « Reel suivant » reste dans la fenêtre,
sans débordement horizontal. Images hors dépôt, dans le dossier Code OS
`skills-verify/refonte-ux-20261008/` ; capture 1280×800 inspectée visuellement.

## Reste / non démontré

- **2.5 reporté** : création de lot par sélecteur macOS et suivi de préparation.
- Pas de vérification sur une conversation réelle : les bornes autour de mots
  contrôlés sont vérifiées, la qualité de transcription et la conservation de
  mots prononcés restent à écouter sur un vrai podcast.
- Habillage complet (sous-titres incrustés, polices, titre) et exécution macOS
  non revalidés de bout en bout. Le test intégral porte sur la production brute.
- Les validations et sessions restent locales au navigateur ; leur statut n'est
  pas synchronisé entre navigateurs. La file de rendu reste en mémoire du serveur.

## Revue Claude — 8 octobre 2026

Revue du diff `origin/main..refonte-ux` (code, sécurité, régressions, lisibilité),
puis passage dans un vrai navigateur sur un lot de test à deux caméras.
Onze commits ajoutés sur la branche, aucun push.

### Corrigé

**Serveur local** (`a3ce0dd`). Le trou principal : caméra, écran, son, décalage
et dossier de sortie étaient repris du corps du POST. Une page ouverte dans le
même navigateur pouvait faire lire `/etc/passwd` ou une URL distante à ffmpeg,
et déposer le rendu n'importe où. Ces champs sont maintenant relus dans le
manifeste du lot, et un reel absent du manifeste est refusé. Avec, dans le même
commit : refus d'un POST venu d'un autre site (`Origin`, `Sec-Fetch-Site`, le
contrôle du `Host` ne suffisait pas), ouvrier de la file qui ne peut plus mourir
en silence, `/lots/reels/<autre lot>/` qui servait les fichiers de tous les lots,
passage non textuel qui coupait la connexion, journal non UTF-8, listage de
dossier, plage `bytes=-8`, 416 sans longueur. Trois tests ajoutés : **9 tests
passent**.

**Rendu brut** (`da71f16`, `9e6f88e`, `6b924d9`). Bornes et coupes calées sur la
grille d'images : mesuré sur 24 i/s et sept coupes, 8,086 s attendues, 8,266 s
avant (+180 ms cumulés), 7,933 s après (+17 ms, qui ne s'accumulent plus).
`fps` posé sur chaque branche image, morceaux de moins de deux images écartés.
Un dossier de sortie relatif se résout depuis `REELS_SORTIE` et non depuis le
répertoire courant : les reels finis atterrissaient à la racine du dépôt public.
Enfin le script dit en français ce qu'il ne sait pas faire, au lieu d'un
traceback dont l'outil n'affiche que la dernière ligne.

**Rendu complet** (`e6632ed`, `9e6f88e`). Les cadres arrivent dans le repère
3840×2160 de l'outil et étaient appliqués tels quels : sur un rush 1920×1080,
ffmpeg répondait « Nothing was written into output file ». Ils sont ramenés à
l'échelle de chaque source, lue par ffprobe. Même correction de dossier de
sortie que ci-dessus.

**Préparation** (`1506069`, `af216a2`). Relancer la préparation d'un lot déjà
préparé plantait sur `KeyError: 'confiance_calage'`, écrasait le nom du lot par
`--lot` (le point 2.4 tombait à la deuxième préparation) et refaisait le mix de
toutes les prises à chaque fois. Le mix lui-même perdait 6 dB : `amix` avec
`normalize=1` divise chaque entrée par leur nombre. Mesuré : −10,4 dB pour un
micro seul, −13,5 dB pour le mix avant, −7,5 dB après (`normalize=0` plus un
limiteur `alimiter=limit=0.89:level=disabled`).

**Interface** (`198eed5`, `cf4db87`, `8b9b1e0`, `c4acdd0`). Chaque panneau prend
la taille de son image, l'aperçu tient exactement le format choisi, la colonne
de droite devient une pile de blocs avec l'envoi en production en tête. Les
commandes du bas sont regroupées par intention avec leur raccourci en `<kbd>`,
l'état du rendu prend une couleur par phase. Les libellés affichés portent leurs
accents. Deux appuis voisins sur « Début ici » tombaient sur la même image
après calage, et le rendu encodait deux fois le même montage sous
« (debut 2) » et « (debut 3) » : l'outil le dit au lieu d'ajouter le doublon.
Le bouton d'envoi redevenait cliquable dès la réponse du serveur, alors que
l'encodage commençait : il affiche maintenant « Rendu en cours… » jusqu'au bout.

### Vérifié, et comment

**Lot de test à deux caméras, hors dépôt.** Deux sources `testsrc2` + `sine`
de 30 s dans `/tmp/lot-test`, préparées par `scripts/preparer-reels.py`.
Whisper hallucine sur des bips : les données de timeline (33 mots, 5 coupes,
4 blancs) ont été **écrites à la main**, hors dépôt, pour que les bornes et les
coupes soient contrôlées. Deux prises supplémentaires ont été ajoutées au
manifeste de test, par copie du même proxy, pour voir les ✓ et les ○ du menu.

**Navigateur réel.** Chrome du service `chrome-dev`, piloté en Node par le
protocole DevTools (`~/outils-captures/`, hors dépôt), fenêtre 1600×1000.
Scénario complet joué : `I` à 5,2 s se cale sur 4,98 s, `O` à 18,4 s sur
18,81 s, clic sur une coupe pour la garder ou la retirer, « Poser un cadrage
ici », récapitulatif de la colonne de droite, puis envoi réel en production.
L'état est passé *en file* → *en cours* (avec le nom du fichier et le nombre de
morceaux) → *prêt* avec les chemins produits ; l'en-tête est passé à
« Validés 1 / 3 » et le menu a pris son ✓. Aucune erreur JavaScript.

**Fichiers produits.** `ffprobe` sur les trois départs : **1080×1920**,
14,250 s / 10,483 s / 10,483 s pour 14,2 / 10,5 / 10,5 s annoncés dans l'outil.
Tous écrits dans `/tmp/lot-test/rendus/Lot test/`, **rien dans le dépôt**
(`git status` propre en dehors des fichiers modifiés volontairement).

**Sécurité.** Chaque brèche a été prouvée fermée par `curl` contre un serveur
de test sur le port 8891, lancé sur `/tmp/lot-test`. Le serveur d'une autre
session (port 8765) n'a pas été touché. Les fichiers de preuve posés dans
`/tmp/lot-test` ont été retirés ensuite.

**Captures.** Dix PNG 1600×1000 dans `~/projets/outil-reels-captures/`, hors
dépôt, prises sur le lot de test chargé. Chacune montre la fenêtre entière
assombrie avec la zone concernée en avant. Pour `08-reels-valides-coches`, le
menu des reels — un `<select>` — a été déplié en liste le temps de la capture ;
les ✓ et ○ sont bien ceux que l'outil écrit.

### Ce qui reste

- **2.5 toujours reporté** : création de lot par sélecteur macOS et suivi de
  préparation.
- **`suivi: true` ne suit rien.** Aucun script ne produit de données `suivi` et
  aucun des deux moteurs de rendu ne les lit. Si un lot active l'option et
  qu'on écrit les données à la main, l'aperçu du navigateur bougera mais le
  rendu restera au cadre fixe : l'aperçu mentirait. Les lignes « Suivi
  automatique uniquement sur demande explicite du lot » plus haut dans ce
  compte rendu laissent croire à une option utilisable ; elle ne l'est pas.
- **Les anciens rendus s'accumulent.** Le rendu complet effaçait les
  `<reel> - *.mp4` du dossier de sortie avant d'écrire ; la refonte a retiré
  cet effacement. C'est plus sûr — un `glob` suivi d'`unlink` dans un dossier
  choisi par l'utilisateur est dangereux — mais changer le titre d'un reel
  laisse désormais l'ancien fichier à côté du nouveau. À trancher.
- **Habillage complet et macOS** : sous-titres incrustés, polices, titre et
  décodage matériel ne sont toujours pas revalidés de bout en bout. Le test
  intégral porte sur la production brute.
- **Pas de vérification sur une vraie conversation** : la transcription et la
  conservation des mots prononcés restent à écouter sur un vrai podcast.
