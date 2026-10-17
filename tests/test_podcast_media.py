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

    def test_cover_failure_restores_audio_and_pipeline_sends_without_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            source.write_text(json.dumps(dict(date='2026-10-17', sources=['https://example.org'], text='Test')))
            provider = Mock()
            provider.synthesize.side_effect = lambda script, out: out.write_bytes(b'original-audio')
            def broken_prepare(output, metadata):
                (output / 'brief.mp3').write_bytes(b'broken-remux')
                metadata['artwork'] = {'partial': True}
                raise ValueError('Missing cover')
            with patch.object(audio, 'build_script', return_value='Bonjour'), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', return_value=60), \
                 patch.object(media, 'validate_audio', side_effect=lambda p, seconds: media.sha(p)), \
                 patch.object(media, 'prepare_media', side_effect=broken_prepare), \
                 patch.object(telegram, 'send_audio', return_value={}) as send:
                settings = Settings(telegram_bot_token='test')
                with patch.dict(os.environ, {'TELEGRAM_AUTHORIZED_USER_ID': 'test'}):
                    audio.run(source, root / 'out', settings, send=True)
                send.assert_called_once()
                self.assertIsNone(send.call_args.kwargs['thumbnail'])
                self.assertEqual((root / 'out/brief.mp3').read_bytes(), b'original-audio')
                metadata = json.loads((root / 'out/brief.json').read_text())
                self.assertTrue(metadata['telegram_sent'])
                self.assertEqual(metadata['artwork_status'], 'unavailable')
                self.assertNotIn('artwork', metadata)

    def test_invalid_audio_still_blocks(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(media, 'prepare_media') as render:
            root = Path(directory)
            (root / 'brief.mp3').write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                media.prepare_with_fallback(root, {'duration_seconds': 60, 'court_duration_seconds': 0})
            render.assert_not_called()

    def test_oversized_thumbnail_sends_audio_without_thumbnail(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telegram.requests, 'post') as post:
            root = Path(directory)
            (root / 'a.mp3').write_bytes(b'audio')
            (root / 'thumb.jpg').write_bytes(b'x' * 200_000)
            post.return_value = Mock(ok=True, json=lambda: {'ok': True})
            telegram.send_audio(root / 'a.mp3', thumbnail=root / 'thumb.jpg', day='2026-10-17',
                                duration=60, bot_token='not-a-token', chat_id='test')
            post.assert_called_once()
            self.assertNotIn('thumbnail', post.call_args.kwargs['files'])


@unittest.skipUnless(os.environ.get('PODCAST_MEDIA_TEST') == '1', 'Real media integration runs in CI')
class MediaIntegration(unittest.TestCase):
    def test_missing_month_still_delivers_unchanged_audio_to_telegram_and_rss(self):
        design = Path(os.environ['PODCAST_DESIGN_ROOT']).resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'audio'
            output.mkdir()
            metadata = dict(date='2027-01-01', destination='canal', telegram_sent=False, court_telegram_sent=False)
            originals = {}
            for kind, (filename, key) in media.TRACKS.items():
                shutil.copyfile(design / f'assets/podcast/archive/2026-10-17/{kind}.mp3', output / filename)
                metadata[key] = audio.duration_seconds(output / filename)
                originals[kind] = (output / filename).read_bytes()
            media.prepare_with_fallback(output, metadata)
            self.assertEqual(metadata['artwork_status'], 'unavailable')
            self.assertNotIn('artwork', metadata)
            with patch.object(telegram.requests, 'post', return_value=Mock(ok=True, json=lambda: {'ok': True})) as post:
                for kind, (filename, key) in media.TRACKS.items():
                    self.assertEqual((output / filename).read_bytes(), originals[kind])
                    telegram.send_audio(output / filename, day=metadata['date'], duration=metadata[key],
                                        bot_token='test', chat_id='test')
                self.assertEqual(post.call_count, 2)
                self.assertTrue(all('thumbnail' not in c.kwargs['files'] for c in post.call_args_list))
            metadata.update(telegram_sent=True, court_telegram_sent=True)
            (output / 'brief.json').write_text(json.dumps(metadata))
            spec = importlib.util.spec_from_file_location('fallback_export', Path(__file__).parents[1] / 'scripts/export-podcast.py')
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
            import xml.etree.ElementTree as ET
            rss = ET.parse(dest / 'feed.xml')
            self.assertIsNone(rss.find('./channel/item/{http://www.itunes.com/dtds/podcast-1.0.dtd}image'))
            self.assertIsNotNone(rss.find('./channel/{http://www.itunes.com/dtds/podcast-1.0.dtd}image'))
            for kind in media.TRACKS:
                self.assertEqual((dest / f'archive/2027-01-01/{kind}.mp3').read_bytes(), originals[kind])
            (output / 'brief.mp3').write_bytes(originals['full'] + b'changed')
            with self.assertRaisesRegex(ValueError, 'audio changed'):
                exporter.export(output, dest)

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
            media.prepare_with_fallback(output, metadata)
            self.assertEqual(metadata['artwork_status'], 'ready')
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
