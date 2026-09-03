#!/usr/bin/env python3
"""A.C.E. 1.6.1 — fast 3–5 source research.

Loads the new 1.6.0 theme release unchanged, then replaces only the 1.5.9 web
research scheduler underneath it. Research discovery and page fetching remain
parallel, but completed evidence is no longer held open by slow workers.

Normal target: 4 distinct websites; minimum 3 when available; maximum 5.
No UI, artifact, voice, model, or button behavior is changed.
"""
from pathlib import Path
import concurrent.futures
import importlib.util
import re
import time
import urllib.parse

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.0.py'

spec = importlib.util.spec_from_file_location('ace_base_160', str(BASE))
b160 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b160)
ace = b160.ace
r159 = b160.b159

ace.VERSION = '1.6.1'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.1'
except Exception:
    pass

# Fast research policy. These are intentionally small hard budgets so a few slow
# websites can never hold up the whole answer.
MIN_SOURCES = 3
TARGET_SOURCES = 4
MAX_SOURCES = 5
MAX_CANDIDATES = 9
DISCOVERY_BUDGET = 2.8
DISCOVERY_REQUEST_TIMEOUT = 2.35
PAGE_BUDGET = 4.25
PAGE_REQUEST_TIMEOUT = 3.55
TARGET_GRACE = 0.55


def _search_one(engine_url):
    engine, url = engine_url
    try:
        page, _ = r159._get(url, timeout=DISCOVERY_REQUEST_TIMEOUT, limit=360_000)
    except Exception:
        return engine, []
    p = r159._Links()
    try:
        p.feed(page)
    except Exception:
        pass
    vals = []
    for href, anchor in p.links:
        u = r159._unwrap_link(href)
        if u:
            vals.append((u, str(anchor or '')[:180]))
    return engine, vals


def _discover_fast(query, max_urls=MAX_CANDIDATES):
    """Parallel search-engine discovery without waiting for late workers."""
    engine_urls = r159._engine_urls(query)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(engine_urls) or 1))
    futs = {ex.submit(_search_one, item): item[0] for item in engine_urls}
    pending = set(futs)
    batches = {}
    deadline = time.monotonic() + DISCOVERY_BUDGET
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = concurrent.futures.wait(
                pending, timeout=remaining,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                break
            for f in done:
                try:
                    engine, vals = f.result()
                    if vals:
                        batches[engine] = vals
                except Exception:
                    pass
            # Once we have a comfortable candidate pool from at least two engines,
            # there is no reason to wait for a slower discovery request.
            if len(batches) >= 2 and sum(len(v) for v in batches.values()) >= max_urls + 3:
                break
    finally:
        for f in pending:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)

    # Round-robin the engines so the candidate pool is not dominated by one
    # discovery source. Final website independence is enforced by domain below.
    order = ['Google', 'Bing', 'DuckDuckGo']
    queues = {k: list(batches.get(k) or []) for k in order}
    out, seen_urls, seen_hosts = [], set(), set()
    made_progress = True
    while len(out) < max_urls and made_progress:
        made_progress = False
        for engine in order:
            q = queues.get(engine) or []
            while q:
                u, anchor = q.pop(0)
                if u in seen_urls:
                    continue
                try:
                    host = (urllib.parse.urlparse(u).hostname or '').lower().removeprefix('www.')
                except Exception:
                    continue
                if not host or host in seen_hosts:
                    continue
                seen_urls.add(u)
                seen_hosts.add(host)
                out.append({'url': u, 'engine': engine, 'anchor': anchor})
                made_progress = True
                break
            if len(out) >= max_urls:
                break

    # If only one engine returned before the deadline, fill from it rather than
    # returning an artificially small pool.
    if len(out) < max_urls:
        for engine, vals in batches.items():
            for u, anchor in vals:
                if len(out) >= max_urls:
                    break
                if u in seen_urls:
                    continue
                try:
                    host = (urllib.parse.urlparse(u).hostname or '').lower().removeprefix('www.')
                except Exception:
                    continue
                if not host or host in seen_hosts:
                    continue
                seen_urls.add(u); seen_hosts.add(host)
                out.append({'url': u, 'engine': engine, 'anchor': anchor})
    return out


