"""Hiérarchie des voix : grands patrons d'abord, commentateurs plafonnés (choix Hugo 15/10)."""
from datetime import datetime, timezone
import unittest

from veille import digest
from veille.config import Settings
from veille.twitter import Tweet


def tw(author, likes=0, source='x', i=[0]):
    i[0] += 1
    return Tweet(id=str(i[0]), author=author, text='t', url='https://x.com/a', created_at=datetime.now(timezone.utc),
                 like_count=likes, source=source)


class VoixTests(unittest.TestCase):
    def setUp(self):
        self.s = Settings(voix_majeures=['sama'], voix_secondaires=['garymarcus'], max_items_par_compte=3)

    def test_caps_per_account_and_commentators_keep_most_shared(self):
        items = [tw('GaryMarcus', n) for n in range(6)] + [tw('emollick', n) for n in range(5)] + \
                [tw('sama', 1)] + [tw('HN', 0, 'hn') for _ in range(5)]
        kept = digest.rebalance(items, self.s)
        marcus = [t.like_count for t in kept if t.author == 'GaryMarcus']
        self.assertEqual(sorted(marcus), [4, 5])
        self.assertEqual(len([t for t in kept if t.author == 'emollick']), 3)
        self.assertEqual(len([t for t in kept if t.source == 'hn']), 5)
        self.assertEqual([t.author for t in kept][:2], ['GaryMarcus', 'GaryMarcus'])  # ordre d'origine conservé

    def test_tags_and_prompt_hierarchy(self):
        text = digest._tweets_to_text([tw('sama'), tw('GaryMarcus'), tw('simonw')], self.s)
        self.assertIn('@sama [VOIX MAJEURE]', text)
        self.assertIn('@GaryMarcus [COMMENTATEUR]', text)
        self.assertNotIn('@simonw [', text)
        prompt = digest._system_prompt('detaille')
        self.assertIn('HIÉRARCHIE DES VOIX', prompt)
        self.assertIn('AU PLUS UNE FOIS', prompt)
        self.assertIn('DEUX fois au maximum', prompt)
        self.assertIn('selon le Financial', prompt)
        self.assertIn('Les Echos', prompt)

    def test_reddit_header(self):
        r = tw('ignored')
        r.source = 'rss'
        r.author = 'top scoring links : LocalLLaMA'
        r.url = 'https://www.reddit.com/r/LocalLLaMA/comments/abc/titre/'
        self.assertIn('Reddit r/LocalLLaMA', digest._tweets_to_text([r], self.s))


if __name__ == '__main__':
    unittest.main()
