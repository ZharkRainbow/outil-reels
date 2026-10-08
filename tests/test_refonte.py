"""Régressions de la refonte : Python standard, toutes les données hors du dépôt.

    python3 -m unittest discover -s tests -v
"""
import importlib
import json
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
