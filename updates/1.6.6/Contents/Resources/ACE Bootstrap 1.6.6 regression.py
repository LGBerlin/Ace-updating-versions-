#!/usr/bin/env python3
"""A.C.E. 1.6.6 — artifact regression repair + preserved fast local research.

This release deliberately loads the proven 1.6.4 SearXNG research runtime rather
than the 1.6.5 Python self-installer. The user's Docker SearXNG at 127.0.0.1:8888
is now the first, direct research endpoint with no per-question readiness probe.

Poster generation/preview/editing is reasserted independently through a narrow
artifact guard, and Open Design is started headlessly when its sidecar is absent.
No chat, voice, theme, Stop, source-recall or presentation behavior is replaced.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.4.py'
GUARD = H / 'ACE Artifact Guard 1.6.6.py'

spec = importlib.util.spec_from_file_location('ace_base_164_for_166', str(BASE))
b164 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b164)
ace = b164.ace
r159 = b164.r159

# Direct local SearXNG path. Do not import/start the 1.6.5 pip-based manager.
LOCAL_SEARXNG = 'http://127.0.0.1:8888'
b164.SEARCH_TIMEOUT = 2.2
b164.SEARX_TOTAL_BUDGET = 4.0
b164._PUBLIC_SEARXNG = ('https://searx.be',)
_original_configured = b164._configured_url


def _candidate_instances_166():
    # Docker/local SearXNG first, directly. No /config probe and no install path.
    out = [LOCAL_SEARXNG]
    try:
        configured = (_original_configured() or '').rstrip('/')
    except Exception:
        configured = ''
    if configured and configured not in out:
        out.append(configured)
    for url in b164._PUBLIC_SEARXNG:
        if url not in out:
            out.append(url)
    return out


b164._candidate_instances = _candidate_instances_166

# Restore/guard poster design + Preview/Edit independently of the research layer.
gspec = importlib.util.spec_from_file_location('ace_artifact_guard_166', str(GUARD))
guard = importlib.util.module_from_spec(gspec)
gspec.loader.exec_module(guard)
guard.install_backend(ace)
guard.patch_frontend(H)

ace.VERSION = '1.6.6'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.6'
except Exception:
    pass

if __name__ == '__main__':
    ace.main()
