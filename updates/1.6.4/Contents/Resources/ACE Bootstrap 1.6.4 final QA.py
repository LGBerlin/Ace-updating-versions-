#!/usr/bin/env python3
"""A.C.E. 1.6.4 — final overnight reliability pass.

Loads 1.6.3 cumulatively. This release is intentionally fix-focused: it hardens
attachment-context scoping across chat/project navigation, prevents clipboard-file
pastes from also dumping unwanted text into the composer, and makes the Live preview
resizer recover cleanly from pointer cancellation/window blur and clamp itself after
window resizes. Existing Update, Voice, Stop, Chat/Live, artifacts, Preview/Edit,
downloads/exports, chats/projects, attachments, command palette and research remain
on the cumulative runtime.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.3.py'
spec = importlib.util.spec_from_file_location('ace_base_163', str(BASE))
b163 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b163)
ace = b163.ace

ace.VERSION = '1.6.4'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.4'
except Exception:
    pass


def patch(path, marker, transform):
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


def idx164(s):
    s = s.replace('app.css?v=163-workspace-polish', 'app.css?v=164-final-qa')
    s = s.replace('app.js?v=163-workspace-polish', 'app.js?v=164-final-qa')
    s = s.replace('Current version: v1.6.3', 'Current version: v1.6.4')
    return s + '\n<!--ACE164_FINAL_QA-->\n'


CSS164 = r'''
.ace163-preview-resizer[data-dragging="1"]::after{background:rgba(67,214,176,.92)}
#ace163PaletteBackdrop[aria-busy="true"]{pointer-events:none}
@media(max-width:760px){.ace163-preview-resizer{width:14px}.ace163-preview-resizer::after{left:6px}}
/*ACE164_FINAL_QA*/
'''


JS164 = r'''
(function(){
  if(window.__ACE164_FINAL_QA__)return;
  window.__ACE164_FINAL_QA__=1;
  const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();

  function queue(){
    try{return window.__ACE162_ATTACHMENT_QUEUE__||null;}catch(_){return null;}
  }
  function clearQueue(){
    try{window.__ACE162_ATTACHMENT_QUEUE__=null;}catch(_){}
  }
  function selectedChatId(){
    const candidates=[
      '[data-chat-id][aria-current="true"]',
      '[data-chat-id][data-active="1"]',
      '[data-chat-id].active',
      '[data-chat-id].selected',
      '[data-chat][aria-current="true"]',
      '[data-chat][data-active="1"]',
      '[data-chat].active',
      '[data-chat].selected'
    ];
    for(const sel of candidates){
      const e=document.querySelector(sel);
      if(!e)continue;
      const v=e.dataset?.chatId||e.dataset?.chat||e.getAttribute('data-chat-id')||e.getAttribute('data-chat');
      if(v)return String(v);
    }
    return '';
  }
  function queueIsSafe(){
    const q=queue();
    if(!q)return true;
    const age=Date.now()-Number(q.created||0);
    if(!Number.isFinite(age)||age<0||age>=8000){clearQueue();return false;}
    const cur=selectedChatId();
    if(cur&&q.chatId&&String(cur)!==String(q.chatId)){clearQueue();return false;}
    return true;
  }

  // Run before the 1.6.2 fetch wrapper. If navigation has moved away from the
  // originating chat, remove the queued hidden context so it cannot leak into a
  // different request. Otherwise leave the proven 1.6.2 injection path untouched.
  const previousFetch=window.fetch.bind(window);
  window.fetch=async function(input,init){
    try{queueIsSafe();}catch(_){}
    return previousFetch(input,init);
  };

  function looksLikeNavigation(el){
    if(!el)return false;
    if(el.closest?.('#ace163PaletteBackdrop'))return false;
    const key=[
      el.id||'',
      el.className||'',
      el.getAttribute?.('aria-label')||'',
      el.getAttribute?.('title')||'',
      el.textContent||''
    ].join(' ');
    if(/send|submit|attach|upload|stop|voice|preview|edit|download|copy/i.test(key))return false;
    if(el.matches?.('[data-chat-id],[data-chat],[data-project-id],[data-project]'))return true;
    if(el.closest?.('[data-chat-id],[data-chat],[data-project-id],[data-project]'))return true;
    return /ace161/i.test(key)&&/\b(chat|project|search|new)\b/i.test(key);
  }
  document.addEventListener('click',e=>{
    const el=e.target?.closest?.('button,a,[role="button"],[data-chat-id],[data-chat],[data-project-id],[data-project]');
    if(looksLikeNavigation(el))clearQueue();
  },true);

  // A clipboard image/file is already handled by the 1.6.2 attachment listener.
  // Prevent the browser from additionally inserting an unwanted path/placeholder
  // when the clipboard contains files but no meaningful text.
  function bindPasteGuard(){
    const ta=document.getElementById('chatInput');
    if(!ta||ta.dataset.ace164PasteGuard==='1')return;
    ta.dataset.ace164PasteGuard='1';
    ta.addEventListener('paste',e=>{
      const files=[...(e.clipboardData?.files||[])];
      if(!files.length)return;
      const text=String(e.clipboardData?.getData?.('text/plain')||'').trim();
      if(!text)e.preventDefault();
    },true);
  }

  function endResize(){
    document.body.classList.remove('ace163-resizing-preview');
    document.querySelectorAll('.ace163-preview-resizer[data-dragging="1"]').forEach(h=>h.dataset.dragging='0');
  }
  function clampPreview(){
    const panel=document.querySelector('[data-ace163-resizable="1"]');
    if(!panel)return;
    const max=Math.max(320,window.innerWidth*.72);
    const r=panel.getBoundingClientRect();
    if(r.width>max+1){
      const w=Math.round(max);
      panel.style.width=w+'px';
      panel.style.maxWidth='72vw';
      panel.style.flexBasis=w+'px';
      try{localStorage.setItem('ace163.livePreviewWidth',String(w));}catch(_){}
    }
  }

  window.addEventListener('pointercancel',endResize,true);
  window.addEventListener('blur',endResize,true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)endResize();});
  window.addEventListener('resize',()=>{endResize();clampPreview();},{passive:true});

  const refresh=()=>{try{bindPasteGuard();queueIsSafe();clampPreview();}catch(_){ }};
  setTimeout(refresh,120);
  setInterval(refresh,1600);
})();
// ACE164_FINAL_QA
'''


def app164(s):
    return s + '\n' + JS164 + '\n// ACE164\n'


patch(H / 'index.html', 'ACE164_FINAL_QA', idx164)
patch(H / 'app.css', 'ACE164_FINAL_QA', lambda s: s + '\n' + CSS164 + '\n')
patch(H / 'app.js', 'ACE164_FINAL_QA', app164)

if __name__ == '__main__':
    ace.main()
