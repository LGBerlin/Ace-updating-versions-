#!/usr/bin/env python3
"""A.C.E. 1.6.8 — narrow poster speed profile.

Loads the measured 1.6.7 runtime unchanged, then applies one validated OpenDesign
request optimization: poster-generation POST /api/chat requests ask supported
agents for low reasoning effort. OpenDesign's Codex adapter turns this into
`model_reasoning_effort="low"`; agents without a reasoning control ignore it.

This release intentionally does not change Docker SearXNG research, poster
Preview/Edit, artifact save routes, voice, theme, Stop, source recall, or the
1.6.7 timing instrumentation.
"""
from pathlib import Path
import importlib.util
import json
import re
import threading
import time

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.7.py'

spec = importlib.util.spec_from_file_location('ace_base_167_for_168', str(BASE))
b167 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b167)
ace = b167.ace

ace.VERSION = '1.6.8'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.8'
except Exception:
    pass

LOG = Path.home() / 'Library' / 'Logs' / 'ACE-Poster-Timing.log'
_LOCK = threading.RLock()
_TERMINAL = {'done', 'complete', 'completed', 'canceled', 'cancelled', 'failed', 'error'}


def _log(message):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}\n')
    except Exception:
        pass


def _poster_job_active():
    try:
        with ace.OPEN_DESIGN_LOCK:
            jobs = list(ace.OPEN_DESIGN_JOBS.values())
    except Exception:
        jobs = []
    for job in reversed(jobs):
        if not isinstance(job, dict):
            continue
        if str(job.get('kind') or '').lower() != 'poster':
            continue
        status = str(job.get('status') or '').lower()
        if status not in _TERMINAL:
            return True
    return False


def _poster_payload(body):
    if not isinstance(body, dict):
        return False
    # First prefer explicit payload signals when present.
    for key in ('kind', 'artifact_kind', 'artifactKind', 'type', 'mode', 'skillId', 'skill_id'):
        value = body.get(key)
        if isinstance(value, str) and 'poster' in value.lower():
            return True
    # A.C.E.'s OpenDesign payload carries the composed user/design prompt. Use
    # the word only as a secondary signal, combined with an active poster job.
    if not _poster_job_active():
        return False
    try:
        text = json.dumps(body, ensure_ascii=False).lower()
    except Exception:
        text = str(body).lower()
    return 'poster' in text or _poster_job_active()


_od0 = getattr(ace, '_od_http_json', None)

if callable(_od0):
    def od_http_json(method, path, *args, **kwargs):
        next_args = args
        applied = False
        if str(method).upper() == 'POST' and str(path).split('?', 1)[0] == '/api/chat':
            if args and isinstance(args[0], dict) and _poster_payload(args[0]):
                body = dict(args[0])
                # OpenDesign validates this against the selected agent. Codex
                # accepts `low`; agents without reasoningOptions ignore it.
                body['reasoning'] = 'low'
                next_args = (body,) + args[1:]
                applied = True
            elif isinstance(kwargs.get('body'), dict) and _poster_payload(kwargs['body']):
                kwargs = dict(kwargs)
                body = dict(kwargs['body'])
                body['reasoning'] = 'low'
                kwargs['body'] = body
                applied = True
        if applied:
            _log('POSTER SPEED profile=low_reasoning endpoint=/api/chat')
        return _od0(method, path, *next_args, **kwargs)

    ace._od_http_json = od_http_json


def _patch_index():
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        s = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.8', s, count=1)
        if '<!--ACE168_POSTER_SPEED-->' not in s:
            s += '\n<!--ACE168_POSTER_SPEED-->\n'
        p.write_text(s, encoding='utf-8')
    except Exception:
        pass


_patch_index()
_log('A.C.E. 1.6.8 poster low-reasoning speed profile loaded')

if __name__ == '__main__':
    ace.main()
