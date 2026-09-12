import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from veille import audio, main, telegram
from veille.config import Settings
from veille.qwen_tts import chunks

MESSAGE = '<b>Agents IA</b>\nUn outil facilite les tests.\n<a href="https://example.org/source">Source</a>'


class AudioTests(unittest.TestCase):
    def test_snapshot_exact_final_selection_and_calm_day(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'brief.json'
            audio.save_snapshot('Rien à signaler.', '10/09/2026', str(target))
            self.assertFalse(target.exists())
            audio.save_snapshot(MESSAGE, '10/09/2026', str(target))
            data = json.loads(target.read_text())
            self.assertEqual(data['message'], MESSAGE)
            self.assertEqual(data['sources'], ['https://example.org/source'])
            self.assertEqual(data['date'], '2026-09-10')
            self.assertNotIn('<b>', data['text'])

    def test_main_handoff_order_and_failure_isolation(self):
        settings = Settings(accounts=['OpenAI'], anthropic_api_key='test',
                            twitterapi_io_key='test', telegram_bot_token='test', telegram_chat_id='test')
        for fail_send, fail_snapshot, dry in [(False, False, False), (True, False, False),
                                               (False, True, False), (False, False, True)]:
            events = []
            def send(*args, **kwargs):
                events.append('written')
                if fail_send:
                    raise RuntimeError('test')
            def snapshot(*args):
                events.append('snapshot')
                if fail_snapshot:
                    raise OSError('disk full')
            with self.subTest(fail_send=fail_send, fail_snapshot=fail_snapshot, dry=dry), \
                 patch.dict('os.environ', {'DAILY_AUDIO_BRIEF': 'true', 'AUDIO_PREVIEW': ''}), \
                 patch.object(main, 'load_settings', return_value=settings), \
                 patch.object(main, 'collect_recent_tweets', return_value=[]), \
                 patch.object(main, 'collect_extra_sources', return_value=[]), \
                 patch.object(main, 'send_message', side_effect=send), \
                 patch.object(audio, 'save_snapshot', side_effect=snapshot), \
                 contextlib.redirect_stdout(io.StringIO()):
                settings.send_when_empty = True
                self.assertEqual(main.run('config.yaml', dry_run=dry), 0)
            self.assertEqual(events, [] if dry else ['written'] if fail_send else ['written', 'snapshot'])

    def test_script_only_receives_final_brief_and_rejects_truncation(self):
        response = SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text='Bonjour.')])
        client = Mock()
        client.messages.create.return_value = response
        with patch.object(audio.anthropic, 'Anthropic') as factory:
            factory.return_value.__enter__.return_value = client
            snapshot = {'date': '2026-09-10', 'text': 'SÉLECTION FINALE'}
            self.assertEqual(audio.build_script(snapshot, Settings()), 'Bonjour.')
            sent = client.messages.create.call_args.kwargs['messages'][0]['content']
            self.assertEqual(json.loads(sent)['brief'], 'SÉLECTION FINALE')
            response.stop_reason = 'max_tokens'
            with self.assertRaises(RuntimeError):
                audio.build_script(snapshot, Settings())

    def test_tts_timeout_is_bounded(self):
        import subprocess
        with patch.object(audio.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tts', 1200)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                audio.QwenTTS().synthesize(Path('script'), Path('output'))
            self.assertEqual(run.call_args.kwargs['timeout'], 1200)

    def test_chunks_preserve_all_words(self):
        script = ('Une information importante mérite une explication.\n' * 100)
        result = chunks(script, 90)
        self.assertEqual(' '.join(result).split(), script.split())
        self.assertTrue(all(len(part) <= 90 for part in result))

    def test_pipeline_test_mode_never_sends_and_archive_escapes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'input.json'
            audio.save_snapshot(MESSAGE, '10/09/2026', str(snapshot))
            provider = Mock()
            provider.synthesize.side_effect = lambda script, out: out.write_bytes(b'mp3')
            with patch.object(audio, 'build_script', return_value='<script>alert(1)</script>'), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', return_value=252), \
                 patch.object(telegram, 'send_audio') as send:
                audio.run(snapshot, root / 'out', Settings())
                send.assert_not_called()
                page = (root / 'out/index.html').read_text()
                self.assertNotIn('<script>', page)
                self.assertIn('&lt;script&gt;', page)
                self.assertIn('4 min 12', page)

    def test_tts_failure_prevents_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            audio.save_snapshot(MESSAGE, '10/09/2026', str(source))
            provider = Mock()
            provider.synthesize.side_effect = RuntimeError('TTS down')
            with patch.object(audio, 'build_script', return_value='Bonjour.'), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(telegram, 'send_audio') as send:
                with self.assertRaises(RuntimeError):
                    audio.run(source, root / 'out', Settings(), send=True)
                send.assert_not_called()

    def test_telegram_native_player_and_redacted_network_errors(self):
        import requests
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'brief.mp3'
            path.write_bytes(b'mp3')
            response = Mock(ok=True)
            response.json.return_value = {'ok': True}
            with patch.object(telegram.requests, 'post', return_value=response) as post:
                telegram.send_audio(path, day='2026-09-10', duration=252, bot_token='SECRET', chat_id='chat')
                self.assertTrue(post.call_args.args[0].endswith('/sendAudio'))
                self.assertEqual(post.call_args.kwargs['data']['caption'], '🎧 Brief IA — 10 septembre · 4 min 12')
                self.assertEqual(post.call_args.kwargs['files']['audio'][2], 'audio/mpeg')
            with patch.object(telegram.requests, 'post', side_effect=requests.Timeout('URL SECRET')) as post:
                with self.assertRaises(RuntimeError) as error:
                    telegram.send_audio(path, day='2026-09-10', duration=252, bot_token='SECRET', chat_id='chat')
                self.assertNotIn('SECRET', str(error.exception))
                self.assertEqual(post.call_count, 1)

    def test_audio_preview_needs_no_telegram_credentials(self):
        settings = Settings(accounts=['OpenAI'], anthropic_api_key='test', twitterapi_io_key='test')
        with patch.dict('os.environ', {'AUDIO_PREVIEW': 'true'}), \
             patch.object(main, 'load_settings', return_value=settings), \
             patch.object(main, 'collect_recent_tweets', return_value=[]), \
             patch.object(main, 'collect_extra_sources', return_value=[SimpleNamespace(created_at=None)]), \
             patch.object(main, 'build_digest', return_value=MESSAGE), \
             patch.object(main, 'send_message') as send, \
             patch.object(audio, 'save_snapshot') as snapshot, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main.run('config.yaml', dry_run=True), 0)
            send.assert_not_called()
            snapshot.assert_called_once()
            self.assertIn(MESSAGE, snapshot.call_args.args[0])

    def test_flag_off_no_snapshot(self):
        settings = Settings(accounts=['OpenAI'], anthropic_api_key='test', twitterapi_io_key='test',
                            telegram_bot_token='test', telegram_chat_id='test', send_when_empty=True)
        with patch.dict('os.environ', {'DAILY_AUDIO_BRIEF': 'false'}), \
             patch.object(main, 'load_settings', return_value=settings), \
             patch.object(main, 'collect_recent_tweets', return_value=[]), \
             patch.object(main, 'collect_extra_sources', return_value=[]), \
             patch.object(main, 'send_message'), patch.object(audio, 'save_snapshot') as snapshot:
            self.assertEqual(main.run('config.yaml', dry_run=False), 0)
            snapshot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
