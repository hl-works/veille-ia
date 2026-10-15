"""Commande /apercu : aperçu privé du digest, jamais publié sur le canal."""
from datetime import datetime, timezone
import unittest
from unittest import mock

from veille import listen
from veille.config import Settings
from veille.twitter import Tweet


def item(source, url='https://x.com/a'):
    return Tweet(id=url, author='a', text='t', url=url, created_at=datetime.now(timezone.utc), source=source)


class ApercuTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(listen._parse_command('/apercu'), ('apercu', 0))
        self.assertEqual(listen._parse_command('/aperçu@MonBot'), ('apercu', 0))
        self.assertEqual(listen._parse_command('/maj 3'), ('maj', 3))

    def test_counts_split_reddit(self):
        counts = listen.source_counts([item('x'), item('rss', 'https://www.reddit.com/r/OpenAI/comments/1'),
                                       item('rss', 'https://openai.com/news/x'), item('hn')])
        self.assertEqual(counts, {'x': 1, 'reddit': 1, 'rss': 1, 'hn': 1})

    def test_preview_goes_to_private_chat_only(self):
        s = Settings(accounts=['sama'], telegram_bot_token='tok', telegram_chat_id='CANAL')
        with mock.patch('veille.twitter.collect_recent_tweets', return_value=[item('x')]), \
             mock.patch('veille.sources.collect_extra_sources', return_value=[]), \
             mock.patch('veille.digest.build_digest', return_value='corps'), \
             mock.patch('veille.telegram.send_message') as send:
            listen.run_preview(s, chat_id=123)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs['chat_id'], '123')
        self.assertIn('APERÇU — non publié', send.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
