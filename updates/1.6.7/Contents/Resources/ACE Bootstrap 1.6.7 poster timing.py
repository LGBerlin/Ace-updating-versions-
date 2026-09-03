#!/usr/bin/env python3
"""A.C.E. 1.6.7 — poster timing instrumentation only.

Loads the regression-safe 1.6.6 runtime unchanged, then measures poster latency
without changing generation quality, research, voice, OpenDesign design logic or
Preview/Edit behavior.

Measurements:
- first poster-job observation;
- OpenDesign run assignment;
- every poster stage transition;
- PPTX availability;
- first usable preview;
- completion;
- duration of each OpenDesign HTTP call, associated with a poster job when possible.

A small UI timer measures user-visible time to a changed poster preview. Detailed
records are appended to ~/Library/Logs/ACE-Poster-Timing.log.
"""
from pathlib import Path
import importlib.util
import json
import re
import threading
import time
import urllib.parse

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.6.py'

spec = importlib.util.spec_from_file_location('ace_base_166_for_167', str(BASE))
b166 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b166)
ace = b166.ace

ace.VERSION = '1.6.7'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.7'
except Exception:
    pass

LOG = Path.home() / 'Library' / 'Logs' / 'ACE-Poster-Timing.log'
_LOCK = threading.RLock()
_LATEST = {'job_id': '', 'started_wall': 0.0}


def _log(message):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}\n')
    except Exception:
        pass


def _is_poster(job):
    return isinstance(job, dict) and str(job.get('kind') or '').lower() == 'poster'


def _ensure_clock(job):
    if not _is_poster(job):
        return False
    with _LOCK:
        if not job.get('_ace167_t0'):
            now = time.monotonic()
            job['_ace167_t0'] = now
            job['_ace167_wall'] = time.time()
            job['_ace167_marks'] = {'first_seen': 0.0}
            job['_ace167_last_stage'] = ''
            job['_ace167_od_calls'] = []
            job_id = str(job.get('job_id') or '')
            _LATEST['job_id'] = job_id
            _LATEST['started_wall'] = float(job['_ace167_wall'])
            _log(f'POSTER START job={job_id or "?"}')
        return True


def _elapsed(job):
    try:
        return max(0.0, time.monotonic() - float(job.get('_ace167_t0') or time.monotonic()))
    except Exception:
        return 0.0


def _mark(job, key, detail=''):
    if not _ensure_clock(job):
        return
    with _LOCK:
        marks = job.setdefault('_ace167_marks', {})
        if key in marks:
            return
        sec = _elapsed(job)
        marks[key] = sec
        suffix = (' ' + detail) if detail else ''
        _log(f'POSTER MARK job={job.get("job_id") or "?"} {key}={sec:.3f}s{suffix}')


def _observe(job):
    if not _ensure_clock(job):
        return
    if job.get('run_id') or job.get('persist_run_id'):
        _mark(job, 'opendesign_run_assigned')
    stage = str(job.get('stage') or '').strip()
    with _LOCK:
        last = str(job.get('_ace167_last_stage') or '')
        if stage and stage != last:
            job['_ace167_last_stage'] = stage
            _log(f'POSTER STAGE job={job.get("job_id") or "?"} t={_elapsed(job):.3f}s stage={stage!r}')
    if job.get('pptx_rel'):
        _mark(job, 'pptx_ready', f'path={job.get("pptx_rel")}')
    if job.get('rendered_pages') or job.get('preview_rel') or job.get('daemon_preview_url'):
        _mark(job, 'preview_ready')
    status = str(job.get('status') or '').lower()
    if status in {'done', 'complete', 'completed'}:
        _mark(job, 'complete')


def _timing_payload(job):
    _observe(job)
    marks = dict(job.get('_ace167_marks') or {})
    calls = list(job.get('_ace167_od_calls') or [])[-30:]
    elapsed = _elapsed(job)
    return {
        'job_id': str(job.get('job_id') or ''),
        'elapsed_seconds': round(elapsed, 3),
        'marks': {k: round(float(v), 3) for k, v in marks.items()},
        'stage': str(job.get('stage') or ''),
        'status': str(job.get('status') or ''),
        'opendesign_calls': calls,
        'log_path': str(LOG),
    }


def _find_job_by_run(run_id):
    rid = str(run_id or '')
    if not rid:
        return None
    try:
        with ace.OPEN_DESIGN_LOCK:
            jobs = list(ace.OPEN_DESIGN_JOBS.values())
    except Exception:
        jobs = []
    for job in jobs:
        if not _is_poster(job):
            continue
        if rid in {str(job.get(k) or '') for k in ('run_id', 'persist_run_id', 'export_run_id')}:
            return job
    return None


def _run_id_from_path(path):
    m = re.search(r'/api/runs/([^/?]+)', str(path or ''))
    return urllib.parse.unquote(m.group(1)) if m else ''


_snapshot0 = ace._job_snapshot
_od0 = getattr(ace, '_od_http_json', None)
_get0 = ace.H.do_GET


def snapshot(job):
    if _is_poster(job):
        _observe(job)
    out = _snapshot0(job)
    if _is_poster(job) and isinstance(out, dict):
        timing = _timing_payload(job)
        out['ace_poster_timing'] = timing
        marks = timing['marks']
        if 'preview_ready' in marks:
            out['ace_poster_timing_line'] = f"Preview ready in {marks['preview_ready']:.1f}s"
        else:
            out['ace_poster_timing_line'] = f"Poster {timing['elapsed_seconds']:.1f}s"
    return out


ace._job_snapshot = snapshot


