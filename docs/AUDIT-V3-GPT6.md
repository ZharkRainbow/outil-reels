# Audit V3 — `refonte-v3`

8 octobre 2026. Base : `refonte-v2..refonte-v3` (11 fichiers, 1 218 insertions, 106 suppressions). J'ai lu `BRIEF-V3`, `COMPTE-RENDU-V3`, le brief et l'audit V2, puis examiné le diff et exécuté l'outil sur le lot ffmpeg `/tmp/lot-v3`. Les cadrages et sorties propres à cet audit sont dans `/tmp/audit-v3-gpt6`. Aucun code ni média du dépôt n'a été modifié.

## Verdict

**V3 partiellement conforme.** La timeline et ses gestes principaux fonctionnent dans Chrome. Les trois LUT fonctionnent sur les images de contrôle et avec `produire-split.py`. En revanche, un lot qui emprunte le moteur de rendu complet par défaut ignore silencieusement l'étalonnage choisi. Le geste « Rétablir » peut aussi effacer une coupe manuelle préexistante.

## Constats, du plus grave au moins grave

### 1. P1 — Le rendu complet ignore les choix de LUT

**Preuve.** `outil/serveur.py:103-118` choisit `rendre-reel.py` quand le manifeste n'a pas de bloc `production`. L'interface montre et exporte pourtant les mêmes menus d'étalonnage dans ce cas (`outil/index.html:1084-1085`). `scripts/rendre-reel.py:168-256` construit le graphe vidéo sans lire `etalonnages` ni appeler `lut3d` ; seul `produire-split.py:103-136` applique les LUT. J'ai appelé la fonction réelle `rendre_reel.monter` sur les mêmes 2 secondes du rush Log de la prise 2, une fois avec `camera=aucun`, une fois avec `camera=delog` : deux MP4 de 229 096 octets, **SHA-256 identiques** `9b3c438e83c8c00794cf9aef750cbab13a805458a92d007ce59a418d8d2437bb`. Les deux ont une durée de 2,002 s. À l'inverse, les trois rendus bruts de contrôle présentent des statistiques d'image différentes (table plus bas). L'utilisateur peut donc valider « Délog » et recevoir un reel sans délogage, sans avertissement, selon le manifeste du lot.

Le même moteur complet continue à incruster un bandeau titre via `rendre-reel.py:425-426`, sans lire `titre_position`. Le champ « aucune » ne pilote donc pas ce moteur ; la promesse du README « rien n'est encore incrusté » ne décrit que le rendu brut.

**Correctif proposé.** Appliquer la même table `etalonnages.json` et `etalonnage.filtre()` dans chaque branche vidéo de `rendre-reel.py`, avant `crop`, puis tester un lot sans `production` avec `Aucun` et `Délog` sur le même rush. Clarifier ou harmoniser le comportement du titre entre les deux moteurs ; la position enregistrée doit avoir le même sens dans chacun.

### 2. P2 — « Rétablir » supprime une coupe manuelle antérieure

**Preuve.** Dans Chrome, j'ai posé une coupe manuelle `[4,0 ; 4,3]` active, puis cliqué « Supprimer les blancs » : la coupe manuelle est restée active, ce qui corrige le défaut V2. Après « Rétablir », cette même coupe est passée à `on=false`. Le code `outil/index.html:827` exécute `coupes.forEach(c=>c.on=false)` ; il n'enregistre pas l'état avant la suppression. Le JSON produit ensuite contient `"coupes":[]` et le reel perd donc aussi la coupe manuelle. Ce résultat est reproductible dans `/tmp/audit-v3-gpt6/flows.cjs`.

**Correctif proposé.** Faire de « Rétablir » l'inverse du dernier clic « Supprimer les blancs » : mémoriser l'état des seules coupes touchées et le restaurer. Si le bouton doit réellement signifier « Tout garder », employer ce libellé et séparer les deux actions. Tester une coupe manuelle active et un blanc inactif avant la séquence de deux clics.

### 3. P3 — La piste n'est pas visuellement exacte par rapport à la capture de Lucas

