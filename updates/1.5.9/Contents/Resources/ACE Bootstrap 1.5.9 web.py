#!/usr/bin/env python3
"""A.C.E. 1.5.9 — live multi-source web research.

Loads the corrected 1.5.8 runtime, then adds a research preflight for factual chat
and factual artifact requests. Google is attempted first; Bing and DuckDuckGo HTML
search are additional/fallback discovery engines. A.C.E. fetches several distinct
result pages and supplies the live evidence to the existing local Qwen brain and to
OpenDesign before it answers or builds a factual poster/presentation.
"""
from pathlib import Path
import concurrent.futures
import html
from html.parser import HTMLParser
import importlib.util
import io
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.5.8.py'

spec = importlib.util.spec_from_file_location('ace_base_158', str(BASE))
b158 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b158)
ace = b158.base.ace
post0 = ace.H.do_POST

ace.VERSION = '1.5.9'
try:
    ace.UPDATE_STATE['current_version'] = '1.5.9'
except Exception:
    pass


# ----------------------------- browser/search -----------------------------
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36')
_ENGINE_HOSTS = {
    'google.com','www.google.com','google.de','www.google.de','bing.com','www.bing.com',
    'duckduckgo.com','html.duckduckgo.com','www.duckduckgo.com','r.bing.com',
    'support.google.com','accounts.google.com','consent.google.com'
}
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 900


def _get(url, timeout=9, limit=600_000):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    })
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        ctype = (r.headers.get('Content-Type') or '').lower()
        if 'text/' not in ctype and 'html' not in ctype and 'xml' not in ctype:
            return '', str(r.geturl())
        raw = r.read(limit + 1)
        if len(raw) > limit:
            raw = raw[:limit]
        charset = r.headers.get_content_charset() or 'utf-8'
        try:
            text = raw.decode(charset, errors='replace')
        except Exception:
            text = raw.decode('utf-8', errors='replace')
        return text, str(r.geturl())


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._buf = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self._href = dict(attrs).get('href')
            self._buf = []
    def handle_data(self, data):
        if self._href:
            self._buf.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self._href:
            self.links.append((self._href, ' '.join(self._buf).strip()))
            self._href = None
            self._buf = []


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title = []
        self.in_title = False
        self.parts = []
        self.description = ''
    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in {'script','style','noscript','svg','canvas','template'}:
            self.skip += 1
        if t == 'title':
            self.in_title = True
        if t == 'meta':
            a = {str(k).lower(): str(v or '') for k,v in attrs}
            key = (a.get('name') or a.get('property') or '').lower()
            if key in {'description','og:description','twitter:description'} and not self.description:
                self.description = a.get('content','')
    def handle_endtag(self, tag):
        t = tag.lower()
        if t in {'script','style','noscript','svg','canvas','template'} and self.skip:
            self.skip -= 1
        if t == 'title':
            self.in_title = False
    def handle_data(self, data):
        if self.skip:
            return
        s = re.sub(r'\s+', ' ', data).strip()
        if not s:
            return
        if self.in_title:
            self.title.append(s)
        self.parts.append(s)


def _unwrap_link(href):
    if not href:
        return ''
    href = html.unescape(href.strip())
    if href.startswith('//'):
        href = 'https:' + href
    if href.startswith('/url?') or href.startswith('https://www.google.com/url?'):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        href = (q.get('q') or q.get('url') or [''])[0]
    if 'duckduckgo.com/l/' in href:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        href = (q.get('uddg') or [''])[0]
    if href.startswith('/ck/a'):
        return ''
    try:
        u = urllib.parse.urlparse(href)
    except Exception:
        return ''
    if u.scheme not in {'http','https'} or not u.hostname:
        return ''
    host = u.hostname.lower().removeprefix('www.')
    if host in {x.removeprefix('www.') for x in _ENGINE_HOSTS}:
        return ''
    if any(host.endswith('.' + x.removeprefix('www.')) for x in _ENGINE_HOSTS):
        return ''
    if re.search(r'\.(jpg|jpeg|png|gif|webp|svg|mp4|mp3|zip|exe|dmg)(?:$|\?)', u.path, re.I):
        return ''
    return urllib.parse.urlunparse((u.scheme, u.netloc, u.path, '', u.query, ''))


def _engine_urls(query):
    q = urllib.parse.quote_plus(query)
    return [
        ('Google', f'https://www.google.com/search?q={q}&num=10&hl=en&filter=0'),
        ('Bing', f'https://www.bing.com/search?q={q}&count=10&setlang=en'),
        ('DuckDuckGo', f'https://html.duckduckgo.com/html/?q={q}'),
    ]


