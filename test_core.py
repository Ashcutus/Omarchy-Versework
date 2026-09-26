import copy
import io
import json
import tempfile
import threading
import unittest
from core import *


def song(title='Paper Moons'):
    return {'title': title, 'lyrics': '[Verse]\nA paper moon above the door\n[Chorus]\nLeave a little light for me', 'style_prompt': 'Quiet folk, brushed drums, warm guitar', 'exclusions': 'distortion', 'vocal_gender': 'female', 'weirdness': 25, 'style_influence': 80, 'variety': 'normal', 'notes': ''}


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.p = create_project('Test EP', 'Dream pop', 4, 180, 240, 1)
    def test_initial_does_not_use_rewrite_and_limit_enforced(self):
        commit_version(self.p, 0, song(), 'initial')
        self.assertEqual(self.p['tracks'][0]['rewrites'], 0)
        commit_version(self.p, 0, song('Second'), 'rewrite', 'Darker')
        with self.assertRaises(ValueError):
            commit_version(self.p, 0, song('Third'), 'rewrite')
        self.assertEqual(self.p['tracks'][0]['current']['title'], 'Second')
    def test_locked_fields_survive_rewrite(self):
        commit_version(self.p, 0, song(), 'initial')
        self.p['tracks'][0]['locks'] = ['lyrics', 'title']
        revision = song('New name')
        revision.update(lyrics='Changed', style_prompt='New sound')
        commit_version(self.p, 0, revision, 'rewrite')
        self.assertEqual(self.p['tracks'][0]['current']['lyrics'], song()['lyrics'])
        self.assertEqual(self.p['tracks'][0]['current']['title'], song()['title'])
        self.assertEqual(self.p['tracks'][0]['current']['style_prompt'], 'New sound')
    def test_approved_tracks_are_immutable(self):
        commit_version(self.p, 0, song(), 'initial')
        self.p['tracks'][0]['approved'] = True
        for kind in ['rewrite', 'edit']:
            with self.assertRaises(ValueError):
                commit_version(self.p, 0, song('Changed'), kind)
        with self.assertRaises(ValueError):
            restore_version(self.p, 0, 0)
    def test_restore_preserves_count_and_old_version(self):
        commit_version(self.p, 0, song(), 'initial')
        commit_version(self.p, 0, song('Second'), 'rewrite')
        restore_version(self.p, 0, 0)
        t = self.p['tracks'][0]
        self.assertEqual(t['rewrites'], 1)
        self.assertEqual(len(t['versions']), 3)
        self.assertEqual(t['versions'][1]['song']['title'], 'Second')
        self.assertEqual(t['current']['title'], song()['title'])
    def test_invalid_output_does_not_consume_rewrite(self):
        commit_version(self.p, 0, song(), 'initial')
        bad = song()
        bad['weirdness'] = 101
        previous = copy.deepcopy(self.p)
        with self.assertRaises(ValueError):
            commit_version(self.p, 0, bad, 'rewrite')
        self.assertEqual(previous, self.p)
    def test_no_op_revision_does_not_use_allowance(self):
        commit_version(self.p, 0, song(), 'initial')
        revised = song()
        revised['notes'] = 'Changed the chorus'
        with self.assertRaisesRegex(ValueError, 'did not change'):
            commit_version(self.p, 0, revised, 'rewrite')
        self.assertEqual(self.p['tracks'][0]['rewrites'], 0)
        self.assertEqual(len(self.p['tracks'][0]['versions']), 1)

    def test_zero_rewrites_can_still_approve(self):
        self.p['limit'] = 0
        commit_version(self.p, 0, song(), 'initial')
        self.assertIn('Limit reached', track_status(self.p, self.p['tracks'][0]))
        self.p['tracks'][0]['approved'] = True
        self.assertEqual(track_status(self.p, self.p['tracks'][0]), 'Approved')
    def test_partial_ep_persists_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            commit_version(self.p, 0, song(), 'initial')
            store.save(self.p)
            store.db.close()
            second = Store(tmp)
            restored = second.list()[0]
            self.assertEqual(restored, self.p)
            self.assertEqual(sum(t['current'] is None for t in restored['tracks']), 3)
            second.db.close()
    def add_collection_context(self):
        self.p['_collection_context'] = {'name': 'Test', 'kind': 'collection', 'theme': 'Shared', 'position': 1, 'total': 4,
            'other_songs': [{'title': t['current']['title'], 'do_not_repeat_these_lyrics': t['current']['lyrics']} for t in self.p['tracks'] if t['current']]}

    def test_revision_prompt_includes_context_feedback_locks(self):
        commit_version(self.p, 0, song(), 'initial')
        commit_version(self.p, 1, song('Neighbour'), 'initial')
        self.add_collection_context()
        self.p['tracks'][0]['locks'] = ['lyrics']
        prompt = prompt_for(self.p, 0, 'More hopeful')
        for text in ['Neighbour', 'More hopeful', 'locked_fields', 'target_seconds', '180', 'track_role', 'do_not_repeat_these_lyrics']:
            self.assertIn(text, prompt)
    def test_export_labels_approval_honestly(self):
        commit_version(self.p, 0, song(), 'initial')
        result = export_text(self.p)
        self.assertIn('Ready for review', result)
        self.assertIn('Not drafted', result)
        for field in LABELS.values():
            self.assertIn(field, result)
    def test_duplicate_draft_gets_one_retry(self):
        commit_version(self.p, 0, song(), 'initial')
        self.add_collection_context()
        unique = song('A new song')
        unique['lyrics'] = 'I count the windows on the hill\nYour boots are drying by the door'
        class Fake:
            calls = 0
            def generate(inner, *args):
                inner.calls += 1
                return song() if inner.calls == 1 else unique
        fake = Fake()
        self.assertEqual(generate_song(fake, 'test', self.p, 1, '', threading.Event()), unique)
        self.assertEqual(fake.calls, 2)

    def test_repeated_duplicate_draft_is_rejected(self):
        commit_version(self.p, 0, song(), 'initial')
        self.add_collection_context()
        class Fake:
            calls = 0
            def generate(inner, *args):
                inner.calls += 1
                return song()
        fake = Fake()
        with self.assertRaisesRegex(ValueError, 'repeating lyrics'):
            generate_song(fake, 'test', self.p, 1, '', threading.Event())
        self.assertEqual(fake.calls, 2)
        self.assertIsNone(self.p['tracks'][1]['current'])

    def test_invalid_brief(self):
        with self.assertRaises(ValueError):
            create_project('EP', 'Folk', 4, 300, 180, 3)


