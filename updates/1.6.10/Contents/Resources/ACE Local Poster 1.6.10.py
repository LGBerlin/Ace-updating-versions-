#!/usr/bin/env python3
"""A.C.E. 1.6.10 deterministic local poster engine.

Poster creation no longer waits for OpenDesign/Codex.  A short local Qwen pass
produces a structured brief, then deterministic Python renders a unique SVG
Preview and a native-text/native-shape PowerPoint.  If Qwen is unavailable or
slow, a deterministic fallback still returns a poster instead of hanging.

In-app Edit is intentionally not installed here.  That is a separate follow-up.
"""
from __future__ import annotations

from pathlib import Path
import base64
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

ROOT = Path.home() / 'Library' / 'Application Support' / 'A.C.E' / 'local-posters'
JOBS = {}
LOCK = threading.RLock()
PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

# Portrait poster: 7.5 x 10 inches at 914400 EMU/inch.
SW = 6_858_000
SH = 9_144_000


def _xml(value):
    return html.escape(str(value or ''), quote=True)


def _slug_topic(prompt):
    text = re.sub(r'\s+', ' ', str(prompt or '')).strip()
    text = re.sub(
        r'^(?:please\s+)?(?:can you\s+|could you\s+)?(?:make|create|build|design|generate|produce|prepare)\s+(?:me\s+)?(?:a\s+|an\s+)?poster\s+(?:about|on|for|explaining)?\s*',
        '', text, flags=re.I,
    ).strip(' .?!')
    if not text:
        text = 'Your Idea'
    if len(text) > 64:
        text = text[:61].rstrip() + '…'
    return text


def _fallback_plan(prompt):
    topic = _slug_topic(prompt)
    low = topic.lower()
    if 'hat' in low or 'headwear' in low:
        return {
            'title': 'Hats Belong at School',
            'subtitle': 'Simple rules can respect expression, comfort, and learning at the same time.',
            'points': [
                {'heading': 'Expression matters', 'body': 'Headwear can be part of a student’s style, identity, culture, or everyday self-expression.'},
                {'heading': 'Comfort supports focus', 'body': 'Reasonable clothing choices can help students feel comfortable and ready to concentrate on schoolwork.'},
                {'heading': 'Use fair, practical rules', 'body': 'Allow hats unless they create a genuine safety, identification, or classroom-disruption problem.'},
            ],
            'footer': 'Respect students. Keep the rules clear. Focus on learning.',
        }
    title = topic[:1].upper() + topic[1:]
    return {
        'title': title,
        'subtitle': 'A clear, practical way to understand the idea and why it matters.',
        'points': [
            {'heading': 'The core idea', 'body': f'Put the main point about {topic} first, in plain language that is easy to understand.'},
            {'heading': 'Why it matters', 'body': 'Connect the idea to people, choices, or outcomes rather than filling the poster with extra detail.'},
            {'heading': 'What to remember', 'body': 'End with one useful takeaway that a reader can understand at a glance.'},
        ],
        'footer': 'Clear message. Strong hierarchy. Easy to scan.',
    }


def _needs_research(prompt):
    return bool(re.search(
        r'\b(latest|current|today|now|history|historical|statistics?|stats?|data|evidence|facts?|numbers?|price|cost|when|who|research|verify)\b',
        str(prompt or ''), re.I,
    ))


def _planner_evidence(sources):
    if not sources:
        return ''
    lines = ['Verified evidence; use only what appears here for concrete factual claims:']
    for i, s in enumerate(sources[:4], 1):
        lines.append(f"S{i} {s.get('domain')} — {str(s.get('excerpt') or '')[:560]}")
    return '\n'.join(lines)[:2600]


