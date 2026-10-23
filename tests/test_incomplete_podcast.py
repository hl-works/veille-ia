"""Repair casting before synthesis; partial success must not appear complete."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from veille import audio, telegram
from veille.config import Settings

VALID = 'IASTRO: Salut, c’est iAstro !\nVICTORIA: Les nouvelles.\nIASTRO: À demain.'
INVALID = 'IASTRO: Salut, c’est iAstro !\nVICTORIA: Les nouvelles.\n---\nIASTRO: À demain.'

def response(text):
    return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)])

class IncompletePodcastTests(unittest.TestCase):
    def test_repairs_roles_before_synthesis_using_same_brief(self):
        client = Mock()
        client.messages.create.side_effect = [response(INVALID), response(VALID)]
        with patch.object(audio.anthropic, 'Anthropic') as factory:
            factory.return_value.__enter__.return_value = client
            result = audio.build_script({'date':'2026-10-19','text':'SOURCE UNIQUE'}, Settings(), 'iastro', 'courte')
        self.assertEqual(result, VALID)
        calls = client.messages.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs['messages'][0], calls[1].kwargs['messages'][0])
        self.assertEqual(calls[1].kwargs['messages'][1]['content'], INVALID)

    def test_repair_is_bounded_and_validation_stays_strict(self):
        client = Mock(); client.messages.create.return_value = response(INVALID)
        with patch.object(audio.anthropic, 'Anthropic') as factory:
            factory.return_value.__enter__.return_value = client
            with self.assertRaises(ValueError):
                audio.build_script({'date':'2026-10-19','text':'SOURCE'}, Settings(), 'iastro', 'courte')
        self.assertEqual(client.messages.create.call_count, 3)

    def test_missing_flash_keeps_full_receipt_but_fails_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'input.json'; output=root/'out'
            source.write_text(json.dumps({'date':'2026-10-19','text':'News','sources':['https://example.org/news']}))
            cfg={**audio.DEFAULT_AUDIO,'version_courte':'true','destination':'canal'}
            def render(script, provider, path, pieces): path.write_bytes(b'audio')
            receipt={'message_id':123}
            with patch.object(audio,'build_script',side_effect=['News',ValueError('Invalid roles')]), \
                 patch.object(audio,'get_provider'), patch.object(audio,'_pieces',return_value=None), \
                 patch.object(audio,'render',side_effect=render), patch.object(audio,'duration_seconds',return_value=60), \
                 patch.object(audio,'write_archive'), patch('veille.podcast_media.prepare_with_fallback'), \
                 patch.object(telegram,'send_audio',return_value=receipt) as send:
                with self.assertRaisesRegex(RuntimeError,'Flash manquant'):
                    audio.run(source,output,Settings(telegram_bot_token='test',telegram_chat_id='test'),send=True,cfg=cfg)
            self.assertEqual(send.call_count,1)
            data=json.loads((output/'brief.json').read_text())
            self.assertTrue(data['telegram_sent'])
            self.assertEqual(data['telegram_receipt'],receipt)
            self.assertFalse(data['audio_complete'])
            self.assertTrue((output/'brief.mp3').exists())