class TransportTests(unittest.TestCase):
    def response(self, parts):
        return io.BytesIO(b'\n'.join(json.dumps(p).encode() for p in parts))
    def test_streamed_json_validates(self):
        client = Ollama()
        raw = json.dumps(song())
        recorded = []
        def request(path, data, timeout):
            recorded.append(data)
            return self.response([{'response': raw[:40]}, {'response': raw[40:], 'done': True, 'done_reason': 'stop'}])
        client.request = request
        result = client.generate('qwen3:8b', 'Brief', threading.Event())
        self.assertEqual(result, song())
        self.assertEqual(recorded[0]['format'], SCHEMA)
    def test_truncated_stream_rejected(self):
        c = Ollama()
        c.request = lambda *a, **kw: self.response([{'response': json.dumps(song())}])
        with self.assertRaises(RuntimeError):
            c.generate('qwen3:8b', 'Brief', threading.Event())
    def test_cancelled_does_not_contact_server(self):
        c = Ollama()
        c.request = lambda *a, **kw: self.fail('Should not contact Ollama')
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(Cancelled):
            c.generate('qwen3:8b', 'Brief', cancelled)
    def test_cloud_models_filtered(self):
        c = Ollama()
        c.request = lambda *a, **kw: io.BytesIO(json.dumps({'models': [{'name': 'qwen3:8b'}, {'name': 'large:cloud'}, {'name': 'remote', 'remote_host': 'https://ollama.com'}]}).encode())
        self.assertEqual(c.models(), ['qwen3:8b'])


if __name__ == '__main__':
    unittest.main()


class CharacterLimitTests(unittest.TestCase):
    def test_exact_limit_and_unicode(self):
        for field in ('style_prompt', 'exclusions'):
            value = song()
            value[field] = 'é' * 1000
            self.assertEqual(validate_song(value)[field], value[field])
            value[field] += 'x'
            with self.assertRaisesRegex(ValueError, '1000'):
                validate_song(value)

    def test_invalid_revision_does_not_use_allowance(self):
        project = create_project('Song', 'Folk', 1, 180, 240, 3)
        commit_version(project, 0, song(), 'initial')
        before = copy.deepcopy(project)
        revision = song()
        revision['exclusions'] = 'x' * 1001
        with self.assertRaises(ValueError):
            commit_version(project, 0, revision, 'rewrite')
        self.assertEqual(project, before)

    def test_brief_and_schema_limits(self):
        create_project('Song', 'x' * 1000, 1, 180, 240, 3)
        with self.assertRaisesRegex(ValueError, '1000'):
            create_project('Song', 'x' * 1001, 1, 180, 240, 3)
        for field in ('style_prompt', 'exclusions'):
            self.assertEqual(SCHEMA['properties'][field]['maxLength'], 1000)


