"""A transient script outage is retried without ever retrying delivery."""
import unittest
from unittest.mock import Mock, patch
from veille import audio


def error(status):
    return audio.anthropic.APIStatusError('service error',
        response=Mock(status_code=status, headers={}), body={})


class ScriptRetryTests(unittest.TestCase):
    def test_529_then_success_preserves_request(self):
        client = Mock()
        client.messages.create.side_effect = [error(529), error(503), 'script']
        with patch.object(audio.time, 'sleep') as sleep:
            self.assertEqual(audio._script_request(client, messages=['original brief']), 'script')
        self.assertEqual(client.messages.create.call_count, 3)
        self.assertEqual([x.args[0] for x in sleep.call_args_list], [5, 15])
        self.assertTrue(all(x.kwargs == {'messages': ['original brief']} for x in client.messages.create.call_args_list))

    def test_permanent_error_is_not_retried(self):
        for status in (400, 401, 403, 404, 422):
            client = Mock(); client.messages.create.side_effect = error(status)
            with patch.object(audio.time, 'sleep') as sleep:
                with self.assertRaises(audio.anthropic.APIStatusError):
                    audio._script_request(client, model='test')
            self.assertEqual(client.messages.create.call_count, 1)
            sleep.assert_not_called()

    def test_outage_is_bounded_and_propagated(self):
        client = Mock(); client.messages.create.side_effect = error(529)
        with patch.object(audio.time, 'sleep') as sleep:
            with self.assertRaises(audio.anthropic.APIStatusError):
                audio._script_request(client)
        self.assertEqual(client.messages.create.call_count, 4)
        self.assertEqual([x.args[0] for x in sleep.call_args_list], [5, 15, 45])

    def test_delivery_job_and_bridge_failures_are_visible(self):
        from pathlib import Path
        import yaml
        workflow = yaml.safe_load(Path('.github/workflows/veille.yml').read_text())
        job = workflow['jobs']['audio']
        self.assertFalse(job.get('continue-on-error', False))
        for step in job['steps']:
            if step.get('name') == 'Publier les deux podcasts publics sur la home':
                self.assertFalse(step.get('continue-on-error', False))
