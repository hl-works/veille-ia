"""ElevenLabs : découpage, filtre accent France, casting (réseau simulé)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from veille import audio, casting, elevenlabs_tts as el


class ElevenLabsTests(unittest.TestCase):
    def test_chunks_keep_every_word_under_limit(self):
        text = ('Une phrase assez longue pour le test. ' * 40 + '\n\n') * 3
        parts = el.chunks(text, 300)
        self.assertTrue(all(len(p) <= 300 for p in parts))
        self.assertEqual(' '.join(parts).split(), text.split())
        self.assertEqual(el.chunks('x' * 50 + ' ' + 'y' * 50, 60)[0], 'x' * 50)

    def test_accent_filter_france_only(self):
        ok = {'voice_id': 'a', 'labels': {'accent': 'parisian', 'language': 'fr'}}
        ca = {'voice_id': 'b', 'labels': {'accent': 'canadian', 'language': 'fr'}}
        qc = {'voice_id': 'c', 'verified_languages': [{'language': 'fr', 'accent': 'québécois', 'locale': 'fr-CA'}]}
        be = {'voice_id': 'd', 'accent': 'belgian', 'language': 'fr'}
        en = {'voice_id': 'e', 'labels': {'accent': 'american', 'language': 'en'}}
        self.assertTrue(el.is_france_french(ok))
        for v in (ca, qc, be, en):
            self.assertFalse(el.is_france_french(v), v)

    def test_french_voices_filters_gender_and_accent(self):
        mine = {'voices': [{'voice_id': 'm1', 'name': 'Claire', 'labels': {'gender': 'female', 'accent': 'parisian', 'language': 'fr'}},
                           {'voice_id': 'm2', 'name': 'Jean', 'labels': {'gender': 'male', 'language': 'fr'}}]}
        shared = {'voices': [{'voice_id': 's1', 'name': 'Julie', 'gender': 'female', 'accent': 'canadian', 'language': 'fr'},
                             {'voice_id': 's2', 'name': 'Léa', 'gender': 'female', 'accent': 'standard', 'language': 'fr', 'locale': 'fr-FR'}]}
        with patch.dict('os.environ', {'ELEVENLABS_API_KEY': 'k'}), \
             patch.object(el, '_get', side_effect=[mine, shared]):
            got = el.french_voices('femme', 4)
        self.assertEqual([v['voice_id'] for v in got], ['m1', 's2'])

    def test_tts_retries_without_language_code(self):
        bad = Mock(ok=False, status_code=400, text='language_code not supported', content=b'')
        good = Mock(ok=True, status_code=200, content=b'mp3')
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'ELEVENLABS_API_KEY': 'k'}), \
             patch.object(el.requests, 'post', side_effect=[bad, good]) as post:
            el.tts('Bonjour', 'v1', Path(d) / 'o.mp3')
            self.assertNotIn('language_code', post.call_args.kwargs['json'])
            self.assertEqual((Path(d) / 'o.mp3').read_bytes(), b'mp3')

    def test_tts_error_is_explicit(self):
        bad = Mock(ok=False, status_code=401, text='missing_permissions', content=b'')
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'ELEVENLABS_API_KEY': 'k'}), \
             patch.object(el.requests, 'post', return_value=bad):
            with self.assertRaises(el.ElevenLabsError) as e:
                el.tts('Bonjour', 'v1', Path(d) / 'o.mp3')
            self.assertEqual(e.exception.status, 401)

    def test_provider_needs_chosen_voice(self):
        cfg = dict(audio.DEFAULT_AUDIO, provider='elevenlabs')
        provider = audio.get_provider(cfg)
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / 's.txt'
            script.write_text('Bonjour.')
            with self.assertRaises(RuntimeError):
                provider.synthesize(script, Path(d) / 'o.mp3')

    def test_casting_first_voice_also_without_lexicon(self):
        calls = []
        def fake_render(text, voice_id, dest, model):
            calls.append((voice_id, dest.name, text))
            dest.write_bytes(b'mp3')
        voices = [{'voice_id': 'v1', 'name': 'Léa', 'source': 'bibliothèque', 'accent': 'fr', 'preview_url': ''},
                  {'voice_id': 'v2', 'name': 'Claire', 'source': 'mes voix', 'accent': 'fr', 'preview_url': ''}]
        with tempfile.TemporaryDirectory() as d, \
             patch.object(casting, 'french_voices', return_value=voices), \
             patch.object(casting, 'render', side_effect=fake_render):
            res = casting.run({'genre': 'femme', 'nombre': 2}, 'Chez OpenAI.', Path(d), {'OpenAI': 'Aupène É-aïe'})
            readme = (Path(d) / 'README.md').read_text()
            self.assertTrue(json.loads((Path(d) / 'casting.json').read_text()))
        self.assertEqual([c[1] for c in calls], ['01-lea.mp3', '01-lea-sans-lexique.mp3', '02-claire.mp3'])
        self.assertEqual(calls[0][2], 'Chez Aupène É-aïe.')
        self.assertEqual(calls[1][2], 'Chez OpenAI.')
        self.assertIn('v2', readme)
        self.assertEqual(len(res), 2)

    def test_casting_records_voice_errors(self):
        def boom(*a, **k):
            raise el.ElevenLabsError(404, 'voice_not_found')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(casting, 'render', side_effect=boom):
            res = casting.run({'voix_ids': ['zz']}, 'Bonjour.', Path(d), {})
            self.assertIn('404', res[0]['erreur'])
            self.assertIn('❌', (Path(d) / 'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
