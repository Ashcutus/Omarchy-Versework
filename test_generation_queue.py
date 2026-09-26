"""Queue lifecycle tests without a desktop or model process."""
import copy
import threading
import unittest
from unittest.mock import Mock, patch

from core import commit_version, create_project
from generation_ui import GenerationMixin
from test_core import song


class QueueHarness(GenerationMixin):
    def __init__(self, projects):
        self.projects = {p['id']: copy.deepcopy(p) for p in projects}
        self.project = copy.deepcopy(projects[0])
        self.busy = False
        self.settings = {'model': 'local'}
        self.failed_jobs = []
        self.collection_id = None
        self.finished = threading.Event()
        self.store = Mock()
        self.store.list.side_effect = lambda: list(copy.deepcopy(self.projects).values())
        self.store.save.side_effect = lambda p: self.projects.update({p['id']: copy.deepcopy(p)})
        self.store.generation_context.side_effect = lambda p, *args: copy.deepcopy(p)
        self.ollama = Mock()
        self.ollama.models.return_value = ['local']
        for key in ('spinner', 'stop_button', 'content', 'sidebar', 'retry_button'):
            setattr(self, key, Mock())
        self.notify = Mock()
        self.show_generation_error = Mock()
        self.flush = lambda: True
        self.render_project = Mock()
        self.review_proposal = lambda original, proposed, accept, discard, **kwargs: accept(proposed)

    def finish(self, message, error=False):
        super().finish(message, error)
        self.finished.set()


class QueueTests(unittest.TestCase):
    def project(self):
        return create_project('Test', 'Folk', 1, 180, 240, None)

    def idle(self, callback, *args):
        callback(*args)

    def test_new_work_retains_previous_failed_jobs(self):
        old, new = self.project(), self.project()
        studio = QueueHarness([old, new])
        prior = (old['id'], 0, 'Earlier feedback', 'sound', None)
        studio.failed_jobs = [prior]
        with patch('generation_ui.GLib.idle_add', self.idle), patch('generation_ui.generate_song', return_value=song()):
            studio.start_jobs([], song_jobs=[(new['id'], 0)])
            self.assertTrue(studio.finished.wait(2))
        self.assertEqual(studio.failed_jobs, [prior])
        self.assertEqual(studio.store.save_jobs.call_args.args[0], [prior])
        self.assertIsNotNone(studio.projects[new['id']]['tracks'][0]['current'])

    def test_retry_preserves_each_job_feedback_and_scope(self):
        first, second = self.project(), self.project()
        studio = QueueHarness([first, second])
        studio.failed_jobs = [(first['id'], 0, 'First feedback', 'sound', None),
                              (second['id'], 0, 'Second feedback', 'lyrics', None)]
        with patch('generation_ui.GLib.idle_add', self.idle), patch('generation_ui.generate_song', return_value=song()) as generate:
            studio.retry_failed()
            self.assertTrue(studio.finished.wait(2))
        self.assertEqual([c.args[4] for c in generate.call_args_list], ['First feedback', 'Second feedback'])
        self.assertEqual([c.kwargs['scope'] for c in generate.call_args_list], ['sound', 'lyrics'])
        self.assertEqual(studio.failed_jobs, [])

    def test_stop_during_discovery_keeps_current_and_remaining(self):
        first, second = self.project(), self.project()
        studio = QueueHarness([first, second])
        entered, release = threading.Event(), threading.Event()
        def models():
            entered.set()
            release.wait(2)
            return ['local']
        studio.ollama.models.side_effect = models
        try:
            with patch('generation_ui.GLib.idle_add', self.idle), patch('generation_ui.generate_song') as generate:
                studio.start_jobs([], song_jobs=[(first['id'], 0), (second['id'], 0)])
                self.assertTrue(entered.wait(1))
                studio.stop()
                self.assertTrue(studio.finished.wait(1))
                generate.assert_not_called()
            self.assertEqual({job[0] for job in studio.failed_jobs}, {first['id'], second['id']})
        finally:
            release.set()

    def test_mixed_batch_saves_successes_and_retries_only_failure(self):
        projects = [self.project() for _ in range(3)]
        studio = QueueHarness(projects)
        studio.ollama.generate.side_effect = [song('First'), RuntimeError('Model failed'), song('Third')]
        with patch('generation_ui.GLib.idle_add', self.idle):
            studio.start_jobs([], song_jobs=[(p['id'], 0) for p in projects])
            self.assertTrue(studio.finished.wait(2))
            self.assertEqual(studio.projects[projects[0]['id']]['tracks'][0]['current']['title'], 'First')
            self.assertIsNone(studio.projects[projects[1]['id']]['tracks'][0]['current'])
            self.assertEqual(studio.projects[projects[2]['id']]['tracks'][0]['current']['title'], 'Third')
            self.assertEqual([job[0] for job in studio.failed_jobs], [projects[1]['id']])
            studio.show_generation_error.assert_called_once()
            self.assertIn('Model failed', studio.show_generation_error.call_args.args[0])
            studio.finished.clear()
            studio.ollama.generate.side_effect = None
            studio.ollama.generate.return_value = song('Recovered')
            studio.retry_failed()
            self.assertTrue(studio.finished.wait(2))
        self.assertEqual(studio.ollama.generate.call_count, 4)
        self.assertEqual(studio.projects[projects[1]['id']]['tracks'][0]['current']['title'], 'Recovered')
        self.assertFalse(studio.failed_jobs)

    def test_discarded_rewrite_does_not_spend_allowance_or_change_history(self):
        project = self.project()
        commit_version(project, 0, song('Saved'), 'initial')
        studio = QueueHarness([project])
        studio.ollama.generate.return_value = song('Proposed')
        studio.review_proposal = lambda original, proposed, accept, discard, **kwargs: discard()
        with patch('generation_ui.GLib.idle_add', self.idle):
            studio.start_jobs([0], 'Try another title')
            self.assertTrue(studio.finished.wait(2))
        track = studio.projects[project['id']]['tracks'][0]
        self.assertEqual(track['current']['title'], 'Saved')
        self.assertEqual(track['rewrites'], 0)
        self.assertEqual(len(track['versions']), 1)
        self.assertFalse(studio.failed_jobs)

    def test_initial_suggestions_can_keep_original_lyrics(self):
        project = self.project()
        project['tracks'][0]['lyrics_source'] = '[Verse]\nMy own original words'
        studio = QueueHarness([project])
        studio.ollama.generate.return_value = song('Suggested')
        def keep_original(original, proposed, accept, discard, allow_unchanged=False):
            self.assertTrue(allow_unchanged)
            self.assertNotEqual(original['lyrics'], proposed['lyrics'])
            accept(original)
        studio.review_proposal = keep_original
        with patch('generation_ui.GLib.idle_add', self.idle):
            studio.start_jobs([0])
            self.assertTrue(studio.finished.wait(2))
        track = studio.projects[project['id']]['tracks'][0]
        self.assertEqual(track['current']['lyrics'], project['tracks'][0]['lyrics_source'])
        self.assertEqual(track['rewrites'], 0)
        self.assertEqual(len(track['versions']), 1)
