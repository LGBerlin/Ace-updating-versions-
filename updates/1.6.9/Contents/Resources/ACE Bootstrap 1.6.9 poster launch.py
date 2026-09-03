#!/usr/bin/env python3
"""A.C.E. 1.6.9 — apply poster speed profile at the actual OpenDesign launch.

Loads the measured/regression-safe 1.6.7 runtime, then installs the narrow
streaming OpenDesign POST /api/chat interceptor from ACE OpenDesign Speed 1.6.9.py.
This supersedes the ineffective 1.6.8 JSON-helper wrapper while preserving the
1.6.7 timer and the 1.6.6 search + poster Preview/Edit regression base.
"""
from pathlib import Path
import importlib.util
import re

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.7.py'
SPEED = H / 'ACE OpenDesign Speed 1.6.9.py'

spec = importlib.util.spec_from_file_location('ace_base_167_for_169', str(BASE))
b167 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b167)
ace = b167.ace

sspec = importlib.util.spec_from_file_location('ace_od_speed_169', str(SPEED))
speed = importlib.util.module_from_spec(sspec)
sspec.loader.exec_module(speed)
speed.install(ace)

ace.VERSION = '1.6.9'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.9'
except Exception:
    pass

try:
    p = H / 'index.html'
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.9', s, count=1)
    if '<!--ACE169_POSTER_LAUNCH-->' not in s:
        s += '\n<!--ACE169_POSTER_LAUNCH-->\n'
    p.write_text(s, encoding='utf-8')
except Exception:
    pass

if __name__ == '__main__':
    ace.main()
