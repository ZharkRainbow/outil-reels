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