**Preuve.** Comparaison à taille native 2 000 × 1 134 : [référence Atelier](/home/lucas/projets/references/atelier/images/selection-lucas-2026-10-08.png) et [capture Chrome V3 après glissement](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F03-cuts.png). Dans la référence, la piste commence sous la zone centrale vers `x=291` et s'étend jusqu'à `x=1971` ; dans la V3 elle traverse presque toute la fenêtre (`x=21..1979`). L'onde de la V3 remplit visuellement presque toute la hauteur sur les passages sonores, avec des blocs serrés ; celle de l'Atelier reste plus fine et plus aérée. La V3 affiche aussi des hachures de blancs avant 5,3 s et après 17,1 s, hors de la zone gardée, tandis que la référence laisse surtout voir un rush atténué à droite de la borne. La ligne transport, l'ordre des contrôles, les capsules, le pied de piste et la séparation des mots sont proches et utilisables ; ce constat concerne la demande « EXACTEMENT » sur la disposition et le dessin.

**Correctif proposé.** Caler la largeur et l'ancrage de la timeline sur la zone de travail montrée par la référence, puis ajuster l'amplitude et l'espacement des pics. Atténuer ou masquer les hachures des coupes hors des bornes gardées. Refaire une capture 2 000 × 1 134 avec des bornes et coupes placées aux mêmes fractions du rush.

### 4. P3 — Une valeur mal formée d'étalonnage casse la réponse HTTP

**Preuve.** `outil/serveur.py:258` appelle `.items()` sur `d.get("etalonnages")` sans vérifier que c'est un objet. `POST /enregistrer` avec `{"etalonnages":["bad"]}` ou `{"etalonnages":17}` coupe la connexion (`requests.ConnectionError`) au lieu de répondre 400 ; `[]` vide passe même avec 200. Les clés de LUT inconnues et les positions de titre inconnues, elles, sont correctement refusées par 400. Le serveur reste vivant : le problème est limité à la requête et à son thread.

**Correctif proposé.** Valider que `etalonnages` est un dictionnaire, que les sources sont `camera` ou `ecran` et que les valeurs sont des clés texte de la table, puis renvoyer 400 de façon uniforme. Ajouter trois cas JSON mal formés au test de route.

## Vérification élément par élément du brief

| Point | Preuve et résultat |
|---|---|
| Transport | **PASS** — bouton rond, `00:00.0 / 00:21.4`, aide Espace et I/O, segment Léger/Normal/Serré, ciseaux et lien Rétablir présents dans Chrome. La référence indique `00:27.2` parce que le rush est différent. |
| Piste et bornes | **PASS fonctionnel** — rail de 64 px, aucun mot ni graduation au repos, deux capsules de 16 × 68 px. Glissement physique du début à 25 % → `00:05.3`, de la fin à 80 % → `00:17.1`. La forme d'onde hors bornes reste visible et atténuée (`globalAlpha=0.23`). Écart visuel au constat 3. |
| Blancs et gestes | **PASS avec réserve** — Léger 6, Normal 7, Serré 9 blancs sur le lot ; « Supprimer » active 7 coupes et affiche 9,2 s à l'arrivée ; « Rétablir » revient à 0 et disparaît. Le cas des coupes manuelles échoue au constat 2. Les bords de chaque blanc sont prévus dans le DOM et le gestionnaire de pointeur ; leur glissement individuel n'a pas été mesuré physiquement dans cet audit. |
| Pied, I/O, départs | **PASS** — sauts `›` et `»` du début : +0,1 puis +0,5 s ; `‹` et `«` de fin : −0,1 puis −0,5 s. I ajoute un second départ à 7,0 s et O fixe la fin à 16,0 s ; les deux poignées de départ et les pastilles D1/D2 apparaissent. `Rush 00:00 → 00:21` reste centré. |
| Transcript et gestes V2 | **PASS** — 41 boutons de mots dans l'onglet Transcript et aucun sur le rail ; l'aperçu se cache lorsque l'onglet s'ouvre. Dans Chrome, dix formats sont proposés ; un point posé en 50/50 disparaît du 80/20 puis revient en 50/50. La touche `N` envoie le reel 1, ouvre le reel 2, affiche `✓ V3 1` et une ligne « En file d'attente » ; `/export-etat` finit avec `ok:true` et le MP4 titré. Les tests de règles V2 passent. La lecture réelle prolongée et un trackpad physique n'ont pas été rejoués. |
| Trois étalonnages | **PASS** — exactement `Aucun`, `709 · Apple Cinestyle`, `Délog · Log M → Rec.709` dans chacun des deux menus. Le catalogue ne contient aucune autre clé visible. Les LUT sont hors du dépôt, `REELS_LUTS` vaut `~/luts` par défaut. |
| Diagnostic et proposition | **PASS sur le lot** — prise 1 : Rec.709, saturation 131,1 / 69,2, proposition Aucun ; prise 2 : Log, saturation 2,9 / 1,8, proposition Délog. Les diagnostics viennent de `/etalonnage`, sur cinq images `signalstats`. |
| LUT visible et fichier absent | **PASS** — `/etalonnage-apercu` renvoie trois JPEG distincts pour la prise 2 ; le menu affiche « fichier absent » pour les deux LUT avec `REELS_LUTS=/tmp/audit-v3-gpt6/no-luts`, et choisir Délog affiche le chemin manquant. Le rendu sans LUT échoue immédiatement avec un message explicite. |
| LUT au rendu | **PASS avec `produire-split.py` ; ÉCHEC avec le rendu complet par défaut** — voir constat 1 et table ci-dessous. Le filtre `lut3d` précède `crop` dans `produire-split.py:136`. |
| Titre | **PASS en rendu brut** — champ pré-rempli `Pourquoi personne ne clique sur ton offre`, édité en `Audit titre éè 2026`, position `milieu` ; le JSON de la page contient les deux valeurs et elles reviennent après rechargement. Les fichiers produits sous `/tmp/audit-v3-gpt6/rendus` portent leurs titres `Audit V3 ...`. Le moteur complet a la réserve du constat 1. |
| Contraintes | **PASS partiel** — pas de build ni framework ni `.cube` dans le diff ; 17 tests passent, `git diff --check` ne signale rien. Sécurité HTTP contrôlée ci-dessous. |