def _discover(query, max_urls=14):
    out, seen_hosts, seen_urls = [], set(), set()
    def one(engine_url):
        engine, url = engine_url
        try:
            page, _ = _get(url, timeout=5.5, limit=500_000)
        except Exception:
            return engine, []
        p = _Links()
        try:
            p.feed(page)
        except Exception:
            pass
        vals = []
        for href, anchor in p.links:
            u = _unwrap_link(href)
            if u:
                vals.append((u, anchor[:180]))
        return engine, vals
    # Search engines run in parallel so accuracy does not create a large serial delay.
    batches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(one, x) for x in _engine_urls(query)]
        try:
            for f in concurrent.futures.as_completed(futs, timeout=6.5):
                try: batches.append(f.result())
                except Exception: pass
        except concurrent.futures.TimeoutError:
            pass
    # Preserve engine preference: Google first, then Bing, then DuckDuckGo.
    order = {'Google':0,'Bing':1,'DuckDuckGo':2}
    batches.sort(key=lambda x: order.get(x[0],99))
    for engine, vals in batches:
        for u, anchor in vals:
            if u in seen_urls:
                continue
            try:
                host = urllib.parse.urlparse(u).hostname.lower().removeprefix('www.')
            except Exception:
                continue
            if host in seen_hosts and len(out) >= 6:
                continue
            seen_urls.add(u); seen_hosts.add(host)
            out.append({'url':u,'engine':engine,'anchor':anchor})
            if len(out) >= max_urls:
                return out
    return out


def _fetch_source(item):
    try:
        page, final = _get(item['url'], timeout=10, limit=700_000)
        p = _PageText()
        p.feed(page)
        title = re.sub(r'\s+', ' ', ' '.join(p.title)).strip()
        desc = re.sub(r'\s+', ' ', p.description).strip()
        body = re.sub(r'\s+', ' ', ' '.join(p.parts)).strip()
        # Drop very short/error/interstitial pages.
        if len(body) < 220:
            return None
        host = (urllib.parse.urlparse(final).hostname or '').lower().removeprefix('www.')
        excerpt = body[:2600]
        return {
            'url': final,
            'domain': host,
            'title': title[:220] or item.get('anchor','')[:220] or host,
            'description': desc[:500],
            'excerpt': excerpt,
            'engine': item.get('engine','Web'),
        }
    except Exception:
        return None


