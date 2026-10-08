# Audit V2 — branche `refonte-v2`

8 octobre 2026. Base examinée : `refonte-ux..refonte-v2` (11 fichiers, 1 261 lignes ajoutées, 325 retirées). Lecture de `README.md`, des deux briefs, des deux comptes rendus, de l'intégralité du diff et des chemins d'exécution concernés. Aucun code modifié. Tous les médias, manifestes, cadrages et rendus de cet audit sont sous `/tmp/audit-v2-gpt6`.

## Verdict par exigence

| Exigence | Verdict et preuve |
|---|---|
| Timeline : forme d'onde, curseur, clic, zoom, mots et coupes | **PASS** pour l'affichage, le curseur et le zoom : Chrome sur le lot synthétique charge 150 pics et 3 mots ; clic physique à 60 % → 1,800 s, glisser à 25 % → 0,751 s ; zoom de 0–3 s à 0,790–2,207 s. Le trackpad réel n'est **pas prouvé** par cet audit. |
| Blancs en masse, réglage individuel, départs et fin | **ÉCHEC partiel** : les poignées et les deux bords de coupe sont présents ; « Supprimer les blancs » active aussi les coupes manuelles (constat 2). Les départs et la fin sont rendus par `bornes()` ; leur glissement physique n'a pas été rejoué ici. |
| « Reel suivant » valide, `N`, navigation libre, ✓ et suivi | **PASS** pour l'envoi et la navigation : POST réel de T1 en 80/20, passage à T2, menu `✓ Test 1 / ○ Test 2`, compteur `1 / 2`, suivi `En file` puis `Prêt`, MP4 présent. Le suivi par format et après rechargement reste incomplet (constat 5). |
| Formats proposés, cadres distincts, table partagée, plusieurs sorties | **PASS en production brute** : huit formats à deux caméras visibles ; dix formats encodés pour `AUDIT-01`, fichiers distincts, dimensions et durées exactes. **ÉCHEC pour le rendu complet** : `v8020` plante (constat 1). Collision de cadrages avec les identifiants longs (constat 3). |
| Interface et acquis de Lucas | **PASS visuel limité** : capture Chrome 1440×900, pas de défilement horizontal ; sources, aperçu 1080×1920 et inspecteur de 300 px côte à côte ; colonne « Cadrages posés » et « Ce qui part en production » conservée. Le cadre fixe et le rendu brut fonctionnent sur le lot. L'aperçu peut diverger du rendu brut si plusieurs points sont posés (constat 4). |
| Contraintes, protections locales, lisibilité | **PASS partiel** : sans build ni nouvelle dépendance ; écoute sur `127.0.0.1`, Host et Origin étrangers refusés, traversée de chemin refusée, chemins de production repris du manifeste. La table unique ne couvre pas le moteur complet (constat 1) et aucun test n'a été ajouté pour V2 (constat 6). |

La capture de contrôle est conservée hors du dépôt : `/home/lucas/.local/share/code-os/files/skills-verify/audit-v2-gpt6/F01.png` (1440×900, lot synthétique uniquement).

## Constats, du plus grave au moins grave

### 1. P1 — Les nouveaux formats échouent sur le rendu complet

**Preuve.** `outil/serveur.py:62-76` choisit `rendre-reel.py` dès que le manifeste ne déclare pas `production`. La page propose pourtant les nouveaux formats par défaut. `scripts/rendre-reel.py:42-54` conserve ses propres tables `FORMATS` et `DOSSIERS`, limitées à `vmc`, `hmc`, `hsolo`, `carre`, alors que `scripts/formats.json` en définit dix. Commande réellement lancée :

```text
python3 scripts/rendre-reel.py /tmp/audit-v2-gpt6/json/v8020.json
code=1
KeyError: 'v8020'
  scripts/rendre-reel.py, ligne 359 : dossier = racine / DOSSIERS[format_]
```

La « table partagée par les trois côtés » du compte rendu ne couvre donc pas le moteur appelé par défaut. La définition de `carre` diverge aussi : 1080×1080 dans `formats.json`, toile 1080×1920 dans `rendre-reel.py`. Le sous-script `rendre-depuis-points.py` refuse explicitement `hsolo` et `carre` (`code=1`, « attend deux zones »), ce que le compte rendu signale déjà.

**Correctif proposé.** Faire lire `formats.json` à `rendre-reel.py` pour les dimensions, zones, dossier et habillage ; définir les gabarits manquants, ou limiter la sélection UI aux formats réellement pris en charge par le moteur du lot. Tester chaque format par le chemin serveur normal, pas seulement par `produire-split.py` appelé directement.

