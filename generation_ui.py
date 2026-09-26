"""Cancellable generation queues and proposal handoff."""
import copy
import queue
import threading
import time
from gi.repository import GLib
from core import Cancelled, commit_version, generate_song
from i18n import t


class GenerationMixin:
    def start_jobs(self, indices, feedback='', song_jobs=None, scope='all', section=None, job_details=None):
        if self.busy or not self.flush():
            return
        if not indices and not song_jobs:
            self.notify(t('All drafts are written.'))
            return
        self.busy = True
        self.cancel_event = threading.Event()
        self.spinner.start()
        self.stop_button.set_visible(True)
        self.content.set_sensitive(False)
        self.sidebar.set_sensitive(False)
        model = self.settings['model']
        self.notify(t('Connecting to {model}…', model=model))
        pairs = list(song_jobs) if song_jobs else [(self.project['id'], index) for index in indices]
        jobs = [tuple(job) for job in job_details] if job_details is not None else [(ident, index, feedback, scope, section) for ident, index in pairs]
        keys = {job[:2] for job in jobs}
        previous = [tuple(job) for job in self.failed_jobs if tuple(job[:2]) not in keys]
        outstanding = previous + list(jobs)
        self.store.save_jobs(outstanding)
        total = len(jobs)
        completed = [0]
        failure_messages = []
        self.failed_jobs = previous
        self.retry_button.set_visible(False)
        def next_job():
            self.store.save_jobs(outstanding)
            if self.cancel_event.is_set():
                self.failed_jobs = list(outstanding)
                self.finish(t('Writing stopped. Completed drafts are saved.'))
                return
            if not jobs:
                if failure_messages:
                    details = '\n'.join(dict.fromkeys(failure_messages))
                    self.finish(t('Song generation failed for {count} item(s). You can retry after fixing the issue. Details: {details}', count=len(failure_messages), details=details), True)
                else:
                    self.finish(f'{completed[0]}/{total} songs processed. {len(self.failed_jobs)} available to retry.' if self.failed_jobs else t('Drafts saved. Ready for review.'))
                return
            ident, index, job_feedback, job_scope, job_section = jobs.pop(0)
            self.project = next((p for p in self.store.list() if p['id'] == ident), None)
            if self.project is None or not 0 <= index < len(self.project['tracks']):
                outstanding[:] = [job for job in outstanding if job[:2] != (ident, index)]
                next_job()
                return
            self.track_index = index
            self.view = 'song'
            snap = self.store.generation_context(self.project, index, self.collection_id)
            kind = 'rewrite' if snap['tracks'][index]['current'] else 'initial'
            if kind == 'rewrite' and (snap['tracks'][index]['approved'] or (snap['limit'] is not None and snap['tracks'][index]['rewrites'] >= snap['limit'])):
                self.failed_jobs.append((ident, index, job_feedback, job_scope, job_section))
                next_job()
                return
            completed[0] += 1
            self.notify(t('Writing song {number}/{count}…', number=completed[0], count=total))
            def failed(message):
                self.failed_jobs.append((ident, index, job_feedback, job_scope, job_section))
                failure_messages.append(message)
                self.notify(message, True)
                next_job()
                return False
            def worker():
                try:
                    # Model discovery can itself be blocked on local transport.
                    # Keep Stop responsive before generation starts as well.
                    discovered = queue.Queue()
                    def discover():
                        try:
                            discovered.put((True, self.ollama.models()))
                        except Exception as exc:
                            discovered.put((False, exc))
                    threading.Thread(target=discover, daemon=True).start()
                    while True:
                        if self.cancel_event.is_set():
                            raise Cancelled()
                        try:
                            ok, result = discovered.get(timeout=0.1)
                            break
                        except queue.Empty:
                            continue
                    if not ok:
                        raise result
                    if model not in result:
                        raise ValueError(t('No local models installed.') + ' ' + model)
                    last = [0.0]
                    def progress(size):
                        if time.monotonic() - last[0] > 1:
                            last[0] = time.monotonic()
                            GLib.idle_add(self.notify, t('Writing song {number}/{count} · {size} characters', number=completed[0], count=total, size=size))
                    data = generate_song(self.ollama, model, snap, index, job_feedback, self.cancel_event, progress, scope=job_scope, section=job_section)
                    GLib.idle_add(accept, index, kind, data, job_feedback)
                except Cancelled:
                    GLib.idle_add(failed, t('Writing stopped. Completed drafts are saved.'))
                except Exception as e:
                    GLib.idle_add(failed, str(e))
            threading.Thread(target=worker, daemon=True).start()
        def accept(index, kind, data, job_feedback):
            if self.cancel_event.is_set():
                self.failed_jobs = list(outstanding)
                self.finish(t('Writing stopped. Completed drafts are saved.'))
                return
            current = self.project['tracks'][index]['current']
            source = self.project['tracks'][index].get('lyrics_source')
            if not current and source and self.project['tracks'][index].get('lyrics_assist') == 'suggest' and source != data['lyrics']:
                current = {**data, 'lyrics': source}
            if current:
                def discard():
                    outstanding[:] = [job for job in outstanding if job[:2] != (self.project['id'], index)]
                    next_job()
                self.review_proposal(current, data, lambda selected: persist(index, kind, selected, job_feedback), discard, allow_unchanged=(kind == 'initial'))
            else:
                persist(index, kind, data, job_feedback)
        def persist(index, kind, data, job_feedback):
            if self.cancel_event.is_set():
                self.failed_jobs = list(outstanding)
                self.finish('Writing stopped. This proposal was not saved.')
                return
            try:
                candidate = copy.deepcopy(self.project)
                commit_version(candidate, index, data, kind, job_feedback, model,
                               candidate['tracks'][index].get('suno_model'))
                if job_feedback:
                    candidate['tracks'][index]['feedback'] = job_feedback
                self.store.save(candidate)
                self.project = candidate
                self.track_index = index
                outstanding[:] = [job for job in outstanding if job[:2] != (candidate['id'], index)]
            except Exception as e:
                self.failed_jobs = list(outstanding)
                self.finish(str(e), True)
                return
            next_job()
        next_job()

    def finish(self, message, error=False):
        self.busy = False
        self.spinner.stop()
        self.stop_button.set_visible(False)
        self.retry_button.set_visible(bool(self.failed_jobs))
        self.store.save_jobs(self.failed_jobs)
        self.content.set_sensitive(True)
        self.sidebar.set_sensitive(True)
        self.editors = {}
        self.render_project()
        self.notify(message, error)
        if error and hasattr(self, 'show_generation_error'):
            self.show_generation_error(message)

    def stop(self):
        self.cancel_event.set()
        self.notify('Stopping writing…')

    def retry_failed(self):
        if not self.failed_jobs or self.busy:
            return
        pending = list(self.failed_jobs)
        feedback, scope, section = pending[0][2:]
        self.start_jobs([], feedback, [(ident, index) for ident, index, *_ in pending], scope, section, job_details=pending)