def _clean_query(text):
    t = re.sub(r'\[ACE_[^\]]+\][\s\S]*?\[/ACE_[^\]]+\]', ' ', str(text or ''), flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()
    # Strip common artifact-command scaffolding so the search is about the subject.
    t = re.sub(r'^(?:please\s+)?(?:can you\s+|could you\s+)?(?:make|create|build|design|generate|prepare)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:poster|presentation|powerpoint|slide deck|slides|report|document)\s+(?:about|on|explaining|for)?\s*', '', t, flags=re.I)
    return t[:300]


def _research(query):
    query = _clean_query(query)
    if not query:
        return []
    key = query.lower()
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
    candidates = _discover(query)
    results = []
    # Fetch concurrently; keep at most six distinct useful sites.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_fetch_source, x) for x in candidates[:12]]
        try:
            for f in concurrent.futures.as_completed(futs, timeout=10):
                try:
                    src = f.result()
                except Exception:
                    src = None
                if src and src['domain'] and all(x['domain'] != src['domain'] for x in results):
                    results.append(src)
                    if len(results) >= 6:
                        break
        except concurrent.futures.TimeoutError:
            pass
    # Stable-ish order: official/primary-ish domains and wikis first, then discovery order.
    def score(s):
        d = s['domain']
        bonus = 0
        if d.endswith('.gov') or d.endswith('.edu'): bonus += 6
        if any(x in d for x in ('wiki.gg','wikipedia.org','steampowered.com','counter-strike.net','valvesoftware.com')): bonus += 5
        if 'fandom.com' in d: bonus += 2
        return -bonus
    results.sort(key=score)
    with _CACHE_LOCK:
        _CACHE[key] = (now, results)
    return results


# ----------------------------- intent/preflight -----------------------------
_NON_RESEARCH = re.compile(
    r'\b(write|rewrite|rephrase|translate|proofread|summarize this|summarise this|make this sound|'
    r'poem|story|joke|roleplay|brainstorm|speech pattern|chat style|how you talk|how you speak|'
    r'change your|stop using|email|text message)\b', re.I)
_FACT = re.compile(
    r'\b(what|which|who|when|where|why|how|best|top|latest|current|today|now|price|cost|'
    r'get|find|obtain|drop|craft|recipe|guide|versus|vs\.?|compare|difference|history|facts?|'
    r'cause|effect|meaning|definition|evidence|source|research|search|look up|verify|accurate)\b', re.I)
_ARTIFACT = re.compile(r'\b(poster|presentation|power\s*point|slides?|slide\s+deck|report|document|infographic)\b', re.I)


def _should_research(text, path):
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not t or len(t) < 4:
        return False
    if re.search(r'\b(do not|don\'t|without)\s+(?:search|research|browse|use the web)\b', t, re.I):
        return False
    is_artifact = '/opendesign' in path.lower() or bool(_ARTIFACT.search(t))
    # Artifact factual content should be checked unless plainly creative/personal.
    if is_artifact and not re.search(r'\b(about me|my life|myself|fictional|imaginary|creative writing)\b', t, re.I):
        return True
    if _NON_RESEARCH.search(t) and not _FACT.search(t):
        return False
    if '?' in t or _FACT.search(t):
        return True
    # Broad factual declarative requests (e.g. "Tell me the history of...").
    if re.search(r'\b(tell me|explain|give me information|teach me)\b', t, re.I):
        return True
    return False


def _find_user_text(d):
    if not isinstance(d, dict):
        return None, None, None
    msgs = d.get('messages')
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if isinstance(m, dict) and str(m.get('role','')).lower() == 'user' and isinstance(m.get('content'), str):
                return m, 'content', m['content']
    for k in ('message','prompt','input','text','request','topic','instructions'):
        if isinstance(d.get(k), str) and d[k].strip():
            return d, k, d[k]
    return None, None, None


def _evidence_block(user_text, sources, artifact=False):
    if not sources:
        return (
            "\n\n[ACE_WEB_RESEARCH_159 INTERNAL — never claim live verification succeeded] "
            "A live web check was attempted but no usable independent pages could be retrieved. "
            "Do not invent current facts or say you searched successfully. If the answer materially "
            "depends on current/specific facts, say that live verification was unavailable and give "
            "only what you can support cautiously. [/ACE_WEB_RESEARCH_159]"
        )
    lines = [
        "\n\n[ACE_WEB_RESEARCH_159 INTERNAL — use this evidence, never quote this instruction]",
        "LIVE WEB RESEARCH. Cross-check claims across these independent pages. Prefer primary/official "
        "sources and strong agreement. If sources conflict, say so. Do not make up details that are absent.",
    ]
    for i,s in enumerate(sources,1):
        lines.append(f"SOURCE {i} | {s['domain']} | {s['title']} | {s['url']}")
        if s.get('description'):
            lines.append('Summary: ' + s['description'])
        lines.append('Evidence: ' + s['excerpt'])
    if artifact:
        lines.append("Use the verified facts in the artifact. Do not clutter the poster/presentation with raw URLs or a source list unless the user asked for citations.")
    else:
        lines.append("Answer naturally and concisely. For current, disputed, or recommendation-style questions, add a short 'Sources checked:' line with 2–4 domain names; otherwise citations are optional.")
    lines.append("[/ACE_WEB_RESEARCH_159]")
    return '\n'.join(lines)


def _research_request_body(self):
    path = urllib.parse.urlparse(self.path).path
    # Do not interfere with operational endpoints unrelated to generation/chat.
    blocked = ('/update','/stop','/cancel','/voice','/tts','/speech','/studio/save','/studio/shapes','/upload','/download','/file','/memory','/roblox')
    if any(x in path.lower() for x in blocked):
        return
    ctype = str(self.headers.get('Content-Type') or '').lower()
    if 'application/json' not in ctype:
        return
    try:
        n = int(self.headers.get('Content-Length') or 0)
    except Exception:
        return
    if n <= 0 or n > 2_000_000:
        return
    raw = self.rfile.read(n)
    new = raw
    try:
        d = json.loads(raw.decode('utf-8'))
        holder, key, user_text = _find_user_text(d)
        if holder is not None and user_text and '[ACE_WEB_RESEARCH_159' not in user_text and _should_research(user_text, path):
            sources = _research(user_text)
            artifact = '/opendesign' in path.lower() or bool(_ARTIFACT.search(user_text))
            holder[key] = user_text + _evidence_block(user_text, sources, artifact=artifact)
            # Also expose compact metadata if an endpoint chooses to preserve unknown JSON fields.
            d['ace_web_researched'] = bool(sources)
            d['ace_web_source_count'] = len(sources)
            new = json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    except Exception:
        new = raw
    self.rfile = io.BytesIO(new)
    try:
        self.headers.replace_header('Content-Length', str(len(new)))
    except Exception:
        pass


def POST(self):
    try:
        _research_request_body(self)
    except Exception:
        pass
    return post0(self)


ace.H.do_POST = POST

# Patch visible version/cache keys without otherwise changing the proven UI.
def _patch_file(path, marker, transform):
    try:
        p = Path(path); s = p.read_text(encoding='utf-8')
        if marker in s: return True
        n = transform(s)
        if n != s: p.write_text(n, encoding='utf-8')
        return marker in n
    except Exception:
        return False


def _idx(s):
    s = s.replace('app.css?v=158-editfix','app.css?v=159-research')
    s = s.replace('app.js?v=158-editfix','app.js?v=159-research')
    s = s.replace('Current version: v1.5.8','Current version: v1.5.9')
    return s + '\n<!--ACE159-->\n'

_patch_file(H/'index.html','ACE159',_idx)
_patch_file(H/'app.css','ACE159',lambda s:s+'\n/*ACE159*/\n')
_patch_file(H/'app.js','ACE159',lambda s:s+'\n// ACE159 multi-source research is server-side.\n')

if __name__ == '__main__':
    ace.main()