def _normalize_plan(raw, prompt):
    fallback = _fallback_plan(prompt)
    if not isinstance(raw, dict):
        return fallback
    title = re.sub(r'\s+', ' ', str(raw.get('title') or '')).strip()[:72]
    subtitle = re.sub(r'\s+', ' ', str(raw.get('subtitle') or '')).strip()[:170]
    footer = re.sub(r'\s+', ' ', str(raw.get('footer') or '')).strip()[:120]
    points = []
    for p in raw.get('points') or []:
        if not isinstance(p, dict):
            continue
        heading = re.sub(r'\s+', ' ', str(p.get('heading') or '')).strip()[:48]
        body = re.sub(r'\s+', ' ', str(p.get('body') or '')).strip()[:230]
        if heading and body:
            points.append({'heading': heading, 'body': body})
        if len(points) >= 3:
            break
    if not title:
        title = fallback['title']
    if not subtitle:
        subtitle = fallback['subtitle']
    while len(points) < 3:
        points.append(fallback['points'][len(points)])
    if not footer:
        footer = fallback['footer']
    return {'title': title, 'subtitle': subtitle, 'points': points[:3], 'footer': footer}


def _parse_json_object(text):
    text = str(text or '').strip()
    try:
        val = json.loads(text)
        if isinstance(val, dict):
            return val
    except Exception:
        pass
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start:end + 1])
            if isinstance(val, dict):
                return val
        except Exception:
            pass
    return None


def _qwen_plan(ace, prompt, evidence=''):
    model = ''
    try:
        model = ace.choose_model(ace.ollama_models()) or ''
    except Exception:
        model = ''
    if not model:
        return None
    instruction = (
        '/no_think\n'
        'Create a concise poster content brief. Return ONLY valid JSON with exactly this schema: '
        '{"title":"...","subtitle":"...","points":[{"heading":"...","body":"..."},{"heading":"...","body":"..."},{"heading":"...","body":"..."}],"footer":"..."}. '
        'Use short, human wording. No filler, no fake statistics, no invented quotations, no citations inside the poster. '
        'Title max 8 words. Subtitle max 22 words. Each heading max 5 words. Each body max 30 words. '
        'If evidence is supplied, concrete factual claims must come only from that evidence.\n\n'
        f'USER REQUEST: {prompt}\n'
    )
    if evidence:
        instruction += '\n' + evidence
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are A.C.E. poster planner. Output compact valid JSON only.'},
            {'role': 'user', 'content': instruction},
        ],
        'stream': False,
        'options': {'temperature': 0.22, 'num_predict': 520},
    }
    req = urllib.request.Request(
        'http://127.0.0.1:11434/api/chat',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=22) as response:
            data = json.loads(response.read(1_000_000).decode('utf-8', errors='replace'))
        content = ((data.get('message') or {}).get('content') or '') if isinstance(data, dict) else ''
        return _parse_json_object(content)
    except Exception:
        return None


def build_plan(ace, prompt, research=None):
    sources = []
    if research and _needs_research(prompt):
        try:
            sources = list(research(prompt) or [])
        except Exception:
            sources = []
    evidence = _planner_evidence(sources)
    raw = _qwen_plan(ace, prompt, evidence)
    return _normalize_plan(raw, prompt), sources


def _wrap(text, chars):
    words = str(text or '').split()
    lines = []
    line = ''
    for word in words:
        test = (line + ' ' + word).strip()
        if line and len(test) > chars:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def _svg_text(x, y, lines, size, fill, weight=400, line_gap=1.25, anchor='start'):
    spans = []
    for i, line in enumerate(lines):
        dy = '0' if i == 0 else f'{size * line_gap:.1f}'
        spans.append(f'<tspan x="{x}" dy="{dy}">{_xml(line)}</tspan>')
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}">' + ''.join(spans) + '</text>'


