import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('podcast_export', Path(__file__).parents[1] / 'scripts/export-podcast.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.dest = Path(self.temp.name) / 'dest'
        self.source.mkdir()
        self.data = dict(date='2026-10-12', destination='canal', telegram_sent=True,
                         court_telegram_sent=True, duration_seconds=60, court_duration_seconds=60)
        for file in ('brief.mp3', 'court.mp3'):
            (self.source / file).write_bytes(b'x' * 2048)
        self.data['artwork'] = {'date': self.data['date']}
        for kind, filename in [('short', 'court.mp3'), ('full', 'brief.mp3')]:
            for suffix in ('cover.jpg', 'cover.png', 'thumbnail.jpg'):
                (self.source / f'{kind}-{suffix}').write_bytes(b'picture')
            digest = hashlib.sha256(b'picture').hexdigest()
            self.data['artwork'][kind] = dict(seconds=60,
                image=f'/assets/podcast/archive/{self.data["date"]}/{kind}-cover-v2.jpg',
                image_sha256=digest, png_sha256=digest, thumbnail_sha256=digest,
                audio_sha256=hashlib.sha256((self.source / filename).read_bytes()).hexdigest())
        # Pixel/codec validation is exercised with real files in the media integration test.
        for name in ('image_info', 'validate_thumbnail'):
            mock = patch('veille.podcast_media.' + name)
            mock.start()
            self.addCleanup(mock.stop)
        self.save()

    def save(self):
        (self.source / 'brief.json').write_text(json.dumps(self.data))

    @patch.object(module.subprocess, 'check_output', return_value='60.2')
    def test_exports_only_public_manifest_and_audio(self, _):
        self.assertTrue(module.export(self.source, self.dest))
        manifest = json.loads((self.dest / 'latest.json').read_text())
        self.assertEqual(manifest['short']['seconds'], 60)
        self.assertEqual(set(p.name for p in self.dest.iterdir()), {'latest.json', 'short.mp3', 'full.mp3', 'archive', 'covers'})
        self.assertNotIn('telegram_sent', manifest)

    @patch.object(module.subprocess, 'check_output', return_value='60')
    def test_cover_lost_after_send_does_not_block_rss_export(self, _):
        (self.source / 'full-cover.jpg').unlink()
        self.assertTrue(module.export(self.source, self.dest))
        latest = json.loads((self.dest / 'latest.json').read_text())
        self.assertEqual(latest['artwork_status'], 'unavailable')
        self.assertNotIn('image', latest['full'])
        self.assertTrue((self.dest / 'full.mp3').is_file())

    def test_private_preview_and_unsent_pair_skipped(self):
        for key, value in [('destination', 'prive'), ('telegram_sent', False), ('court_telegram_sent', False)]:
            original = self.data[key]
            self.data[key] = value
            self.save()
            self.assertFalse(module.export(self.source, self.dest))
            self.assertFalse(self.dest.exists())
            self.data[key] = original

    @patch.object(module.subprocess, 'check_output', return_value='60')
    def test_missing_second_audio_preserves_current_pair(self, _):
        module.export(self.source, self.dest)
        original = (self.dest / 'latest.json').read_bytes()
        (self.source / 'brief.mp3').unlink()
        self.data['date'] = '2026-10-13'
        self.save()
        with self.assertRaises(ValueError):
            module.export(self.source, self.dest)
        self.assertEqual((self.dest / 'latest.json').read_bytes(), original)

    @patch.object(module.subprocess, 'check_output', return_value='60')
    def test_old_run_cannot_replace_newer_episode(self, _):
        module.export(self.source, self.dest)
        self.data['date'] = '2026-10-11'
        self.save()
        self.assertFalse(module.export(self.source, self.dest))

    @patch.object(module.subprocess, 'check_output', return_value='nan')
    def test_invalid_duration_is_rejected(self, _):
        with self.assertRaises(ValueError):
            module.export(self.source, self.dest)

if __name__ == '__main__':
    unittest.main()