### 2. P1 — « Supprimer les blancs » supprime aussi une coupe manuelle conservée

**Preuve.** Sur Chrome, les données de T1 contiennent un blanc et une coupe manuelle, tous deux désactivés. Résultat observé :

```text
avant                         [["blanc",false],["manuel",false]]
clic « Supprimer les blancs »  [["blanc",true], ["manuel",true]]
clic « Tout garder »           [["blanc",false],["manuel",false]]
```

`outil/index.html:639` fait `coupes.forEach(c=>c.on=true)` sans regarder `c.type`. Le bouton promet seulement de couper les blancs proposés. Un clic peut donc retirer du rendu un passage coupé manuellement puis volontairement rétabli.

**Correctif proposé.** N'activer que les coupes de type `blanc` (et préciser séparément le sort des propositions `reprise`). Garder l'état des coupes manuelles. Ajouter un test de geste avec un blanc et une coupe manuelle dans des états opposés.

### 3. P2 — Deux formats du même reel peuvent écraser le même cadrage serveur

**Preuve.** `outil/serveur.py:193-199` ajoute le format après l'identifiant, puis tronque le nom à 60 caractères. Un reel à identifiant de 60 `X` dans le lot de test `Long` a renvoyé le même fichier pour deux POST successifs :

```text
POST format=vmc    → 200, Long XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.json
POST format=v8020  → 200, Long XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.json
```

Le second POST remplace le premier JSON. Si le premier rendu tourne encore, le nom commun provoque aussi un `409` « déjà dans la file ». Le nom du MP4 dans `produire-split.py` porte bien le format ; cette collision se produit avant le rendu, dans la sauvegarde et le suivi serveur.

**Correctif proposé.** Réserver le suffixe de format avant toute troncature et ajouter un identifiant stable ou une empreinte courte du couple `(lot, reel, format)` aux noms internes. Tester deux formats sur un identifiant long, dont deux envois rapprochés.

### 4. P2 — L'aperçu peut montrer un cadrage qui ne sera pas produit en brut

**Preuve.** En lecture, `outil/index.html:489` choisit `cadrageA(vid.currentTime)` parmi les points posés ; `cadrageA()` passe au point suivant ou interpole. `scripts/produire-split.py:2-3,54-56,93` annonce puis applique uniquement `d['points'][0]` à toute la vidéo. Deux points différents donnent donc un aperçu mobile ou changeant et un MP4 entièrement cadré sur le premier point. Le cadre fixe par défaut reste fonctionnel quand un seul point existe.

**Correctif proposé.** En mode production brute, rendre l'aperçu à partir du premier point seulement et indiquer clairement que les autres points ne seront pas utilisés, ou prendre en charge les points successifs dans ce moteur. Un test à deux points doit comparer une image avant et après le second point dans l'aperçu et le MP4.

### 5. P3 — Le suivi ne distingue pas les formats et disparaît au rechargement

**Preuve.** `outil/index.html:842-877` garde `envois` en mémoire, avec `e.nom=reel.nom` ; aucun format n'est ajouté à la ligne. `validations[reel.id]` dans `marquerReels()` n'a qu'une case par reel. Le compte rendu V2 reconnaît expressément ces limites. Deux productions du même reel sont deux lignes homonymes ; après recharge, le ✓ local peut rester mais la liste de production est vide. Cela affaiblit la demande de suivi « pour chaque reel envoyé » lorsque plusieurs formats sont produits.

**Correctif proposé.** Identifier le suivi par `(lot, reel, format, tâche)` et afficher le format et le fichier ; relire les états sauvegardés depuis le serveur au chargement, ou signaler clairement que la liste ne couvre que la session ouverte.

### 6. P3 — La couverture de régression V2 est insuffisante

**Preuve.** `git diff refonte-ux..refonte-v2 -- tests/test_refonte.py | wc -l` donne `0`. Les neuf tests Python existants passent, mais aucun ne teste la nouvelle timeline, le bouton de blancs, la table de formats, un rendu `v8020`, deux formats pour le même reel ou le chemin de rendu complet. Le fichier `outil/index.html` atteint 1 156 lignes de CSS/HTML/JS ; les commentaires et `scripts/formats.py` sont lisibles, mais `rendre-reel.py` garde des tables concurrentes et le comportement du bouton tient dans un `forEach` non testé.

**Correctif proposé.** Ajouter quelques tests de parcours ciblés : états mixtes blanc/manuelle, sauvegarde par format avec identifiant long, chaque format via le serveur en mode brut et complet. Déplacer les règles de sélection des formats et de nommage dans des fonctions courtes testables, sans introduire de build.

