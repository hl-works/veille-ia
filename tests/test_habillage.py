"""Habillage : 3 morceaux par style + démo, erreurs consignées (réseau simulé)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from veille import elevenlabs_tts as el
from veille import habillage as h


class HabillageTests(unittest.TestCase):
    def test_styles_produce_pieces_and_demo(self):
        prompts = []
        def fake_compose(prompt, secs, dest):
            prompts.append((prompt, secs))
            dest.write_bytes(b'mp3')
        def fake_synth(self, script, output):
            output.write_bytes(b'mp3')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(h, 'compose', side_effect=fake_compose), \
             patch.object(h, 'demo', side_effect=lambda *a: a[-1].write_bytes(b'demo')), \
             patch.object(el.ElevenLabsTTS, 'synthesize', fake_synth):
            res = h.run({'habillage': {'styles': [{'nom': 'nu-disco', 'ambiance': 'groovy'}]}}, Path(d), {})
            self.assertTrue((Path(d) / '01-nu-disco-DEMO.mp3').exists())
        self.assertEqual([s for _, s in prompts], [8, 3, 6])
        self.assertIn('round full warm bass', prompts[0][0])
        self.assertIn('groovy', prompts[0][0])
        self.assertEqual(res[0]['demo'], '01-nu-disco-DEMO.mp3')

    def test_missing_music_access_is_reported(self):
        def denied(prompt, secs, dest):
            raise el.ElevenLabsError(401, 'missing_permissions music_generation')
        def fake_synth(self, script, output):
            output.write_bytes(b'mp3')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(h, 'compose', side_effect=denied), \
             patch.object(el.ElevenLabsTTS, 'synthesize', fake_synth):
            res = h.run({'habillage': {'styles': [{'nom': 'x'}]}}, Path(d), {})
            self.assertIn('401', (Path(d) / 'README.md').read_text())
        self.assertIn('missing_permissions', res[0]['erreur'])

    def test_univers_board_music_only(self):
        seen = []
        def fake_compose(prompt, secs, dest):
            seen.append((prompt, secs))
            dest.write_bytes(b'mp3')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(h, 'compose', side_effect=fake_compose), \
             patch.object(el.ElevenLabsTTS, 'synthesize', side_effect=AssertionError('pas de voix')):
            res = h.run({'habillage': {'univers': [{'nom': 'french-touch', 'ambiance': 'filtered disco house'}],
                                       'duree_s': 15}}, Path(d), {})
            self.assertTrue((Path(d) / '01-french-touch.mp3').exists())
        self.assertEqual(seen[0][1], 15.0)
        self.assertIn('filtered disco house', seen[0][0])
        self.assertEqual(res[0]['demo'], '01-french-touch.mp3')


if __name__ == '__main__':
    unittest.main()
