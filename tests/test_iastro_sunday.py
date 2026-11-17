import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sunday", Path(__file__).parents[1] / "scripts/announce-iastro-sunday.py")
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

SUNDAY = dt.datetime(2026, 11, 22, 8, 10, tzinfo=a.PARIS)   # dimanche W47
MONDAY = dt.datetime(2026, 11, 23, 8, 10, tzinfo=a.PARIS)
PAGE = "https://hl-consulting.tech/knowledge-hub/comics/2026-W47/"


class SundayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.calls, self.saved = [], []

    def api(self, method, payload):
        self.calls.append((method, payload))
        if method == "getMe": return {"id": 123}
        if method == "getChat": return {"id": -1001, "type": "channel", "username": "VeilleIA_HL", "title": "Le Radar iA · iAstro"}
        if method == "getChatMember": return {"can_post_messages": True}
        if method in ("sendPhoto", "sendMessage"): return {"message_id": 400, "chat": {"id": -1001}}
        raise AssertionError(method)

    def save(self, record, receipt):
        self.saved.append(record["status"]); receipt.write_text(json.dumps(record))

    def run_main(self, argv, when=SUNDAY, issue="2026-W47", cover="https://x/cover.png", history="rien"):
        with patch.object(a, "RECEIPTS", self.dir), patch.object(a, "tg", self.api), \
             patch.object(a, "persist", self.save), patch.object(a, "now_paris", return_value=when), \
             patch.object(a, "latest_issue", return_value=(issue, PAGE)), \
             patch.object(a, "history_check", return_value=(history, [])), \
             patch.object(a, "verify_live", return_value=(cover, "sha" if cover else None)), \
             patch.dict(a.os.environ, {"TELEGRAM_CHANNEL_ID": "-1001"}), patch("sys.argv", ["x"] + argv):
            a.main()

    def sends(self):
        return [m for m, _ in self.calls if m.startswith("send")]

    def test_not_sunday_does_nothing(self):
        self.run_main(["--send", "--only-sunday"], when=MONDAY)
        self.assertEqual(self.calls, [])

    def test_sunday_sends_once_then_noop(self):
        self.run_main(["--send", "--only-sunday"])
        self.assertEqual(self.saved, ["reserved", "sent"]); self.assertEqual(self.sends(), ["sendPhoto"])
        self.run_main(["--send", "--only-sunday"])
        self.assertEqual(self.sends(), ["sendPhoto"])

    def test_stale_issue_is_not_reannounced(self):
        self.run_main(["--send", "--only-sunday"], issue="2026-W42")
        self.assertEqual(self.calls, [])

    def test_previous_week_still_ok(self):
        self.run_main(["--send", "--only-sunday"], issue="2026-W46")
        self.assertEqual(self.sends(), ["sendPhoto"])

    def test_no_cover_falls_back_to_text(self):
        self.run_main(["--send"], cover=None)
        self.assertEqual(self.sends(), ["sendMessage"])

    def test_dry_run_sends_nothing(self):
        self.run_main([])
        self.assertEqual(self.sends(), []); self.assertEqual(self.saved, [])

    def test_already_visible_in_channel(self):
        self.run_main(["--send"], history=PAGE)
        self.assertEqual(self.sends(), [])

    def test_reserved_blocks_retry(self):
        (self.dir / "2026-W47.json").write_text('{"status":"reserved"}')
        with self.assertRaises(RuntimeError):
            self.run_main(["--send"])
        self.assertEqual(self.calls, [])

    def test_is_recent_across_year(self):
        self.assertTrue(a.is_recent("2026-W53", dt.date(2027, 1, 3)))
        self.assertTrue(a.is_recent("2026-W53", dt.date(2027, 1, 10)))
        self.assertTrue(a.is_recent("2026-W47-r2", dt.date(2026, 11, 22)))
        self.assertFalse(a.is_recent("2026-W45", dt.date(2026, 11, 22)))


if __name__ == "__main__":
    unittest.main()
