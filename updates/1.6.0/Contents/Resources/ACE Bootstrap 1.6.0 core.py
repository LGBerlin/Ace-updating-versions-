#!/usr/bin/env python3
"""A.C.E. 1.6.0 — research speed/coverage and deterministic Preview Edit routing.

Loads 1.5.9 cumulatively, keeps its multi-source research and all earlier features,
then removes the 1.5.8 alert/clone based Edit shim that could loop. The toolbar Edit
button is routed once at window-capture level to the real PPTX-backed poster editor.
Research keeps Google/Bing/DuckDuckGo discovery, decodes Bing redirect targets, uses
strict wall-clock budgets, and never waits for slow worker pools after enough evidence
has been collected.
"""
from pathlib import Path
import base64
import concurrent.futures
import html
import importlib.util
import json
import re
import threading
import time
import urllib.parse

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.5.9.py'

spec = importlib.util.spec_from_file_location('ace_base_159', str(BASE))
b159 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b159)
ace = b159.ace

ace.VERSION = '1.6.0'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.0'
except Exception:
    pass

# ----------------------------- faster research -----------------------------
_RESEARCH_CANCEL_160 = threading.Event()
_orig_unwrap_159 = b159._unwrap_link


def _bing_target_160(href):
    try:
        h = html.unescape(str(href or '').strip())
        if h.startswith('/ck/a'):
            h = 'https://www.bing.com' + h
        u = urllib.parse.urlparse(h)
        host = (u.hostname or '').lower().removeprefix('www.')
        if host != 'bing.com' or not u.path.startswith('/ck/a'):
            return ''
        token = (urllib.parse.parse_qs(u.query).get('u') or [''])[0]
        token = urllib.parse.unquote(token)
        if token.startswith('a1'):
            token = token[2:]
        if not token:
            return ''
        token += '=' * ((4 - len(token) % 4) % 4)
        out = base64.urlsafe_b64decode(token.encode('ascii')).decode('utf-8', 'replace')
        return out if out.startswith(('http://', 'https://')) else ''
    except Exception:
        return ''


def _unwrap_link_160(href):
    target = _bing_target_160(href)
    return _orig_unwrap_159(target or href)


def _discover_160(query, max_urls=16):
    if _RESEARCH_CANCEL_160.is_set():
        return []
    out, seen_hosts, seen_urls = [], set(), set()

    def one(engine_url):
        engine, url = engine_url
        if _RESEARCH_CANCEL_160.is_set():
            return engine, []
        try:
            page, _ = b159._get(url, timeout=3.2, limit=360_000)
        except Exception:
            return engine, []
        p = b159._Links()
        try:
            p.feed(page)
        except Exception:
            pass
        vals = []
        for href, anchor in p.links:
            u = _unwrap_link_160(href)
            if u:
                vals.append((u, anchor[:180]))
        return engine, vals

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    futs = [ex.submit(one, x) for x in b159._engine_urls(query)]
    batches = []
    try:
        for f in concurrent.futures.as_completed(futs, timeout=3.8):
            if _RESEARCH_CANCEL_160.is_set():
                break
            try:
                batches.append(f.result())
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        pass
    finally:
        for f in futs:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)

    order = {'Google': 0, 'Bing': 1, 'DuckDuckGo': 2}
    batches.sort(key=lambda x: order.get(x[0], 99))
    for engine, vals in batches:
        for u, anchor in vals:
            if u in seen_urls:
                continue
            try:
                host = (urllib.parse.urlparse(u).hostname or '').lower().removeprefix('www.')
            except Exception:
                continue
            if not host:
                continue
            if host in seen_hosts and len(out) >= 7:
                continue
            seen_urls.add(u)
            seen_hosts.add(host)
            out.append({'url': u, 'engine': engine, 'anchor': anchor})
            if len(out) >= max_urls:
                return out
    return out


def _fetch_source_160(item):
    if _RESEARCH_CANCEL_160.is_set():
        return None
    try:
        page, final = b159._get(item['url'], timeout=4.0, limit=460_000)
        if _RESEARCH_CANCEL_160.is_set():
            return None
        p = b159._PageText()
        p.feed(page)
        title = re.sub(r'\s+', ' ', ' '.join(p.title)).strip()
        desc = re.sub(r'\s+', ' ', p.description).strip()
        body = re.sub(r'\s+', ' ', ' '.join(p.parts)).strip()
        if len(body) < 180:
            return None
        host = (urllib.parse.urlparse(final).hostname or '').lower().removeprefix('www.')
        if not host:
            return None
        return {
            'url': final,
            'domain': host,
            'title': title[:220] or item.get('anchor', '')[:220] or host,
            'description': desc[:420],
            'excerpt': body[:2300],
            'engine': item.get('engine', 'Web'),
        }
    except Exception:
        return None


def _source_score_160(s):
    d = str(s.get('domain') or '').lower()
    bonus = 0
    if d.endswith('.gov') or d.endswith('.edu'):
        bonus += 8
    if any(x in d for x in ('wikipedia.org', 'wiki.gg', 'steampowered.com',
                             'counter-strike.net', 'valvesoftware.com')):
        bonus += 5
    if 'fandom.com' in d:
        bonus += 1
    return -bonus