if callable(_od0):
    def od_http_json(method, path, *args, **kwargs):
        start = time.perf_counter()
        ok = False
        error = ''
        try:
            result = _od0(method, path, *args, **kwargs)
            ok = True
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            sec = time.perf_counter() - start
            rid = _run_id_from_path(path)
            job = _find_job_by_run(rid)
            record = {
                'method': str(method),
                'path': str(path)[:220],
                'seconds': round(sec, 3),
                'ok': bool(ok),
            }
            if error:
                record['error'] = error[:180]
            if job is not None:
                _ensure_clock(job)
                with _LOCK:
                    job.setdefault('_ace167_od_calls', []).append(record)
                    if len(job['_ace167_od_calls']) > 60:
                        del job['_ace167_od_calls'][:-60]
                _log(f'OD CALL job={job.get("job_id") or "?"} t={_elapsed(job):.3f}s {method} {path} duration={sec:.3f}s ok={ok}')
            else:
                _log(f'OD CALL job=? {method} {path} duration={sec:.3f}s ok={ok}')

    ace._od_http_json = od_http_json


def _latest_poster():
    try:
        with ace.OPEN_DESIGN_LOCK:
            jobs = list(ace.OPEN_DESIGN_JOBS.values())
    except Exception:
        jobs = []
    posters = [j for j in jobs if _is_poster(j)]
    if not posters:
        return None
    for job in reversed(posters):
        if str(job.get('job_id') or '') == str(_LATEST.get('job_id') or ''):
            return job
    return posters[-1]


def GET(self):
    try:
        path = ace.urllib.parse.urlparse(self.path).path
        if path == '/api/poster-timing':
            job = _latest_poster()
            if not job:
                self.json_out({'ok': True, 'poster': None, 'log_path': str(LOG)})
            else:
                self.json_out({'ok': True, 'poster': _timing_payload(job)})
            return
    except Exception as e:
        try:
            if ace.urllib.parse.urlparse(self.path).path == '/api/poster-timing':
                self.json_out({'error': str(e)}, 500)
                return
        except Exception:
            pass
    return _get0(self)


ace.H.do_GET = GET


# User-visible end-to-end timer. It watches the existing poster studio and does
# not intercept generation, Edit, Preview, search, Send, Stop or download events.
UI_MARKER = 'ACE167_POSTER_TIMER'
UI_JS = r'''
(function(){
  if(window.__ACE167_POSTER_TIMER__)return;window.__ACE167_POSTER_TIMER__=1;
  let started=0,startSrc='',finished=false,badge=null,lastActive=0;
  function root(){return document.getElementById('artifactStudio')||document.querySelector('.artifact-studio');}
  function image(r){if(!r)return null;const a=[...r.querySelectorAll('img')].filter(x=>{const b=x.getBoundingClientRect();return b.width>80&&b.height>80;});a.sort((x,y)=>{x=x.getBoundingClientRect();y=y.getBoundingClientRect();return y.width*y.height-x.width*x.height;});return a[0]||null;}
  function ensure(r){if(badge&&badge.isConnected)return badge;badge=document.createElement('div');badge.id='ace167PosterTimer';badge.style.cssText='position:absolute;right:12px;top:10px;z-index:20;font:600 11px/1.2 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:#A5BE88;background:#0E2308dd;border:1px solid #2D4A22;border-radius:999px;padding:5px 8px;pointer-events:none;';try{const cs=getComputedStyle(r);if(cs.position==='static')r.style.position='relative';r.appendChild(badge);}catch(_){}return badge;}
  function reset(r){started=performance.now();finished=false;const im=image(r);startSrc=im?String(im.currentSrc||im.src||''):'';lastActive=performance.now();const b=ensure(r);b.textContent='Poster 0.0s';b.style.color='#A5BE88';}
  function tick(){const r=root();if(!r)return;const txt=String(r.innerText||'').toLowerCase();const active=/creating a poster|designing (?:a )?poster|building (?:a )?poster|poster.*(?:creating|designing|building)/i.test(txt);if(active){lastActive=performance.now();if(!started||finished)reset(r);}if(!started)return;const im=image(r);const src=im?String(im.currentSrc||im.src||''):'';const changed=!!src&&src!==startSrc;const sec=(performance.now()-started)/1000;const b=ensure(r);if(!finished&&changed){finished=true;b.textContent='Preview ready '+sec.toFixed(1)+'s';b.style.color='#85B764';return;}if(!finished){b.textContent='Poster '+sec.toFixed(1)+'s';}if(finished&&performance.now()-lastActive>120000){started=0;}}
  setInterval(tick,100);try{new MutationObserver(tick).observe(document.body,{childList:true,subtree:true,characterData:true});}catch(_){}
})();
// ACE167_POSTER_TIMER
'''


def _patch_ui():
    try:
        p = H / 'app.js'
        s = p.read_text(encoding='utf-8')
        if UI_MARKER not in s:
            p.write_text(s + '\n' + UI_JS + '\n', encoding='utf-8')
    except Exception:
        pass
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        s = re.sub(r'app\.js\?v=[^"\']+', 'app.js?v=167-poster-timing', s, count=1)
        s = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.7', s, count=1)
        if '<!--ACE167_POSTER_TIMING-->' not in s:
            s += '\n<!--ACE167_POSTER_TIMING-->\n'
        p.write_text(s, encoding='utf-8')
    except Exception:
        pass


_patch_ui()
_log('A.C.E. 1.6.7 poster timing instrumentation loaded')

if __name__ == '__main__':
    ace.main()
