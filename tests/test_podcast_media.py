"""The actual MP3/cover/Telegram/export chain, with network writes mocked."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from veille import audio, podcast_media as media, telegram
from veille.config import Settings


class MediaGuards(unittest.TestCase):
    def test_missing_renderer_blocks_before_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch.object(telegram.requests, 'post') as post:
            with self.assertRaisesRegex(RuntimeError, 'PODCAST_DESIGN_ROOT'):
                media.prepare_media(Path(directory), {})
            post.assert_not_called()

    def test_cover_failure_prevents_all_sends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            source.write_text(json.dumps(dict(date='2026-10-17', sources=['https://example.org'], text='Test')))
            provider = Mock()
            provider.synthesize.side_effect = lambda script, out: out.write_bytes(b'mp3')
            with patch.object(audio, 'build_script', return_value='Bonjour'), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', return_value=60), \
                 patch('veille.podcast_media.prepare_media', side_effect=ValueError('Missing cover')), \
                 patch.object(telegram, 'send_audio') as send, patch.object(telegram, 'send_message') as message:
                with self.assertRaisesRegex(ValueError, 'Missing cover'):
                    audio.run(source, root / 'out', Settings(), send=True)
                send.assert_not_called()
                message.assert_not_called()
                self.assertFalse(json.loads((root / 'out/brief.json').read_text())['telegram_sent'])

    def test_oversized_thumbnail_blocks_before_upload(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telegram.requests, 'post') as post:
            root = Path(directory)
            (root / 'a.mp3').write_bytes(b'audio')
            (root / 'thumb.jpg').write_bytes(b'x' * 200_000)
            with self.assertRaises(ValueError):
                telegram.send_audio(root / 'a.mp3', thumbnail=root / 'thumb.jpg', day='2026-10-17',
                                    duration=60, bot_token='not-a-token', chat_id='test')
            post.assert_not_called()


@unittest.skipUnless(os.environ.get('PODCAST_MEDIA_TEST') == '1', 'Real media integration runs in CI')
class MediaIntegration(unittest.TestCase):
    def test_same_artwork_in_mp3_telegram_and_rss(self):
        design = Path(os.environ['PODCAST_DESIGN_ROOT']).resolve()
        day = '2026-10-17'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'audio'
            output.mkdir()
            metadata = dict(date=day, destination='canal', telegram_sent=False, court_telegram_sent=False)
            original = {}
            for kind, (filename, duration_key) in media.TRACKS.items():
                shutil.copyfile(design / f'assets/podcast/archive/{day}/{kind}.mp3', output / filename)
                metadata[duration_key] = audio.duration_seconds(output / filename)
                original[kind] = media.audio_hash(output / filename)
            media.prepare_media(output, metadata)
            (output / 'brief.json').write_text(json.dumps(metadata))
            for kind, (filename, _) in media.TRACKS.items():
                self.assertEqual(media.audio_hash(output / filename), original[kind])
            # Inspect multipart bytes while file handles are still open.
            uploads = []
            def capture(url, **kwargs):
                self.assertTrue(url.endswith('/sendAudio'))
                uploads.append({k: value[1].read() for k, value in kwargs['files'].items()})
                return Mock(ok=True, json=lambda: {'ok': True})
            with patch.object(telegram.requests, 'post', side_effect=capture):
                for kind, (filename, key) in media.TRACKS.items():
                    telegram.send_audio(output / filename, thumbnail=output / f'{kind}-thumbnail.jpg',
                                        day=day, duration=metadata[key], bot_token='test', chat_id='test')
            for i, (kind, (filename, _)) in enumerate(media.TRACKS.items()):
                self.assertEqual(uploads[i]['audio'], (output / filename).read_bytes())
                self.assertEqual(uploads[i]['thumbnail'], (output / f'{kind}-thumbnail.jpg').read_bytes())
            metadata.update(telegram_sent=True, court_telegram_sent=True)
            (output / 'brief.json').write_text(json.dumps(metadata))
            spec = importlib.util.spec_from_file_location('export_media', Path(__file__).parents[1] / 'scripts/export-podcast.py')
            exporter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(exporter)
            site = root / 'site'
            dest = site / 'assets/podcast'
            self.assertTrue(exporter.export(output, dest))
            for name in ('show.json', 'show-cover-v1.jpg'):
                shutil.copyfile(design / 'assets/podcast' / name, dest / name)
            (dest / 'episodes.json').write_text(json.dumps({'episodes': []}))
            subprocess.run([os.sys.executable, str(design / 'scripts/build_podcast_feed.py'),
                            '--root', str(site), '--archive-latest'], check=True)
            before = (dest / 'feed.xml').read_bytes()
            for i, (kind, (filename, _)) in enumerate(media.TRACKS.items()):
                self.assertEqual((dest / f'archive/{day}/{kind}.mp3').read_bytes(), uploads[i]['audio'])
                self.assertEqual((dest / f'archive/{day}/{kind}-cover-v2.jpg').read_bytes(),
                                 (output / f'{kind}-cover.jpg').read_bytes())
            self.assertIn(b'full-cover-v2.jpg', before)
            exporter.export(output, dest)
            subprocess.run([os.sys.executable, str(design / 'scripts/build_podcast_feed.py'),
                            '--root', str(site), '--archive-latest'], check=True)
            self.assertEqual((dest / 'feed.xml').read_bytes(), before)
            # A date/duration mismatch or changed file can never be exported.
            for mutate in ('date', 'duration', 'audio', 'image'):
                altered = json.loads(json.dumps(metadata))
                target = None
                if mutate == 'date': altered['artwork']['date'] = '2026-10-18'
                elif mutate == 'duration': altered['duration_seconds'] += 1
                else:
                    target = output / ('brief.mp3' if mutate == 'audio' else 'full-cover.jpg')
                    saved = target.read_bytes()
                    target.write_bytes(saved + b'changed')
                with self.assertRaises(ValueError): media.validate_prepared(output, altered)
                if target: target.write_bytes(saved)
            if os.environ.get('PODCAST_MEDIA_PREVIEW_DIR'):
                shutil.copytree(output, os.environ['PODCAST_MEDIA_PREVIEW_DIR'], dirs_exist_ok=True)


if __name__ == '__main__':
    unittest.main()
