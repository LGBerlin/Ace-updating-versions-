#!/usr/bin/env python3
"""A.C.E. 1.6.0 — forest/lime color-system refresh only.

Loads the proven A.C.E. 1.5.9 runtime unchanged. On first launch, this release
rewrites color values inside the existing app.css declarations in place. It does
not add an overlay stylesheet, replace the UI shell, move controls, or alter any
button/event-handler logic.
"""
from pathlib import Path
import colorsys
import importlib.util
import re

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

MARKER = 'ACE160_THEME'
PALETTE = {
    'base': '#0E1A08',
    'surface': '#132C0A',
    'surface_alt': '#0E2308',
    'border': '#2D4A22',
    'accent': '#6FAE42',
    'accent_soft': '#85B764',
    'text': '#E7E2D3',
    'muted': '#A5BE88',
    'dark_text': '#0E1A08',
}
_TARGET_RGB = {
    (14, 26, 8), (19, 44, 10), (14, 35, 8), (45, 74, 34),
    (111, 174, 66), (133, 183, 100), (231, 226, 211),
    (165, 190, 136),
}

_HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')
_RGB = re.compile(
    r'rgba?\(\s*([0-9.]+%?)\s*,\s*([0-9.]+%?)\s*,\s*([0-9.]+%?)'
    r'(?:\s*,\s*([0-9.]+%?))?\s*\)',
    re.I,
)
_VAR = re.compile(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;}]+)')


def _hex_to_rgba(token):
    h = token[1:]
    if len(h) == 3:
        r, g, b = (int(c * 2, 16) for c in h)
        return r, g, b, None
    if len(h) == 4:
        r, g, b, a = (int(c * 2, 16) for c in h)
        return r, g, b, a / 255.0
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), None
    if len(h) == 8:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16) / 255.0
    return None


def _rgba_hex(rgb, alpha=None):
    r, g, b = [max(0, min(255, int(round(x)))) for x in rgb]
    if alpha is None:
        return '#%02X%02X%02X' % (r, g, b)
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return '#%02X%02X%02X%02X' % (r, g, b, a)


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _map_rgb(r, g, b):
    rgb = (int(r), int(g), int(b))
    if rgb in _TARGET_RGB:
        return rgb
    rn, gn, bn = [x / 255.0 for x in rgb]
    h, l, s = colorsys.rgb_to_hls(rn, gn, bn)
    deg = h * 360.0

    # Preserve semantic danger/warning colors so Stop/errors remain immediately legible.
    if s >= 0.34 and l >= 0.18 and (deg >= 330 or deg <= 55):
        return rgb

    base = (14, 26, 8)
    surface = (19, 44, 10)
    border = (45, 74, 34)
    accent = (111, 174, 66)
    accent_soft = (133, 183, 100)
    text = (231, 226, 211)
    muted = (165, 190, 136)

    # Very dark UI colors become the reference forest backgrounds.
    if l <= 0.085:
        t = max(0.0, min(1.0, (l - 0.025) / 0.06))
        return tuple(round(x) for x in _mix(base, surface, t))
    if l <= 0.18:
        t = max(0.0, min(1.0, (l - 0.085) / 0.095))
        return tuple(round(x) for x in _mix(surface, border, t))

    # Existing cyan/blue/green accents become the reference leaf/lime accent family.
    if s >= 0.25 and 65 <= deg <= 285:
        if l >= 0.52:
            return accent_soft
        if l >= 0.26:
            return accent
        return border

    # Light neutral/cool text becomes warm off-white; mid neutrals become muted green.
    if l >= 0.76:
        if s <= 0.32:
            t = max(0.0, min(1.0, (l - 0.76) / 0.24))
            hi = (247, 244, 235)
            return tuple(round(x) for x in _mix(text, hi, t))
        return text
    if l >= 0.42:
        t = max(0.0, min(1.0, (l - 0.42) / 0.34))
        return tuple(round(x) for x in _mix((116, 145, 93), muted, t))
    if l >= 0.22:
        t = max(0.0, min(1.0, (l - 0.22) / 0.20))
        return tuple(round(x) for x in _mix(border, (99, 123, 79), t))

    return rgb