class ProductionTests(unittest.TestCase):
    def test_direction_is_per_song_and_survives_storage(self):
        project = create_project('Song', 'Folk', 2, 180, 240, 3)
        direction = {'density': 'stripped', 'dynamics': 'steady', 'vocals': 'intimate', 'notes': 'Fingerpicked guitar only.'}
        project['tracks'][0]['production'] = production_direction(direction)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite3')
            store.save(project)
            saved = store.list()[0]
            self.assertEqual(saved['tracks'][0]['production'], production_direction(direction))
            first = prompt_for(saved, 0)
            second = prompt_for(saved, 1)
            self.assertIn('Fingerpicked guitar only.', first)
            self.assertIn('bracketed performance cues', first)
            self.assertIn('no doubled lead', first)
            self.assertNotIn('Fingerpicked guitar only.', second)
            commit_version(saved, 0, song(), 'initial')
            revision = prompt_for(saved, 0, 'Less busy')
            self.assertIn('Fingerpicked guitar only.', revision)
            self.assertIn('Less busy', revision)

    def test_legacy_defaults_and_validation(self):
        self.assertEqual(production_direction()['density'], 'style')
        self.assertEqual(production_brief({})['delivery'], [])
        with self.assertRaises(ValueError):
            production_direction({'density': 'invalid'})
        with self.assertRaises(ValueError):
            production_direction({'notes': 'x' * 1001})

class ProductionDeliveryTests(unittest.TestCase):
    def project(self, existing=False):
        project = create_project('Test', 'Folk', 1, 180, 240, 3)
        project['tracks'][0]['production'] = {
            'density': 'stripped', 'dynamics': 'steady', 'vocals': 'intimate'}
        if existing:
            commit_version(project, 0, song(), 'initial')
        return project

    def compliant(self, project):
        output = song('Revised')
        for field, cues in production_requirements(project['tracks'][0]).items():
            output[field] += '\n' + '\n'.join(cues)
        return output

    def test_new_and_rewrite_compose_omitted_cues_without_retry(self):
        from unittest.mock import Mock
        for existing in (False, True):
            with self.subTest(existing=existing):
                project = self.project(existing)
                client = Mock()
                client.generate.return_value = song()
                result = generate_song(client, 'local', project, 0, 'Less produced',
                                       threading.Event())
                self.assertEqual(missing_production(result, project['tracks'][0]), [])
                self.assertEqual(client.generate.call_count, 1)

    def test_composition_does_not_mutate_new_or_existing_project(self):
        from unittest.mock import Mock
        for existing in (False, True):
            project = self.project(existing)
            before = copy.deepcopy(project)
            client = Mock()
            client.generate.return_value = song()
            generate_song(client, 'local', project, 0, 'Less produced', threading.Event())
            self.assertEqual(project, before)
            self.assertEqual(client.generate.call_count, 1)

    def test_locks_and_instrumental_output(self):
        project = self.project(True)
        track = project['tracks'][0]
        track['locks'] = ['lyrics', 'style_prompt', 'exclusions']
        self.assertEqual(missing_production(song(), track), [])
        track['locks'] = []
        output = song()
        output['vocal_gender'] = 'instrumental'
        for field, cues in production_requirements(track, instrumental=True).items():
            output[field] += '\n' + '\n'.join(cues)
        self.assertEqual(missing_production(output, track), [])
        self.assertNotIn('intimate solo vocal', output['style_prompt'])

    def test_latest_choices_in_collection_context(self):
        project = self.project(True)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite3')
            collection = make_collection('Album', songs=[project['tracks'][0]['id']])
            project['tracks'][0]['production']['density'] = 'restrained'
            store.save(project)
            store.save_collection(collection)
            context = store.generation_context(project, 0, collection['id'])
            requirements = production_requirements(context['tracks'][0])
            self.assertIn('restrained arrangement', requirements['style_prompt'])
            self.assertNotIn('sparse arrangement', requirements['style_prompt'])


class PerformanceFeelTests(unittest.TestCase):
    def test_each_feel_reaches_initial_and_rewrite_checks(self):
        from unittest.mock import Mock
        for feel in ('human', 'live', 'polished'):
            for existing in (False, True):
                project = create_project('Test', 'Folk', 1, 180, 240, 3)
                if existing:
                    commit_version(project, 0, song(), 'initial')
                track = project['tracks'][0]
                track['production'] = {'feel': feel}
                output = song('New phrasing')
                for field, cues in production_requirements(track).items():
                    output[field] += '\n' + '\n'.join(cues)
                client = Mock()
                client.generate.side_effect = [song(), output]
                result = generate_song(client, 'local', project, 0, 'More natural', threading.Event())
                self.assertEqual(missing_production(result, track), [])
                self.assertEqual(client.generate.call_count, 1)

    def test_old_choices_keep_style_feel(self):
        direction = production_direction({'density': 'stripped'})
        self.assertEqual(direction['feel'], 'style')


