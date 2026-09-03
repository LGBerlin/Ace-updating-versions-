#!/usr/bin/env python3
"""A.C.E. 1.6.10 — stabilization/integration rebuild.

Active runtime is deliberately reset to the proven 1.6.4 line.  The failed
1.6.7–1.6.9 poster timing/speed wrappers are not imported.  Two isolated modules
are then installed together:
  1) grounded local-Docker SearXNG research with opened-page evidence;
  2) deterministic local poster generation with unique Preview/PPTX outputs.

Normal chat, Qwen, Pocket TTS, forest/lime theme, Stop, source recall and the
existing non-poster artifact paths remain inherited from the 1.6.4 chain.
In-app poster Edit is intentionally deferred to a later release.
"""
from pathlib import Path
import importlib.util
import re

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.4.py'
GROUND = H / 'ACE Grounded Research 1.6.10.py'
POSTER = H / 'ACE Local Poster 1.6.10.py'

spec = importlib.util.spec_from_file_location('ace_base_164_for_1610', str(BASE))
b164 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b164)
ace = b164.ace

rspec = importlib.util.spec_from_file_location('ace_grounded_1610', str(GROUND))
grounded = importlib.util.module_from_spec(rspec)
rspec.loader.exec_module(grounded)
research = grounded.install(b164)

pspec = importlib.util.spec_from_file_location('ace_local_poster_1610', str(POSTER))
poster = importlib.util.module_from_spec(pspec)
pspec.loader.exec_module(poster)
poster.install(ace, H, research=research)

ace.VERSION = '1.6.10'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.10'
except Exception:
    pass

try:
    p = H / 'index.html'
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.10', s, count=1)
    if '<!--ACE1610_INTEGRATION-->' not in s:
        s += '\n<!--ACE1610_INTEGRATION-->\n'
    p.write_text(s, encoding='utf-8')
except Exception:
    pass

if __name__ == '__main__':
    ace.main()
