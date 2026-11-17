import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("weekly", Path(__file__).parents[1] / "scripts/iastro-weekly.py")
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)


def plan(**over):
    news = [{"id": f"n{i}", "brand_id": b, "sources": [{"url": "https://openai.com/x", "published_at": "2026-11-18"}],
             "panels": [{"scene_en": "s", "alt": "a", "dialogue": [{"speaker": "Iastro", "text": "t", "side": "left"}]}] * 6}
            for i, b in enumerate(["openai", "anthropic", "google", "meta"])]
    news[0].update(over)
    return {"news": news}


class WeeklyTests(unittest.TestCase):
    def test_week_of_sunday(self):
        self.assertEqual(w.week(dt.date(2026, 11, 22)), ("2026-W47", dt.date(2026, 11, 16), dt.date(2026, 11, 22)))

    def test_candidates_limited_to_week_and_sorted(self):
        feed = [{"date": "2026-11-15", "score": 99}, {"date": "2026-11-17", "score": 50}, {"date": "2026-11-20", "score": 80}]
        got = w.candidates(feed, dt.date(2026, 11, 16), dt.date(2026, 11, 22))
        self.assertEqual([c["score"] for c in got], [80, 50])

    def test_plan_ok_and_sides_forced(self):
        p = plan(); w.check_plan(p, dt.date(2026, 11, 16), dt.date(2026, 11, 22))
        self.assertEqual(p["news"][0]["panels"][0]["dialogue"][0]["side"], "right")

    def test_plan_rejects_tweet_source_unknown_brand_future_source(self):
        bad = [plan(sources=[{"url": "https://x.com/a", "published_at": "2026-11-18"}]),
               plan(brand_id="xai"),
               plan(sources=[{"url": "https://openai.com/x", "published_at": "2026-11-23"}]),
               plan(panels=[])]
        for p in bad:
            with self.assertRaises(AssertionError):
                w.check_plan(p, dt.date(2026, 11, 16), dt.date(2026, 11, 22))

    def test_index_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            kh = Path(d) / "knowledge-hub"; kh.mkdir()
            (kh / "sitemap.xml").write_text("<urlset>\n</urlset>\n")
            (kh / "llms.txt").write_text("- [iAstro Sunday — x](u): y\n\nfin\n")
            for _ in range(2):
                w.add_to_index(Path(d), "2026-W47", "16 novembre–22 novembre 2026", "Titre")
            self.assertEqual((kh / "sitemap.xml").read_text().count("<loc>"), 2)
            self.assertEqual((kh / "llms.txt").read_text().count("2026-W47"), 1)


class PortraitTests(unittest.TestCase):
    def test_next_month_portrait_only_last_week(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d); art = site / "assets/podcast/art"; art.mkdir(parents=True)
            (art / "manifest.json").write_text('{"portraits": [], "pending_months": [1, 2]}')
            (art / "prompts.json").write_text('{"portraits": {}}')
            (art / "iastro-12-v1.png").write_bytes(b"x")
            calls = []
            def fake(prompt, refs, ar, dest):
                calls.append(dest.name); dest.write_bytes(b"png"); return 1024, 1024
            orig, w.draw = w.draw, fake
            try:
                self.assertEqual(w.ensure_portraits(site, dt.date(2026, 12, 13), site), [])
                made = w.ensure_portraits(site, dt.date(2026, 12, 27), site)
                self.assertEqual(calls, ["iastro-01-v1.png"])
                self.assertIn("JANUARY", made[0][1])
                self.assertEqual(w.ensure_portraits(site, dt.date(2026, 12, 27), site), [])
            finally:
                w.draw = orig
            import json
            m = json.loads((art / "manifest.json").read_text())
            self.assertEqual(m["pending_months"], [2]); self.assertEqual(m["portraits"][0]["month"], 1)


if __name__ == "__main__":
    unittest.main()
