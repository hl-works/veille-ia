import unittest
from unittest.mock import Mock, patch

from veille import http_retry


class PostRetryTests(unittest.TestCase):
    def test_retries_on_busy_then_succeeds(self):
        busy, ok = Mock(status_code=429), Mock(status_code=200)
        with patch.object(http_retry.requests, 'post', side_effect=[busy, busy, ok]) as post, \
             patch.object(http_retry.time, 'sleep') as sleep:
            self.assertIs(http_retry.post('u'), ok)
        self.assertEqual(post.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10, 20])

    def test_client_error_returned_immediately(self):
        bad = Mock(status_code=401)
        with patch.object(http_retry.requests, 'post', return_value=bad) as post, \
             patch.object(http_retry.time, 'sleep'):
            self.assertIs(http_retry.post('u'), bad)
        self.assertEqual(post.call_count, 1)


if __name__ == '__main__':
    unittest.main()
