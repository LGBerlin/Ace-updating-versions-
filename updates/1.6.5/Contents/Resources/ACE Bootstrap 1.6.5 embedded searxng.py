#!/usr/bin/env python3
"""A.C.E. 1.6.5 — managed private SearXNG.

Builds directly on 1.6.4. A.C.E. now owns a private SearXNG runtime: on first
launch it is prepared automatically in A.C.E.'s Application Support directory,
then started on 127.0.0.1:8888 whenever A.C.E. runs.

No Docker or separately launched search application is required. 1.6.4's exact
source-memory behavior and emergency fallbacks are preserved.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.4.py'
MANAGER = H / 'ACE SearXNG Manager.py'

spec = importlib.util.spec_from_file_location('ace_base_164', str(BASE))
b164 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b164)
ace = b164.ace
r159 = b164.r159

mspec = importlib.util.spec_from_file_location('ace_managed_searxng', str(MANAGER))
sx = importlib.util.module_from_spec(mspec)
mspec.loader.exec_module(sx)

ace.VERSION = '1.6.5'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.5'
except Exception:
    pass

# Keep SearXNG's own network work tightly bounded. The local service itself
# handles parallel metasearch; A.C.E. performs only one local request.
b164.SEARCH_TIMEOUT = 2.2
b164.SEARX_TOTAL_BUDGET = 3.8

# Public SearXNG is now only an emergency fallback while the managed local
# runtime is unavailable (for example during the one-time first-launch setup).
b164._PUBLIC_SEARXNG = ('https://searx.be',)

_original_configured = b164._configured_url


def _managed_candidates():
    # Once installed, starting the localhost service normally takes only a
    # moment. Never wait for the potentially longer first-time dependency setup
    # inside a chat request; that setup starts in the background at app launch.
    if sx.ensure_started(block=True, timeout=2.4):
        return [sx.LOCAL_URL]

    # Respect an explicit user-configured private instance, if one exists.
    try:
        configured = _original_configured()
    except Exception:
        configured = ''
    if configured and configured.rstrip('/') != sx.LOCAL_URL:
        return [configured.rstrip('/')]

    # Emergency-only public fallback. The managed runtime continues preparing in
    # the background and will take over automatically on the next search.
    return list(b164._PUBLIC_SEARXNG)


b164._candidate_instances = _managed_candidates

# Begin preparing/starting the private service as soon as A.C.E. launches so it
# is normally ready before the first researched question arrives.
sx.ensure_started_async()


def _patch_index():
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        marker = 'ACE165_EMBEDDED_SEARXNG'
        if marker in s:
            return
        s = s.replace('Current version: v1.6.4', 'Current version: v1.6.5')
        p.write_text(s + '\n<!--ACE165_EMBEDDED_SEARXNG-->\n', encoding='utf-8')
    except Exception:
        pass


_patch_index()

if __name__ == '__main__':
    ace.main()