def _rgb_part(value):
    value = value.strip()
    if value.endswith('%'):
        return max(0, min(255, round(float(value[:-1]) * 2.55)))
    return max(0, min(255, round(float(value))))


def _alpha_part(value):
    if value is None:
        return None
    value = value.strip()
    if value.endswith('%'):
        return max(0.0, min(1.0, float(value[:-1]) / 100.0))
    return max(0.0, min(1.0, float(value)))


def _semantic_color(var_name):
    n = var_name.lower()
    if any(x in n for x in ('danger', 'error', 'warning', 'warn', 'stop', 'red')):
        return None
    if any(x in n for x in ('cyan2', 'accent2', 'accent-soft', 'secondary-accent')):
        return PALETTE['accent_soft']
    if any(x in n for x in ('cyan', 'accent', 'primary', 'highlight', 'active')):
        return PALETTE['accent']
    if any(x in n for x in ('muted', 'subtext', 'secondary-text', 'dim')):
        return PALETTE['muted']
    if any(x in n for x in ('text', 'foreground', 'fg')):
        return PALETTE['text']
    if any(x in n for x in ('line', 'border', 'stroke', 'divider')):
        return PALETTE['border']
    if any(x in n for x in ('raised', 'panel', 'surface', 'card', 'elevated')):
        return PALETTE['surface']
    if any(x in n for x in ('background', 'backdrop', 'canvas', 'base', 'page', 'bg')):
        return PALETTE['base']
    return None


def _rewrite_value(value):
    def hx(m):
        parsed = _hex_to_rgba(m.group(0))
        if not parsed:
            return m.group(0)
        r, g, b, a = parsed
        return _rgba_hex(_map_rgb(r, g, b), a)

    value = _HEX.sub(hx, value)

    def rg(m):
        try:
            r, g, b = (_rgb_part(m.group(i)) for i in (1, 2, 3))
            a = _alpha_part(m.group(4))
            nr, ng, nb = _map_rgb(r, g, b)
            if a is None:
                return f'rgb({nr}, {ng}, {nb})'
            return f'rgba({nr}, {ng}, {nb}, {a:.3f}'.rstrip('0').rstrip('.') + ')'
        except Exception:
            return m.group(0)

    return _RGB.sub(rg, value)


def _rewrite_declarations(block):
    # First set semantic custom properties to the exact reference palette.
    def var_repl(m):
        name, value = m.group(1), m.group(2)
        chosen = _semantic_color(name)
        if chosen and re.fullmatch(r'\s*(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\s*', value):
            return f'{name}: {chosen}'
        return f'{name}: {_rewrite_value(value)}'

    block = _VAR.sub(var_repl, block)
    return _rewrite_value(block)


def _leaf_blocks(css):
    stack = []
    pairs = []
    child = []
    for i, ch in enumerate(css):
        if ch == '{':
            if stack:
                child[-1] = True
            stack.append(i)
            child.append(False)
        elif ch == '}' and stack:
            start = stack.pop()
            had_child = child.pop()
            if not had_child:
                pairs.append((start, i))
    return pairs


def _theme_css(css):
    if MARKER in css:
        return css
    out = css
    # Work backwards so character offsets stay valid.
    for start, end in sorted(_leaf_blocks(css), reverse=True):
        body = out[start + 1:end]
        out = out[:start + 1] + _rewrite_declarations(body) + out[end:]
    return out + '\n/* ACE160_THEME — direct color values rewritten in place; no overlay rules. */\n'


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


def _idx(s):
    s = re.sub(r'app\.css\?v=[^"\']+', 'app.css?v=160-forest', s, count=1)
    s = re.sub(r'app\.js\?v=[^"\']+', 'app.js?v=160-forest', s, count=1)
    s = s.replace('Current version: v1.5.9', 'Current version: v1.6.0')
    return s + '\n<!--ACE160_THEME-->\n'


_patch_file(H / 'app.css', MARKER, _theme_css)
_patch_file(H / 'index.html', 'ACE160_THEME', _idx)

if __name__ == '__main__':
    ace.main()
