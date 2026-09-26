"""Versework: local project storage, revision rules and Ollama transport."""
from __future__ import annotations
import copy
import json
import os
import queue
import re
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ['title', 'lyrics', 'style_prompt', 'exclusions', 'vocal_gender', 'weirdness', 'style_influence', 'variety']
SUNO_MODELS = {
    'v6': {'label': 'v6 — Precise', 'about': 'Balanced, reliable and polished; choose this when you know what you want.',
           'guidance': 'MODEL-SPECIFIC SUNO PROMPT (v6, precise): Follow the creative brief closely. Make the style prompt specific and coherent: lead with the main genre, then groove/tempo feel, defining instruments, vocal delivery and production character. Keep every detail purposeful and avoid contradictory directions. Write deliberate, singable lyrics with clear sections, natural stresses and a strong hook that serves the brief.'},
    'v6-wild': {'label': 'v6-wild — Experimental', 'about': 'More varied and unpredictable; choose this to explore unexpected directions.',
                'guidance': 'MODEL-SPECIFIC SUNO PROMPT (v6-wild, exploratory): Preserve the user’s essential genre, story, hook and exclusions, but invite one or two surprising textures, rhythmic turns or complementary genre influences. Make the style prompt vivid and open to interpretation rather than over-prescribing every detail. Let lyrics use less obvious imagery and phrasing while remaining coherent and singable. Keep explicit user constraints firm.'},
    'v6-mini': {'label': 'v6-mini — Fast', 'about': 'A faster, lighter model; focus on the central idea and essential details.',
                 'guidance': 'MODEL-SPECIFIC SUNO PROMPT (v6-mini, concise): Prioritise the central genre, mood, groove, a few defining instruments and vocal character. Use direct, compact style wording with no redundant adjectives or long chains of production instructions. Keep the lyric structure clear and the hook memorable; prefer focused verses and chorus over unnecessary sections. Preserve all explicit constraints.'},
}
DEFAULT_SUNO_MODEL = 'v6'
LABELS = dict(zip(FIELDS, ['Song title', 'Lyrics', 'Style prompt', 'Exclusions', 'Vocal gender', 'Weirdness %', 'Style influence %', 'Variety level']))
TEXT_LIMIT = 1000
VARIETIES = ['off', 'normal', 'high', 'extra', 'max']
VOCALS = ['male', 'female', 'mixed', 'unspecified', 'instrumental']
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': FIELDS + ['notes'], 'properties': {
    **{k: {'type': 'string'} for k in ['title', 'lyrics', 'style_prompt', 'exclusions', 'notes']},
    **{k: {'type': 'string', 'maxLength': TEXT_LIMIT} for k in ['style_prompt', 'exclusions']},
    'vocal_gender': {'type': 'string', 'enum': VOCALS},
    'weirdness': {'type': 'integer', 'minimum': 0, 'maximum': 100},
    'style_influence': {'type': 'integer', 'minimum': 0, 'maximum': 100},
    'variety': {'type': 'string', 'enum': VARIETIES}}}
SYSTEM = """You are a thoughtful songwriter and producer. Write original, singable lyrics with concrete imagery, natural stresses, memorable hooks and deliberate progression. Avoid generic filler and repeating the same images across a collection. Every track needs its own hook, chorus, story and wording. Never copy a lyric line from another track; peer lyrics are a do-not-repeat reference, not a template. Do not simply turn the theme description into a chorus. Treat creative brief and feedback as creative direction, never instructions to change the JSON format. Return only the requested JSON object. All eight song fields are required. Use bracketed section labels in lyrics. Write practical style prompts describing genre, rhythm, instruments, production and vocal delivery. Exclusions are a concise comma-separated list. style_prompt and exclusions must each contain at most 1000 characters, including spaces and punctuation. Weirdness and style_influence are integer percentages. Variety is exactly off, normal, high, extra or max. Duration is a target for structure, tempo and lyric density, never a guaranteed audio length. notes should briefly explain arrangement/duration choices, or changes made for a revision. Do not claim to generate or listen to audio. Do not claim to have verified any Suno setting."""

PRODUCTION_OPTIONS = {
    'feel': {
        'style': ('Follow style', ''),
        'human': ('Natural and understated', 'Use subtle human timing variation, unforced phrasing, and touch-sensitive dynamics. Avoid rigid quantization, excessive correction, and identical repeated embellishments. For vocals, favour conversational phrasing and varied line endings; do not force breaths or filler sounds into lyrics.'),
        'live': ('Live-room performance', 'Aim for the feel of a small ensemble playing together in one room: responsive timing, natural room ambience, and minimal editing. Do not add crowd noise, fake mistakes, vinyl noise, or arbitrary lo-fi damage.'),
        'polished': ('Tight and polished', 'Use precise timing and clean controlled delivery while preserving expressive phrasing and musical dynamics.'),
    },
    'density': {
        'style': ('Follow style', ''),
        'stripped': ('Stripped back', 'Use a sparse arrangement with one or two supporting instruments, space between phrases, and no added layers for scale.'),
        'restrained': ('Restrained', 'Use a small, clearly defined ensemble. Keep supporting layers sparse; avoid stacked hooks, ornamental fills, and automatic chorus thickening.'),
        'balanced': ('Balanced', 'Use a clear core arrangement with selective supporting layers; each addition must serve the song.'),
        'full': ('Full production', 'Allow a rich layered arrangement while keeping the lead and core musical ideas clear.'),
    },
    'dynamics': {
        'style': ('Follow style', ''),
        'steady': ('Steady and contained', 'Keep intensity contained throughout. Do not add a giant final chorus, cinematic rise, drop, or key change.'),
        'gentle': ('Gentle build', 'Build gradually through performance and subtle instrumentation, without an oversized climax.'),
        'dramatic': ('Dramatic build', 'Allow deliberate contrast and a strong climax where the song calls for it.'),
    },
    'vocals': {
        'style': ('Follow style', ''),
        'intimate': ('Intimate solo', 'Use a close, natural solo lead, restrained delivery, minimal effects, no doubled lead, harmonies, choir, or ad-libs.'),
        'natural': ('Natural lead', 'Keep the lead vocal natural and clear, with minimal processing and only occasional purposeful backing vocals.'),
        'layered': ('Layered vocals', 'Allow deliberate harmonies and vocal layers while keeping the lead intelligible.'),
    },
}

