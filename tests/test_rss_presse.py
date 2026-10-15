"""Presse généraliste : filtre IA (FR + EN) et chapô ajouté au texte."""
from datetime import datetime, timezone
import unittest
from unittest import mock

from veille import sources
from veille.config import Settings


FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Les Echos</title>
<item><title>Mistral l\xc3\xa8ve 2 milliards</title><link>https://ex.fr/1</link>
<description>&lt;p&gt;La start-up d'intelligence artificielle fran\xc3\xa7aise...&lt;/p&gt;</description>
<pubDate>%s</pubDate></item>
<item><title>Le prix du cuivre recule</title><link>https://ex.fr/2</link>
<description>March\xc3\xa9s des m\xc3\xa9taux.</description><pubDate>%s</pubDate></item>
</channel></rss>"""


try:
    import feedparser  # noqa: F401
    HAS_FP = True
except ImportError:
    HAS_FP = False


class PresseTests(unittest.TestCase):
    @unittest.skipUnless(HAS_FP, 'feedparser absent')
    def setUp(self):
        pass

    def _fetch(self, ai_filter):
        now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000').encode()
        resp = mock.Mock(content=FEED % (now, now))
        resp.raise_for_status = mock.Mock()
        with mock.patch('veille.sources.requests.get', return_value=resp):
            return sources.fetch_rss(['https://ex.fr/rss'], lookback_hours=24, ai_filter=ai_filter)

    def test_filter_keeps_only_ai_and_adds_summary(self):
        items = self._fetch(True)
        self.assertEqual([i.url for i in items], ['https://ex.fr/1'])
        self.assertIn("intelligence artificielle", items[0].text)
        self.assertNotIn('<p>', items[0].text)

    def test_no_filter_keeps_all(self):
        self.assertEqual(len(self._fetch(False)), 2)

    def test_french_keywords(self):
        self.assertTrue(sources._looks_ai_related("L'IA générative arrive en PME"))
        self.assertFalse(sources._looks_ai_related("Le prix du cuivre recule"))

    def test_settings_load_filtered_feeds(self):
        from veille.config import load_settings
        s = load_settings('config.yaml')
        self.assertTrue(any('lesechos' in u for u in s.rss_feeds_filtres))
        self.assertIsInstance(s, Settings)


if __name__ == '__main__':
    unittest.main()
