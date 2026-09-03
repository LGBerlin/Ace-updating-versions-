#!/usr/bin/env python3
"""A.C.E. 1.6.2 — low-latency research answers.

Builds directly on the proven 1.6.1 fast 3–5-site scheduler. Keeps the same
cross-check policy, but shortens hard web budgets and compresses each retrieved
page to the query-relevant evidence before the local Qwen model sees it.

No UI, theme, voice, artifact, button, or model-selection behavior is changed.
"""
from pathlib import Path
import importlib.util
import re
import time
import urllib.parse

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.1.py'

spec = importlib.util.spec_from_file_location('ace_base_161', str(BASE))
b161 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b161)
ace = b161.ace
r159 = b161.r159

ace.VERSION = '1.6.2'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.2'
except Exception:
    pass

# Keep 3–5 independent sites, but bound research much more tightly.
b161.MIN_SOURCES = 3
b161.TARGET_SOURCES = 4
b161.MAX_SOURCES = 5
b161.MAX_CANDIDATES = 7
b161.DISCOVERY_BUDGET = 1.8
b161.DISCOVERY_REQUEST_TIMEOUT = 1.55
b161.PAGE_BUDGET = 3.0
b161.PAGE_REQUEST_TIMEOUT = 2.55
b161.TARGET_GRACE = 0.30

_STOP = {
    'the','and','for','that','with','this','from','what','when','where','which','who','why','how',
    'are','was','were','will','would','could','should','can','does','did','has','have','had','about',
    'into','than','then','them','they','their','there','your','you','our','out','get','find','tell',
    'give','make','current','latest','best','more','most','some','any','all','its','his','her','not',
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]{2,}")
_SENT = re.compile(r'(?<=[.!?])\s+|\s*[•|]\s*')


def _terms(query):
    vals=[]
    for w in _WORD.findall(str(query or '').lower()):
        if w not in _STOP and w not in vals:
            vals.append(w)
    return vals[:14]


def _compact_excerpt(body, query, limit=560):
    """Select a few query-relevant sentences instead of dumping page text."""
    body = re.sub(r'\s+', ' ', str(body or '')).strip()
    if not body:
        return ''
    terms = _terms(query)
    sentences = [s.strip() for s in _SENT.split(body) if 35 <= len(s.strip()) <= 900]
    if not sentences:
        return body[:limit]

    scored=[]
    for i,s in enumerate(sentences[:220]):
        low=s.lower()
        hits=sum(1 for t in terms if t in low)
        exact=sum(low.count(t) for t in terms)
        # Favor direct query overlap, but keep a small lead-paragraph preference.
        score=hits*6 + min(exact,8)*1.3 + max(0, 2.5-(i*0.10))
        if any(x in low for x in ('cookie','privacy policy','sign in','subscribe','advertisement')):
            score-=8
        scored.append((score,i,s))
    scored.sort(key=lambda x:(x[0],-x[1]), reverse=True)

    chosen=[]; used=0
    for score,i,s in scored:
        if score <= 0 and chosen:
            continue
        remaining=limit-used
        if remaining < 80:
            break
        piece=s[:remaining]
        chosen.append((i,piece));used+=len(piece)+1
        if used>=limit or len(chosen)>=4:
            break
    if not chosen:
        return body[:limit]
    chosen.sort(key=lambda x:x[0])
    return ' '.join(x[1] for x in chosen)[:limit]


_original_discover = b161._discover_fast


def _discover_with_query(query, max_urls=7):
    items=_original_discover(query, max_urls=max_urls)
    for item in items:
        item['_ace_query']=query
    return items


def _fetch_source_compact(item):
    """Fetch less data and retain only the evidence most relevant to the question."""
    try:
        page, final = r159._get(
            item['url'],
            timeout=b161.PAGE_REQUEST_TIMEOUT,
            limit=280_000,
        )
        p = r159._PageText(); p.feed(page)
        title = re.sub(r'\s+', ' ', ' '.join(p.title)).strip()
        desc = re.sub(r'\s+', ' ', p.description).strip()
        body = re.sub(r'\s+', ' ', ' '.join(p.parts)).strip()
        if len(body) < 180:
            return None
        host=(urllib.parse.urlparse(final).hostname or '').lower().removeprefix('www.')
        if not host:
            return None
        query=str(item.get('_ace_query') or '')
        excerpt=_compact_excerpt(body, query, limit=560)
        if len(excerpt) < 120:
            excerpt=body[:560]
        return {
            'url': final,
            'domain': host,
            'title': title[:180] or item.get('anchor','')[:180] or host,
            'description': desc[:180],
            'excerpt': excerpt,
            'engine': item.get('engine','Web'),
        }
    except Exception:
        return None


# Existing 1.6.1 research function resolves these globals at call time.
b161._discover_fast = _discover_with_query
b161._fetch_source_fast = _fetch_source_compact


def _compact_evidence_block(user_text, sources, artifact=False):
    if not sources:
        return (
            "\n\n[ACE_WEB_RESEARCH_162 INTERNAL] Live verification returned no usable pages. "
            "Do not claim current facts were verified; answer cautiously. [/ACE_WEB_RESEARCH_162]"
        )
    lines=[
        "\n\n[ACE_WEB_RESEARCH_162 INTERNAL]",
        "Cross-check the independent sources below. Prefer agreement and primary/official sources; do not invent missing facts.",
    ]
    for i,s in enumerate(sources[:5],1):
        title=str(s.get('title') or s.get('domain') or '')[:180]
        domain=str(s.get('domain') or '')
        evidence=str(s.get('excerpt') or '')[:560]
        lines.append(f"S{i} {domain} — {title}")
        lines.append(evidence)
    if artifact:
        lines.append("Use the verified facts in the artifact; omit raw source lists unless requested.")
    else:
        lines.append("Answer directly. For current/disputed/recommendation questions, end with 'Sources checked:' and 2–4 domains.")
    lines.append("[/ACE_WEB_RESEARCH_162]")
    return '\n'.join(lines)


# 1.5.9's request preflight looks these module globals up at runtime.
r159._evidence_block = _compact_evidence_block


def _patch_index():
    try:
        p=H/'index.html';s=p.read_text(encoding='utf-8')
        marker='ACE162_LOW_LATENCY'
        if marker in s:return
        s=s.replace('Current version: v1.6.1','Current version: v1.6.2')
        p.write_text(s+'\n<!--ACE162_LOW_LATENCY-->\n',encoding='utf-8')
    except Exception:
        pass

_patch_index()

if __name__ == '__main__':
    ace.main()
