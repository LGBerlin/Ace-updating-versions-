#!/usr/bin/env python3
"""A.C.E. 1.6.4 — SearXNG-first research.

Builds on 1.6.3. Ordinary factual research now uses a SearXNG instance as the
primary search backend. A.C.E. consumes SearXNG result snippets directly rather
than scraping search engines and opening several result pages itself.

Normal behavior:
- one SearXNG search request;
- keep 3–5 distinct source domains;
- feed only compact result evidence to Qwen in /no_think mode;
- retain exact source URLs so a follow-up "sources?" returns them immediately.

A configured/private SearXNG URL is preferred, then localhost, then a short
conservative list of public SearXNG instances. The previous A.C.E. research
crawler is used only if every SearXNG option is unavailable.
"""
from pathlib import Path
from html.parser import HTMLParser
import importlib.util
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.3.py'

spec = importlib.util.spec_from_file_location('ace_base_163', str(BASE))
b163 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b163)
ace = b163.ace
r159 = b163.r159

ace.VERSION = '1.6.4'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.4'
except Exception:
    pass

# Keep the proven pre-SearXNG research path only as an emergency fallback.
_FALLBACK_RESEARCH = r159._research

MIN_SOURCES = 3
TARGET_SOURCES = 4
MAX_SOURCES = 5
SEARCH_TIMEOUT = 2.4
SEARX_TOTAL_BUDGET = 6.5
SEARCH_CACHE_TTL = 900
_SOURCE_MEMORY_TTL = 3600

_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36'
)

# Private/configured and localhost instances are always preferred. Public
# fallbacks are tried one at a time, never fanned out.
_PUBLIC_SEARXNG = (
    'https://search.inetol.net',
    'https://searx.be',
    'https://search.bus-hit.me',
)

_SEARX_CACHE = {}
_SEARX_CACHE_LOCK = threading.Lock()
_LAST_SOURCES = {'at': 0.0, 'query': '', 'items': []}
_LAST_SOURCES_LOCK = threading.Lock()

_SOURCE_REQUEST = re.compile(
    r'\b(?:sources?|source links?|links?|urls?|where did you get|where did that come from|'
    r'show me (?:the )?sources?|what (?:websites?|sites?) did you use)\b',
    re.I,
)

_SKIP_HOSTS = {
    'google.com', 'www.google.com', 'bing.com', 'www.bing.com',
    'duckduckgo.com', 'www.duckduckgo.com',
}


def _norm_base(url):
    url = str(url or '').strip()
    if not url:
        return ''
    if '://' not in url:
        url = 'http://' + url
    return url.rstrip('/')


def _configured_url():
    env = _norm_base(os.environ.get('ACE_SEARXNG_URL', ''))
    if env:
        return env
    for p in (
        Path.home() / 'Library/Application Support/A.C.E./searxng-url.txt',
        H / 'searxng-url.txt',
    ):
        try:
            val = _norm_base(p.read_text(encoding='utf-8').strip())
            if val:
                return val
        except Exception:
            pass
    return ''


def _candidate_instances():
    out = []
    for u in (
        _configured_url(),
        'http://127.0.0.1:8888',
        'http://localhost:8888',
        *_PUBLIC_SEARXNG,
    ):
        u = _norm_base(u)
        if u and u not in out:
            out.append(u)
    return out


def _http(url, accept='application/json,text/html;q=0.9,*/*;q=0.5', timeout=SEARCH_TIMEOUT, limit=850_000):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': accept,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = int(getattr(r, 'status', 200) or 200)
        ctype = str(r.headers.get('Content-Type') or '').lower()
        raw = r.read(limit + 1)
        if len(raw) > limit:
            raw = raw[:limit]
        charset = r.headers.get_content_charset() or 'utf-8'
        try:
            text = raw.decode(charset, errors='replace')
        except Exception:
            text = raw.decode('utf-8', errors='replace')
        return status, ctype, text, str(r.geturl())


def _clean_text(value, limit):
    s = re.sub(r'\s+', ' ', str(value or '')).strip()
    return s[:limit]


def _domain(url):
    try:
        return (urllib.parse.urlparse(str(url or '')).hostname or '').lower().removeprefix('www.')
    except Exception:
        return ''


def _result_item(url, title='', snippet='', engines=None, score=0.0):
    url = str(url or '').strip()
    host = _domain(url)
    if not url or not host or host in {x.removeprefix('www.') for x in _SKIP_HOSTS}:
        return None
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in {'http', 'https'}:
            return None
    except Exception:
        return None
    return {
        'url': url,
        'domain': host,
        'title': _clean_text(title or host, 180),
        'excerpt': _clean_text(snippet, 360),
        'engines': list(engines or [])[:6],
        'score': float(score or 0.0),
        'engine': 'SearXNG',
    }


