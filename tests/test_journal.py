from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from veille import journal

DIGEST = """<b>📌 L'essentiel du jour</b>

🚀 <b>Mistral sort un modèle</b>
Texte <b>important</b> visible.
<blockquote expandable>🔎 <b>Pour aller plus loin —</b> Détails. Source : <a href="https://x.com/a">@a</a></blockquote>

<b>⚖️ La Californie poursuit OpenAI</b>
Autre texte.

<b>✨ La phrase du jour</b>
Une idée forte."""


class JournalTests(unittest.TestCase):
    def test_headlines_skip_fixed_sections_and_inline_bold(self):
        self.assertEqual(journal.headlines(DIGEST), ["🚀 Mistral sort un modèle", "⚖️ La Californie poursuit OpenAI"])

    def test_teaser_single_message_with_button(self):
        text, markup = journal.teaser(DIGEST, date(2026, 11, 17))
        self.assertIn("mardi 17 novembre 2026", text)
        self.assertNotIn("Détails", text)
        self.assertEqual(markup["inline_keyboard"][0][0]["url"],
                         "https://hl-consulting.tech/knowledge-hub/veille-ia/journal/2026-11-17/")

    def test_calm_day_keeps_short_note(self):
        text, markup = journal.teaser("Bonjour ☀️ Journée calme.", date(2026, 11, 17))
        self.assertIn("Journée calme", text); self.assertEqual(markup, {})

    def test_page_body(self):
        html = journal.body_html(DIGEST)
        self.assertIn('<h2 id="s1">🚀 Mistral sort un modèle</h2>', html)
        self.assertIn('<details class="jr-more"><summary>Pour aller plus loin</summary>', html)
        self.assertNotIn("essentiel du jour", html)
        self.assertIn('class="jr-quote-title"', html)

    def test_build_site_navigation_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            src, site = Path(d) / "j", Path(d) / "site"
            for day in (date(2026, 11, 16), date(2026, 11, 17)):
                journal.save(DIGEST, day, src)
            self.assertEqual(len(journal.build_site(src, site)), 2)
            page = (site / "knowledge-hub/veille-ia/journal/2026-11-16/index.html").read_text()
            self.assertIn("2026-11-17 →", page)
            self.assertEqual(journal.build_site(src, site), [])


if __name__ == "__main__":
    unittest.main()