def build_svg(plan):
    title_lines = _wrap(plan['title'], 24)[:3]
    subtitle_lines = _wrap(plan['subtitle'], 55)[:3]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1200" viewBox="0 0 900 1200">',
        '<rect width="900" height="1200" fill="#0E1A08"/>',
        '<rect x="68" y="64" width="132" height="12" rx="6" fill="#85B764"/>',
        _svg_text(68, 142, title_lines, 55, '#F3EFE3', 800, 1.05),
    ]
    sub_y = 142 + len(title_lines) * 58 + 12
    out.append(_svg_text(68, sub_y, subtitle_lines, 21, '#AFCB92', 400, 1.22))
    card_y0 = max(330, sub_y + len(subtitle_lines) * 28 + 42)
    for i, point in enumerate(plan['points'][:3], 1):
        y = card_y0 + (i - 1) * 205
        out.append(f'<rect x="68" y="{y}" width="764" height="174" rx="26" fill="#132C0A" stroke="#2D4A22" stroke-width="2"/>')
        out.append(f'<circle cx="117" cy="{y + 49}" r="25" fill="#6FAE42"/>')
        out.append(_svg_text(117, y + 57, [str(i)], 23, '#0E1A08', 800, 1.0, 'middle'))
        out.append(_svg_text(162, y + 55, _wrap(point['heading'], 32)[:2], 25, '#F3EFE3', 700, 1.0))
        out.append(_svg_text(162, y + 98, _wrap(point['body'], 62)[:3], 17, '#BFD4AA', 400, 1.32))
    out.append('<line x1="68" y1="1110" x2="832" y2="1110" stroke="#2D4A22" stroke-width="2"/>')
    out.append(_svg_text(68, 1153, _wrap(plan['footer'], 78)[:2], 15, '#85B764', 600, 1.15))
    out.append('</svg>')
    return ''.join(out)


def _sp(shape_id, name, x, y, w, h, fill, text='', font_size=14, color='E7E2D3', bold=False, radius=False, valign='ctr'):
    geom = 'roundRect' if radius else 'rect'
    txt = ''
    if text:
        paras = []
        for line in str(text).split('\n'):
            paras.append(
                '<a:p><a:pPr algn="l"/><a:r><a:rPr lang="en-US" sz="%d" b="%d">'
                '<a:solidFill><a:srgbClr val="%s"/></a:solidFill><a:latin typeface="Arial"/></a:rPr>'
                '<a:t>%s</a:t></a:r><a:endParaRPr lang="en-US" sz="%d"/></a:p>'
                % (int(font_size * 100), 1 if bold else 0, color, _xml(line), int(font_size * 100))
            )
        txt = '<p:txBody><a:bodyPr wrap="square" anchor="%s" lIns="90000" rIns="90000" tIns="45000" bIns="45000"/><a:lstStyle/>%s</p:txBody>' % (valign, ''.join(paras))
    else:
        txt = '<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>'
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="%s"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
        '<a:ln><a:noFill/></a:ln></p:spPr>%s</p:sp>'
        % (shape_id, _xml(name), x, y, w, h, geom, fill, txt)
    )


def _slide_xml(plan):
    shapes = []
    sid = 2
    shapes.append(_sp(sid, 'Background', 0, 0, SW, SH, '0E1A08')); sid += 1
    shapes.append(_sp(sid, 'Accent', 520_000, 480_000, 1_000_000, 95_000, '85B764', radius=True)); sid += 1
    shapes.append(_sp(sid, 'Title', 520_000, 730_000, 5_820_000, 1_300_000, '0E1A08', plan['title'], 28, 'F3EFE3', True, False, 't')); sid += 1
    shapes.append(_sp(sid, 'Subtitle', 520_000, 1_890_000, 5_820_000, 760_000, '0E1A08', plan['subtitle'], 14, 'AFCB92', False, False, 't')); sid += 1
    ys = [2_780_000, 4_470_000, 6_160_000]
    for i, (point, y) in enumerate(zip(plan['points'][:3], ys), 1):
        shapes.append(_sp(sid, f'Card {i}', 520_000, y, 5_820_000, 1_390_000, '132C0A', radius=True)); sid += 1
        shapes.append(_sp(sid, f'Number {i}', 720_000, y + 220_000, 520_000, 520_000, '6FAE42', str(i), 18, '0E1A08', True, True)); sid += 1
        shapes.append(_sp(sid, f'Heading {i}', 1_350_000, y + 180_000, 4_560_000, 420_000, '132C0A', point['heading'], 18, 'F3EFE3', True, False, 't')); sid += 1
        shapes.append(_sp(sid, f'Body {i}', 1_350_000, y + 590_000, 4_560_000, 650_000, '132C0A', point['body'], 12, 'BFD4AA', False, False, 't')); sid += 1
    shapes.append(_sp(sid, 'Footer', 520_000, 8_530_000, 5_820_000, 350_000, '0E1A08', plan['footer'], 10, '85B764', True, False, 't'))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + ''.join(shapes) +
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


