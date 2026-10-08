"""Régressions de la refonte : Python standard, toutes les données hors du dépôt.

    python3 -m unittest discover -s tests -v
"""
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / 'outil'))
sys.path.insert(0, str(RACINE / 'scripts'))
serveur = importlib.import_module('serveur')
formats = importlib.import_module('formats')
PAGE = RACINE / 'outil' / 'index.html'


class ServeurLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        self.lots = self.racine / 'lots'
        (self.lots / 'Podcast').mkdir(parents=True)
        (self.lots / 'Podcast' / 'reels.json').write_text(json.dumps(
            {'lot': 'Podcast', 'rendu': False, 'sortie': 'Vertical',
             'reels': [{'id': 'P1-03', 'camera': 'lots/Podcast/haut.mp4',
                        'ecran': 'lots/Podcast/bas.mp4', 'decalage': 0.5}]}))
        (self.lots / 'Podcast' / 'proxy.mp4').write_bytes(bytes(range(256)))
        self.modifs = [patch.object(serveur.reglages, 'LOTS', self.lots),
                       patch.object(serveur, 'DEPOT', self.racine / 'cadrages')]
        for modif in self.modifs:
            modif.start()
        self.http = serveur.ThreadingHTTPServer(('127.0.0.1', 0), serveur.H)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        for modif in reversed(self.modifs):
            modif.stop()
        self.tmp.cleanup()

    def requete(self, chemin, methode='GET', entetes=None, donnees=None):
        req = urllib.request.Request(self.base + chemin, method=methode,
                                     headers=entetes or {}, data=donnees)
        try:
            reponse = urllib.request.urlopen(req)
        except urllib.error.HTTPError as erreur:
            reponse = erreur
        with reponse:
            return reponse.status, reponse.headers, reponse.read()

    def test_entree_et_cache(self):
        for chemin in ('/?lot=exemple', '/outil/index.html', '/lots/exemple/reels.json',
                       '/lots/Podcast/reels.json'):
            code, entetes, contenu = self.requete(chemin)
            self.assertEqual(code, 200)
            self.assertEqual(entetes['Cache-Control'], 'no-store')
            self.assertTrue(contenu)

    def test_hote_refuse(self):
        for methode in ('GET', 'HEAD', 'POST'):
            self.assertEqual(self.requete('/', methode, {'Host': 'autre.example'})[0], 403)

    def test_range_et_chemin(self):
        code, entetes, contenu = self.requete('/lots/Podcast/proxy.mp4',
                                             entetes={'Range': 'bytes=10-19'})
        self.assertEqual((code, contenu), (206, bytes(range(10, 20))))
        self.assertEqual(entetes['Content-Range'], 'bytes 10-19/256')
        self.assertEqual(self.requete('/lots/Podcast/%2e%2e/%2e%2e/secret')[0], 404)

    def test_lot_historique_et_liste(self):
        (self.lots / 'reels.json').write_text('{"lot":"Ancien"}')
        self.assertEqual(json.loads(self.requete('/lots/reels/reels.json')[2])['lot'], 'Ancien')
        # sans quoi /lots/reels/<autre lot>/ servirait tous les lots du serveur
        self.assertEqual(self.requete('/lots/reels/Podcast/reels.json')[0], 404)
        self.assertEqual({lot['id'] for lot in json.loads(self.requete('/lots')[2])},
                         {'exemple', 'Podcast', 'reels'})

    def test_enregistrer_sans_rendu(self):
        d = {'reel': 'P1-03', 'lot_id': 'Podcast', 'format': 'vmc', 'debuts': [0],
             'points': [], 'rendu': False}
        code, _, contenu = self.requete('/enregistrer', 'POST',
                                        {'Content-Type': 'application/json'}, json.dumps(d).encode())
        reponse = json.loads(contenu)
        self.assertEqual(code, 200)
        self.assertTrue(reponse['garde'])
        sauve = json.loads((serveur.DEPOT / reponse['fichier']).read_text())
        self.assertEqual(sauve['reel'], 'P1-03')

    def test_chemins_repris_du_manifeste(self):
        """Le corps de la requete ne doit pas pouvoir designer les fichiers :
        c'est ffmpeg qui les ouvrirait, et le rendu qui ecrirait la sortie."""
        d = {'reel': 'P1-03', 'lot_id': 'Podcast', 'format': 'vmc', 'debuts': [0],
             'points': [], 'rendu': False, 'camera': '/etc/passwd',
             'audio': 'http://ailleurs.example/a.wav', 'sortie': '../../ailleurs',
             'decalage': 99}
        code, _, contenu = self.requete('/enregistrer', 'POST',
                                        {'Content-Type': 'application/json'}, json.dumps(d).encode())
        self.assertEqual(code, 200)
        sauve = json.loads((serveur.DEPOT / json.loads(contenu)['fichier']).read_text())
        self.assertEqual(sauve['camera'], 'lots/Podcast/haut.mp4')
        self.assertEqual(sauve['decalage'], 0.5)
        self.assertEqual(sauve['sortie'], 'Vertical')
        self.assertNotIn('audio', sauve)
        for inconnu in ({'reel': 'absent', 'lot_id': 'Podcast', 'debuts': [0]},
                        {'reel': 'P1-03', 'lot_id': 'Fantome', 'debuts': [0]}):
            self.assertEqual(self.requete('/enregistrer', 'POST', {}, json.dumps(inconnu).encode())[0], 400)

    def test_post_d_un_autre_site_refuse(self):
        d = json.dumps({'reel': 'P1-03', 'lot_id': 'Podcast', 'debuts': [0]}).encode()
        for entetes in ({'Origin': 'http://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.requete('/enregistrer', 'POST', entetes, d)[0], 403)
        self.assertEqual(self.requete('/enregistrer', 'POST',
                                      {'Origin': f'http://127.0.0.1:{self.http.server_port}',
                                       'Sec-Fetch-Site': 'same-origin'}, d)[0], 200)

    def test_passage_non_textuel_et_dossier(self):
        d = json.dumps({'passage': 123, 'reel': 'P1-03', 'lot_id': 'Podcast', 'debuts': [0]}).encode()
        self.assertEqual(self.requete('/enregistrer', 'POST', {}, d)[0], 200)
        self.assertEqual(self.requete('/lots/Podcast/')[0], 404)
        self.assertEqual(json.loads(self.requete('/export-etat?nom=jamais-vu')[2])['ok'], False)

    def lot_long(self, ident):
        """Un lot dont l'identifiant de reel depasse a lui seul la coupe du nom."""
        (self.lots / 'Long').mkdir()
        (self.lots / 'Long' / 'reels.json').write_text(json.dumps(
            {'lot': 'Long', 'rendu': False,
             'reels': [{'id': ident, 'camera': 'lots/Long/haut.mp4',
                        'ecran': 'lots/Long/bas.mp4'}]}))

    def envoyer(self, ident, lot, cle):
        d = {'reel': ident, 'lot_id': lot, 'format': cle, 'debuts': [0], 'points': []}
        code, _, contenu = self.requete('/enregistrer', 'POST',
                                        {'Content-Type': 'application/json'},
                                        json.dumps(d).encode())
        # un refus repond en HTML : seul le code compte alors
        return code, (json.loads(contenu) if code == 200 else {})

    def test_un_fichier_par_format_meme_sur_un_identifiant_long(self):
        """Le nom de travail est coupe a soixante caracteres. Quand la coupe
        tombait APRES le format, deux formats d'un reel au nom long rendaient le
        meme fichier : le second ecrasait le cadrage du premier."""
        ident = 'Podcast-de-rentree-partie-deux-segment-quinze-prise-trois-bis-B'
        self.lot_long(ident)
        noms = {}
        for cle in formats.ORDRE:
            code, reponse = self.envoyer(ident, 'Long', cle)
            self.assertEqual((code, reponse['garde']), (200, True))
            noms[cle] = reponse['fichier']
            self.assertLessEqual(len(reponse['fichier']), 65)
        self.assertEqual(len(set(noms.values())), len(formats.ORDRE))
        for cle, nom in noms.items():
            sauve = json.loads((serveur.DEPOT / nom).read_text())
            self.assertEqual((sauve['reel'], sauve['format']), (ident, cle))

    def test_format_inconnu_refuse(self):
        self.assertEqual(self.envoyer('P1-03', 'Podcast', 'vertical-maison')[0], 400)

    def test_un_export_fini_survit_au_redemarrage(self):
        """ETATS vit en memoire. Sans l'issue posee a cote du journal, la colonne
        de suivi rouvrait un export reussi en « rate » apres un redemarrage."""
        serveur.DEPOT.mkdir(parents=True, exist_ok=True)
        for code, attendu in ((0, True), (1, False)):
            (serveur.DEPOT / 'T.log').write_text('Reel pret : T.mp4')
            (serveur.DEPOT / 'T.etat').write_text(str(code))
            reponse = json.loads(self.requete('/export-etat?nom=T')[2])
            self.assertEqual((reponse['fini'], reponse['ok']), (True, attendu))
        # un journal sans issue = un rendu coupe en route, et non un succes
        (serveur.DEPOT / 'T.etat').unlink()
        self.assertEqual(json.loads(self.requete('/export-etat?nom=T')[2])['ok'], False)


class TousLesFormats(unittest.TestCase):
    """La page propose dix formats : les deux moteurs doivent les tenir tous."""

    def test_table_coherente(self):
        noms = set()
        for cle in formats.ORDRE:
            f = formats.trouver(cle)
            noms.add(f['fichier'])
            self.assertIn(formats.dossier(cle), ('Vertical', 'Horizontal'))
            self.assertIn('cap_y', formats.habillage(cle))
            for _, z in formats.zones(cle):
                self.assertLessEqual(z['x'] + z['w'], f['W'])
                self.assertLessEqual(z['y'] + z['h'], f['H'])
                self.assertIn(z['source'], ('camera', 'ecran'))
        # deux formats du meme reel se distinguent par le nom de fichier
        self.assertEqual(len(noms), len(formats.ORDRE))

    def test_le_rendu_habille_cadre_les_dix_formats(self):
        """rendre-reel.py gardait sa propre table de quatre formats : le 80/20
        pose dans la page sortait en « KeyError: v8020 »."""
        rendre = importlib.import_module('rendre-reel')
        for cle in formats.ORDRE:
            zones = dict(formats.zones(cle))
            cadre = {}
            for nom, z in zones.items():
                h, w = 1080, round(1080 * z['w'] / z['h'])
                if w > 1920:
                    w, h = 1920, round(1920 * z['h'] / z['w'])
                cadre[nom] = {'x': 0, 'y': 0, 'w': w, 'h': h}
            point = {'t': 0, 'camera': cadre['a']}
            if 'b' in zones:
                point['ecran'] = cadre['b']
            d = {'format': cle, 'camera': 'haut.mp4', 'ecran': 'bas.mp4',
                 'source': {'w': 1920}, 'points': [point]}
            with patch.object(rendre, 'taille_source', lambda _: (1920, 1080)):
                pts = rendre.cadrages(d)
            self.assertEqual(len(pts), 1, cle)
            self.assertEqual(set(pts[0]) - {'t', 'glisse'}, {'A', 'B'}, cle)
            if formats.une_camera(cle):
                # rien a empiler : la zone unique sert les deux places
                self.assertEqual(pts[0]['A'], pts[0]['B'], cle)

    def test_le_rendu_brut_accepte_les_dix_formats(self):
        brut = importlib.import_module('produire-split')
        for cle in formats.ORDRE:
            d = {'format': cle, 'camera': 'haut.mp4', 'debuts': [0], 'fin': 10,
                 'points': [{'t': 0, 'camera': {'x': 0, 'y': 0, 'w': 100, 'h': 100}}]}
            if not formats.une_camera(cle):
                d['ecran'] = 'bas.mp4'
            brut.verifier(d)          # ne doit rien lever
        with self.assertRaises(ValueError):
            brut.verifier({'format': 'vmc', 'camera': 'haut.mp4',
                           'debuts': [0], 'fin': 10, 'points': [{}]})


class ReglesDeLaPage(unittest.TestCase):
    """Les trois decisions qui se discutent vivent dans un bloc sans DOM de
    outil/index.html, justement pour etre rejouables ici."""

    def regles(self):
        page = PAGE.read_text(encoding='utf-8')
        debut = page.index('const REGLES={')
        return page[debut:page.index('\n};', debut) + 3]

    @unittest.skipUnless(shutil.which('node'), 'node absent')
    def test_regles_rejouees(self):
        essai = self.regles() + """
const dit=(ok,quoi)=>{if(!ok){console.error('RATE : '+quoi);process.exit(1)}};

// « Supprimer les blancs » ne doit toucher que les coupes proposees par l'analyse
let coupes=[{type:'blanc',on:false},{type:'reprise',on:false},{type:'manuel',on:false}];
coupes.forEach(c=>{if(REGLES.proposee(c))c.on=true});
dit(coupes[0].on&&coupes[1].on,'le blanc et la reprise partent au rendu');
dit(!coupes[2].on,'la coupe posee a la main reste posee');
// « Tout garder » va dans l'autre sens pour tout le monde : il ne retire rien
coupes.forEach(c=>c.on=false);
dit(coupes.every(c=>!c.on),'tout garder remet tout');

// l'apercu suit le moteur : un seul cadre en production brute
dit(REGLES.cadreFige(true)&&!REGLES.cadreFige(false),'cadre fige en brut seulement');
dit(!REGLES.pointsIgnores(true,1),'un seul point : rien a signaler');
dit(REGLES.pointsIgnores(true,2),'deux points en brut : il faut le dire');
dit(!REGLES.pointsIgnores(false,5),'en rendu habille les points servent tous');

// le suivi distingue (reel, format), et deux couples differents ne se confondent pas
dit(REGLES.cleEnvoi('P1-03','vmc')!==REGLES.cleEnvoi('P1-03','hmc'),'un format, une ligne');
dit(REGLES.cleEnvoi('P1-03','vmc')===REGLES.cleEnvoi('P1-03','vmc'),'la cle est stable');
dit(REGLES.cleEnvoi('P1','03-vmc')!==REGLES.cleEnvoi('P1-03','vmc'),'pas de telescopage');
dit(REGLES.cleEnvoi('P1-03')===REGLES.cleEnvoi('P1-03','vmc'),'sans format : le vertical 50/50');
console.log('regles de la page : OK');
"""
        r = subprocess.run(['node', '-e', essai], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)


class NomsDuRendu(unittest.TestCase):
    def test_identifiants_libres_avant_montage(self):
        rendre = importlib.import_module('rendre-reel')
        class MontageAtteint(Exception):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            fichier = dossier / 'cadrage.json'
            for ident, attendu in [('P1-03', 'P1-03.mp4'), ('7', '07.mp4'), ('A/B', 'A-B.mp4')]:
                fichier.write_text(json.dumps({'reel': ident, 'format': 'vmc',
                                               'points': [{}], 'debuts': [0]}))
                def montage(d, debut, brut):
                    self.assertEqual(brut.name, attendu)
                    raise MontageAtteint
                with patch.object(sys, 'argv', ['rendre-reel.py', str(fichier)]), \
                     patch.object(rendre, 'SORTIE', dossier), \
                     patch.object(rendre, 'monter', montage):
                    with self.assertRaises(MontageAtteint):
                        rendre.main()


if __name__ == '__main__':
    unittest.main()
