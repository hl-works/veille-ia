"""Podcast : voix edge (femme par défaut), format solo/duo, destination privée."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from veille import audio, telegram
from veille.config import Settings

MESSAGE = '<b>Agents IA</b>\nUn outil facilite les tests.\n<a href="https://example.org/source">Source</a>'


class PodcastTests(unittest.TestCase):
    def test_segments_solo_and_duo_keep_every_word(self):
        solo = 'Bonjour.\n\nPremier sujet.\n\nFin.'
        self.assertEqual(audio.segments(solo, 'solo'),
                         [('femme', 'Bonjour.'), ('femme', 'Premier sujet.'), ('femme', 'Fin.')])
        duo = 'ELLE: Bonjour.\nLUI: Un modèle sort.\nsuite sans préfixe\nelle : Au revoir.'
        self.assertEqual(audio.segments(duo, 'duo'),
                         [('femme', 'Bonjour.'), ('homme', 'Un modèle sort.'),
                          ('homme', 'suite sans préfixe'), ('femme', 'Au revoir.')])

    def test_audio_config_defaults_and_env_override(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg_path = Path(directory) / 'c.yaml'
            cfg_path.write_text('audio:\n  format: duo\n  voix_femme: fr-FR-DeniseNeural\n')
            with patch.dict('os.environ', {'AUDIO_DESTINATION': 'canal', 'AUDIO_FORMAT': ''}):
                cfg = audio.audio_config(str(cfg_path))
            self.assertEqual(cfg['format'], 'duo')
            self.assertEqual(cfg['destination'], 'canal')
            self.assertEqual(cfg['provider'], 'edge')
            self.assertEqual(cfg['voix_femme'], 'fr-FR-DeniseNeural')
            self.assertIsInstance(audio.get_provider(cfg), audio.EdgeTTS)

    def test_duo_uses_duo_prompt(self):
        response = SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text='ELLE: Bonjour.')])
        client = Mock()
        client.messages.create.return_value = response
        with patch.object(audio.anthropic, 'Anthropic') as factory:
            factory.return_value.__enter__.return_value = client
            audio.build_script({'date': '2026-09-25', 'text': 'x'}, Settings(), 'duo')
            self.assertIn('FORMAT DUO', client.messages.create.call_args.kwargs['system'])

    def test_private_destination_sends_to_hugo_not_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            audio.save_snapshot(MESSAGE, '10/09/2026', str(source))
            provider = Mock()
            provider.synthesize.side_effect = lambda script, out: out.write_bytes(b'mp3')
            settings = Settings(telegram_bot_token='t', telegram_chat_id='@canal')
            cfg = dict(audio.DEFAULT_AUDIO)
            for dest, env, expected in [('prive', {'TELEGRAM_AUTHORIZED_USER_ID': '42'}, '42'),
                                        ('canal', {}, '@canal')]:
                cfg['destination'] = dest
                with self.subTest(dest=dest), patch.dict('os.environ', env), \
                     patch.object(audio, 'build_script', return_value='Bonjour.'), \
                     patch.object(audio, 'get_provider', return_value=provider), \
                     patch.object(audio, 'duration_seconds', return_value=60), \
                     patch.object(telegram, 'send_audio') as send:
                    audio.run(source, root / dest, settings, send=True, cfg=cfg)
                    self.assertEqual(send.call_args.kwargs['chat_id'], expected)
            cfg['destination'] = 'prive'
            with patch.dict('os.environ', {'TELEGRAM_AUTHORIZED_USER_ID': ''}), \
                 patch.object(audio, 'build_script', return_value='Bonjour.'), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', return_value=60), \
                 patch.object(telegram, 'send_audio') as send:
                with self.assertRaises(RuntimeError):
                    audio.run(source, root / 'none', settings, send=True, cfg=cfg)
                send.assert_not_called()

    def test_edge_provider_concatenates_voices(self):
        import sys, types
        calls = []
        class FakeCommunicate:
            def __init__(self, text, voice):
                calls.append(voice)
            async def save(self, dest):
                Path(dest).write_bytes(b'x')
        fake = types.SimpleNamespace(Communicate=FakeCommunicate)
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 's.txt'
            script.write_text('ELLE: A.\nELLE: B.\nLUI: C.\nELLE: D.')
            cfg = dict(audio.DEFAULT_AUDIO, format='duo')
            with patch.dict(sys.modules, {'edge_tts': fake}), \
                 patch.object(audio.subprocess, 'run') as run:
                audio.EdgeTTS(cfg).synthesize(script, Path(directory) / 'o.mp3')
            self.assertEqual(calls, [cfg['voix_femme'], cfg['voix_homme'], cfg['voix_femme']])
            self.assertIn('concat', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
