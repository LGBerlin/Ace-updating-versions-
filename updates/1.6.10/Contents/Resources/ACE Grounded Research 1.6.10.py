#!/usr/bin/env python3
"""A.C.E. 1.6.10 grounded research layer.

SearXNG remains the fast discovery engine, but snippets are no longer treated as
sufficient evidence for confident factual answers.  The top distinct results are
opened concurrently under a tight budget and reduced to query-relevant evidence.
Concrete claims must be supported by that evidence; missing facts stay missing.
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
import urllib.parse

LOCAL_SEARXNG = 'http://127.0.0.1:8888'
MAX_SOURCES = 5
MIN_PAGE_SOURCES = 2
PAGE_TIMEOUT = 2.45
PAGE_BUDGET = 3.65
CACHE_TTL = 900

_STOP = {
    'the','and','for','that','with','this','from','what','when','where','which','who','why','how',
    'are','was','were','will','would','could','should','can','does','did','has','have','had','about',
    'into','than','then','them','they','their','there','your','you','our','out','get','find','tell',
    'give','make','current','latest','best','more','most','some','any','all','its','his','her','not',
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]{2,}")
_SENT = re.compile(r'(?<=[.!?])\s+|\s*[•|]\s*')
_CACHE = {}
_CACHE_LOCK = threading.RLock()


def _terms(query):
    out = []
    for word in _WORD.findall(str(query or '').lower()):
        if word not in _STOP and word not in out:
            out.append(word)
    return out[:16]


def compact_excerpt(text, query, limit=680):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not text:
        return ''
    terms = _terms(query)
    sentences = [s.strip() for s in _SENT.split(text) if 32 <= len(s.strip()) <= 950]
    if not sentences:
        return text[:limit]
    ranked = []
    for i, sentence in enumerate(sentences[:260]):
        low = sentence.lower()
        hits = sum(1 for t in terms if t in low)
        occurrences = sum(min(3, low.count(t)) for t in terms)
        score = hits * 7 + occurrences * 1.5 + max(0.0, 2.2 - i * .055)
        if any(x in low for x in ('cookie policy','accept cookies','privacy policy','sign in','subscribe now','advertisement')):
            score -= 12
        ranked.append((score, i, sentence))
    ranked.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    picked = []
    used = 0
    for score, i, sentence in ranked:
        if picked and score <= 0:
            continue
        room = limit - used
        if room < 80:
            break
        piece = sentence[:room]
        picked.append((i, piece))
        used += len(piece) + 1
        if len(picked) >= 5 or used >= limit:
            break
    if not picked:
        return text[:limit]
    picked.sort(key=lambda x: x[0])
    return ' '.join(x[1] for x in picked)[:limit]


def _source_quality(item):
    host = str(item.get('domain') or '').lower()
    score = float(item.get('score') or 0.0)
    if host.endswith('.gov') or host.endswith('.edu'):
        score += 10
    if host.endswith('.int'):
        score += 8
    if host.endswith('.org'):
        score += 1
    if any(x in host for x in ('reddit.com','quora.com','pinterest.','facebook.','instagram.','tiktok.','medium.com')):
        score -= 6
    return score


def install(b164):
    """Install over a loaded A.C.E. 1.6.4 module; return a public research helper."""
    r159 = b164.r159

    # Keep the known-good local Docker SearXNG path first and avoid the broken
    # 1.6.5 Python/PyPI manager entirely.
    b164.SEARCH_TIMEOUT = 1.9
    b164.SEARX_TOTAL_BUDGET = 2.5
    b164._PUBLIC_SEARXNG = ()
    original_configured = b164._configured_url

    def candidates():
        out = [LOCAL_SEARXNG]
        try:
            configured = str(original_configured() or '').rstrip('/')
        except Exception:
            configured = ''
        if configured and configured not in out:
            out.append(configured)
        return out

    b164._candidate_instances = candidates
    searx_discover = b164._research_searxng

    def fetch_page(item, query):
        try:
            page, final = r159._get(item['url'], timeout=PAGE_TIMEOUT, limit=330_000)
            parser = r159._PageText()
            parser.feed(page)
            body = re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()
            if len(body) < 180:
                return None
            host = (urllib.parse.urlparse(final).hostname or '').lower().removeprefix('www.')
            if not host:
                return None
            title = re.sub(r'\s+', ' ', ' '.join(parser.title)).strip()
            excerpt = compact_excerpt(body, query, 680)
            if len(excerpt) < 100:
                return None
            out = dict(item)
            out.update({
                'url': final,
                'domain': host,
                'title': title[:190] or str(item.get('title') or host)[:190],
                'excerpt': excerpt,
                'evidence_kind': 'page',
            })
            return out
        except Exception:
            return None

    def research(query):
        clean = r159._clean_query(query)
        if not clean:
            return []

        # Preserve the exact fast source-recall behavior from 1.6.4.
        try:
            if b164._SOURCE_REQUEST.search(clean):
                prior = b164._remembered_sources()
                if prior:
                    for x in prior:
                        x['_ace_source_recall'] = True
                    return prior
        except Exception:
            pass

        key = clean.lower()
        now = time.time()
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached and now - cached[0] < CACHE_TTL:
                return [dict(x) for x in cached[1]]

        discovered = list(searx_discover(clean) or [])[:MAX_SOURCES]
        if not discovered:
            return []
        discovered.sort(key=_source_quality, reverse=True)

        ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_SOURCES, len(discovered)))
        futures = {ex.submit(fetch_page, item, clean): item for item in discovered}
        pending = set(futures)
        page_results = []
        deadline = time.monotonic() + PAGE_BUDGET
        try:
            while pending and time.monotonic() < deadline:
                remaining = max(0.01, deadline - time.monotonic())
                done, pending = concurrent.futures.wait(
                    pending, timeout=remaining,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    break
                for f in done:
                    try:
                        src = f.result()
                    except Exception:
                        src = None
                    if src and all(x.get('domain') != src.get('domain') for x in page_results):
                        page_results.append(src)
                if len(page_results) >= 4:
                    break
        finally:
            for f in pending:
                f.cancel()
            ex.shutdown(wait=False, cancel_futures=True)

        page_results.sort(key=_source_quality, reverse=True)
        final = page_results[:MAX_SOURCES]

        # Failed page fetches may still be useful for navigation/source recall,
        # but are explicitly marked snippet-only so the model cannot treat them
        # as equivalent to opened evidence.
        if len(final) < MAX_SOURCES:
            used = {x.get('domain') for x in final}
            for item in discovered:
                if item.get('domain') in used:
                    continue
                snippet = str(item.get('excerpt') or '').strip()
                if not snippet:
                    continue
                x = dict(item)
                x['excerpt'] = snippet[:360]
                x['evidence_kind'] = 'snippet'
                final.append(x)
                used.add(x.get('domain'))
                if len(final) >= MAX_SOURCES:
                    break

        if final:
            try:
                b164._remember(clean, final)
            except Exception:
                pass
            with _CACHE_LOCK:
                _CACHE[key] = (now, [dict(x) for x in final])
        return final

    def evidence_block(user_text, sources, artifact=False):
        recall = bool(sources and sources[0].get('_ace_source_recall'))
        if recall:
            lines = [
                '\n\n[ACE_GROUNDED_1610 INTERNAL]',
                'The user asked for sources from the previous researched answer. Return the exact titles and URLs below; do not invent or replace them.',
            ]
            for i, s in enumerate(sources[:MAX_SOURCES], 1):
                lines.append(f"S{i} {s.get('title') or s.get('domain')} | {s.get('url')}")
            lines.append('[/ACE_GROUNDED_1610]')
            return '\n'.join(lines)

        if not sources:
            return (
                '\n\n[ACE_GROUNDED_1610 INTERNAL] Live research returned no usable evidence. '
                'Do not claim that current facts were verified. Do not invent names, numbers, dates, quotations or specifics. '
                'Say verification was unavailable when the answer depends on live facts. [/ACE_GROUNDED_1610]'
            )

        page_count = sum(1 for s in sources if s.get('evidence_kind') == 'page')
        lines = [
            '\n\n[ACE_GROUNDED_1610 INTERNAL]',
            'STRICT EVIDENCE MODE. Answer concrete factual claims ONLY from the evidence below.',
            'Every specific name, number, date, event, quotation, product detail or current-status claim must be explicitly supported below.',
            'Never fill an evidence gap with a plausible guess. If the evidence does not support a requested detail, say that it was not verified.',
            'If sources conflict, state the conflict. Prefer opened PAGE evidence over SEARCH-SNIPPET evidence.',
            f'Opened evidence pages: {page_count}.',
        ]
        if page_count < MIN_PAGE_SOURCES:
            lines.append('Fewer than two source pages were opened successfully. Be especially cautious and avoid confident detailed claims.')
        for i, s in enumerate(sources[:MAX_SOURCES], 1):
            kind = 'PAGE' if s.get('evidence_kind') == 'page' else 'SEARCH-SNIPPET'
            lines.append(f"SOURCE {i} [{kind}] {s.get('domain')} | {s.get('title')} | {s.get('url')}")
            lines.append(str(s.get('excerpt') or '')[:700])
        if artifact:
            lines.append('For an artifact, use only supported factual content. It is better to omit a fact than invent it.')
        else:
            lines.append("Answer directly. End factual researched answers with 'Sources checked:' followed by 2–4 source domains actually listed above.")
        lines.append('[/ACE_GROUNDED_1610]')
        return '\n'.join(lines)

    r159._research = research
    r159._evidence_block = evidence_block
    return research