DRUM_FEELS = [
    ('Machine-perfect', 'grid-locked drums, uniform hits', 'timing drift', '[Drums: machine-perfect timing]'),
    ('Tight session drummer', 'tight played drums, subtle touch variation', 'identical drum velocities', '[Drums: tight human pocket]'),
    ('Relaxed pocket', 'relaxed drum pocket, varied ghost notes', 'rigid drum quantization, identical drum loops', '[Drums: relaxed pocket, ghost notes]'),
    ('Loose live drummer', 'loose live drums, push-and-pull timing', 'rigid drum quantization, identical drum loops', '[Drums: loose live feel]'),
    ('Sloppy Sunday night in the pub', 'ragged pub-band drums, drifting fills', 'rigid drum quantization, identical drum loops', '[Drums: ragged pub-band feel]'),
]


def drum_feel(value):
    return DRUM_FEELS[min(4, max(0, (int(value) + 12) // 25))]


def production_direction(value=None):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError('Invalid production direction.')
    result = {}
    for key, options in PRODUCTION_OPTIONS.items():
        choice = value.get(key, 'style')
        if choice not in options:
            raise ValueError('Invalid production choice.')
        result[key] = choice
    notes = value.get('notes', '')
    if not isinstance(notes, str) or len(notes) > TEXT_LIMIT:
        raise ValueError('Production notes must be 1000 characters or fewer.')
    result['notes'] = notes
    drums = value.get('drums')
    if drums is not None and (type(drums) is not int or not 0 <= drums <= 100):
        raise ValueError('Drum feel must be a whole number from 0 to 100.')
    result['drums'] = drums
    return result


def production_brief(track):
    direction = production_direction(track.get('production'))
    return {
        'choices': direction,
        'delivery': [PRODUCTION_OPTIONS[key][direction[key]][1]
                     for key in PRODUCTION_OPTIONS if direction[key] != 'style']
                    + ([drum_feel(direction['drums'])[1] + '. ' + drum_feel(direction['drums'])[2]] if direction['drums'] is not None else []),
        'instructions': 'Apply this direction to style_prompt and concise bracketed performance cues in lyrics. Keep cues separate from sung words. Add relevant unwanted production elements to exclusions. Respect locked fields. For instrumental songs, omit vocal directions and vocal lyric cues. Keep style_prompt and exclusions within 1000 characters each. If specific production choices conflict with broad genre conventions, follow the specific choices. These are creative requests, not guarantees of audio behaviour.',
    }


# Compact, auditable delivery cues. These are writing directions, not Suno API parameters.
PRODUCTION_CUES = {
    'drums': {},
    'feel': {
        'human': ('natural timing and phrasing', 'hard quantization, excessive pitch correction', '[Natural phrasing, subtle timing variation]'),
        'live': ('live-room ensemble feel', 'hard quantization, excessive editing, crowd noise', '[Live-room feel, responsive timing]'),
        'polished': ('precise timing, expressive phrasing', '', '[Precise, expressive performance]'),
    },
    'density': {
        'stripped': ('sparse arrangement', 'dense layering', '[Sparse arrangement]'),
        'restrained': ('restrained arrangement', 'overproduction', '[Restrained arrangement]'),
        'balanced': ('balanced arrangement', '', '[Balanced arrangement]'),
        'full': ('full layered arrangement', '', '[Full arrangement]'),
    },
    'dynamics': {
        'steady': ('contained dynamics', 'dramatic builds, key changes', '[Contained dynamics throughout]'),
        'gentle': ('gentle build', 'explosive drops', '[Gentle build]'),
        'dramatic': ('dramatic build', '', '[Dramatic build]'),
    },
    'vocals': {
        'intimate': ('intimate solo vocal', 'vocal doubling, choir, ad-libs', '[Intimate solo vocal]'),
        'natural': ('natural lead vocal', 'heavy vocal processing', '[Natural lead vocal]'),
        'layered': ('layered vocals', '', '[Layered vocals]'),
    },
}


def production_requirements(track, instrumental=False):
    direction = production_direction(track.get('production'))
    required = {'style_prompt': [], 'exclusions': [], 'lyrics': []}
    for key, options in PRODUCTION_CUES.items():
        if key == 'drums':
            continue
        if key == 'vocals' and instrumental:
            continue
        if direction[key] == 'style':
            continue
        style, exclusions, cue = options[direction[key]]
        if key == 'feel' and direction['drums'] is not None:
            if (direction['drums'] < 13 and direction['feel'] in ('human', 'live')) or (direction['drums'] >= 63 and direction['feel'] == 'polished'):
                style = 'other instruments: ' + style
                cue = cue.replace('[', '[Other instruments: ', 1)
                exclusions = exclusions.replace('hard quantization, ', '')
        required['style_prompt'].append(style)
        required['exclusions'].extend(exclusions.split(', ') if exclusions else [])
        required['lyrics'].append(cue)
    if direction['drums'] is not None:
        style, exclusions, cue = drum_feel(direction['drums'])[1:]
        required['style_prompt'].append(style)
        required['exclusions'].extend(exclusions.split(', '))
        required['lyrics'].append(cue)
    if track.get('lyrics_source') and track.get('lyrics_assist') == 'preserve':
        required.pop('lyrics', None)
    return {field: values for field, values in required.items() if field not in track.get('locks', [])}


def missing_production(song, track):
    instrumental = song.get('vocal_gender') == 'instrumental'
    missing = []
    for field, values in production_requirements(track, instrumental).items():
        for value in values:
            if value.casefold() not in song[field].casefold():
                missing.append(f'{field}: {value}')
    return missing


def production_preview(track, instrumental=False):
    """Expose exactly the fixed cues that will accompany a generated draft."""
    direction = production_direction(track.get('production'))
    conflicts = []
    if direction['drums'] is not None:
        if direction['drums'] < 13 and direction['feel'] in ('human', 'live'):
            conflicts.append('Machine-perfect drums override human timing for drums; other instruments retain the selected feel.')
        if direction['drums'] >= 63 and direction['feel'] == 'polished':
            conflicts.append('Loose drums override precise timing for drums; other instruments retain the selected feel.')
    return {'cues': production_requirements(track, instrumental), 'conflicts': conflicts,
            'notes': direction['notes']}


def compose_production(song, track):
    """Reserve space for mandatory cues locally instead of retrying the model."""
    result = copy.deepcopy(song)
    required = production_requirements(track, song.get('vocal_gender') == 'instrumental')
    direction = production_direction(track.get('production'))
    # Remove obsolete, app-managed cues when production settings change. We do
    # not attempt to interpret or silently delete arbitrary creative prose.
    catalogue = [entry for key, options in PRODUCTION_CUES.items()
                 if direction.get(key, 'style') != 'style' or (key == 'vocals' and song.get('vocal_gender') == 'instrumental')
                 for entry in options.values()]
    if direction['drums'] is not None:
        catalogue += [entry[1:] for entry in DRUM_FEELS]
    for field, column in (('style_prompt', 0), ('exclusions', 1), ('lyrics', 2)):
        if field not in required:
            continue
        content = result[field]
        selected = required[field]
        for entry in catalogue:
            values = entry[column].split(', ') if field == 'exclusions' else [entry[column]]
            for value in values:
                if value and not any(value in cue for cue in selected):
                    content = re.sub(re.escape(value), '', content, flags=re.IGNORECASE)
        missing = [cue for cue in selected if cue.casefold() not in content.casefold()]
        if not missing:
            result[field] = content
            continue
        if field == 'lyrics':
            result[field] = '\n'.join(missing) + '\n\n' + content.lstrip()
        else:
            # Reserve all selected cues, including ones already present near
            # the end of a long model prompt that trimming could otherwise lose.
            for cue in selected:
                content = re.sub(re.escape(cue), '', content, flags=re.IGNORECASE)
            suffix = '; '.join(selected)
            budget = TEXT_LIMIT - len(suffix) - 2
            if budget < 0:
                raise ValueError('Production directions exceed the Suno field limit.')
            content = content[:budget].strip(' ,;\n')
            result[field] = (content + '; ' if content else '') + suffix
    return result


def scoped_track(track, scope='all'):
    if scope not in ('all', 'lyrics', 'sound', 'section'):
        raise ValueError('Choose all, lyrics, sound or section for the rewrite scope.')
    result = copy.deepcopy(track)
    allowed = {'lyrics'} if scope in ('lyrics', 'section') else set(FIELDS) - {'title', 'lyrics'} if scope == 'sound' else set(FIELDS)
    result['locks'] = list(dict.fromkeys(track.get('locks', []) + [field for field in FIELDS if field not in allowed]))
    return result


def replace_lyric_section(current, proposed, section):
    """Replace one uniquely named section while preserving every other byte."""
    if not section or not re.fullmatch(r'\[[^\n\]]+\]', section):
        raise ValueError('Select an exact lyric section heading, such as [Verse 1].')
    def locate(text):
        starts = list(re.finditer(r'^' + re.escape(section) + r'[ \t]*$', text, re.MULTILINE))
        if len(starts) != 1:
            raise ValueError('The selected section must appear exactly once in both the current and proposed lyrics.')
        start = starts[0].start()
        following = re.search(r'^\[[^\n\]]+\][ \t]*$', text[starts[0].end():], re.MULTILINE)
        end = starts[0].end() + following.start() if following else len(text)
        return start, end
    start, end = locate(current)
    new_start, new_end = locate(proposed)
    replacement = proposed[new_start:new_end].rstrip() + ('\n\n' if end < len(current) else '')
    return current[:start] + replacement + current[end:]


class Cancelled(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_song(value):
    if not isinstance(value, dict):
        raise ValueError('The model did not return a song object.')
    out = {}
    for field in FIELDS:
        v = value.get(field)
        if field in ['weirdness', 'style_influence']:
            if type(v) is not int or not 0 <= v <= 100:
                raise ValueError(f'{LABELS[field]} must be an integer from 0 to 100.')
        elif not isinstance(v, str):
            raise ValueError(f'{LABELS[field]} is missing or is not text.')
        elif len(v) > 100000:
            raise ValueError(f'{LABELS[field]} is too long.')
        if field in ['style_prompt', 'exclusions'] and len(v) > TEXT_LIMIT:
            raise ValueError(f'{LABELS[field]} must be {TEXT_LIMIT} characters or fewer.')
        if field in ['title', 'style_prompt'] and not v.strip():
            raise ValueError(f'{LABELS[field]} cannot be empty.')
        out[field] = v
    if out['vocal_gender'] not in VOCALS or out['variety'] not in VARIETIES:
        raise ValueError('The model returned an unsupported vocal or variety option.')
    if out['vocal_gender'] != 'instrumental' and not out['lyrics'].strip():
        raise ValueError('The song needs lyrics unless it is instrumental.')
    out['notes'] = str(value.get('notes', ''))[:20000]
    return out


def create_project(name, style, count, minimum, maximum, limit, theme='', language='English', lyrics='', suno_model=DEFAULT_SUNO_MODEL):
    if len(style) > TEXT_LIMIT:
        raise ValueError(f'Style prompt must be {TEXT_LIMIT} characters or fewer.')
    if not name.strip() or not style.strip():
        raise ValueError('Give the project a name and a style prompt.')
    if not (1 <= count <= 20 and 30 <= minimum <= maximum <= 1200 and (limit is None or 0 <= limit <= 20)):
        raise ValueError('Check song count (1–20), duration (30–1200 seconds) and rewrites (0–20).')
    lyrics = str(lyrics or '').strip()
    if len(lyrics) > 100000:
        raise ValueError('Provided lyrics are too long.')
    if suno_model not in SUNO_MODELS:
        raise ValueError('Choose a supported Suno model.')
    return {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': name.strip(), 'style': style.strip(), 'count': count,
            'minimum': minimum, 'maximum': maximum, 'limit': limit, 'theme': theme.strip(),
            'lyrics_source': lyrics, 'lyrics_assist': 'suggest',
            'language': language.strip() or 'English', 'created': now(), 'updated': now(),
            'tracks': [{'id': uuid.uuid4().hex, 'number': i + 1, 'current': None, 'versions': [],
                        'rewrites': 0, 'approved': False, 'locks': [], 'feedback': '',
                        'lyrics_source': lyrics if i == 0 else '', 'lyrics_assist': 'suggest',
                        'suno_model': suno_model} for i in range(count)]}


def commit_version(project, index, song, kind, feedback='', model='', suno_model=None):
    track = project['tracks'][index]
    if track['approved']:
        raise ValueError('Reopen this approved song before changing it.')
    if kind == 'rewrite':
        if not track['current']:
            raise ValueError('Generate an initial draft first.')
        if project['limit'] is not None and track['rewrites'] >= project['limit']:
            raise ValueError('This song has reached its rewrite limit.')
    elif kind == 'initial' and track['current']:
        raise ValueError('This song already has an initial draft.')
    data = copy.deepcopy(song)
    if kind == 'rewrite':
        for field in track['locks']:
            if field in FIELDS:
                data[field] = track['current'][field]
    data = validate_song(data)
    if kind == 'rewrite' and all(data[k] == track['current'][k] for k in FIELDS):
        raise ValueError('The model did not change any unlocked song fields. Your rewrite allowance is unchanged; try more specific feedback.')
    suno_model = suno_model or track.get('suno_model', DEFAULT_SUNO_MODEL)
    if suno_model not in SUNO_MODELS:
        raise ValueError('Choose a supported Suno model.')
    track['suno_model'] = suno_model
    version = {'at': now(), 'kind': kind, 'feedback': feedback, 'model': model, 'suno_model': suno_model, 'song': data}
    track['versions'].append(version)
    track['current'] = copy.deepcopy(data)
    if kind == 'rewrite':
        track['rewrites'] += 1
    project['updated'] = now()


def restore_version(project, index, version_index):
    version = project['tracks'][index]['versions'][version_index]
    song = copy.deepcopy(version['song'])
    project['tracks'][index]['suno_model'] = version.get('suno_model', DEFAULT_SUNO_MODEL)
    commit_version(project, index, song, 'restore', f'Restored version {version_index + 1}')


def track_status(project, track):
    if track['approved']:
        return 'Approved'
    if not track['current']:
        return 'Not drafted'
    if project['limit'] is not None and track['rewrites'] >= project['limit']:
        return 'Limit reached · review needed'
    return 'Ready for review'


def prompt_for(project, index, feedback=''):
    track = project['tracks'][index]
    context = project.get('_collection_context')
    peers = copy.deepcopy(context.get('other_songs', [])) if context else []
    brief = {'project': project['name'], 'style': project['style'], 'theme': project['theme'],
             'language': project['language'], 'track_number': context['position'] if context else 1,
             'total_tracks': context['total'] if context else 1,
             'target_seconds': [project['minimum'], project['maximum']], 'other_tracks': peers}
    role = 'Self-contained single'
    if context:
        brief['collection'] = {k: v for k, v in context.items() if k != 'other_songs'}
        role = ('A distinct standalone song in a themed collection' if context['kind'] == 'collection' else
                f"Song {context['position']} of {context['total']} on this {context['kind']}")
    brief['production'] = production_brief(track)
    model = track.get('suno_model', DEFAULT_SUNO_MODEL)
    if model not in SUNO_MODELS:
        model = DEFAULT_SUNO_MODEL
    brief['suno_model'] = {'id': model, 'about': SUNO_MODELS[model]['about']}
    brief['required_delivery_cues'] = production_requirements(track, (track.get('current') or {}).get('vocal_gender') == 'instrumental')
    brief['track_role'] = role
    source = track.get('lyrics_source', '')
    if source and track.get('current') and track.get('lyrics_assist') == 'preserve':
        source = track['current']['lyrics']
    if source:
        brief['user_lyrics'] = source
        brief['lyrics_handling'] = track.get('lyrics_assist', 'suggest')
    action = 'Write the initial song. Give this song its own identity. It may stand alone or belong to an optional collection. Read peer lyrics only to avoid repeating them. Write a completely new hook and chorus, not a paraphrase of a peer chorus. The working title is metadata only: never copy it into lyrics unless user-supplied lyrics explicitly contain it.'
    if source:
        if track.get('lyrics_assist', 'suggest') == 'preserve':
            action += ' The user supplied lyrics are authoritative. Preserve their sung words exactly and use the other fields to complete the Suno settings. Do not rewrite or add lyric lines.'
        else:
            action += ' The user supplied lyrics are starting material. Keep their voice and strongest lines, improve phrasing where useful, and explain concrete suggestions in notes.'
    if track['current']:
        action = 'Revise this song according to the feedback. Make substantive changes to unlocked song fields that address the feedback. Preserve strengths and anything not targeted by feedback. Describing a change in notes without actually changing the song is not a revision.'
        brief.update(current_song=track['current'], feedback=feedback, locked_fields=track['locks'])
    result = action + '\nCreative brief:\n' + json.dumps(brief, ensure_ascii=False) + '\nReturn JSON matching this schema:\n' + json.dumps(SCHEMA)
    if track['current']:
        result += '\n\nYOUR REVISION TASK NOW:\n' + feedback + '\nOnly these fields are locked: ' + ', '.join(track['locks']) + '\nWrite the revised song JSON now. The lyrics must actually reflect the requested changes. Do not copy the old song unchanged.'
    else:
        result += '\n\nFINAL WRITING CHECK: This is track ' + str(brief['track_number']) + '. Invent an entirely new chorus. Do not reuse any line from the peer tracks shown above. Shared genre does not mean shared lyrics.'
    result += '\n' + SUNO_MODELS[model]['guidance'] + '\nLYRIC SOURCE CHECK: The working title is not lyric content. Never use it as a lyric hook or line. If user lyrics are supplied, follow the selected preserve-or-suggest instruction exactly.\nPRODUCTION DELIVERY CHECK: Include every required_delivery_cues phrase verbatim in its named field. Put lyrics cues on separate bracketed lines before the sung lyrics; do not sing them. Integrate style phrases naturally and remove contradictory production descriptions. Exclusions name unwanted elements. For instrumental output omit vocal cues and vocal exclusions. Locked fields must stay unchanged. Stay within the 1000-character field limits. Apply arrangement notes too; mentioning a change only in notes does not count.'
    return result


def overlapping_lines(project, index, song):
    def lines(lyrics):
        return {re.sub(r'[^\w\s]', '', line.lower()).strip() for line in lyrics.splitlines() if len(line.strip()) >= 24 and not line.strip().startswith('[')}
    incoming = lines(song['lyrics'])
    repeated = set()
    for peer in project.get('_collection_context', {}).get('other_songs', []):
        common = incoming & lines(peer.get('do_not_repeat_these_lyrics', ''))
        if len(common) >= 2:
            repeated.update(common)
    return sorted(repeated)


def title_used_as_lyric(project, index, song):
    source = project['tracks'][index].get('lyrics_source', '')
    if source and project['tracks'][index].get('lyrics_assist') == 'preserve':
        return False
    title = project.get('name', '').strip().casefold()
    lyrics = song.get('lyrics', '').casefold()
    # Avoid treating ordinary short words such as “a” or “home” as title bleed.
    if len(title) < 5 and ' ' not in title:
        return False
    if source and re.search(r'(?<!\w)' + re.escape(title) + r'(?!\w)', source.casefold()):
        return False
    return re.search(r'(?<!\w)' + re.escape(title) + r'(?!\w)', lyrics) is not None


def generate_song(client, model, project, index, feedback, cancel, progress=None, scope='all', section=None):
    project = copy.deepcopy(project)
    track = scoped_track(project['tracks'][index], scope)
    project['tracks'][index] = track
    if scope == 'section' and not track.get('current'):
        raise ValueError('Generate an initial draft before rewriting a section.')
    prompt = prompt_for(project, index, feedback)
    if scope != 'all':
        prompt += '\nRewrite scope: ' + scope + '. Preserve all fields outside this scope exactly.'
    if scope == 'section':
        replace_lyric_section(track['current']['lyrics'], track['current']['lyrics'], section)
        prompt += '\nRewrite only the section headed ' + section + '; retain its exact heading and return the complete song JSON.'
    for attempt in range(2):
        song = client.generate(model, prompt, cancel, progress)
        if cancel.is_set():
            raise Cancelled()
        if track.get('current'):
            for field in track['locks']:
                if field in FIELDS:
                    song[field] = track['current'][field]
        if track.get('lyrics_source') and track.get('lyrics_assist') == 'preserve':
            song['lyrics'] = track['current']['lyrics'] if track.get('current') else track['lyrics_source']
        if scope == 'section' and 'lyrics' not in track['locks'] and not (track.get('lyrics_source') and track.get('lyrics_assist') == 'preserve'):
            song['lyrics'] = replace_lyric_section(track['current']['lyrics'], song['lyrics'], section)
        # Section rewrites must not insert arrangement cues elsewhere in lyrics.
        delivery_track = copy.deepcopy(track)
        if scope == 'section':
            delivery_track['locks'].append('lyrics')
        song = compose_production(song, delivery_track)
        repeats = overlapping_lines(project, index, song) if not project['tracks'][index]['current'] else []
        titled = title_used_as_lyric(project, index, song)
        if track.get('current') and ('lyrics' in track['locks'] or scope == 'section'):
            titled = titled and not title_used_as_lyric(project, index, track['current'])
        if not repeats and not titled:
            return validate_song(song)
        if titled and attempt == 1:
            raise ValueError('The model kept using the working title in the lyrics after one retry. Nothing was saved and no rewrite was used. Try a different working title or another model.')
        if titled and attempt == 0:
            prompt += '\n\nThe previous response used the working title in the lyrics. Remove that title from every sung line and hook; it is metadata only. Return the complete song JSON again.'
        if attempt == 0 and repeats:
            prompt += '\n\nThe previous draft repeated lines from another track. Write a fresh song with a completely different chorus and imagery. DO NOT USE ANY OF THESE LINES:\n' + '\n'.join(repeats)
    raise ValueError('The model kept repeating lyrics from another track after one retry. This draft was not saved. Try writing this track again or choose another model.')


def export_text(project):
    lines = [f"# {project['name']}", '', f"Style: {project['style']}", f"Target length: {project['minimum']}–{project['maximum']} seconds per song", '']
    for track in project['tracks']:
        lines.extend([f"## {track['number']:02d}. " + (track['current']['title'] if track['current'] else 'Not drafted'),
                      f"Suno model: {track.get('suno_model', DEFAULT_SUNO_MODEL)}",
                      f"Status: {track_status(project, track)} · Rewrites: {track['rewrites']}/{'∞' if project['limit'] is None else project['limit']}", ''])
        if track['current']:
            lines.append(song_text(track['current']))
    return '\n'.join(lines)


def song_text(song, suno_model=None):
    fields = [f'{LABELS[k]}\n{song[k]}' for k in FIELDS]
    if suno_model:
        fields.insert(0, 'Suno model\n' + suno_model)
    return '\n\n'.join(fields) + '\n'


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.folder / 'projects.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL, updated TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
        if not self.db.execute('SELECT 1 FROM migrations WHERE name=?', ('song-library-v1',)).fetchone():
            with self.db:
                for (body,) in self.db.execute('SELECT body FROM projects').fetchall():
                    old = json.loads(body)
                    if len(old['tracks']) > 1:
                        coll = make_collection(old['name'], 'collection', old.get('theme', ''), [t['id'] for t in old['tracks']])
                        self.db.execute('INSERT INTO collections VALUES (?, ?)', (coll['id'], json.dumps(coll)))
                self.db.execute('INSERT INTO migrations VALUES (?)', ('song-library-v1',))
        self.db.commit()
        self.backup()
    def save(self, project):
        project = self.validate_project(project)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO projects VALUES (?, ?, ?)',
                            (project['id'], json.dumps(project, ensure_ascii=False), now()))
    def list(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM projects ORDER BY updated DESC')]
    @staticmethod
    def validate_project(project):
        value = copy.deepcopy(project)
        if not isinstance(value, dict) or value.get('schema_version', 1) != 1:
            raise ValueError('Unsupported song history version.')
        for key in ('id', 'name', 'style'):
            if not isinstance(value.get(key), str) or not value[key]:
                raise ValueError('Song history is missing ' + key + '.')
        if not isinstance(value.get('tracks'), list) or not value['tracks']:
            raise ValueError('Song history contains no tracks.')
        if value.get('limit') is not None and (type(value['limit']) is not int or not 0 <= value['limit'] <= 20):
            raise ValueError('Invalid rewrite limit.')
        if not (type(value.get('minimum')) is int and type(value.get('maximum')) is int
                and 30 <= value['minimum'] <= value['maximum'] <= 1200):
            raise ValueError('Invalid song duration.')
        for track in value['tracks']:
            if not isinstance(track, dict) or not isinstance(track.get('id'), str) or not isinstance(track.get('versions'), list):
                raise ValueError('Invalid track history.')
            if type(track.get('rewrites')) is not int or track['rewrites'] < 0:
                raise ValueError('Invalid rewrite count.')
            if type(track.get('approved')) is not bool or not isinstance(track.get('locks'), list) or any(field not in FIELDS for field in track['locks']):
                raise ValueError('Invalid track review settings.')
            if track.get('state', 'active') not in ('active', 'archive', 'trash'):
                raise ValueError('Invalid library state.')
            track.setdefault('suno_model', DEFAULT_SUNO_MODEL)
            if track['suno_model'] not in SUNO_MODELS:
                raise ValueError('Invalid Suno model.')
            for version in track['versions']:
                if not isinstance(version, dict) or 'song' not in version:
                    raise ValueError('Invalid saved version.')
                version.setdefault('suno_model', DEFAULT_SUNO_MODEL)
                if version['suno_model'] not in SUNO_MODELS:
                    raise ValueError('Invalid saved Suno model.')
            if track.get('current') is not None:
                validate_song(track['current'])
            for version in track['versions']:
                validate_song(version['song'])
        value['schema_version'] = 1
        return value

    def get(self, project_id):
        row = self.db.execute('SELECT body FROM projects WHERE id=?', (project_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def library_metadata(self):
        # SQLite extracts only the fields needed by a library listing, not revision bodies.
        return [{'id': row[0], 'name': row[1], 'updated': row[2]} for row in self.db.execute(
            "SELECT id, json_extract(body, '$.name'), updated FROM projects ORDER BY updated DESC")]

    def library_projects(self):
        """Project-shaped summaries; large lyric and revision fields stay in SQLite."""
        projects = {}
        rows = self.db.execute("""
            SELECT p.id, json_extract(p.body, '$.name'), json_extract(p.body, '$.style'),
                   json_extract(p.body, '$.theme'), json_extract(p.body, '$.count'),
                   json_extract(p.body, '$.limit'), json_extract(t.value, '$.id'),
                   json_extract(t.value, '$.number'), json_type(t.value, '$.current'),
                   json_extract(t.value, '$.current.title'), json_extract(t.value, '$.rewrites'),
                   json_extract(t.value, '$.approved'), json_extract(t.value, '$.state')
            FROM projects p, json_each(p.body, '$.tracks') t
            ORDER BY p.updated DESC, p.id, CAST(t.key AS INTEGER)
        """)
        for ident, name, style, theme, count, limit, track_id, number, current_type, title, rewrites, approved, state in rows:
            project = projects.setdefault(ident, {'id': ident, 'name': name, 'style': style,
                'theme': theme or '', 'count': count, 'limit': limit, 'tracks': []})
            project['tracks'].append({'id': track_id, 'number': number,
                'current': {'title': title} if current_type == 'object' else None,
                'rewrites': rewrites, 'approved': bool(approved), 'state': state or 'active'})
        return list(projects.values())

    def save_jobs(self, jobs):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO jobs VALUES (1, ?)', (json.dumps(list(jobs)),))

    def list_jobs(self):
        row = self.db.execute('SELECT body FROM jobs WHERE id=1').fetchone()
        return [tuple(job) for job in json.loads(row[0])] if row else []

    def apply_settings(self, settings, apply_existing=False):
        limit = settings.get('rewrite_limit', settings.get('limit', 3))
        if limit is not None and (type(limit) is not int or not 0 <= limit <= 20):
            raise ValueError('Invalid rewrite limit.')
        if settings.get('default_suno_model', DEFAULT_SUNO_MODEL) not in SUNO_MODELS:
            raise ValueError('Choose a supported Suno model.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (1, ?)', (json.dumps(settings),))
            if apply_existing:
                for project in self.list():
                    project['limit'] = limit
                    self.db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(project), project['id']))

    def backups(self):
        return sorted((self.folder / 'backups').glob('*.sqlite3'), reverse=True)

    def backup(self, destination=None):
        folder = self.folder / 'backups'
        folder.mkdir(exist_ok=True)
        destination = Path(destination) if destination else folder / (datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        if destination.resolve() == (self.folder / 'projects.sqlite3').resolve():
            raise ValueError('Choose a separate backup file.')
        with sqlite3.connect(destination) as target:
            self.db.backup(target)
        for old in self.backups()[10:]:
            old.unlink()
        return destination

    def restore_backup(self, path):
        path = Path(path).resolve()
        if not path.is_file() or path == (self.folder / 'projects.sqlite3').resolve():
            raise ValueError('Choose an existing backup file.')
        source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('The backup is damaged.')
            for (body,) in source.execute('SELECT body FROM projects'):
                self.validate_project(json.loads(body))
            for table in ('settings', 'collections', 'migrations'):
                source.execute('SELECT * FROM ' + table + ' LIMIT 1')
            self.backup()
            source.backup(self.db)
            self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
            self.db.commit()
        finally:
            source.close()

    def import_history(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get('schema_version', 1) != 1 or not isinstance(snapshot.get('songs'), list):
            raise ValueError('Choose an exported Versework history file.')
        projects = []
        for entry in snapshot['songs']:
            if not isinstance(entry, dict) or not isinstance(entry.get('brief'), dict) or not isinstance(entry.get('track'), dict):
                raise ValueError('Each exported song needs a brief and track history.')
            project = copy.deepcopy(entry['brief'])
            project.update(id=uuid.uuid4().hex, tracks=[copy.deepcopy(entry['track'])], count=1)
            project['tracks'][0].update(id=uuid.uuid4().hex, number=1, state='active')
            projects.append(self.validate_project(project))
        collection = snapshot.get('collection')
        if collection:
            if not isinstance(collection, dict) or any(not isinstance(collection.get(key), str) for key in ('name', 'kind')) or not isinstance(collection.get('theme', ''), str):
                raise ValueError('Invalid collection history.')
            collection = make_collection(collection['name'], collection['kind'], collection.get('theme', ''),
                                         [p['tracks'][0]['id'] for p in projects])
        self.backup()
        with self.db:
            for project in projects:
                self.db.execute('INSERT INTO projects VALUES (?, ?, ?)', (project['id'], json.dumps(project), now()))
            if collection:
                self.db.execute('INSERT INTO collections VALUES (?, ?)', (collection['id'], json.dumps(collection)))
        return [p['id'] for p in projects]

    def set_song_state(self, track_id, state):
        if state not in ('active', 'archive', 'trash'):
            raise ValueError('Unknown library state.')
        for project in self.list():
            for track in project['tracks']:
                if track['id'] == track_id:
                    track['state'] = state
                    self.save(project)
                    return project
        raise ValueError('Song no longer exists.')

    def duplicate_song(self, track_id):
        for project in self.list():
            for track in project['tracks']:
                if track['id'] == track_id:
                    result = copy.deepcopy(project)
                    result.update(id=uuid.uuid4().hex, name=project['name'] + ' (copy)', count=1, created=now(), updated=now())
                    result['tracks'] = [copy.deepcopy(track)]
                    result['tracks'][0].update(id=uuid.uuid4().hex, number=1, state='active', approved=False)
                    self.save(result)
                    return result
        raise ValueError('Song no longer exists.')
    def settings(self):
        row = self.db.execute('SELECT body FROM settings WHERE id=1').fetchone()
        saved = {'model': 'qwen3:8b', 'default_suno_model': DEFAULT_SUNO_MODEL,
                 'ui_language': 'system', 'colour_mode': 'system', 'colours': {},
                 **(json.loads(row[0]) if row else {})}
        if saved.get('default_suno_model') not in SUNO_MODELS:
            saved['default_suno_model'] = DEFAULT_SUNO_MODEL
        return saved
    def save_settings(self, settings):
        if settings.get('default_suno_model', DEFAULT_SUNO_MODEL) not in SUNO_MODELS:
            raise ValueError('Choose a supported Suno model.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (1, ?)', (json.dumps(settings),))

    def collections(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM collections ORDER BY rowid')]
    def save_collection(self, collection):
        known = {t['id'] for p in self.list() for t in p['tracks']}
        if any(ident not in known for ident in collection['songs']):
            raise ValueError('A selected song no longer exists.')
        validated = make_collection(collection['name'], collection['kind'], collection['theme'], collection['songs'])
        validated['id'] = collection['id']
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO collections VALUES (?, ?)', (validated['id'], json.dumps(validated, ensure_ascii=False)))
    def pending_songs(self, collection_id):
        collection = next((c for c in self.collections() if c['id'] == collection_id), None)
        if not collection:
            return []
        lookup = {track['id']: (p['id'], i, track) for p in self.list() for i, track in enumerate(p['tracks'])}
        return [(lookup[key][0], lookup[key][1]) for key in collection['songs'] if key in lookup and not lookup[key][2]['current']]

    def generation_context(self, project, index, collection_id=None):
        result = copy.deepcopy(project)
        track_id = project['tracks'][index]['id']
        chosen = next((c for c in self.collections() if c['id'] == collection_id and track_id in c['songs']), None)
        if chosen:
            lookup = {t['id']: t for p in self.list() for t in p['tracks']}
            peers = [{'title': lookup[i]['current']['title'], 'style': lookup[i]['current']['style_prompt'],
                      'do_not_repeat_these_lyrics': lookup[i]['current']['lyrics'][:1000]}
                     for i in chosen['songs'] if i != track_id and i in lookup and lookup[i]['current']]
            result['_collection_context'] = {'name': chosen['name'], 'kind': chosen['kind'], 'theme': chosen['theme'],
                                             'position': chosen['songs'].index(track_id) + 1, 'total': len(chosen['songs']), 'other_songs': peers}
        return result


def make_collection(name, kind='collection', theme='', songs=()):
    if not name.strip():
        raise ValueError('Give the collection a name.')
    if kind not in ['collection', 'album', 'ep']:
        raise ValueError('Choose Collection, Album or EP.')
    return {'id': uuid.uuid4().hex, 'name': name.strip(), 'kind': kind, 'theme': theme.strip(), 'songs': list(dict.fromkeys(songs))}


class Ollama:
    """Loopback only, no cloud models, no remote endpoint, no proxy."""
    def __init__(self):
        self.base = 'http://127.0.0.1:11434'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.connect_timeout = 10
        self.inactivity_timeout = 120
    def request(self, path, data=None, timeout=10):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={'Content-Type': 'application/json'})
        try:
            return self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read(20000)).get('error', str(e))
            except Exception:
                detail = str(e)
            raise RuntimeError(f'Ollama: {detail}') from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError('Cannot reach local Ollama. Open Settings → Start Ollama, then Check connection.') from e
    def models(self):
        with self.request('/api/tags') as r:
            models = json.load(r).get('models', [])
        return [m['name'] for m in models if not m.get('remote_model') and not m.get('remote_host') and 'cloud' not in m['name'].lower()]
    def generate(self, model, prompt, cancel, progress=None):
        if not model or 'cloud' in model.lower():
            raise ValueError('Choose an installed local model.')
        if cancel.is_set():
            raise Cancelled()
        payload = {'model': model, 'prompt': prompt, 'system': SYSTEM, 'format': SCHEMA, 'stream': True,
                   'think': False, 'keep_alive': '10m', 'options': {'temperature': 0.8, 'num_ctx': 16384, 'num_predict': 6000}}
        # Blocking I/O lives in a daemon reader. The caller remains responsive
        # even while the connection is being established or a line is partial.
        events = queue.Queue()
        stopped = threading.Event()
        connection = []
        def read_stream():
            try:
                with self.request('/api/generate', payload, timeout=self.connect_timeout) as response:
                    connection.append(response)
                    if stopped.is_set():
                        return
                    stream_socket = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                    if stream_socket is not None:
                        stream_socket.settimeout(self.inactivity_timeout)
                    for line in response:
                        if stopped.is_set():
                            return
                        events.put(('line', line))
            except Exception as error:
                events.put(('error', error))
            finally:
                events.put(('end', None))
        threading.Thread(target=read_stream, daemon=True, name='versework-ollama-stream').start()
        chunks, done, count = [], False, 0
        try:
            while not done:
                if cancel.is_set():
                    raise Cancelled()
                try:
                    event, value = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if event == 'error':
                    if isinstance(value, (TimeoutError, socket.timeout)):
                        raise RuntimeError('Local Ollama stopped responding. Try a smaller model or a shorter brief; your previous draft is unchanged.') from value
                    raise value
                if event == 'end':
                    break
                if not value.strip():
                    continue
                part = json.loads(value)
                if part.get('error'):
                    raise RuntimeError(str(part['error']))
                chunk = part.get('response', '')
                chunks.append(chunk)
                count += len(chunk)
                if progress:
                    progress(count)
                if part.get('done'):
                    if part.get('done_reason') == 'length':
                        raise ValueError('The model ran out of output space. Try a shorter brief or another model.')
                    done = True
        finally:
            stopped.set()
            if connection:
                stream_socket = getattr(getattr(getattr(connection[0], 'fp', None), 'raw', None), '_sock', None)
                if stream_socket is not None:
                    try:
                        stream_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        if cancel.is_set():
            raise Cancelled()
        if not done:
            raise RuntimeError('Ollama stopped before completing the song. Your previous draft is unchanged.')
        try:
            return validate_song(json.loads(''.join(chunks)))
        except json.JSONDecodeError as e:
            raise ValueError('The model returned incomplete JSON. Try again or choose another model.') from e
