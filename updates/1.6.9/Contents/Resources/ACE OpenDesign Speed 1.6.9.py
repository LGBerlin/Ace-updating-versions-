#!/usr/bin/env python3
"""Narrow OpenDesign/Codex poster launch interceptor for A.C.E. 1.6.9.

The poster launch uses OpenDesign's streaming POST /api/chat path rather than
A.C.E.'s JSON helper. This module intercepts only that outbound urllib Request
when all of these are true:
- an A.C.E. poster job is currently active;
- request path is exactly /api/chat;
- JSON payload identifies agentId=codex;
- projectId is one of A.C.E.'s ace_* OpenDesign projects.

It then adds reasoning=low. Every other request is delegated byte-for-byte.
"""
from pathlib import Path
import json
import threading
import time
import urllib.parse
import urllib.request

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


def _active_poster(ace):
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
        if str(job.get('status') or '').lower() not in _TERMINAL:
            return job
    return None


def _decode_request(req):
    if not isinstance(req, urllib.request.Request):
        return None
    try:
        if str(req.get_method() or '').upper() != 'POST':
            return None
        parsed = urllib.parse.urlsplit(req.full_url)
        if parsed.path != '/api/chat':
            return None
        host = (parsed.hostname or '').lower()
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            return None
        raw = req.data
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            return None
        body = json.loads(bytes(raw).decode('utf-8'))
        if not isinstance(body, dict):
            return None
        if str(body.get('agentId') or '').lower() != 'codex':
            return None
        project = str(body.get('projectId') or '')
        if not project.startswith('ace_'):
            return None
        return body
    except Exception:
        return None


def rewrite_request(req):
    """Pure request transform used by runtime and QA."""
    body = _decode_request(req)
    if body is None:
        return req, False, {}
    previous = body.get('reasoning')
    body = dict(body)
    body['reasoning'] = 'low'
    data = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    headers = dict(req.header_items())
    # urllib will recalculate Content-Length for the new data.
    headers.pop('Content-length', None)
    headers.pop('Content-Length', None)
    out = urllib.request.Request(
        req.full_url,
        data=data,
        headers=headers,
        method=req.get_method(),
    )
    meta = {
        'agent': str(body.get('agentId') or ''),
        'project': str(body.get('projectId') or ''),
        'model': str(body.get('model') or 'default'),
        'previous_reasoning': '' if previous is None else str(previous),
    }
    return out, True, meta


def install(ace):
    original = ace.urllib.request.urlopen
    if getattr(original, '_ace169_opendesign_speed', False):
        return

    def urlopen(req, *args, **kwargs):
        next_req = req
        applied = False
        meta = {}
        if _active_poster(ace) is not None:
            next_req, applied, meta = rewrite_request(req)
        if applied:
            _log(
                'POSTER SPEED APPLIED low_reasoning via=urlopen '
                f"agent={meta.get('agent')} model={meta.get('model')} "
                f"project={meta.get('project')} previous={meta.get('previous_reasoning') or 'default'}"
            )
        return original(next_req, *args, **kwargs)

    urlopen._ace169_opendesign_speed = True
    urlopen._ace169_original = original
    ace.urllib.request.urlopen = urlopen
    _log('A.C.E. 1.6.9 OpenDesign streaming poster interceptor loaded')