def build_pptx(plan, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    parts = {
        '[Content_Types].xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/><Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/><Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        '_rels/.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        'docProps/app.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>A.C.E.</Application><PresentationFormat>Custom</PresentationFormat><Slides>1</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips><ScaleCrop>false</ScaleCrop><Company>A.C.E.</Company><AppVersion>1.6.10</AppVersion></Properties>''',
        'docProps/core.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{_xml(plan['title'])}</dc:title><dc:creator>A.C.E.</dc:creator><cp:lastModifiedBy>A.C.E.</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>''',
        'ppt/presentation.xml': f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst><p:sldSz cx="{SW}" cy="{SH}" type="custom"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle/></p:presentation>''',
        'ppt/_rels/presentation.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/><Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/></Relationships>''',
        'ppt/presProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>''',
        'ppt/viewProps.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr/><p:slideViewPr/><p:notesTextViewPr><a:cViewPr/></p:notesTextViewPr><p:gridSpacing cx="72008" cy="72008"/></p:viewPr>''',
        'ppt/tableStyles.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>''',
        'ppt/theme/theme1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="A.C.E. Theme"><a:themeElements><a:clrScheme name="A.C.E."><a:dk1><a:srgbClr val="0E1A08"/></a:dk1><a:lt1><a:srgbClr val="F3EFE3"/></a:lt1><a:dk2><a:srgbClr val="132C0A"/></a:dk2><a:lt2><a:srgbClr val="BFD4AA"/></a:lt2><a:accent1><a:srgbClr val="6FAE42"/></a:accent1><a:accent2><a:srgbClr val="85B764"/></a:accent2><a:accent3><a:srgbClr val="2D4A22"/></a:accent3><a:accent4><a:srgbClr val="AFCB92"/></a:accent4><a:accent5><a:srgbClr val="7E9C66"/></a:accent5><a:accent6><a:srgbClr val="D8D1BE"/></a:accent6><a:hlink><a:srgbClr val="6FAE42"/></a:hlink><a:folHlink><a:srgbClr val="85B764"/></a:folHlink></a:clrScheme><a:fontScheme name="A.C.E."><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="A.C.E."><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>''',
        'ppt/slideMasters/slideMaster1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>''',
        'ppt/slideMasters/_rels/slideMaster1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>''',
        'ppt/slideLayouts/slideLayout1.xml': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>''',
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>''',
        'ppt/slides/slide1.xml': _slide_xml(plan),
        'ppt/slides/_rels/slide1.xml.rels': '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>''',
    }
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data.encode('utf-8'))
    return path


def create_artifact(ace, prompt, research=None, root=None):
    started = time.perf_counter()
    plan, sources = build_plan(ace, prompt, research=research)
    job_id = 'lp_' + uuid.uuid4().hex[:16]
    base = Path(root or ROOT) / job_id
    base.mkdir(parents=True, exist_ok=True)
    svg_name = f'ACE Poster {job_id[-8:]}.svg'
    pptx_name = f'ACE Poster {job_id[-8:]}.pptx'
    svg_path = base / svg_name
    pptx_path = base / pptx_name
    svg = build_svg(plan)
    svg_path.write_text(svg, encoding='utf-8')
    build_pptx(plan, pptx_path)
    preview = 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')
    job = {
        'job_id': job_id,
        'kind': 'poster',
        'status': 'done',
        'stage': 'Ready',
        'local_poster': True,
        'title': plan['title'],
        'preview': preview,
        'preview_path': str(svg_path),
        'pptx_path': str(pptx_path),
        'download_url': '/api/local-poster/download?job=' + urllib.parse.quote(job_id),
        'seconds': round(time.perf_counter() - started, 3),
        'source_count': len(sources),
    }
    with LOCK:
        JOBS[job_id] = job
    return job


