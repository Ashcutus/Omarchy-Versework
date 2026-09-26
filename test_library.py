import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from string import Formatter
from core import Store, create_project, make_collection, commit_version, prompt_for
from appearance import read_palette, colour_css, mix_colour, resolved_palette, text_on
import i18n
from test_core import song


class LibraryTests(unittest.TestCase):
    def test_legacy_collections_migrate_once_without_changing_songs(self):
        with tempfile.TemporaryDirectory() as folder:
            p = create_project('Earlier EP', 'Dream pop', 3, 180, 240, 3, 'Night')
            commit_version(p, 0, song(), 'initial')
            original = copy.deepcopy(p)
            db = sqlite3.connect(Path(folder) / 'projects.sqlite3')
            db.execute('CREATE TABLE projects (id TEXT PRIMARY KEY, body TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('INSERT INTO projects VALUES (?, ?, ?)', (p['id'], json.dumps(p), p['updated']))
            db.commit()
            db.close()
            store = Store(folder)
            self.assertEqual(store.list()[0], original)
            self.assertEqual(store.collections()[0]['songs'], [t['id'] for t in p['tracks']])
            store.db.close()
            store = Store(folder)
            self.assertEqual(len(store.collections()), 1)
            self.assertEqual(store.list()[0], original)
            store.db.close()

    def test_collection_membership_order_and_format_preserve_song_history(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            projects = [create_project(name, 'Folk', 1, 180, 240, 3) for name in ['One', 'Two']]
            for p in projects:
                commit_version(p, 0, song(p['name']), 'initial')
                store.save(p)
            before = store.list()
            ids = [p['tracks'][0]['id'] for p in projects]
            coll = make_collection('Shared theme', 'collection', 'Rain', ids)
            store.save_collection(coll)
            coll.update(kind='album', songs=list(reversed(ids)))
            store.save_collection(coll)
            self.assertEqual(store.collections()[0]['songs'], list(reversed(ids)))
            self.assertEqual(store.collections()[0]['kind'], 'album')
            coll['songs'] = []
            store.save_collection(coll)
            self.assertEqual(store.list(), before)
            store.db.close()

    def test_unknown_song_does_not_overwrite_collection(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            coll = make_collection('Empty')
            store.save_collection(coll)
            invalid = copy.deepcopy(coll)
            invalid['songs'] = ['missing']
            with self.assertRaises(ValueError):
                store.save_collection(invalid)
            self.assertEqual(store.collections()[0], coll)
            store.db.close()

    def test_context_combines_collection_theme_without_changing_lyric_language(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            p = create_project('One', 'Folk', 1, 180, 240, 3, 'Personal theme', 'Welsh')
            q = create_project('Two', 'Pop', 1, 180, 240, 3)
            commit_version(q, 0, song('Neighbour'), 'initial')
            store.save(p)
            store.save(q)
            coll = make_collection('Record', 'album', 'Collection theme', [q['tracks'][0]['id'], p['tracks'][0]['id']])
            store.save_collection(coll)
            original = copy.deepcopy(p)
            result = store.generation_context(p, 0, coll['id'])
            prompt = prompt_for(result, 0)
            for value in ['Welsh', 'Personal theme', 'Collection theme', 'Neighbour', 'album']:
                self.assertIn(value, prompt)
            self.assertEqual(result['_collection_context']['position'], 2)
            self.assertEqual(p, original)
            store.db.close()

    def test_reorganised_batch_only_uses_selected_collection(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            project = create_project('Batch', 'Pop', 3, 180, 240, 3)
            commit_version(project, 2, song('Unrelated song'), 'initial')
            store.save(project)
            selected = make_collection('Selected', 'album', '', [project['tracks'][0]['id']])
            store.save_collection(selected)
            self.assertEqual(store.pending_songs(selected['id']), [(project['id'], 0)])
            context = store.generation_context(project, 0, selected['id'])
            prompt = prompt_for(context, 0)
            self.assertNotIn('Unrelated song', prompt)
            self.assertIn('"total_tracks": 1', prompt)
            self.assertNotIn('Unrelated song', prompt_for(project, 0))
            store.db.close()

    def test_settings_default_to_system_and_preserve_legacy_model(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.save_settings({'model': 'another:8b'})
            saved = store.settings()
            self.assertEqual(saved['ui_language'], 'system')
            self.assertEqual(saved['colour_mode'], 'system')
            self.assertEqual(saved['model'], 'another:8b')
            self.assertEqual(saved['default_suno_model'], 'v6')
            store.db.close()


class AppearanceTests(unittest.TestCase):
    def test_palette_reads_current_omarchy_state(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / '.local/state/omarchy/current/theme/colors.toml'
            p.parent.mkdir(parents=True)
            p.write_text('background="#121212"\nforeground="#fefefe"\naccent="#AA22CC"\nlighter_background="#242424"')
            result = read_palette(folder)
            self.assertEqual(result['accent'], '#AA22CC')
            self.assertEqual(result['surface'], '#242424')
            self.assertIn('#AA22CC', colour_css(result))
            p.write_text('background="invalid css"')
            self.assertEqual(read_palette(folder), {})

    def test_native_fallback_does_not_force_a_palette(self):
        self.assertEqual(colour_css({}), '')
        self.assertEqual(resolved_palette({'colour_mode': 'system', 'colours': {'accent': '#FFFFFF'}}, {}), {})

    def test_invalid_custom_colour_rejected(self):
        with self.assertRaises(ValueError):
            colour_css({'background': 'red; }', 'surface': '#123456', 'foreground': '#FFFFFF', 'accent': '#223344'})
        self.assertEqual(text_on('#FFFFFF'), '#000000')
        self.assertEqual(text_on('#000000'), '#ffffff')

    def test_controls_use_readable_solid_colours(self):
        dark = {'background': '#100B20', 'surface': '#281A45', 'foreground': '#F5F1FF', 'accent': '#8B3DFF'}
        light = {'background': '#FAFAFA', 'surface': '#E8E8E8', 'foreground': '#161616', 'accent': '#5A20B5'}
        self.assertEqual(mix_colour('#000000', '#FFFFFF', 0.5), '#808080')
        for palette in (dark, light):
            css = colour_css(palette)
            button_bg = mix_colour(palette['background'], palette['surface'], 0.72)
            self.assertIn(f'button, dropdown > button {{ background: {button_bg};', css)
            self.assertIn(f'button.suggested-action {{ background: {palette["accent"]}; color: {text_on(palette["accent"])};', css)


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('en')
    def test_locale_precedence(self):
        self.assertEqual(i18n.system_language({'LANG': 'de_DE.UTF-8'}), 'de')
        self.assertEqual(i18n.system_language({'LANG': 'en_US.UTF-8', 'LC_MESSAGES': 'fr_FR.UTF-8'}), 'fr')
        self.assertEqual(i18n.system_language({'LANG': 'en_US.UTF-8', 'LANGUAGE': 'es:de'}), 'es')
        self.assertEqual(i18n.system_language({'LANG': 'de_DE.UTF-8', 'LC_ALL': 'C.UTF-8'}), 'en')
        self.assertEqual(i18n.system_language({'LANG': 'zz_ZZ.UTF-8'}), 'en')
    def test_catalogue_placeholders_match(self):
        def placeholders(value):
            return {field for _,field,_,_ in Formatter().parse(value) if field is not None}
        for code, messages in i18n.CATALOGUES.items():
            for key, value in messages.items():
                self.assertEqual(placeholders(key), placeholders(value), (code, key))
    def test_interface_translation_is_explicit(self):
        i18n.set_language('fr')
        self.assertEqual(i18n.t('Settings'), 'Paramètres')
        self.assertEqual(i18n.t('Songs: {n}', n=3), 'Chansons : 3')


if __name__ == '__main__':
    unittest.main()