def _json_results(text):
    try:
        d = json.loads(text)
    except Exception:
        return []
    raw = d.get('results') if isinstance(d, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        engines = x.get('engines')
        if not isinstance(engines, list):
            engine = x.get('engine')
            engines = [str(engine)] if engine else []
        item = _result_item(
            x.get('url'),
            x.get('title'),
            x.get('content') or x.get('snippet') or x.get('description'),
            engines,
            x.get('score') or 0.0,
        )
        if item:
            out.append(item)
    return out


class _SearxHTML(HTMLParser):
    """Tolerant parser for SearXNG's simple result HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._root_tag = ''
        self._root_depth = 0
        self._href = ''
        self._title_parts = []
        self._snippet_parts = []
        self._heading_depth = 0
        self._content_depth = 0

    def _reset_result(self):
        self._root_tag = ''
        self._root_depth = 0
        self._href = ''
        self._title_parts = []
        self._snippet_parts = []
        self._heading_depth = 0
        self._content_depth = 0

    def handle_starttag(self, tag, attrs):
        a = {str(k).lower(): str(v or '') for k, v in attrs}
        classes = set(a.get('class', '').lower().replace('_', '-').split())
        t = tag.lower()

        if not self._root_tag and t in {'article', 'div'} and (
            'result' in classes or 'result-default' in classes or 'result-content' in classes
        ):
            self._root_tag = t
            self._root_depth = 1
            return

        if not self._root_tag:
            return

        if t == self._root_tag:
            self._root_depth += 1
        if t in {'h3', 'h4'}:
            self._heading_depth += 1
        if t in {'p', 'div'} and (
            'content' in classes or 'result-content' in classes or 'result_content' in classes
        ):
            self._content_depth += 1
        if t == 'a' and a.get('href') and not self._href:
            href = a.get('href', '')
            if href.startswith('http://') or href.startswith('https://'):
                self._href = href

    def handle_data(self, data):
        if not self._root_tag:
            return
        s = re.sub(r'\s+', ' ', data).strip()
        if not s:
            return
        if self._heading_depth:
            self._title_parts.append(s)
        elif self._content_depth:
            self._snippet_parts.append(s)

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self._root_tag:
            return
        if t in {'h3', 'h4'} and self._heading_depth:
            self._heading_depth -= 1
        if t in {'p', 'div'} and self._content_depth:
            self._content_depth -= 1
        if t == self._root_tag:
            self._root_depth -= 1
            if self._root_depth <= 0:
                item = _result_item(
                    self._href,
                    ' '.join(self._title_parts),
                    ' '.join(self._snippet_parts),
                    ['html'],
                    0.0,
                )
                if item:
                    self.results.append(item)
                self._reset_result()


def _html_results(text):
    p = _SearxHTML()
    try:
        p.feed(text)
    except Exception:
        pass
    return p.results


def _rank_and_select(items):
    # SearXNG has already aggregated engine rankings. Keep that order mostly
    # intact, with a small preference for official/primary-looking domains.
    seen = set()
    scored = []
    for i, x in enumerate(items or []):
        host = str(x.get('domain') or '').lower()
        if not host or host in seen:
            continue
        seen.add(host)
        bonus = 0.0
        if host.endswith('.gov') or host.endswith('.edu'):
            bonus += 3.0
        if any(host.endswith(s) for s in ('.org', '.int')):
            bonus += 0.5
        if any(bad in host for bad in ('pinterest.', 'facebook.', 'instagram.', 'tiktok.')):
            bonus -= 3.0
        base_score = float(x.get('score') or 0.0)
        scored.append((bonus + base_score, -i, x))
    scored.sort(reverse=True, key=lambda t: (t[0], t[1]))
    chosen = [t[2] for t in scored[:MAX_SOURCES]]
    return chosen


def _search_instance(base, query):
    q = urllib.parse.urlencode({
        'q': query,
        'format': 'json',
        'categories': 'general',
        'language': 'auto',
        'safesearch': '1',
    })
    url = base + '/search?' + q
    try:
        status, ctype, text, _ = _http(url)
        if status == 200:
            vals = _json_results(text)
            if vals:
                return _rank_and_select(vals), 'json'
    except urllib.error.HTTPError as e:
        # JSON is disabled on many public SearXNG instances. 403/404 means try
        # the normal HTML results page once; never bypass auth/rate limits.
        if int(getattr(e, 'code', 0) or 0) not in {403, 404}:
            return [], ''
    except Exception:
        return [], ''

    q2 = urllib.parse.urlencode({
        'q': query,
        'categories': 'general',
        'language': 'auto',
        'safesearch': '1',
    })
    try:
        status, ctype, text, _ = _http(
            base + '/search?' + q2,
            accept='text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
        )
        if status == 200:
            vals = _html_results(text)
            if vals:
                return _rank_and_select(vals), 'html'
    except Exception:
        pass
    return [], ''


def _remember(query, items):
    with _LAST_SOURCES_LOCK:
        _LAST_SOURCES['at'] = time.time()
        _LAST_SOURCES['query'] = query
        _LAST_SOURCES['items'] = [dict(x) for x in items[:MAX_SOURCES]]


def _remembered_sources():
    with _LAST_SOURCES_LOCK:
        if time.time() - float(_LAST_SOURCES.get('at') or 0) > _SOURCE_MEMORY_TTL:
            return []
        return [dict(x) for x in (_LAST_SOURCES.get('items') or [])]


def _research_searxng(query):
    clean = r159._clean_query(query)
    if not clean:
        return []

    # "Sources?" is answered from the previous SearXNG result set instantly.
    if _SOURCE_REQUEST.search(clean):
        prior = _remembered_sources()
        if prior:
            for x in prior:
                x['_ace_source_recall'] = True
            return prior

    key = clean.lower()
    now = time.time()
    with _SEARX_CACHE_LOCK:
        cached = _SEARX_CACHE.get(key)
        if cached and now - cached[0] < SEARCH_CACHE_TTL:
            vals = [dict(x) for x in cached[1]]
            if vals:
                _remember(clean, vals)
            return vals

    best = []
    deadline = time.monotonic() + SEARX_TOTAL_BUDGET
    for base in _candidate_instances():
        if time.monotonic() >= deadline:
            break
        vals, fmt = _search_instance(base, clean)
        if len(vals) > len(best):
            best = vals
        if len(vals) >= MIN_SOURCES:
            best = vals
            break

    best = best[:MAX_SOURCES]
    if best:
        _remember(clean, best)
        with _SEARX_CACHE_LOCK:
            _SEARX_CACHE[key] = (now, [dict(x) for x in best])
        return best

    # Emergency compatibility fallback only. This is no longer the normal path.
    try:
        vals = _FALLBACK_RESEARCH(clean)
    except Exception:
        vals = []
    vals = list(vals or [])[:MAX_SOURCES]
    if vals:
        _remember(clean, vals)
    return vals


def _searx_evidence_block(user_text, sources, artifact=False):
    recall = bool(sources and sources[0].get('_ace_source_recall'))
    if not sources:
        return (
            '\n\n[ACE_SEARXNG_164 INTERNAL] SearXNG returned no usable results. '
            'Do not pretend live verification succeeded. [/ACE_SEARXNG_164]'
        )

    lines = ['\n\n[ACE_SEARXNG_164 INTERNAL]']
    if recall:
        lines.append(
            'The user asked for the sources from the previous researched answer. '
            'Return the exact titles and URLs below. Do not run a new factual answer.'
        )
    else:
        lines.append(
            'SearXNG already searched multiple engines. Answer from these 3–5 distinct '
            'result sources only. Cross-check agreement; prefer primary/official sources. '
            'Do not invent details beyond the snippets.'
        )
    for i, s in enumerate(sources[:MAX_SOURCES], 1):
        title = _clean_text(s.get('title') or s.get('domain'), 150)
        url = str(s.get('url') or '')[:600]
        excerpt = _clean_text(s.get('excerpt'), 320)
        lines.append(f'S{i} {title}')
        lines.append(f'URL: {url}')
        if excerpt and not recall:
            lines.append('Evidence: ' + excerpt)
    if artifact:
        lines.append(
            'Use the verified facts in the artifact. Keep source URLs available but do not '
            'clutter the artifact unless the user asks for citations.'
        )
    elif recall:
        lines.append('Give the source list now, with clickable full URLs and no extra research.')
    else:
        lines.append(
            'Use /no_think. Answer immediately and concisely, normally 60–150 words. '
            'Do not show raw URLs unless the user asks for sources.'
        )
        lines.append('/no_think')
    lines.append('[/ACE_SEARXNG_164]')
    return '\n'.join(lines)


# Replace only the research backend and evidence packet. The rest of A.C.E. 1.6.3,
# including its fast-history handling, voice, UI and artifact behavior, remains intact.
r159._research = _research_searxng
r159._evidence_block = _searx_evidence_block


def _patch_index():
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        marker = 'ACE164_SEARXNG'
        if marker in s:
            return
        s = s.replace('Current version: v1.6.3', 'Current version: v1.6.4')
        p.write_text(s + '\n<!--ACE164_SEARXNG-->\n', encoding='utf-8')
    except Exception:
        pass


_patch_index()

if __name__ == '__main__':
    ace.main()
