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
import re

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


RESIZER163_FIXED = r'''  function bindPreviewResizer(){
    const els=[...document.querySelectorAll('[id],[class]')];
    const panel=els.find(e=>{
      if(!visible(e))return false;
      const key=(String(e.id||'')+' '+String(e.className||'')).toLowerCase();
      return key.includes('ace161')&&key.includes('preview')&&e.getBoundingClientRect().width>220;
    });
    if(!panel||panel.dataset.ace163Resizable==='1')return;
    panel.dataset.ace163Resizable='1';
    const cs=getComputedStyle(panel);if(cs.position==='static')panel.style.position='relative';
    const h=document.createElement('div');h.className='ace163-preview-resizer';h.setAttribute('role','separator');h.setAttribute('aria-orientation','vertical');h.title='Drag to resize Live preview · double-click to reset';
    const rect=panel.getBoundingClientRect();
    const onRight=rect.left>window.innerWidth/2;h.style[onRight?'left':'right']='0';
    panel.appendChild(h);
    try{const saved=Number(localStorage.getItem('ace163.livePreviewWidth')||0);if(saved>=320)panel.style.width=Math.min(saved,window.innerWidth*.72)+'px';}catch(_){ }
    let state=null;
    const save=()=>{try{localStorage.setItem('ace163.livePreviewWidth',String(Math.round(panel.getBoundingClientRect().width)));}catch(_){ }};
    const finish=()=>{
      if(!state)return;
      const pid=state.pointerId;
      window.removeEventListener('pointermove',move,true);
      window.removeEventListener('pointerup',up,true);
      window.removeEventListener('pointercancel',cancel,true);
      window.removeEventListener('blur',cancel,true);
      document.removeEventListener('visibilitychange',hidden,true);
      try{if(h.hasPointerCapture&&h.hasPointerCapture(pid))h.releasePointerCapture(pid);}catch(_){ }
      document.body.classList.remove('ace163-resizing-preview');h.dataset.dragging='0';
      state=null;save();
    };
    const move=e=>{
      if(!state||e.pointerId!==state.pointerId)return;
      const dx=e.clientX-state.startX;const w=Math.max(320,Math.min(window.innerWidth*.72,state.startW+(onRight?-dx:dx)));
      panel.style.width=Math.round(w)+'px';panel.style.maxWidth='72vw';panel.style.flexBasis=Math.round(w)+'px';
    };
    const up=e=>{if(!state||e.pointerId!==state.pointerId)return;finish();};
    const cancel=()=>finish();
    const hidden=()=>{if(document.hidden)finish();};
    h.addEventListener('pointerdown',e=>{
      if(state)finish();
      e.preventDefault();
      state={pointerId:e.pointerId,startX:e.clientX,startW:panel.getBoundingClientRect().width};
      h.dataset.dragging='1';document.body.classList.add('ace163-resizing-preview');
      try{h.setPointerCapture(e.pointerId);}catch(_){ }
      window.addEventListener('pointermove',move,true);
      window.addEventListener('pointerup',up,true);
      window.addEventListener('pointercancel',cancel,true);
      window.addEventListener('blur',cancel,true);
      document.addEventListener('visibilitychange',hidden,true);
    });
    h.addEventListener('dblclick',()=>{if(state)finish();panel.style.width='';panel.style.maxWidth='';panel.style.flexBasis='';try{localStorage.removeItem('ace163.livePreviewWidth');}catch(_){ }});
  }'''


JS164 = r'''
(function(){
  if(window.__ACE164_FINAL_QA__)return;
  window.__ACE164_FINAL_QA__=1;

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

  window.addEventListener('resize',clampPreview,{passive:true});
  const refresh=()=>{try{bindPasteGuard();queueIsSafe();clampPreview();}catch(_){ }};
  setTimeout(refresh,120);
  setInterval(refresh,1600);
})();
// ACE164_FINAL_QA
'''


def app164(s):
    pattern = r"  function bindPreviewResizer\(\)\{[\s\S]*?\n  \}\n\n  document\.addEventListener\('keydown',e=>\{"
    replacement = RESIZER163_FIXED + "\n\n  document.addEventListener('keydown',e=>{"
    s2, count = re.subn(pattern, lambda _: replacement, s, count=1)
    if count != 1:
        return s
    return s2 + '\n' + JS164 + '\n// ACE164\n'


patch(H / 'index.html', 'ACE164_FINAL_QA', idx164)
patch(H / 'app.css', 'ACE164_FINAL_QA', lambda s: s + '\n' + CSS164 + '\n')
patch(H / 'app.js', 'ACE164_FINAL_QA', app164)

if __name__ == '__main__':
    ace.main()
