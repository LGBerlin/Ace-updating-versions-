#!/usr/bin/env python3
"""A.C.E. 1.6.3 — instant researched answers.

Builds on 1.6.2. Keeps the same 3–5 website cross-check, but removes the main
remaining response delay for ordinary researched chat: Qwen thinking mode and
unnecessarily large conversation history.

Artifact generation and complex design work are left unchanged.
"""
from pathlib import Path
import importlib.util
import io
import json
import re
import urllib.parse

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.2.py'

spec = importlib.util.spec_from_file_location('ace_base_162', str(BASE))
b162 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b162)
ace = b162.ace
r159 = b162.r159

ace.VERSION = '1.6.3'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.3'
except Exception:
    pass

# Qwen's supported soft switch. Only routine researched chat uses it; artifact
# generation keeps the previous behavior so design/build quality is not traded away.
_DETAIL = re.compile(r'\b(detailed|detail|comprehensive|in depth|deep dive|thorough|full explanation|step[- ]by[- ]step|long answer)\b', re.I)
_THINK = re.compile(r'/(?:think|no_think)\b', re.I)


def _instant_evidence_block(user_text, sources, artifact=False):
    block = b162._compact_evidence_block(user_text, sources, artifact=artifact)
    if artifact or not sources:
        return block
    # Respect an explicit user think/no-think switch if they supplied one.
    if _THINK.search(str(user_text or '')):
        return block
    if _DETAIL.search(str(user_text or '')):
        answer_rule = 'Give the requested level of detail, but do not narrate hidden reasoning.'
    else:
        answer_rule = 'Answer immediately and directly; default to about 80–180 words unless more is needed for correctness.'
    return block + '\n/no_think\n[ACE163_FAST_RESPONSE INTERNAL] ' + answer_rule + ' [/ACE163_FAST_RESPONSE]'


# 1.5.9 research preflight resolves this global at request time.
r159._evidence_block = _instant_evidence_block


# Long chats can make local-model prefill dominate latency. For ordinary factual
# chat only, keep system instructions plus the most recent conversational turns.
# We do this only when the payload is already large; short chats are untouched.
_HISTORY_TRIGGER_CHARS = 6500
_HISTORY_KEEP_NON_SYSTEM = 8
_CONTEXT_REF = re.compile(
    r'\b(earlier|previous|previously|above|before|we discussed|we talked about|as I said|as you said|that earlier|those earlier)\b',
    re.I,
)
_SKIP_PATH = (
    '/opendesign', '/studio', '/artifact', '/upload', '/download', '/file',
    '/voice', '/tts', '/speech', '/update', '/stop', '/cancel', '/memory',
)


def _last_user(messages):
    for m in reversed(messages or []):
        if isinstance(m, dict) and str(m.get('role', '')).lower() == 'user':
            c = m.get('content')
            if isinstance(c, str):
                return c
    return ''


def _compact_messages(messages):
    if not isinstance(messages, list):
        return messages
    total = sum(len(str(m.get('content') or '')) for m in messages if isinstance(m, dict))
    if total <= _HISTORY_TRIGGER_CHARS:
        return messages
    current = _last_user(messages)
    # Context-reference language means the older conversation may genuinely matter.
    keep_n = 12 if _CONTEXT_REF.search(current) else _HISTORY_KEEP_NON_SYSTEM
    system = [m for m in messages if isinstance(m, dict) and str(m.get('role', '')).lower() == 'system']
    non_system = [m for m in messages if not (isinstance(m, dict) and str(m.get('role', '')).lower() == 'system')]
    kept = non_system[-keep_n:]
    return system + kept


_prev_post = ace.H.do_POST


def _precompact_request(self):
    path = urllib.parse.urlsplit(self.path).path.lower()
    if any(x in path for x in _SKIP_PATH):
        return
    ctype = str(self.headers.get('Content-Type') or '').lower()
    if 'application/json' not in ctype:
        return
    try:
        n = int(self.headers.get('Content-Length') or 0)
    except Exception:
        return
    if n <= 0 or n > 3_000_000:
        return
    raw = self.rfile.read(n)
    new = raw
    try:
        d = json.loads(raw.decode('utf-8'))
        msgs = d.get('messages') if isinstance(d, dict) else None
        if isinstance(msgs, list):
            user_text = _last_user(msgs)
            # Only trim the history for questions that the existing research gate
            # considers factual/research-worthy. Ordinary conversational context is untouched.
            if user_text and r159._should_research(user_text, path):
                d['messages'] = _compact_messages(msgs)
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
        _precompact_request(self)
    except Exception:
        pass
    return _prev_post(self)


ace.H.do_POST = POST


def _patch_index():
    try:
        p = H / 'index.html'
        s = p.read_text(encoding='utf-8')
        marker = 'ACE163_INSTANT_RESEARCH'
        if marker in s:
            return
        s = s.replace('Current version: v1.6.2', 'Current version: v1.6.3')
        p.write_text(s + '\n<!--ACE163_INSTANT_RESEARCH-->\n', encoding='utf-8')
    except Exception:
        pass


_patch_index()

if __name__ == '__main__':
    ace.main()