def _fetch_source_fast(item):
    """Fetch one candidate under a short page timeout."""
    try:
        page, final = r159._get(item['url'], timeout=PAGE_REQUEST_TIMEOUT, limit=440_000)
        p = r159._PageText()
        p.feed(page)
        title = re.sub(r'\s+', ' ', ' '.join(p.title)).strip()
        desc = re.sub(r'\s+', ' ', p.description).strip()
        body = re.sub(r'\s+', ' ', ' '.join(p.parts)).strip()
        if len(body) < 220:
            return None
        host = (urllib.parse.urlparse(final).hostname or '').lower().removeprefix('www.')
        if not host:
            return None
        return {
            'url': final,
            'domain': host,
            'title': title[:220] or item.get('anchor', '')[:220] or host,
            'description': desc[:420],
            'excerpt': body[:1900],
            'engine': item.get('engine', 'Web'),
        }
    except Exception:
        return None


def _source_score(s):
    d = str(s.get('domain') or '').lower()
    score = 0
    if d.endswith('.gov') or d.endswith('.edu'):
        score += 8
    if any(x in d for x in ('wikipedia.org', 'wiki.gg', 'steampowered.com', 'counter-strike.net', 'valvesoftware.com')):
        score += 5
    if any(x in d for x in ('reddit.com', 'quora.com', 'medium.com', 'fandom.com')):
        score -= 2
    # Prefer pages with a real title/description because they are less likely to
    # be block/interstitial pages even when body length passed the threshold.
    if s.get('title'):
        score += 1
    if s.get('description'):
        score += 1
    return score


def _research_fast(query):
    """Return 3–5 distinct useful sites without waiting for stragglers."""
    query = r159._clean_query(query)
    if not query:
        return []
    key = query.lower()
    now = time.time()
    with r159._CACHE_LOCK:
        cached = r159._CACHE.get(key)
        if cached and now - cached[0] < r159._CACHE_TTL:
            return cached[1]

    candidates = _discover_fast(query)
    if not candidates:
        with r159._CACHE_LOCK:
            r159._CACHE[key] = (now, [])
        return []

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(candidates)))
    futs = {ex.submit(_fetch_source_fast, x): x for x in candidates}
    pending = set(futs)
    results = []
    seen_domains = set()
    deadline = time.monotonic() + PAGE_BUDGET
    target_reached_at = None

    try:
        while pending and len(results) < MAX_SOURCES:
            now_mono = time.monotonic()
            hard_remaining = deadline - now_mono
            if hard_remaining <= 0:
                break

            # Once four independent sites are already in hand, allow only a tiny
            # grace period for an already-near-complete fifth source.
            if len(results) >= TARGET_SOURCES:
                if target_reached_at is None:
                    target_reached_at = now_mono
                grace_remaining = TARGET_GRACE - (now_mono - target_reached_at)
                if grace_remaining <= 0:
                    break
                timeout = min(hard_remaining, grace_remaining)
            else:
                timeout = hard_remaining

            done, pending = concurrent.futures.wait(
                pending, timeout=timeout,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                break
            for f in done:
                try:
                    src = f.result()
                except Exception:
                    src = None
                if not src:
                    continue
                domain = str(src.get('domain') or '').lower()
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)
                results.append(src)
                if len(results) >= MAX_SOURCES:
                    break

            if len(results) >= TARGET_SOURCES and target_reached_at is None:
                target_reached_at = time.monotonic()

            # If three sources are available but the fourth is unusually slow,
            # we still prefer a fast answer over waiting out the full page budget.
            if len(results) >= MIN_SOURCES and target_reached_at is None:
                elapsed = PAGE_BUDGET - max(0.0, deadline - time.monotonic())
                if elapsed >= 3.15:
                    break
    finally:
        for f in pending:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)

    results.sort(key=_source_score, reverse=True)
    results = results[:MAX_SOURCES]
    with r159._CACHE_LOCK:
        r159._CACHE[key] = (now, results)
    return results


# 1.5.9's POST handler resolves the module-global _research function at call
# time, so replacing that function accelerates both normal chat and factual
# artifact research without altering any request routing or UI behavior.
r159._research = _research_fast


def _patch_index():
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        marker = 'ACE161_FAST_RESEARCH'
        if marker in s:
            return
        s = s.replace('Current version: v1.6.0', 'Current version: v1.6.1')
        p.write_text(s + '\n<!--ACE161_FAST_RESEARCH-->\n', encoding='utf-8')
    except Exception:
        pass


_patch_index()

if __name__ == '__main__':
    ace.main()