## Vérifications reproductibles

### Tests et diff

```text
python3 -m py_compile outil/*.py scripts/*.py tests/*.py  → code 0
python3 -m unittest discover -s tests -v              → Ran 9 tests in 4.157s, OK
git diff --check refonte-ux..refonte-v2                → aucune sortie, code 0
git status --short --branch (avant audit)             → ## refonte-v2
```

### Lot ffmpeg et sorties réelles

Deux sources distinctes de 3 s ont été fabriquées sous `/tmp/audit-v2-gpt6/sources` avec `testsrc2` + sinus 440 Hz et `smptebars` + sinus 880 Hz, 640×360, 24 i/s. Commandes `ffmpeg -v error -y -f lavfi -i testsrc2=size=640x360:rate=24 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 3 -c:v libx264 -pix_fmt yuv420p -c:a aac .../camera.mp4` et équivalent `smptebars`/880 Hz pour `ecran.mp4` : code 0, aucune erreur. Un proxy côte à côte et un manifeste à deux reels ont servi à Chrome et au serveur local. Dix JSON ont été créés sous `/tmp/audit-v2-gpt6/json` avec le même identifiant `AUDIT-01`, début `0`, fin `2`, aucune coupe, cadres au ratio de chaque zone. Commande exécutée :

```text
for key in vmc v8020 v7030 hmc h5050 vcons v6535 v6040 hsolo carre; do
  python3 scripts/produire-split.py /tmp/audit-v2-gpt6/json/$key.json /tmp/audit-v2-gpt6/rendus || exit 1
done
```

Sortie : dix fois `Reel pret`, code 0. `ffprobe` a confirmé **10 fichiers distincts**, tous avec vidéo et audio AAC à 48 kHz, `video=2.000s` et `audio=2.000s`. Dimensions : `vmc`, `v8020`, `v7030`, `vcons`, `v6535`, `v6040` = 1080×1920 ; `hmc`, `h5050`, `hsolo` = 1920×1080 ; `carre` = 1080×1080. Un autre rendu `vmc`, départ 0 et coupes `[0.5,1.0]`, `[1.5,1.75]`, a donné trois morceaux, vidéo **1.250 s** et audio **1.250 s**. Ces observations prouvent le cas sans coupe et le calage simple avec deux coupes ; elles ne prouvent ni la qualité de transcription réelle ni l'habillage complet.

### Navigateur et serveur

Chrome headless a ouvert `/?lot=Audit` sur un serveur isolé au port 8992. Il a affiché les huit formats à deux caméras, 150 pics de forme d'onde, trois mots, les départs et la fin. Les événements souris CDP ont placé la tête de lecture à **1,800429 s** par clic à 60 %, puis à **0,751072 s** par glissement à 25 %. Le format `v8020` a changé l'aperçu à 1080×1920 et le cadre haut à 1519×2160 dans le repère source. Le bouton principal a enregistré et envoyé T1 en 80/20, ouvert T2 et marqué T1 ✓ ; `/export-etat` a fini par répondre `{"fini":true,"ok":true}` avec `/tmp/audit-v2-gpt6/rendus-server/T1 - vertical 80-20.mp4`. Aucune exception JavaScript capturée. Capture 1440×900 : aperçu et colonne de droite visibles, `document.documentElement.scrollWidth > innerWidth` vaut `false`.

```text
ss -ltnp '( sport = :8992 )'                      → LISTEN 127.0.0.1:8992
curl -H 'Host: evil.example' /                   → 403
curl -H 'Origin: http://evil.example' -d ... /enregistrer → 403
curl /lots/Audit/%2e%2e/%2e%2e/etc/passwd        → 404
curl -H 'Range: bytes=-8' /lots/Audit/proxy.mp4  → 206, Content-Range: bytes 292966-292973/292974, corps 8 octets
POST format=unknown                              → 400 « Format inconnu »
POST reel=NOPE avec camera=/etc/passwd           → 400 « Reel absent du manifeste »
POST d'un reel autorisé avec chemins forgés      → chemins sauvegardés repris du manifeste, pas du corps
HEAD /lots/Audit/reels.json                      → 200, Cache-Control: no-store
```

Les protections du serveur validées par Lucas sont conservées dans les chemins exercés. Cet audit ne constitue pas une revue exhaustive de sécurité des décodeurs externes (`ffmpeg`, Chrome, whisper).

**BLOCKED — NOT PROVEN :** la V2 complète n'est pas validable tant que les formats proposés peuvent échouer dans le moteur de rendu par défaut et que « Supprimer les blancs » active des coupes manuelles.
