from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from veille import audio, journal, semaine, telegram

DIGEST = '<b>🚀 Mistral</b>\nTexte <a href="https://mistral.ai/news">x</a>.'


class SemaineTests(unittest.TestCase):
    def test_bounds_and_label(self):
        self.assertEqual(semaine.week_bounds(date(2026, 11, 22)),
                         ("semaine-2026-W47", date(2026, 11, 16), date(2026, 11, 22)))
        self.assertEqual(semaine.period_label(date(2026, 11, 30), date(2026, 12, 6)), "du 30 novembre au 6 décembre")

    def test_snapshot_needs_enough_days(self):
        with tempfile.TemporaryDirectory() as d:
            for day in (16, 17):
                journal.save(DIGEST, date(2026, 11, day), d)
            with self.assertRaises(RuntimeError):
                semaine.week_snapshot(Path(d), date(2026, 11, 16), date(2026, 11, 22))
            journal.save(DIGEST, date(2026, 11, 18), d)
            journal.save(DIGEST, date(2026, 11, 23), d)  # semaine suivante : ignorée
            snap = semaine.week_snapshot(Path(d), date(2026, 11, 16), date(2026, 11, 22))
            self.assertEqual(snap["days"], 3); self.assertEqual(snap["sources"], ["https://mistral.ai/news"])
            self.assertNotIn("<b>", snap["text"])

    def test_private_by_default_then_public_publishes_feed_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); cwd = os.getcwd()
            (root / "config.yaml").write_text(Path("config.yaml").read_text())
            (root / "audio.yaml").write_text("format: iastro\nprovider: edge\n")
            for day in (16, 17, 18):
                journal.save(DIGEST, date(2026, 11, day), root / "journal")
            site = root / "site"; (site / "assets/podcast").mkdir(parents=True)
            provider = Mock(); provider.synthesize.side_effect = lambda s, o: o.write_bytes(b"mp3" * 400)
            os.chdir(root)
            try:
                common = [patch.object(audio, "build_script", return_value="IASTRO: Salut, c'est iAstro ! x\nVICTORIA: y\nIASTRO: z"),
                          patch.object(audio, "get_provider", return_value=provider),
                          patch.object(audio, "duration_seconds", return_value=980),
                          patch.object(audio, "_pieces", return_value=None),
                          patch.object(telegram, "send_audio", return_value={"message_id": 9})]
                for c in common: c.start()
                send = telegram.send_audio
                with patch.dict(os.environ, {"TELEGRAM_AUTHORIZED_USER_ID": "42", "WEEKLY_PUBLIC": ""}):
                    meta = semaine.run(date(2026, 11, 22), root / "out", send=True, site=site)
                self.assertEqual(send.call_args.kwargs["chat_id"], "42")
                self.assertIn("À VALIDER", send.call_args.kwargs["caption_suffix"])
                self.assertFalse((site / "assets/podcast/semaine/episodes.json").exists())
                with patch.dict(os.environ, {"TELEGRAM_AUTHORIZED_USER_ID": "42", "WEEKLY_PUBLIC": "true"}):
                    meta = semaine.run(date(2026, 11, 22), root / "out2", send=False, site=site)
                entry = json.loads((site / "assets/podcast/semaine/episodes.json").read_text())["episodes"][0]
                self.assertEqual((entry["id"], entry["date"], entry["full"]["seconds"]), ("semaine-2026-W47", "2026-11-22", 980))
                self.assertTrue((site / "assets/podcast/archive/semaine-2026-W47/full.mp3").is_file())
            finally:
                patch.stopall(); os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
