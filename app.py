#!/usr/bin/env python3
"""Versework: a native, song-first GTK workspace."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from core import (DRUM_FEELS, drum_feel, PRODUCTION_OPTIONS, production_direction, TEXT_LIMIT, FIELDS, LABELS, VARIETIES, VOCALS, SUNO_MODELS, DEFAULT_SUNO_MODEL, Store, Ollama, Cancelled, create_project,
                  make_collection, commit_version, restore_version, generate_song, track_status, song_text)
from appearance import COLOUR_KEYS, LAYOUT_CSS, read_palette, colour_css, resolved_palette, valid_colour
from updater import current_revision, latest_revision, install_update, confirm_startup, has_rollback, rollback_installation
from i18n import LANGUAGES, set_language, system_language, t
from generation_ui import GenerationMixin
from workflow_ui import WorkflowMixin
from production_ui import ProductionMixin

APP_ID = 'io.versework.Studio'
DATA = Path(os.environ.get('VERSEWORK_DATA', str(Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'versework/data')))


def box(vertical=True, spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def label(text, css=None):
    w = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        w.add_css_class(css)
    if css == 'error':
        w.set_visible(bool(text))
        w.connect('notify::label', lambda *_: w.set_visible(bool(w.get_label())))
    return w


def button(text, callback, primary=False):
    w = Gtk.Button(label=text)
    w.connect('clicked', lambda *_: callback())
    if primary:
        w.add_css_class('suggested-action')
    return w


def margins(widget, amount=20):
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(widget, 'set_margin_' + side)(amount)
    return widget


def scrolled(child, height=None):
    w = Gtk.ScrolledWindow(hexpand=True, vexpand=height is None)
    w.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    w.set_child(child)
    if height:
        w.set_min_content_height(height)
    return w


def text_input(text='', height=120):
    w = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
    w.set_left_margin(12)
    w.set_right_margin(12)
    w.set_top_margin(12)
    w.set_bottom_margin(12)
    w.set_pixels_above_lines(2)
    w.set_pixels_below_lines(2)
    w.get_buffer().set_text(text)
    wrap = scrolled(w, height)
    wrap.add_css_class('text-editor')
    return w, wrap


def limit_text(widget, container):
    """Reject over-limit insertions, while preserving existing text for correction."""
    buffer = widget.get_buffer()
    counter = label('', 'caption')
    counter.set_halign(Gtk.Align.END)
    container.append(counter)
    def update(*_):
        count = buffer.get_char_count()
        counter.set_text(f'{count} / {TEXT_LIMIT}')
        if count > TEXT_LIMIT:
            counter.add_css_class('error')
        else:
            counter.remove_css_class('error')
    def inserting(buf, location, text, length):
        if buf.get_char_count() + len(text) > TEXT_LIMIT:
            buf.stop_emission_by_name('insert-text')
            widget.error_bell()
    buffer.connect('insert-text', inserting)
    buffer.connect('changed', update)
    update()


def dropdown(values, selected=None, captions=None):
    w = Gtk.DropDown.new_from_strings(captions or [t(v) for v in values])
    w.values = values
    if selected in values:
        w.set_selected(values.index(selected))
    return w


def text_of(widget):
    if isinstance(widget, Gtk.TextView):
        b = widget.get_buffer()
        return b.get_text(b.get_start_iter(), b.get_end_iter(), True)
    if isinstance(widget, Gtk.SpinButton):
        return widget.get_value_as_int()
    if isinstance(widget, Gtk.DropDown):
        if hasattr(widget, 'values'):
            return widget.values[widget.get_selected()]
        item = widget.get_selected_item()
        return item.get_string() if item else ''
    return widget.get_text()


def spin(value, low, high, step=1):
    w = Gtk.SpinButton.new_with_range(low, high, step)
    w.set_value(value)
    return w


def song_title(project, index):
    track = project['tracks'][index]
    if track['current']:
        return track['current']['title']
    return project['name'] + (f" · {index + 1}" if project['count'] > 1 else '')


def collection_kind(collection):
    return t({'collection': 'Collection', 'album': 'Album', 'ep': 'EP'}[collection['kind']])


class Studio(GenerationMixin, ProductionMixin, WorkflowMixin, Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE if '--smoke' in sys.argv else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.store = Store(DATA)
        self.settings = self.store.settings()
        set_language(self.settings['ui_language'])
        self.ollama = Ollama()
        self.project = None
        self.track_index = None
        self.editors, self.lockers = {}, {}
        self.feedback_editor = None
        self.collection_id = None
        self.view = 'library'
        self.busy = False
        self.settings_window = None
        self.cancel_event = threading.Event()
        self.smoke_ok = False
        self.update_running = False
        self.update_installed = False
        self.restart_requested = False
        self.failed_jobs = self.store.list_jobs()
        self.connect('activate', self.activate)

    def activate(self, *_):
        if hasattr(self, 'win'):
            self.win.present()
            return
        self.win = Gtk.ApplicationWindow(application=self, title='Versework')
        self.win.set_default_size(1220, 840)
        self.win.connect('close-request', self.close)
        self.layout_provider = Gtk.CssProvider()
        self.layout_provider.load_from_data(LAYOUT_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.layout_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.native_colours = self.native_palette()
        self.colour_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.colour_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.last_palette = None
        self.refresh_theme()
        GLib.timeout_add_seconds(3, self.refresh_theme)
        self.build_shell()
        self.win.present()
        confirm_startup(Path(__file__).resolve().parent)
        if '--smoke' in sys.argv:
            GLib.timeout_add(300, self.smoke)

    def refresh_theme(self):
        palette = resolved_palette(self.settings)
        if palette != self.last_palette:
            self.colour_provider.load_from_data(colour_css(palette).encode())
            self.last_palette = palette
        return True

    def build_shell(self):
        header = Gtk.HeaderBar()
        header.set_title_widget(label('Versework', 'heading'))
        self.new_song_button = button(t('New song'), self.new_dialog, True)
        self.settings_button = button(t('Settings'), self.settings_dialog)
        header.pack_start(self.new_song_button)
        header.pack_end(self.settings_button)
        self.suno_button = button(t('Open Suno'), self.open_suno)
        self.suno_button.set_tooltip_text(t('Open Suno in your browser to log in or create music.'))
        header.pack_end(self.suno_button)
        self.win.set_titlebar(header)
        root = box(spacing=0)
        self.win.set_child(root)
        body = box(False, 0)
        body.set_vexpand(True)
        root.append(body)
        self.sidebar = box(spacing=14)
        self.sidebar.add_css_class('sidebar')
        self.sidebar.set_size_request(190, -1)
        self.sidebar.set_hexpand(False)
        body.append(self.sidebar)
        self.content = box()
        self.content.set_hexpand(True)
        body.append(self.content)
        footer = box(False)
        footer.add_css_class('status-footer')
        self.spinner = Gtk.Spinner()
        footer.append(self.spinner)
        self.status = label(t('Saved on this computer'), 'caption')
        self.status.set_hexpand(True)
        footer.append(self.status)
        self.stop_button = button(t('Stop writing'), self.stop)
        self.stop_button.set_visible(self.busy)
        footer.append(self.stop_button)
        self.retry_button = button('Retry failed songs', self.retry_failed)
        self.retry_button.set_visible(bool(self.failed_jobs))
        footer.append(self.retry_button)
        root.append(footer)
        self.refresh_projects()
        if self.view == 'song' and self.project:
            self.render_project()
        else:
            self.render_library()
        if self.busy:
            self.spinner.start()
            self.content.set_sensitive(False)
            self.sidebar.set_sensitive(False)

    def notify(self, text, error=False):
        self.status.set_text(text)
        self.status.remove_css_class('error')
        if error:
            self.status.add_css_class('error')

    def clear(self, container):
        while container.get_first_child():
            container.remove(container.get_first_child())

    def refresh_projects(self):
        self.clear(self.sidebar)
        self.sidebar.append(button(t('Songs'), lambda: self.show_library(None)))
        self.sidebar.append(label(t('Collections'), 'caption'))
        listing = box(spacing=6)
        for coll in self.store.collections():
            inner = box(spacing=3)
            inner.append(label(coll['name']))
            inner.append(label(collection_kind(coll), 'caption'))
            b = Gtk.Button(child=inner)
            b.connect('clicked', lambda _, ident=coll['id']: self.show_library(ident))
            listing.append(b)
        self.sidebar.append(scrolled(listing))
        self.sidebar.append(button(t('New collection'), self.collection_dialog))

    def song_rows(self):
        return [(p, i) for p in self.store.list() for i in range(len(p['tracks']))]

    def current_collection(self):
        return next((c for c in self.store.collections() if c['id'] == self.collection_id), None)

    def show_library(self, collection_id=None):
        if self.busy:
            self.notify(t('Finish or stop writing first.'))
            return
        if not self.flush():
            return
        self.collection_id = collection_id
        self.editors, self.lockers, self.feedback_editor = {}, {}, None
        self.project, self.track_index = None, None
        self.view = 'library'
        self.render_library()

    def render_library(self):
        self.clear(self.content)
        outer = margins(box(spacing=20), 20)
        self.content.append(outer)
        coll = self.current_collection()
        head = box(False)
        headings = box(spacing=6)
        headings.set_hexpand(True)
        headings.append(label(coll['name'] if coll else t('Songs'), 'title'))
        headings.append(label(collection_kind(coll) if coll else t('Start with a song. Organise it later.'), 'caption'))
        head.append(headings)
        if coll:
            head.append(button(t('Manage collection'), lambda: self.collection_dialog(coll)))
            head.append(button(t('Review songs'), self.collection_feedback))
            head.append(button(t('Export'), self.export_dialog))
        outer.append(head)
        if coll and coll['theme']:
            outer.append(label(coll['theme']))
        if coll and self.store.pending_songs(coll['id']):
            outer.append(button(t('Write remaining drafts'), self.generate_missing, True))
        songs = [(p, i) for p in self.store.library_projects() for i in range(len(p['tracks']))]
        if coll:
            mapping = {p['tracks'][i]['id']: (p, i) for p, i in songs}
            songs = [mapping[ident] for ident in coll['songs'] if ident in mapping]
        search = Gtk.SearchEntry(placeholder_text=t('Search songs'))
        outer.append(search)
        states = dropdown(['active', 'archive', 'trash'], 'active', ['Active songs', 'Archived songs', 'Trash'])
        outer.append(states)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.library_list = listing
        for p, i in songs:
            track = p['tracks'][i]
            row = Gtk.ListBoxRow()
            row.add_css_class('library-row')
            layout = box(False, 16)
            layout.append(Gtk.Image.new_from_icon_name('audio-x-generic-symbolic'))
            description = box(spacing=5)
            description.set_hexpand(True)
            description.append(label(song_title(p, i), 'heading'))
            brief_label = label(p.get('theme') or p['style'], 'caption')
            brief_label.set_lines(2)
            description.append(brief_label)
            description.append(label(t(track_status(p, track)), 'caption'))
            layout.append(description)
            layout.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))
            row.set_child(layout)
            row.song_ref = (p['id'], i)
            row.song_state = track.get('state', 'active')
            row.search_text = (song_title(p, i) + ' ' + p.get('theme', '') + ' ' + p['style']).casefold()
            listing.append(row)
        listing.connect('row-activated', lambda _, row: self.load_project(*row.song_ref))
        listing.set_filter_func(lambda row: row.song_state == text_of(states) and search.get_text().casefold() in row.search_text)
        states.connect('notify::selected', lambda *_: listing.invalidate_filter())
        search.connect('search-changed', lambda *_: listing.invalidate_filter())
        if songs:
            outer.append(scrolled(listing))
        if not songs:
            empty = box(spacing=12)
            empty.set_vexpand(True)
            empty.set_valign(Gtk.Align.CENTER)
            empty.append(label(t('No songs yet'), 'heading'))
            empty.append(label(t('Write independently, or gather songs around a theme and shape an album or EP.'), 'caption'))
            empty.append(button(t('New song'), self.new_dialog, True))
            outer.append(empty)
        else:
            outer.append(label(t('Songs: {n}', n=len(songs)), 'caption'))

    def welcome(self):
        self.show_library()

    def load_project(self, ident, index=0):
        if self.busy or not self.flush():
            return
        self.project = next(p for p in self.store.list() if p['id'] == ident)
        self.track_index = index
        self.view = 'song'
        self.render_project()

    def render_project(self):
        self.editors, self.lockers, self.feedback_editor = {}, {}, None
        self.copy_buttons = {}
        self.clear(self.content)
        outer = margins(box(spacing=12), 20)
        outer.set_vexpand(True)
        self.content.append(outer)
        p, i = self.project, self.track_index or 0
        self.track_index = i
        track = p['tracks'][i]
        breadcrumb = box(False)
        coll = self.current_collection()
        breadcrumb.append(button(coll['name'] if coll else t('Songs'), lambda: self.show_library(self.collection_id)))
        title = label(song_title(p, i), 'title')
        title.set_hexpand(True)
        breadcrumb.append(title)
        breadcrumb.append(button(t('Production'), self.production_dialog))
        breadcrumb.append(button(t('Organise song'), self.organise_dialog))
        outer.append(breadcrumb)
        sub = box(False, 16)
        sub.append(label(t(track_status(p, track)), 'accent'))
        sub.append(label(t('Target: {minimum}–{maximum} seconds', minimum=p['minimum'], maximum=p['maximum']), 'caption'))
        sub.append(label(t('Rewrites: {used}/{limit}', used=track['rewrites'], limit='∞' if p['limit'] is None else p['limit']), 'caption'))
        outer.append(sub)
        if not track['current']:
            panel = margins(box(spacing=16), 20)
            panel.add_css_class('card')
            panel.append(label(t('Song brief'), 'heading'))
            panel.append(label(p['style']))
            if p['theme']:
                panel.append(label(p['theme'], 'caption'))
            panel.append(label(t('Lyric language') + ': ' + p['language'], 'caption'))
            panel.append(label(t('Suno model'), 'heading'))
            self.suno_model_selector = dropdown(list(SUNO_MODELS), track.get('suno_model', DEFAULT_SUNO_MODEL), [t(SUNO_MODELS[key]['label']) for key in SUNO_MODELS])
            panel.append(self.suno_model_selector)
            self.suno_model_hint = label(t(SUNO_MODELS[track.get('suno_model', DEFAULT_SUNO_MODEL)]['about']), 'caption')
            panel.append(self.suno_model_hint)
            self.suno_model_selector.connect('notify::selected', lambda *_: self.suno_model_hint.set_text(t(SUNO_MODELS[text_of(self.suno_model_selector)]['about'])))
            panel.append(button(t('Write song'), lambda: self.start_jobs([i]), True))
            outer.append(panel)
            return
        toolbar = box(False)
        toolbar.append(button(t('Save'), self.save_edits))
        copy_song_button = button(t('Copy song'), lambda: self.copy_current(copy_song_button))
        toolbar.append(copy_song_button)
        toolbar.append(button(t('Versions'), self.history_dialog))
        toolbar.append(button(t('Export song'), self.export_dialog))
        toolbar.append(button('Song tools', self.manage_song_dialog))
        toolbar.append(button(t('Reopen') if track['approved'] else t('Approve song'), self.approve, not track['approved']))
        outer.append(toolbar)
        self.editor_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.editor_stack.set_vhomogeneous(False)
        switcher = Gtk.StackSwitcher(stack=self.editor_stack, halign=Gtk.Align.START)
        outer.append(switcher)
        outer.append(self.editor_stack)
        self.editor_stack.set_vexpand(True)
        pages = {}
        for name in ['Lyrics', 'Sound', 'Review']:
            page = box(spacing=18)
            page.set_margin_top(8)
            page.set_margin_end(8)
            page.set_margin_bottom(8)
            pages[name] = page
            self.editor_stack.add_titled(scrolled(page), name, t(name))
        model_box = box(spacing=8)
        model_box.append(label(t('Suno model'), 'heading'))
        self.suno_model_selector = dropdown(list(SUNO_MODELS), track.get('suno_model', DEFAULT_SUNO_MODEL), [t(SUNO_MODELS[key]['label']) for key in SUNO_MODELS])
        self.suno_model_selector.set_sensitive(not track['approved'] and not self.busy)
        model_box.append(self.suno_model_selector)
        self.suno_model_hint = label(t(SUNO_MODELS[track.get('suno_model', DEFAULT_SUNO_MODEL)]['about']), 'caption')
        model_box.append(self.suno_model_hint)
        model_box.append(label(t('Choose the same Suno model in Create. Versework prepares the prompts but does not create the audio.'), 'caption'))
        self.suno_model_selector.connect('notify::selected', lambda *_: self.suno_model_hint.set_text(t(SUNO_MODELS[text_of(self.suno_model_selector)]['about'])))
        pages['Sound'].append(model_box)
        self.editor_stack.set_visible_child_name(getattr(self, 'editor_tab', 'Lyrics'))
        self.editor_stack.connect('notify::visible-child-name', lambda *_: setattr(self, 'editor_tab', self.editor_stack.get_visible_child_name()))
        song = track['current']
        for field in FIELDS:
            target = pages['Lyrics'] if field in ['title', 'lyrics'] else pages['Sound']
            fieldbox = box(spacing=8)
            head = box(False)
            title = label(t(LABELS[field]), 'heading')
            title.set_hexpand(True)
            head.append(title)
            lock = Gtk.CheckButton(label=t('Lock'), active=field in track['locks'])
            lock.set_sensitive(not track['approved'] and not self.busy)
            self.lockers[field] = lock
            head.append(lock)
            copy_control = self.field_copy_button(field)
            self.copy_buttons[field] = copy_control
            head.append(copy_control)
            fieldbox.append(head)
            if field in ['lyrics', 'style_prompt', 'exclusions']:
                widget, wrap = text_input(song[field], 120 if field == 'lyrics' else 100)
                if field == 'lyrics':
                    fieldbox.set_vexpand(True)
                    wrap.set_vexpand(True)
                fieldbox.append(wrap)
                if field in ['style_prompt', 'exclusions']:
                    limit_text(widget, fieldbox)
            elif field in ['weirdness', 'style_influence']:
                widget = spin(song[field], 0, 100)
                fieldbox.append(widget)
            elif field in ['variety', 'vocal_gender']:
                widget = dropdown(VARIETIES if field == 'variety' else VOCALS, song[field])
                fieldbox.append(widget)
            else:
                widget = Gtk.Entry(text=song[field])
                fieldbox.append(widget)
            widget.set_sensitive(not track['approved'] and not self.busy)
            self.editors[field] = widget
            target.append(fieldbox)
        refresh = button(t('Refresh lyrics'), self.refresh_lyrics_dialog)
        refresh.set_sensitive(not track['approved'] and not self.busy and (p['limit'] is None or track['rewrites'] < p['limit']))
        pages['Lyrics'].append(refresh)
        pages['Lyrics'].append(label(t('Lock fields to preserve them exactly during rewrites.'), 'caption'))
        review = pages['Review']
        review.append(label(t('Feedback'), 'heading'))
        review.append(label(t('Describe what to change, or add listening notes from Suno.'), 'caption'))
        self.feedback_editor, wrap = text_input(track.get('feedback', ''), 170)
        wrap.set_vexpand(True)
        self.feedback_editor.set_sensitive(not track['approved'] and not self.busy)
        review.append(wrap)
        self.rewrite_scope = dropdown(['all', 'lyrics', 'sound', 'section'], 'all',
                                      ['Everything unlocked', 'Lyrics only', 'Sound only', 'Selected section'])
        review.append(self.rewrite_scope)
        self.rewrite_section = Gtk.Entry(placeholder_text='Section heading, e.g. [Chorus]')
        review.append(self.rewrite_section)
        revise = button(t('Rewrite song'), self.rewrite, True)
        revise.set_sensitive(not track['approved'] and not self.busy and (p['limit'] is None or track['rewrites'] < p['limit']))
        review.append(revise)
        if song.get('notes'):
            review.append(label(song['notes'], 'caption'))
        review.append(label(t('Duration is a writing target; Suno determines the audio length.'), 'caption'))

    def flush(self):
        if not self.project or self.track_index is None or self.busy:
            return True
        try:
            candidate = copy.deepcopy(self.project)
            track = candidate['tracks'][self.track_index]
            if not track['approved']:
                if hasattr(self, 'suno_model_selector'):
                    track['suno_model'] = text_of(self.suno_model_selector)
                if self.editors:
                    song = {k: text_of(w) for k, w in self.editors.items()}
                    song['notes'] = track['current'].get('notes', '')
                    if song != track['current']:
                        commit_version(candidate, self.track_index, song, 'edit')
                    track['locks'] = [k for k, w in self.lockers.items() if w.get_active()]
                    if self.feedback_editor:
                        track['feedback'] = text_of(self.feedback_editor)
                self.store.save(candidate)
                self.project = candidate
            return True
        except Exception as e:
            self.notify(str(e), True)
            return False

    def save_edits(self):
        if self.flush():
            self.render_project()
            self.notify(t('Edits saved.'))

    def flash_copy(self, control, default_label):
        if control is None:
            return
        control.set_label(t('Copied'))
        control.add_css_class('copy-confirmed')
        def restore():
            if control.get_root() is None:
                return False
            control.set_label(default_label)
            control.remove_css_class('copy-confirmed')
            return False
        GLib.timeout_add(1200, restore)

    def field_copy_button(self, field):
        control = button(t('Copy'), lambda: self.copy_field(field, control))
        return control

    def copy_field(self, field, control=None):
        self.copy(str(text_of(self.editors[field])))
        self.flash_copy(control, t('Copy'))

    def copy_current(self, control=None):
        if self.flush():
            track = self.project['tracks'][self.track_index]
            self.copy(song_text(track['current'], track.get('suno_model', DEFAULT_SUNO_MODEL)))
            self.flash_copy(control, t('Copy song'))

    def copy(self, value):
        self.win.get_clipboard().set(value)
        self.notify(t('Copied to clipboard.'))

    def open_suno(self):
        launcher = Gtk.UriLauncher.new('https://suno.com/create')
        def opened(source, result):
            try:
                source.launch_finish(result)
            except GLib.Error as error:
                if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                    self.notify(t('Could not open Suno: {error}', error=error.message), True)
        launcher.launch(self.win, None, opened)

    def dialog(self, title, width=640, height=650):
        window = Gtk.Window(application=self, title=title, transient_for=self.win, modal=True)
        window.set_default_size(width, height)
        header = Gtk.HeaderBar(show_title_buttons=False)
        heading = label(title, 'heading')
        heading.set_wrap(False)
        header.set_title_widget(heading)
        header.pack_end(button(t('Close'), window.close))
        window.set_titlebar(header)
        controller = Gtk.EventControllerKey()
        def key(_, keyval, *args):
            if keyval == Gdk.KEY_Escape:
                window.close()
                return True
            return False
        controller.connect('key-pressed', key)
        window.add_controller(controller)
        window.escape_controller = controller
        child = margins(box(spacing=14), 16)
        root = box(spacing=0)
        root.append(scrolled(child))
        window.actions = margins(box(False), 16)
        window.actions.set_visible(False)
        root.append(window.actions)
        window.set_child(root)
        return window, child

    def new_dialog(self):
        if self.busy:
            self.notify(t('Finish or stop writing first.'))
            return
        window, c = self.dialog(t('New song'))
        entries = {}
        for key, title, value in [('name', 'Working title', ''), ('language', 'Lyric language', 'English')]:
            c.append(label(t(title), 'heading'))
            entries[key] = Gtk.Entry(text=value)
            c.append(entries[key])
        c.append(label(t('Your lyrics (optional)'), 'heading'))
        user_lyrics, lyrics_wrap = text_input('', 180)
        c.append(lyrics_wrap)
        c.append(label(t('Leave empty to have Ollama write the lyrics.'), 'caption'))
        lyrics_handling = dropdown(['suggest', 'preserve'], 'suggest',
                                   [t('Offer improvement suggestions'), t('Leave my lyrics unchanged')])
        c.append(lyrics_handling)
        c.append(label(t('Style prompt'), 'heading'))
        style, wrap = text_input('', 110)
        c.append(wrap)
        limit_text(style, c)
        c.append(label(t('Suno model'), 'heading'))
        suno_model = dropdown(list(SUNO_MODELS), self.settings.get('default_suno_model', DEFAULT_SUNO_MODEL), [t(SUNO_MODELS[key]['label']) for key in SUNO_MODELS])
        c.append(suno_model)
        c.append(label(t(SUNO_MODELS[text_of(suno_model)]['about']), 'caption'))
        c.append(label(t('Choose the same Suno model in Create. Versework prepares the prompts but does not create the audio.'), 'caption'))
        c.append(label(t('Optional theme'), 'heading'))
        theme, wrap = text_input('', 80)
        c.append(wrap)
        production = Gtk.Expander(label=t('Production direction'))
        production_box = box(spacing=16)
        production_box.set_margin_top(16)
        production.set_child(production_box)
        collect_production = self.production_controls(production_box, {'density': 'restrained'})
        c.append(production)
        collections = self.store.collections()
        ids = [''] + [x['id'] for x in collections]
        pick = dropdown(ids, self.collection_id or '', [t('No collection')] + [x['name'] for x in collections])
        c.append(label(t('Collection (optional)'), 'heading'))
        c.append(pick)
        default_limit = self.settings.get('rewrite_limit', 3)
        unlimited = Gtk.CheckButton(label=t('Disable rewrite limits completely'), active=default_limit is None)
        c.append(unlimited)
        count, minimum, maximum, limit = spin(1, 1, 20), spin(180, 30, 1200, 15), spin(240, 30, 1200, 15), spin(default_limit if default_limit is not None else 3, 0, 20)
        limit.set_sensitive(not unlimited.get_active())
        unlimited.connect('toggled', lambda w: limit.set_sensitive(not w.get_active()))
        for title, widget in [('Song count', count), ('Minimum length (seconds)', minimum), ('Maximum length (seconds)', maximum), ('AI rewrites per song', limit)]:
            row = box(False)
            l = label(t(title))
            l.set_hexpand(True)
            row.append(l)
            row.append(widget)
            c.append(row)
        error = label('', 'error')
        c.append(error)
        def save():
            try:
                if not self.flush():
                    return
                p = create_project(text_of(entries['name']) or t('Untitled song'), text_of(style), text_of(count), text_of(minimum), text_of(maximum), None if unlimited.get_active() else text_of(limit), text_of(theme), text_of(entries['language']), text_of(user_lyrics), text_of(suno_model))
                for track in p['tracks']:
                    track['lyrics_assist'] = text_of(lyrics_handling)
                for track in p['tracks']:
                    track['production'] = collect_production()
                self.store.save(p)
                coll_id = text_of(pick)
                if coll_id:
                    coll = next(c for c in self.store.collections() if c['id'] == coll_id)
                    coll['songs'].extend(track['id'] for track in p['tracks'])
                    self.store.save_collection(coll)
                self.project, self.track_index, self.collection_id, self.view = p, 0, coll_id or None, 'song'
                self.refresh_projects()
                self.render_project()
                window.close()
            except Exception as e:
                error.set_text(str(e))
        window.actions.append(button(t('Create'), save, True))
        window.actions.set_visible(True)
        window.controls = {'suno_model': suno_model, 'style': style, 'lyrics': user_lyrics, 'unlimited': unlimited, 'limit': limit}
        window.present()
        return window

    def collection_dialog(self, existing=None):
        if self.busy or not self.flush():
            return
        window, c = self.dialog(t('Manage collection') if existing else t('New collection'), 720, 740)
        current = copy.deepcopy(existing) if existing else make_collection(t('Collection'))
        c.append(label(t('Name'), 'heading'))
        name = Gtk.Entry(text=current['name'] if existing else '')
        c.append(name)
        c.append(label(t('Format'), 'heading'))
        kind = dropdown(['collection', 'album', 'ep'], current['kind'], [t('Collection'), t('Album'), t('EP')])
        c.append(kind)
        c.append(label(t('Optional theme'), 'heading'))
        theme, wrap = text_input(current['theme'], 80)
        c.append(wrap)
        c.append(label(t('Choose songs and their running order. Their drafts and history stay intact.'), 'caption'))
        lookup = {p['tracks'][i]['id']: song_title(p, i) for p, i in self.song_rows()}
        ordered = [ident for ident in current['songs'] if ident in lookup] + [ident for ident in lookup if ident not in current['songs']]
        selected = set(current['songs'])
        rows = box(spacing=7)
        c.append(rows)
        checks = {}
        def render():
            self.clear(rows)
            checks.clear()
            for index, ident in enumerate(ordered):
                row = box(False)
                check = Gtk.CheckButton(label=lookup[ident], active=ident in selected, hexpand=True)
                check.connect('toggled', lambda w, key=ident: selected.add(key) if w.get_active() else selected.discard(key))
                checks[ident] = check
                row.append(check)
                def move(offset, pos=index):
                    target = pos + offset
                    if 0 <= target < len(ordered):
                        ordered[pos], ordered[target] = ordered[target], ordered[pos]
                        render()
                up = button('↑', lambda fn=move: fn(-1))
                up.set_tooltip_text(t('Move up'))
                up.set_sensitive(index > 0)
                down = button('↓', lambda fn=move: fn(1))
                down.set_tooltip_text(t('Move down'))
                down.set_sensitive(index < len(ordered) - 1)
                row.append(up)
                row.append(down)
                rows.append(row)
        render()
        error = label('', 'error')
        c.append(error)
        def save():
            try:
                changed = make_collection(name.get_text(), text_of(kind), text_of(theme), [key for key in ordered if key in selected])
                if existing:
                    changed['id'] = existing['id']
                self.store.save_collection(changed)
                window.close()
                self.refresh_projects()
                self.show_library(changed['id'])
            except Exception as e:
                error.set_text(str(e))
        window.actions.append(button(t('Save collection'), save, True))
        window.actions.set_visible(True)
        window.present()
        return window

    def organise_dialog(self):
        if self.busy or not self.flush():
            return
        window, c = self.dialog(t('Organise song'), 560, 430)
        c.append(label(t('Add this song to any collection. Unchecking removes only the membership.'), 'caption'))
        track_id = self.project['tracks'][self.track_index]['id']
        collections = self.store.collections()
        checks = []
        for coll in collections:
            check = Gtk.CheckButton(label=coll['name'], active=track_id in coll['songs'])
            c.append(check)
            checks.append((coll, check))
        if not checks:
            c.append(label(t('No collections yet. Create one from the sidebar.')))
        error = label('', 'error')
        c.append(error)
        def save():
            try:
                for coll, check in checks:
                    if check.get_active() and track_id not in coll['songs']:
                        coll['songs'].append(track_id)
                    elif not check.get_active():
                        coll['songs'] = [i for i in coll['songs'] if i != track_id]
                    self.store.save_collection(coll)
                self.refresh_projects()
                window.close()
            except Exception as e:
                error.set_text(str(e))
        window.actions.append(button(t('Save'), save, True))
        window.actions.set_visible(True)
        window.present()

    def settings_dialog(self):
        if self.settings_window:
            self.settings_window.present()
            return self.settings_window
        window, c = self.dialog(t('Settings'), 670, 740)
        self.settings_window = window
        def closing(*_):
            self.settings_window = None
            return False
        window.connect('close-request', closing)
        c.append(label(t('Appearance'), 'heading'))
        c.append(Gtk.Separator())
        c.append(label(t('Rewrite limits'), 'heading'))
        rewrite_limit = spin(self.settings.get('rewrite_limit', 3) if self.settings.get('rewrite_limit', 3) is not None else 3, 0, 20)
        unlimited = Gtk.CheckButton(label=t('Disable rewrite limits completely'), active=self.settings.get('rewrite_limit', 3) is None)
        c.append(unlimited)
        limit_row = box(False)
        limit_label = label(t('Default rewrites per song'))
        limit_label.set_hexpand(True)
        limit_row.append(limit_label)
        limit_row.append(rewrite_limit)
        c.append(limit_row)
        apply_existing = Gtk.CheckButton(label='Apply this limit to existing songs', active=False)
        c.append(apply_existing)
        rewrite_limit.set_sensitive(not unlimited.get_active())
        unlimited.connect('toggled', lambda w: rewrite_limit.set_sensitive(not w.get_active()))
        mode = dropdown(['system', 'custom'], self.settings.get('colour_mode', 'system'), [t('Follow Omarchy theme'), t('Custom colours')])
        c.append(mode)
        palette = resolved_palette(self.settings) or self.native_colours
        colour_entries = {}
        colour_box = box(spacing=9)
        c.append(colour_box)
        for key, title in zip(COLOUR_KEYS, ['Background', 'Surface', 'Text', 'Accent']):
            row = box(False)
            caption = label(t(title))
            caption.set_hexpand(True)
            row.append(caption)
            entry = Gtk.Entry(text=palette[key], width_chars=9, max_length=7)
            colour_entries[key] = entry
            picker = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
            rgba = Gdk.RGBA()
            rgba.parse(palette[key])
            picker.set_rgba(rgba)
            def picked(w, _, field=entry):
                value = w.get_rgba()
                field.set_text('#%02X%02X%02X' % tuple(round(v * 255) for v in (value.red, value.green, value.blue)))
            picker.connect('notify::rgba', picked)
            def typed(w, target=picker):
                if valid_colour(w.get_text()):
                    colour = Gdk.RGBA()
                    colour.parse(w.get_text())
                    if not target.get_rgba().equal(colour):
                        target.set_rgba(colour)
            entry.connect('changed', typed)
            row.append(entry)
            row.append(picker)
            colour_box.append(row)
        def mode_changed(*_):
            colour_box.set_sensitive(text_of(mode) == 'custom')
        mode.connect('notify::selected', mode_changed)
        mode_changed()
        def reset():
            mode.set_selected(0)
            for key, colour in (read_palette() or self.native_colours).items():
                colour_entries[key].set_text(colour)
        c.append(button(t('Restore theme colours'), reset))
        c.append(label(t('Colours affect Versework only. Theme changes are followed automatically.'), 'caption'))
        c.append(Gtk.Separator())
        c.append(label(t('Interface language'), 'heading'))
        languages = dropdown([code for code, _ in LANGUAGES], self.settings.get('ui_language', 'system'), [t(title) if code == 'system' else title for code, title in LANGUAGES])
        c.append(languages)
        local_name = dict(LANGUAGES).get(system_language(), 'English')
        c.append(label(t('System language: {language}', language=local_name), 'caption'))
        c.append(label(t('Only the interface changes. Song text and lyric language stay unchanged.'), 'caption'))
        c.append(Gtk.Separator())
        c.append(label(t('Default Suno model for new songs'), 'heading'))
        suno_default = dropdown(list(SUNO_MODELS), self.settings.get('default_suno_model', DEFAULT_SUNO_MODEL), [t(SUNO_MODELS[key]['label']) for key in SUNO_MODELS])
        c.append(suno_default)
        default_model_hint = label(t(SUNO_MODELS[text_of(suno_default)]['about']), 'caption')
        c.append(default_model_hint)
        c.append(label(t('Choose the same Suno model in Create. Versework prepares the prompts but does not create the audio.'), 'caption'))
        suno_default.connect('notify::selected', lambda *_: default_model_hint.set_text(t(SUNO_MODELS[text_of(suno_default)]['about'])))
        c.append(Gtk.Separator())
        expander = Gtk.Expander(label=t('Local writing'))
        engine = box(spacing=16)
        engine.set_margin_top(16)
        expander.set_child(engine)
        c.append(expander)
        engine.append(label(t('Only connects to Ollama on this computer.'), 'caption'))
        engine.append(label(t('Local model')))
        model = Gtk.Entry(text=self.settings.get('model', 'qwen3:8b'))
        engine.append(model)
        listing = Gtk.DropDown.new_from_strings([])
        engine.append(listing)
        listing.connect('notify::selected', lambda *_: model.set_text(text_of(listing)) if text_of(listing) else None)
        state = label('', 'caption')
        engine.append(state)
        def check():
            state.set_text(t('Checking local Ollama…'))
            def worker():
                try:
                    names = self.ollama.models()
                    def done():
                        if self.settings_window is not window:
                            return
                        previous = model.get_text()
                        listing.set_model(Gtk.StringList.new(names))
                        if previous in names:
                            listing.set_selected(names.index(previous))
                        state.set_text(t('Connected: {models}', models=', '.join(names)) if names else t('No local models installed.'))
                    GLib.idle_add(done)
                except Exception as e:
                    message = str(e)
                    def failed():
                        if self.settings_window is window:
                            state.set_text(message)
                    GLib.idle_add(failed)
            threading.Thread(target=worker, daemon=True).start()
        def start():
            exe = shutil.which('ollama')
            if not exe:
                state.set_text(t('Ollama is not installed. Run setup-ollama.sh first.'))
                return
            env = os.environ.copy()
            env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1', OLLAMA_VULKAN='1')
            with (DATA / 'ollama.log').open('ab') as log:
                subprocess.Popen([exe, 'serve'], env=env, stdout=log, stderr=log, start_new_session=True)
            state.set_text(t('Ollama start requested. Check connection in a moment.'))
        controls = box(False)
        controls.append(button(t('Check connection'), check))
        controls.append(button(t('Start Ollama'), start))
        engine.append(controls)
        error = label('', 'error')
        c.append(error)
        def apply():
            try:
                if not model.get_text().strip() or 'cloud' in model.get_text().lower():
                    raise ValueError(t('Choose a local model.'))
                colours = {key: entry.get_text() for key, entry in colour_entries.items()}
                if text_of(mode) == 'custom':
                    colour_css(colours)
                if not self.flush():
                    return
                new_limit = None if unlimited.get_active() else int(rewrite_limit.get_value())
                saved = {**self.settings, 'model': model.get_text().strip(), 'default_suno_model': text_of(suno_default), 'colour_mode': text_of(mode), 'colours': colours,
                         'ui_language': text_of(languages), 'rewrite_limit': new_limit}
                self.store.apply_settings(saved, apply_existing=apply_existing.get_active())
                self.settings = saved
                if self.project:
                    self.project = next(p for p in self.store.list() if p['id'] == self.project['id'])
                set_language(saved['ui_language'])
                self.refresh_theme()
                window.close()
                self.new_song_button.set_label(t('New song'))
                self.settings_button.set_label(t('Settings'))
                self.suno_button.set_label(t('Open Suno'))
                self.suno_button.set_tooltip_text(t('Open Suno in your browser to log in or create music.'))
                self.stop_button.set_label(t('Stop writing'))
                self.refresh_projects()
                if self.view == 'song' and self.project:
                    self.render_project()
                else:
                    self.render_library()
                if self.busy:
                    self.content.set_sensitive(False)
                    self.sidebar.set_sensitive(False)
                self.notify(t('Settings saved.'))
            except Exception as e:
                error.set_text(str(e))
        self.recovery_controls(c)
        self.update_controls(c)
        window.actions.append(button(t('Apply'), apply, True))
        window.actions.append(button(t('Close'), window.close))
        window.actions.set_visible(True)
        # Named handles also make real GTK interaction tests precise.
        window.controls = {'language': languages, 'mode': mode, 'colours': colour_entries, 'model': model,
                           'rewrite_limit': rewrite_limit, 'unlimited': unlimited, 'apply_existing': apply_existing, 'suno_default': suno_default,
                           'apply': apply, 'close': window.close, 'reset': reset}
        window.present()
        return window

    def update_controls(self, container):
        container.append(Gtk.Separator())
        container.append(label(t('App updates'), 'heading'))
        state = label(t('Check GitHub for the latest version of Versework.'), 'caption')
        container.append(state)
        action = button(t('Check for updates'), lambda: check())
        container.append(action)
        target = Path(__file__).resolve().parent
        if has_rollback(target):
            def rollback():
                if self.busy or self.update_running or not self.flush():
                    return
                try:
                    rollback_installation(target)
                    self.restart_requested = True
                    self.quit()
                except Exception as exc:
                    state.set_text(str(exc))
            container.append(button('Restore previous app version and restart', rollback))
        found = [None]
        if self.update_installed:
            state.set_text(t('Update installed. Restart Versework to use it.'))
            action.set_label(t('Restart Versework'))
        elif self.update_running:
            state.set_text(t('An update check or installation is already running.'))
            action.set_sensitive(False)
            def refresh_when_done():
                if action.get_root() is None:
                    return False
                if self.update_running:
                    return True
                action.set_sensitive(True)
                state.set_text(t('Update installed. Restart Versework to use it.') if self.update_installed else t('Check GitHub for the latest version of Versework.'))
                action.set_label(t('Restart Versework') if self.update_installed else t('Check for updates'))
                return False
            GLib.timeout_add(250, refresh_when_done)

        def finish(revision=None, error=None, installed=False, warning=''):
            self.update_running = False
            action.set_sensitive(True)
            if error:
                state.set_text(t('Update failed: {error}', error=str(error)))
                found[0] = None
                action.set_label(t('Check for updates'))
            elif installed:
                self.update_installed = True
                state.set_text(t('Update installed. Restart Versework to use it.'))
                if warning:
                    state.set_text(state.get_text() + '\n' + warning)
                action.set_label(t('Restart Versework'))
            elif revision == current_revision(target):
                state.set_text(t('Versework is up to date.'))
            else:
                found[0] = revision
                state.set_text(t('An update is available. Your songs and settings will be preserved.'))
                action.set_label(t('Install update'))
            return False

        def check():
            if self.update_installed:
                if self.busy:
                    state.set_text(t('Finish or stop writing first.'))
                elif self.flush():
                    self.restart_requested = True
                    self.quit()
                return
            if self.update_running:
                return
            if self.busy:
                state.set_text(t('Finish or stop writing first.'))
                return
            if not (target / '.versework-revision').exists() or (target / '.git').exists():
                state.set_text(t('Open the installed app to update. Run install.sh once if needed.'))
                return
            if not self.flush():
                return
            revision = found[0]
            self.update_running = True
            action.set_sensitive(False)
            state.set_text(t('Installing update…') if revision else t('Checking for updates…'))
            def worker():
                try:
                    if revision:
                        warning = install_update(target, revision)
                        GLib.idle_add(finish, None, None, True, warning)
                    else:
                        GLib.idle_add(finish, latest_revision())
                except Exception as exc:
                    GLib.idle_add(finish, None, str(exc))
            threading.Thread(target=worker, daemon=True).start()

    def native_palette(self):
        context = self.win.get_style_context()
        result = {}
        for key, token in [('background', 'theme_bg_color'), ('surface', 'theme_bg_color'), ('foreground', 'theme_fg_color'), ('accent', 'theme_selected_bg_color')]:
            found, colour = context.lookup_color(token)
            if not found:
                colour = self.win.get_color()
            result[key] = '#%02X%02X%02X' % tuple(round(v * 255) for v in (colour.red, colour.green, colour.blue))
        return result

    def approve(self):
        if self.busy or not self.flush():
            return
        p = copy.deepcopy(self.project)
        p['tracks'][self.track_index]['approved'] = not p['tracks'][self.track_index]['approved']
        self.store.save(p)
        self.project = p
        self.render_project()

    def generate_missing(self):
        if self.flush():
            self.start_jobs([], song_jobs=self.store.pending_songs(self.collection_id))

    def rewrite(self):
        if not self.flush():
            return
        feedback = self.project['tracks'][self.track_index]['feedback'].strip()
        if not feedback:
            self.notify(t('Add feedback before requesting a rewrite.'), True)
            return
        self.start_jobs([self.track_index], feedback, scope=text_of(self.rewrite_scope), section=self.rewrite_section.get_text().strip() or None)

    def refresh_lyrics_dialog(self):
        if self.busy or not self.flush():
            return
        track = self.project['tracks'][self.track_index]
        if track['approved'] or (self.project['limit'] is not None and track['rewrites'] >= self.project['limit']):
            return
        window, c = self.dialog(t('Refresh lyrics'), 620, 460)
        c.append(label(t('Choose a starting point, then review the instructions before rewriting.'), 'caption'))
        choices = {
            'Light polish': 'Lightly polish the lyrics for natural phrasing, rhythm and singability. Preserve the story, structure and core hook.',
            'Stronger chorus': 'Rewrite the chorus with a stronger, memorable hook and natural singable phrasing. Keep the verses and story as close as possible.',
            'Fresh lyrics': 'Write completely fresh lyrics with new imagery and a new hook, keeping the creative brief, theme and production direction.',
            'Update delivery cues': 'Update the bracketed lyric performance cues to match my saved production direction. Preserve the sung words wherever possible. Align the style prompt and exclusions with those directions.',
        }
        for title, instruction in choices.items():
            def choose(text=instruction):
                current = text_of(self.feedback_editor).strip()
                self.feedback_editor.get_buffer().set_text(current + '\n\n' + text if current else text)
                window.close()
                self.editor_stack.set_visible_child_name('Review')
                self.feedback_editor.grab_focus()
            c.append(button(t(title), choose))
        c.append(label(t('Uses the normal rewrite allowance when you start rewriting. Locked fields remain unchanged.'), 'caption'))
        window.present()
        return window

    def collection_feedback(self):
        if self.busy or not self.flush():
            return
        collection = self.current_collection()
        if not collection:
            return
        lookup = {p['tracks'][i]['id']: (p, i) for p, i in self.song_rows()}
        window, c = self.dialog(t('Review songs'), 640, 600)
        c.append(label(t('Describe what to change, or add listening notes from Suno.'), 'caption'))
        feedback, wrap = text_input('', 150)
        c.append(wrap)
        choices = []
        for key in collection['songs']:
            if key not in lookup:
                continue
            project, index = lookup[key]
            track = project['tracks'][index]
            if track['current'] and not track['approved'] and (project['limit'] is None or track['rewrites'] < project['limit']):
                check = Gtk.CheckButton(label=song_title(project, index), active=True)
                c.append(check)
                choices.append((project, index, check))
        error = label('', 'error')
        c.append(error)
        def run():
            selected = [(project['id'], index) for project, index, check in choices if check.get_active()]
            if not text_of(feedback).strip() or not selected:
                error.set_text(t('Select songs and enter feedback.'))
                return
            window.close()
            self.start_jobs([], text_of(feedback), selected)
        window.actions.append(button(t('Rewrite selected songs'), run, True))
        window.actions.set_visible(True)
        window.present()

    def history_dialog(self):
        if not self.flush():
            return
        window, c = self.dialog(t('Version history'), 720, 720)
        track = self.project['tracks'][self.track_index]
        c.append(label(t('Restoring never resets the rewrite counter.'), 'caption'))
        pick = Gtk.DropDown.new_from_strings([t('Version {number} · {kind} · {date}', number=i+1, kind=t(v['kind']), date=v['at']) for i, v in enumerate(track['versions'])])
        pick.set_selected(len(track['versions']) - 1)
        c.append(pick)
        preview, wrap = text_input('', 360)
        preview.set_editable(False)
        wrap.set_vexpand(True)
        c.append(wrap)
        note = label('', 'caption')
        c.append(note)
        def changed(*_):
            version = track['versions'][pick.get_selected()]
            preview.get_buffer().set_text(song_text(version['song'], version.get('suno_model', track.get('suno_model', DEFAULT_SUNO_MODEL))))
            note.set_text(version.get('feedback') or version['song'].get('notes', ''))
        pick.connect('notify::selected', changed)
        changed()
        def restore():
            try:
                candidate = copy.deepcopy(self.project)
                restore_version(candidate, self.track_index, pick.get_selected())
                self.store.save(candidate)
                self.project = candidate
                self.editors = {}
                self.render_project()
                window.close()
                self.notify(t('Version restored.'))
            except Exception as e:
                note.set_text(str(e))
        restore_button = button(t('Restore version'), restore, True)
        restore_button.set_sensitive(not track['approved'] and not self.busy)
        window.actions.append(restore_button)
        window.actions.set_visible(True)
        window.present()

    def export_dialog(self):
        if not self.flush():
            return
        collection = self.current_collection() if self.view == 'library' else None
        if self.view == 'song':
            rows = [(self.project, self.track_index)]
            title = song_title(self.project, self.track_index)
        else:
            lookup = {p['tracks'][i]['id']: (p, i) for p, i in self.song_rows()}
            rows = [lookup[key] for key in collection['songs'] if key in lookup] if collection else list(lookup.values())
            title = collection['name'] if collection else t('Songs')
        lines = ['# ' + title, '']
        if collection:
            lines.extend([collection_kind(collection), collection['theme'], ''])
        for p, i in rows:
            track = p['tracks'][i]
            lines.extend(['## ' + song_title(p, i), t(track_status(p, track)), ''])
            if track['current']:
                lines.append(song_text(track['current'], track.get('suno_model', DEFAULT_SUNO_MODEL)))
        content = '\n'.join(lines)
        snapshot = {'collection': collection, 'songs': [{'brief': {k:v for k,v in p.items() if k != 'tracks'}, 'track': p['tracks'][i]} for p,i in rows]}
        window, c = self.dialog(t('Export songs'), 700, 650)
        preview, wrap = text_input(content, 400)
        preview.set_editable(False)
        wrap.set_vexpand(True)
        c.append(wrap)
        copy_all_button = button(t('Copy all'), lambda: (self.copy(content), self.flash_copy(copy_all_button, t('Copy all'))))
        window.actions.append(copy_all_button)
        window.actions.set_visible(True)
        def save():
            picker = Gtk.FileChooserNative(title=t('Choose export folder'), transient_for=window,
                action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label=t('Export here'), cancel_label=t('Cancel'))
            def response(dialog, code):
                if code == Gtk.ResponseType.ACCEPT:
                    try:
                        folder = Path(dialog.get_file().get_path()) / ('Versework-' + str(time.time_ns()))
                        folder.mkdir()
                        (folder / 'songs.md').write_text(content)
                        (folder / 'history.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
                        self.notify(t('Exported to {path}', path=folder))
                        window.close()
                    except Exception as e:
                        self.notify(str(e), True)
                dialog.destroy()
            picker.connect('response', response)
            picker.show()
        window.actions.append(button(t('Save text and history'), save, True))
        window.actions.set_visible(True)
        window.present()

    def close(self, *_):
        if self.update_running:
            self.notify(t('Wait for the update to finish before closing.'), True)
            return True
        if self.busy:
            self.cancel_event.set()
            return False
        if not self.flush():
            return True
        self.cancel_event.set()
        return False

    def smoke(self):
        try:
            p = create_project('Last Train Home', 'Warm analogue synths, understated indie pop, intimate vocals.', 1, 180, 240, 3, 'Finding a little hope at the end of the night', 'English')
            song = {'title': 'Last Train Home', 'lyrics': '[Verse 1]\nYour coffee rings the timetable\nA small moon on the page\nWe leave the platform quietly\nAnd let the morning wait\n\n[Chorus]\nKeep one light on for me\nPast the end of the line\nThere is still a place to be\nWhere your window meets mine', 'style_prompt': 'Intimate indie synth-pop, 92 BPM, warm analogue pads, soft drum machine, rounded bass, close-miked female vocals.', 'exclusions': 'harsh distortion, stadium drums', 'vocal_gender': 'female', 'weirdness': 35, 'style_influence': 75, 'variety': 'normal', 'notes': 'Interface verification fixture. Not model-generated.'}
            commit_version(p, 0, song, 'initial')
            self.store.save(p)
            collection = make_collection('After the streetlights', 'collection', 'Small stories from the city after dark', [p['tracks'][0]['id']])
            self.store.save_collection(collection)
            self.load_project(p['id'], 0)
            self.copy_buttons['lyrics'].emit('clicked')
            assert self.copy_buttons['lyrics'].get_label() == t('Copied')
            self.approve()
            self.approve()
            # Close must discard unsaved settings, even with an invalid model field.
            before = copy.deepcopy(self.store.settings())
            window = self.settings_dialog()
            window.controls['model'].set_text('')
            window.escape_controller.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
            assert self.settings_window is None
            assert self.store.settings() == before
            window = self.settings_dialog()
            assert window.controls['model'].get_text() == before['model']
            # Applying appearance/language cannot alter song content or its language.
            window.controls['language'].set_selected(4)  # Français
            window.controls['mode'].set_selected(1)
            window.controls['colours']['accent'].set_text('#4375BB')
            window.controls['apply']()
            assert self.settings['ui_language'] == 'fr'
            assert self.settings_window is None
            self.settings_dialog()
            assert self.settings_window.get_title() == 'Paramètres'
            assert self.store.list()[0]['language'] == 'English'
            assert self.store.list()[0]['tracks'][0]['current'] == song
            self.settings_window.controls['reset']()
            self.settings_window.controls['language'].set_selected(0)
            self.settings_window.controls['apply']()
            assert self.settings_window is None
            # Apply must close even when there are no pending changes.
            before = copy.deepcopy(self.store.settings())
            window = self.settings_dialog()
            window.controls['apply']()
            assert self.settings_window is None
            assert self.store.settings() == before
            # Validation failures keep the dialog open so the user can correct them.
            window = self.settings_dialog()
            window.controls['model'].set_text('')
            window.controls['apply']()
            assert self.settings_window is window
            assert self.store.settings() == before
            window.close()
            assert self.settings['colour_mode'] == 'system'
            assert self.settings['ui_language'] == 'system'
            limited, container = text_input()
            limit_text(limited, box())
            buf = limited.get_buffer()
            buf.set_text('é' * TEXT_LIMIT)
            buf.insert(buf.get_end_iter(), 'x', -1)
            assert len(text_of(limited)) == TEXT_LIMIT
            buf.delete(buf.get_start_iter(), buf.get_iter_at_offset(1))
            buf.insert(buf.get_end_iter(), 'x', -1)
            assert len(text_of(limited)) == TEXT_LIMIT
            self.smoke_ok = True
            print('GTK_SMOKE_OK: song editor, settings close/reopen, language and colour apply/reset', flush=True)
            GLib.timeout_add(300, self.capture_smoke)
        except Exception:
            import traceback
            traceback.print_exc()
            self.quit()
        return False

    def render_capture(self, window, path):
        gi.require_version('Graphene', '1.0')
        from gi.repository import Graphene
        snapshot = Gtk.Snapshot.new()
        Gtk.WidgetPaintable.new(window).snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        rect = Graphene.Rect()
        rect.init(0, 0, window.get_width(), window.get_height())
        window.get_renderer().render_texture(node, rect).save_to_png(str(path))

    def capture_smoke(self):
        try:
            self.render_capture(self.win, DATA / 'preview.png')
            self.settings_dialog()
            GLib.timeout_add(300, self.capture_settings)
        except Exception:
            import traceback
            traceback.print_exc()
            self.smoke_ok = False
            self.quit()
        return False

    def capture_settings(self):
        try:
            self.render_capture(self.settings_window, DATA / 'settings.png')
            self.settings_window.close()
            self.show_library()
            GLib.timeout_add(300, self.capture_library)
        except Exception:
            self.smoke_ok = False
            self.quit()
        return False

    def capture_library(self):
        try:
            self.render_capture(self.win, DATA / 'library.png')
            print('GTK_RENDER_OK', flush=True)
        except Exception:
            self.smoke_ok = False
        self.quit()
        return False


if __name__ == '__main__':
    app = Studio()
    result = app.run([sys.argv[0]])
    if app.restart_requested:
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())])
    sys.exit(1 if '--smoke' in sys.argv and not app.smoke_ok else result)