def _research_160(query):
    query = b159._clean_query(query)
    if not query:
        return []
    _RESEARCH_CANCEL_160.clear()
    key = query.lower()
    now = time.time()
    with b159._CACHE_LOCK:
        cached = b159._CACHE.get(key)
        if cached and now - cached[0] < b159._CACHE_TTL:
            return cached[1]

    candidates = _discover_160(query)
    if not candidates or _RESEARCH_CANCEL_160.is_set():
        return []

    results = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(candidates)))
    futs = [ex.submit(_fetch_source_160, x) for x in candidates[:14]]
    try:
        for f in concurrent.futures.as_completed(futs, timeout=4.8):
            if _RESEARCH_CANCEL_160.is_set():
                break
            try:
                src = f.result()
            except Exception:
                src = None
            if src and all(x.get('domain') != src.get('domain') for x in results):
                results.append(src)
                if len(results) >= 5:
                    break
    except concurrent.futures.TimeoutError:
        pass
    finally:
        for f in futs:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)

    results.sort(key=_source_score_160)
    if results:
        with b159._CACHE_LOCK:
            b159._CACHE[key] = (now, results)
    return results


b159._unwrap_link = _unwrap_link_160
b159._discover = _discover_160
b159._fetch_source = _fetch_source_160
b159._research = _research_160

_post159 = b159.POST


def POST_160(self):
    try:
        path = urllib.parse.urlparse(self.path).path.lower()
        if path in {'/api/stop', '/api/opendesign/cancel'}:
            _RESEARCH_CANCEL_160.set()
    except Exception:
        pass
    return _post159(self)


ace.H.do_POST = POST_160

# ----------------------------- deterministic Edit -----------------------------
def _patch_file(path, marker, transform):
    try:
        p = Path(path)
        s = p.read_text(encoding='utf-8')
        if marker in s:
            return True
        n = transform(s)
        if n != s:
            p.write_text(n, encoding='utf-8')
        return marker in n
    except Exception:
        return False


def _idx_160(s):
    s = s.replace('app.css?v=159-research', 'app.css?v=160-corefix')
    s = s.replace('app.js?v=159-research', 'app.js?v=160-corefix')
    s = s.replace('Current version: v1.5.9', 'Current version: v1.6.0')
    return s + '\n<!--ACE160-->\n'


CSS160 = r'''
.ace160-toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(8px);z-index:2147483647;background:#09131b;color:#e7f6f2;border:1px solid #22d3a7aa;border-radius:10px;padding:9px 13px;box-shadow:0 12px 34px #0008;font:600 12px/1.25 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;opacity:0;transition:opacity .16s ease,transform .16s ease;pointer-events:none}.ace160-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}.ace160-toast.bad{border-color:#ff7b7baa;color:#ffe4e4}
/*ACE160*/
'''

JS160 = r'''
(function(){
  if(window.__ACE160_EDIT_ROUTER__)return;
  window.__ACE160_EDIT_ROUTER__=1;
  const S={busy:false,last:0,timer:0};
  function studio(){return document.getElementById('artifactStudio')||document.querySelector('.artifact-studio');}
  function isEditButton(b){
    if(!b)return false;
    const t=((b.textContent||'')+' '+(b.title||'')+' '+(b.getAttribute('aria-label')||'')).replace(/\s+/g,' ').trim().toLowerCase();
    return /^edit(?:\b|\s|$)/.test(t)||t==='edit poster'||t==='edit preview';
  }
  function toast(msg,bad){
    let x=document.getElementById('ace160Toast');
    if(!x){x=document.createElement('div');x.id='ace160Toast';x.className='ace160-toast';document.body.appendChild(x);}
    x.textContent=msg;x.className='ace160-toast'+(bad?' bad':'');
    requestAnimationFrame(()=>x.classList.add('show'));
    clearTimeout(S.timer);S.timer=setTimeout(()=>x.classList.remove('show'),2600);
  }
  function ready(){try{return typeof studioJob!=='undefined'&&studioJob&&studioJob.job_id;}catch(_){return false;}}
  function previewReady(){
    const r=studio();if(!r)return false;
    return [...r.querySelectorAll('img')].some(i=>{const b=i.getBoundingClientRect();return b.width>80&&b.height>80;});
  }
  async function openEditor(){
    const now=Date.now();if(S.busy||now-S.last<450)return;S.last=now;
    if(!ready()){toast('Finish generating the preview before editing.');return;}
    if(!previewReady()){toast('The preview is still loading. Try Edit again in a moment.');return;}
    if(typeof window.acePosterEdit156!=='function'){toast('The poster editor is unavailable for this artifact.',true);return;}
    S.busy=true;
    try{
      const r=window.acePosterEdit156();
      if(r&&typeof r.then==='function')await r;
    }catch(err){toast((err&&err.message)||'Could not open the poster editor.',true);}
    finally{setTimeout(()=>{S.busy=false;},300);}
  }
  window.addEventListener('click',e=>{
    const b=e.target&&e.target.closest&&e.target.closest('button,a,[role="button"]');
    const r=studio();if(!b||!r||!r.contains(b)||!isEditButton(b))return;
    e.preventDefault();e.stopPropagation();if(e.stopImmediatePropagation)e.stopImmediatePropagation();
    openEditor();
  },true);
})();
// ACE160_EDIT_ROUTER
'''


def _app_160(s):
    s = re.sub(
        r'\n\(function\(\)\{\n\s*if\(window\.__ACE158_EDIT_FIX_FINAL__\)[\s\S]*?\n\}\)\(\);\n// ACE158_FINAL\n',
        '\n', s, count=1)
    if 'ACE158_FINAL' not in s:
        s += '\n// ACE158_FINAL superseded by ACE160\n'
    return s + '\n' + JS160 + '\n// ACE160\n'


_patch_file(H / 'index.html', 'ACE160', _idx_160)
_patch_file(H / 'app.css', 'ACE160', lambda s: s + '\n' + CSS160)
_patch_file(H / 'app.js', 'ACE160', _app_160)

if __name__ == '__main__':
    ace.main()
