"""Real GTK regression tests. Run with VERSEWORK_GUI_TEST=1 under a display."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('VERSEWORK_GUI_TEST') == '1', 'Requires an explicitly enabled GTK display')
class WorkflowGuiTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.Gtk, self.GLib = app.Gtk, app.GLib
        self.folder = tempfile.TemporaryDirectory()
        with patch.object(app, 'DATA', Path(self.folder.name)):
            self.studio = app.Studio()
        self.studio.set_application_id('io.versework.Test' + Path(self.folder.name).name.replace('_', ''))
        self.studio.register(None)
        with patch.object(app, 'confirm_startup'):
            self.studio.activate()
        self.pump()

    def tearDown(self):
        for window in list(self.studio.get_windows()):
            window.destroy()
        self.studio.store.db.close()
        self.folder.cleanup()
        self.pump()

    def pump(self):
        context = self.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def widgets(self, widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from self.widgets(child)
            child = child.get_next_sibling()

    def click(self, window, caption):
        control = next(w for w in self.widgets(window) if isinstance(w, self.Gtk.Button) and w.get_label() == caption)
        control.emit('clicked')
        self.pump()

    def test_unlimited_new_song_and_unset_drums(self):
        self.studio.settings['rewrite_limit'] = None
        window = self.studio.new_dialog()
        views = [w for w in self.widgets(window) if isinstance(w, self.Gtk.TextView)]
        views[1].get_buffer().set_text('Acoustic folk')
        window.controls['suno_model'].set_selected(1)
        self.click(window, 'Create')
        self.assertIsNone(self.studio.project['limit'])
        self.assertIsNone(self.studio.project['tracks'][0]['production']['drums'])
        self.assertIsNone(self.studio.store.list()[0]['limit'])
        self.assertEqual(self.studio.project['tracks'][0]['suno_model'], 'v6-wild')

    def test_suno_model_selection_is_saved_and_used_for_rewrite_prompts(self):
        from core import create_project, commit_version, prompt_for
        from test_core import song
        project = create_project('Test', 'Folk', 1, 180, 240, 3)
        commit_version(project, 0, song(), 'initial')
        self.studio.store.save(project)
        self.studio.load_project(project['id'], 0)
        self.studio.suno_model_selector.set_selected(2)
        self.assertTrue(self.studio.flush())
        stored = self.studio.store.get(project['id'])
        self.assertEqual(stored['tracks'][0]['suno_model'], 'v6-mini')
        self.assertIn('v6-mini, concise', prompt_for(stored, 0, 'Keep this simple'))

    def test_settings_saves_v6_as_default_for_new_songs(self):
        window = self.studio.settings_dialog()
        self.assertEqual(window.controls['suno_default'].get_selected(), 0)
        window.controls['suno_default'].set_selected(2)
        window.controls['apply']()
        self.assertEqual(self.studio.settings['default_suno_model'], 'v6-mini')
        self.assertEqual(self.studio.new_dialog().controls['suno_model'].get_selected(), 2)

    def test_apply_existing_refreshes_open_song_and_survives_save(self):
        from core import create_project, commit_version
        from test_core import song
        project = create_project('Test', 'Folk', 1, 180, 240, 3)
        commit_version(project, 0, song(), 'initial')
        project['tracks'][0]['rewrites'] = 3
        self.studio.store.save(project)
        self.studio.load_project(project['id'], 0)
        window = self.studio.settings_dialog()
        window.controls['unlimited'].set_active(True)
        existing = next(w for w in self.widgets(window) if isinstance(w, self.Gtk.CheckButton) and w.get_label() == 'Apply this limit to existing songs')
        existing.set_active(True)
        window.controls['apply']()
        self.pump()
        self.assertIsNone(self.studio.project['limit'])
        self.assertTrue(self.studio.flush())
        self.assertIsNone(self.studio.store.list()[0]['limit'])
        self.assertFalse(window.get_visible())

    def test_unrelated_settings_do_not_overwrite_individual_limit(self):
        from core import create_project
        project = create_project('Test', 'Folk', 1, 180, 240, 9)
        self.studio.store.save(project)
        self.studio.load_project(project['id'], 0)
        window = self.studio.settings_dialog()
        window.controls['apply']()
        self.assertEqual(self.studio.project['limit'], 9)
        self.assertFalse(window.get_visible())

    def test_review_accepts_only_checked_changes(self):
        from test_core import song
        original, proposed = song('Saved'), song('Suggested')
        proposed['lyrics'] = '[Verse]\nProposed lyric changes'
        accepted, discarded = [], []
        self.studio.review_proposal(original, proposed, accepted.append, lambda: discarded.append(True))
        window = next(w for w in self.studio.get_windows() if w.get_title() == 'Review proposed changes')
        check = next(w for w in self.widgets(window) if isinstance(w, self.Gtk.CheckButton) and w.get_label() == 'Lyrics')
        check.set_active(False)
        self.click(window, 'Accept selected changes')
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['title'], proposed['title'])
        self.assertEqual(accepted[0]['lyrics'], original['lyrics'])
        self.assertEqual(discarded, [])

    def test_closing_proposal_discards_without_accepting(self):
        from test_core import song
        accepted, discarded = [], []
        self.studio.review_proposal(song('Saved'), song('Suggested'), accepted.append, lambda: discarded.append(True))
        window = next(w for w in self.studio.get_windows() if w.get_title() == 'Review proposed changes')
        window.close()
        self.pump()
        self.assertFalse(accepted)
        self.assertEqual(discarded, [True])
