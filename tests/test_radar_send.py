import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from veille import radar_send

DIGEST = '<b>🚀 Mistral sort un modèle</b>\nTexte.\n\n<b>✨ La phrase du jour</b>\nIdée.'


class RadarSendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cwd = os.getcwd()
        Path(self.tmp.name, "config.yaml").write_text(Path("config.yaml").read_text())
        os.chdir(self.tmp.name); self.addCleanup(os.chdir, self.cwd); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "-1", "ANTHROPIC_API_KEY": "a",
                                           "TWITTERAPI_IO_KEY": "x"}); self.env.start(); self.addCleanup(self.env.stop)

    def write(self, digest=DIGEST):
        radar_send.PENDING.write_text(json.dumps({"date": "2026-11-18", "digest": digest, "message": "COMPLET"}))

    def status(self):
        return json.loads(radar_send.PENDING.read_text())

    def test_album_when_pages_render(self):
        self.write()
        with patch.object(radar_send, "wait_live", return_value=True), patch.object(radar_send, "fetch", return_value=None), \
             patch("veille.radar_pages.render", return_value=[Path("a.png"), Path("b.png")]), \
             patch.object(radar_send, "send_album", return_value=[{"message_id": 1}]) as album, \
             patch.object(radar_send, "send_message") as msg:
            radar_send.main()
        self.assertIn("Mistral sort un modèle", album.call_args.args[1]); msg.assert_not_called()
        self.assertEqual(self.status()["mode"], "album")
        with patch.object(radar_send, "send_album") as again:  # jamais deux fois
            radar_send.main()
        again.assert_not_called()

    def test_fallback_to_headlines_when_render_fails(self):
        self.write()
        with patch.object(radar_send, "wait_live", return_value=False), patch.object(radar_send, "fetch", return_value=None), \
             patch("veille.radar_pages.render", side_effect=RuntimeError("chromium")), \
             patch.object(radar_send, "send_message") as msg:
            radar_send.main()
        self.assertIn("Lire le journal", json.dumps(msg.call_args.kwargs["reply_markup"], ensure_ascii=False))
        self.assertEqual(self.status()["mode"], "titres")

    def test_uncertain_album_is_never_resent(self):
        self.write()
        with patch.object(radar_send, "wait_live", return_value=True), patch.object(radar_send, "fetch", return_value=None), \
             patch("veille.radar_pages.render", return_value=[Path("a.png")]), \
             patch.object(radar_send, "send_album", side_effect=RuntimeError("Album non confirmé ; pas de réessai automatique")), \
             patch.object(radar_send, "send_message") as msg:
            with self.assertRaises(RuntimeError):
                radar_send.main()
        msg.assert_not_called(); self.assertEqual(self.status()["status"], "uncertain")

    def test_calm_day_sends_short_note(self):
        self.write("Bonjour ☀️ Journée calme.")
        with patch.object(radar_send, "send_message") as msg:
            radar_send.main()
        self.assertEqual(msg.call_args.args[0], "COMPLET")


if __name__ == "__main__":
    unittest.main()
