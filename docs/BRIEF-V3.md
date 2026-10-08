# Brief V3 : la timeline exacte de l Atelier, l étalonnage, le titre

Rédigé le 08/10/2026 au soir. Part de la branche refonte-v2 (V2 terminée et auditée). Lire
docs/BRIEF-V2.md et docs/COMPTE-RENDU-V2.md d abord. À copier dans docs/BRIEF-V3.md.

## 1. La timeline : copier EXACTEMENT celle de la sélection de l Atelier
Lucas : « c est vraiment ça que je kiffais le plus ». Modèle à reproduire fidèlement :
~/projets/references/atelier/images/selection-lucas-2026-10-08.png (capture de Lucas) et
images/selection.png ; code de référence : static/editor/selection/trimmer.js, trim-edit.js,
rails.js, playback.js, et timeline.py (forme d onde, blancs).
Éléments, de haut en bas, sous l aperçu :
- ligne de transport : bouton lecture rond, « 00:00.0 / 00:27.2 », aide « Espace lecture · I / O fixer
  début / fin » ; à droite un segment « Léger · Normal · Serré » (sensibilité de détection des blancs),
  le bouton « ✂ Supprimer les blancs » et le lien « Rétablir » ;
- la piste : forme d onde pleine largeur ; la zone gardée encadrée avec deux poignées verticales
  (début, fin) qu on attrape et glisse ; les blancs supprimés hachurés dans la piste ; la forme d onde
  hors bornes reste visible mais atténuée (on voit le rush avant et après) ;
- sous la piste : à gauche « DÉBUT « ‹ 00:00.3 › » » (sauts fins et larges), au centre « Rush 00:00 →
  00:38 », à droite « FIN « ‹ 00:31.1 › » ».
Les mots transcrits peuvent rester accessibles (onglet « Transcript » à côté de « Aperçu », comme dans
l Atelier) mais ne doivent plus encombrer la piste. Les départs multiples (D1, D2) restent possibles.
Garder l accent de couleur de la V2 si l orange de l Atelier jure avec le reste ; la DISPOSITION et les
GESTES doivent être ceux de l Atelier.

## 2. Étalonnage (LUT) par rush, simple
Modèle : ~/projets/references/atelier/images/etalonnage-lucas-2026-10-08.png et grading.py
(détection Log / Rec.709 par signalstats, mesurée sur de vrais rushes).
- Dans la colonne de gauche ou l inspecteur, pour chaque caméra : « Étalonnage » = menu avec EXACTEMENT
  trois choix : « Aucun », « 709 · Apple Cinestyle » (fichier « Apple - Cinestyle (sans LOG).cube »),
  « Délog · Log M → Rec.709 » (fichier « Log M to Rec709.cube »). Rien d autre.
- Sous le menu, la ligne de diagnostic comme l Atelier (« Rec.709 détecté · saturation 15.6 ») et une
  suggestion par défaut (Log détecté → Délog ; 709 → Aucun).
- Les LUT ne sont PAS dans le dépôt (public) : dossier configurable (REELS_LUTS dans reglages.py,
  défaut ~/luts) ; pour les tests, ~/projets/references/luts. Si le fichier manque, le dire clairement.
- L aperçu applique la LUT (image fixe de contrôle calculée par ffmpeg lut3d, comme l Atelier, suffit) et
  le rendu (produire-split.py) l applique avant le recadrage.

## 3. Le titre de chaque reel
- Champ « Titre » éditable en tête de la colonne de droite, pré-rempli par le titre proposé dans le
  manifeste (Claude propose un titre par reel quand il prépare le lot ; Lucas le modifie).
- Le titre est enregistré avec le cadrage, sert au nom du fichier produit, et est gardé pour la future
  incrustation (encadré au-dessus ou au milieu de la vidéo) : prévoir le champ « position du titre »
  (haut / milieu / aucun) sans encore incruster.

## 4. Contraintes et vérification
Inchangées (sans build, sans framework, dépôt public sans données ni LUT, serveur local protégé).
Lot de test ffmpeg dans /tmp ; vérifier en vrai navigateur les gestes de la timeline (glisser les
poignées, Léger/Normal/Serré change les blancs, Supprimer puis Rétablir), et produire un reel par
étalonnage (contrôler visuellement l effet de la LUT sur une image extraite).