class UserLyricsTests(unittest.TestCase):
    def test_user_lyrics_are_in_prompt_and_preserve_mode_wins(self):
        project = create_project('Working title', 'Quiet folk', 1, 180, 240, 3,
                                 lyrics='[Verse]\nKeep this line exactly.')
        track = project['tracks'][0]
        track['lyrics_assist'] = 'preserve'
        prompt = prompt_for(project, 0)
        self.assertIn('Keep this line exactly.', prompt)
        self.assertIn('authoritative', prompt)
        self.assertNotIn('Working title', project['tracks'][0]['lyrics_source'])

    def test_preserve_mode_keeps_lyrics_from_model_output(self):
        from unittest.mock import Mock
        project = create_project('Working title', 'Quiet folk', 1, 180, 240, 3,
                                 lyrics='[Verse]\nKeep this line exactly.')
        project['tracks'][0]['lyrics_assist'] = 'preserve'
        output = song('Different generated title')
        client = Mock()
        client.generate.return_value = output
        result = generate_song(client, 'local', project, 0, '', threading.Event())
        self.assertEqual(result['lyrics'], project['tracks'][0]['lyrics_source'])

    def test_working_title_is_rejected_from_generated_lyrics(self):
        from unittest.mock import Mock
        project = create_project('Working title', 'Quiet folk', 1, 180, 240, 3)
        clean = song('Different title')
        client = Mock()
        client.generate.side_effect = [dict(song(), lyrics='[Verse]\nWorking title is here.'), clean]
        result = generate_song(client, 'local', project, 0, '', threading.Event())
        self.assertEqual(result, clean)
        self.assertIn('working title', client.generate.call_args.args[1].lower())

    def test_unlimited_rewrites_are_allowed(self):
        project = create_project('Song', 'Folk', 1, 180, 240, None)
        commit_version(project, 0, song(), 'initial')
        for number in range(5):
            commit_version(project, 0, song(f'Rewrite {number}'), 'rewrite')
        self.assertEqual(project['tracks'][0]['rewrites'], 5)

    def test_drum_feel_slider_maps_to_prompt_requirements(self):
        project = create_project('Quiet room', 'Acoustic folk', 1, 180, 240, 3)
        project['tracks'][0]['production'] = production_direction({'drums': 100})
        self.assertEqual(drum_feel(100)[0], 'Sloppy Sunday night in the pub')
        requirements = production_requirements(project['tracks'][0])
        self.assertTrue(any('ragged pub-band drums' in value for value in requirements['style_prompt']))
        self.assertIn('[Drums: ragged pub-band feel]', requirements['lyrics'])
        self.assertIn('rigid drum quantization', requirements['exclusions'])


class SunoModelTests(unittest.TestCase):
    def test_v6_is_default_and_each_model_gets_appropriate_prompt_guidance(self):
        project = create_project('Song', 'Folk', 1, 180, 240, 3)
        track = project['tracks'][0]
        self.assertEqual(track['suno_model'], 'v6')
        expectations = {'v6': 'v6, precise', 'v6-wild': 'v6-wild, exploratory', 'v6-mini': 'v6-mini, concise'}
        for model, phrase in expectations.items():
            track['suno_model'] = model
            self.assertIn(phrase, prompt_for(project, 0))

    def test_suno_model_is_saved_with_each_generation_and_restored_with_version(self):
        project = create_project('Song', 'Folk', 1, 180, 240, 3)
        project['tracks'][0]['suno_model'] = 'v6-wild'
        commit_version(project, 0, song(), 'initial')
        self.assertEqual(project['tracks'][0]['versions'][0]['suno_model'], 'v6-wild')
        project['tracks'][0]['suno_model'] = 'v6-mini'
        restore_version(project, 0, 0)
        self.assertEqual(project['tracks'][0]['suno_model'], 'v6-wild')

    def test_export_identifies_model_for_each_track(self):
        project = create_project('Song', 'Folk', 1, 180, 240, 3, suno_model='v6-mini')
        self.assertIn('Suno model: v6-mini', export_text(project))
        self.assertIn('Suno model\nv6-mini', song_text(song(), 'v6-mini'))