def install(ace, H, research=None):
    """Install backend routes and the local-poster frontend interception."""
    post0 = ace.H.do_POST
    get0 = ace.H.do_GET

    def POST(self):
        try:
            path = ace.urllib.parse.urlparse(self.path).path
        except Exception:
            path = self.path
        if path == '/api/local-poster/start':
            try:
                body = ace.parse_json(self)
                prompt = str((body or {}).get('prompt') or '').strip()
                if not prompt:
                    self.json_out({'error': 'Poster prompt is empty.'}, 400)
                    return
                job = create_artifact(ace, prompt, research=research)
                self.json_out({'ok': True, 'job': job})
            except Exception as e:
                self.json_out({'error': 'Local poster failed: ' + str(e)}, 500)
            return
        return post0(self)

    def GET(self):
        try:
            parsed = ace.urllib.parse.urlparse(self.path)
        except Exception:
            return get0(self)
        if parsed.path == '/api/local-poster/download':
            q = ace.urllib.parse.parse_qs(parsed.query)
            job_id = str((q.get('job') or [''])[0])
            with LOCK:
                job = JOBS.get(job_id)
            p = Path(str((job or {}).get('pptx_path') or ''))
            if not job or not p.is_file():
                self.send_error(404, 'Poster not found')
                return
            data = p.read_bytes()
            name = p.name.replace('"', '')
            self.send_response(200)
            self.send_header('Content-Type', PPTX_MIME)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Content-Disposition', f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(data)
            return
        return get0(self)

    ace.H.do_POST = POST
    ace.H.do_GET = GET
    patch_frontend(Path(H))