## Rendus et sécurité : preuves reproductibles

Trois JSON de cadrage exportés dans `/tmp/audit-v3-gpt6/{aucun,cine709,delog}.json` ont été rendus avec `REELS_LUTS=/home/lucas/projets/references/luts python3 scripts/produire-split.py <json> /tmp/audit-v3-gpt6/rendus`. Les trois MP4 ont une piste vidéo 1080 × 1920 et une piste audio ; `ffprobe` donne 15,708 s aux deux pistes. Image extraite à 5 s, puis `ffmpeg signalstats` :

| Choix caméra | YAVG | YLOW | YHIGH | SATAVG |
|---|---:|---:|---:|---:|
| Aucun | 102,6 | 75 | 133 | 2,37 |
| Cinestyle | 93,5 | 57 | 117 | 2,98 |
| Délog | 97,1 | 56 | 133 | 5,08 |

Les trois images sont `/tmp/audit-v3-gpt6/{aucun,cine709,delog}.png`. Le changement est visible, notamment sur les plages colorées du rush Log. Les mesures portent sur une image du reel synthétique, pas sur un tournage réel.

Serveur supervisé par Portly au port 8795, écoute confirmée sur `127.0.0.1`. Requêtes réelles : Host étranger → 403 ; Origin étranger au POST → 403 ; traversée `/lots/V3/%2e%2e/%2e%2e/etc/passwd` → 404 ; source de rush forgée sur `/etalonnage` → 400 ; clé de LUT inconnue sur `/enregistrer` → 400 ; position de titre inconnue → 400 ; Range `bytes=-8` sur le proxy → 206, huit octets et `Content-Range: bytes 1119798-1119805/1119806`. Les chemins de rush et d'audio envoyés au rendu sont repris du manifeste par `fiche_du_lot` et `CHAMPS_DU_LOT`. La seule anomalie HTTP constatée est au constat 4.

`python3 -m pytest tests/ -q` → **17 passed in 5.68s**. Les vérifications Chrome n'ont produit aucune exception JavaScript ni requête échouée lors du parcours principal. La capture de référence et les captures de cet audit ont toutes les dimensions annoncées, sont lisibles ; les captures d'audit répondent en HTTPS 200, `image/png`, `Cache-Control: private, no-store`. La même clé média reçoit 401 sur `/api/health`.

## Captures Chrome headless

![F01 — timeline avant geste](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F01-initial.png)

![F02 — bornes après glissement](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F02-trim.png)

![F03 — blancs supprimés et comparaison à la référence](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F03-cuts.png)

![F04 — message de LUT absente](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F04-missing-lut.png)

![F05 — titre édité et état restauré](/home/lucas/.local/share/code-os/files/skills-verify/audit-v3-gpt6/F05-final.png)

**Verdict final : ÉCHEC partiel.** Le brief V3 n'est entièrement validable qu'une fois l'étalonnage harmonisé entre les deux moteurs et le sens de « Rétablir » fixé. Les autres points listés ci-dessus ont des preuves positives dans les conditions précisées.