def patch_frontend(H):
    marker = 'ACE1610_LOCAL_POSTER'
    js = r'''
(function(){
  if(window.__ACE1610_LOCAL_POSTER__)return;window.__ACE1610_LOCAL_POSTER__=1;
  const q=id=>document.getElementById(id);
  function posterIntent(t){
    t=String(t||'').toLowerCase().replace(/\s+/g,' ').trim();
    if(!/\bposter\b/.test(t))return false;
    if(/\b(?:explain|tell me about|talk about|discuss|why did|what is|how does)\b/.test(t)&&!/\b(?:make|create|build|design|generate|produce|prepare)\b/.test(t))return false;
    return /\b(?:make|create|build|design|generate|produce|prepare)\b[\s\S]{0,90}\bposter\b|\bposter\b[\s\S]{0,55}\b(?:make|create|build|design|generate|produce|prepare)\b/.test(t)||/\b(?:i need|i want|give me|can you|could you|please)\b[\s\S]{0,80}\bposter\b/.test(t);
  }
  function otherArtifact(t){return /\b(?:presentation|powerpoint|power point|slides?|slide deck|document|report|infographic|flyer|brochure)\b/i.test(String(t||''));}
  function root(){return q('artifactStudio')||document.querySelector('.artifact-studio');}
  function status(text){
    const r=root();if(!r)return;
    const e=q('studioStatus')||q('studioStage')||r.querySelector('.studio-status,.studio-stage,[data-studio-stage]');
    if(e)e.textContent=text;
  }
  function clearLocalPreview(){const e=q('ace1610LocalPosterPreview');if(e)e.remove();}
  function showStudio(){const r=root();if(!r)return null;r.classList.remove('hidden');const cw=q('chatWorkspace');if(cw)cw.classList.add('with-studio');return r;}
  function renderPreview(data){
    const r=showStudio();if(!r)return;
    clearLocalPreview();
    const box=document.createElement('div');box.id='ace1610LocalPosterPreview';box.style.cssText='position:absolute;inset:58px 12px 12px;display:flex;align-items:center;justify-content:center;z-index:4;pointer-events:none;background:#0E1A08;border-radius:12px;overflow:hidden;';
    const im=document.createElement('img');im.alt='A.C.E. poster preview';im.src=data;im.style.cssText='display:block;max-width:100%;max-height:100%;object-fit:contain;box-shadow:0 12px 36px rgba(0,0,0,.38);';box.appendChild(im);r.appendChild(box);
    const empty=q('studioEmpty');if(empty)empty.classList.add('hidden');
  }
  function configureToolbar(job){
    const dl=q('studioDownload');if(dl){dl.href=job.download_url;dl.classList.remove('disabled');dl.removeAttribute('aria-disabled');dl.dataset.aceLocalPoster='1';dl.setAttribute('download','');}
    const ed=q('studioEdit');if(ed){ed.dataset.aceLocalPoster='1';ed.style.display='none';}
    const old=q('ace167PosterTimer');if(old)old.style.display='none';
  }
  function restoreForOtherArtifact(){
    const ed=q('studioEdit');if(ed&&ed.dataset.aceLocalPoster){delete ed.dataset.aceLocalPoster;ed.style.display='';}
    const dl=q('studioDownload');if(dl&&dl.dataset.aceLocalPoster){delete dl.dataset.aceLocalPoster;}
    clearLocalPreview();
  }
  async function localPoster(text){
    const input=q('chatInput');if(input)input.value='';
    try{
      if(typeof messages!=='undefined'&&Array.isArray(messages)){messages.push({role:'user',content:text});if(typeof save==='function')save();if(typeof renderChat==='function')renderChat();}
    }catch(_){}
    try{if(typeof busy!=='undefined')busy=true;}catch(_){}const sb=q('sendBtn');if(sb)sb.disabled=true;
    showStudio();status('Building poster locally…');clearLocalPreview();
    const ed=q('studioEdit');if(ed)ed.style.display='none';
    try{
      const res=await fetch('/api/local-poster/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:text})});
      const data=await res.json();if(!res.ok||data.error||!data.job)throw Error(data.error||'Poster generation failed.');
      try{if(typeof studioPollTimer!=='undefined'&&studioPollTimer){clearTimeout(studioPollTimer);studioPollTimer=null;}}catch(_){}
      try{if(typeof studioJob!=='undefined')studioJob=data.job;}catch(_){}
      renderPreview(data.job.preview);configureToolbar(data.job);status('Ready');
      try{if(typeof messages!=='undefined'&&Array.isArray(messages)){messages.push({role:'assistant',content:'Poster ready.'});if(typeof save==='function')save();if(typeof renderChat==='function')renderChat();}}catch(_){}
    }catch(e){status('Poster could not be created.');try{if(typeof messages!=='undefined'&&Array.isArray(messages)){messages.push({role:'assistant',content:'I could not create that poster: '+e.message});if(typeof save==='function')save();if(typeof renderChat==='function')renderChat();}}catch(_){}
    finally{try{if(typeof busy!=='undefined')busy=false;}catch(_){}if(sb)sb.disabled=false;try{if(typeof updateStopControl==='function')updateStopControl();}catch(_){}}
  }
  function install(){
    try{
      if(typeof send!=='function'||send.__ace1610LocalPoster)return;
      const original=send;
      const wrapped=async function(){
        let text='';try{text=String(arguments[0]||((q('chatInput')||{}).value)||'').trim();}catch(_){}
        if(posterIntent(text)){return localPoster(text);}
        if(otherArtifact(text))restoreForOtherArtifact();
        return original.apply(this,arguments);
      };
      wrapped.__ace1610LocalPoster=1;wrapped.__aceOriginal=original;send=wrapped;
    }catch(_){}
  }
  install();setTimeout(install,0);setTimeout(install,500);
  const style=document.createElement('style');style.textContent='#ace167PosterTimer{display:none!important}';document.head.appendChild(style);
})();
// ACE1610_LOCAL_POSTER
'''
    try:
        p = H / 'app.js'
        s = p.read_text(encoding='utf-8')
        if marker not in s:
            p.write_text(s + '\n' + js + '\n', encoding='utf-8')
    except Exception:
        pass
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        s = re.sub(r'app\.js\?v=[^"\']+', 'app.js?v=1610-integrated', s, count=1)
        s = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.10', s, count=1)
        if '<!--ACE1610_LOCAL_POSTER-->' not in s:
            s += '\n<!--ACE1610_LOCAL_POSTER-->\n'
        p.write_text(s, encoding='utf-8')
    except Exception:
        pass
