#!/usr/bin/env python3
"""A.C.E. 1.6.3 — workspace ergonomics and Live preview polish.

Loads 1.6.2 cumulatively. This release adds a keyboard-first command palette,
reliable shortcuts for the existing New Chat / AI Search / Chat-Live controls,
safer attachment-queue clearing when the user navigates away from a send, and a
non-invasive resizer for the 1.6.1 Live preview drawer. Existing updater, voice,
Stop, Chat/Live, artifact preview/Edit, downloads/exports, chats/projects,
attachments and web research remain on the proven cumulative runtime.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.2.py'
spec = importlib.util.spec_from_file_location('ace_base_162', str(BASE))
b162 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b162)
ace = b162.ace

ace.VERSION = '1.6.3'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.3'
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


def idx163(s):
    s = s.replace('app.css?v=162-attachments', 'app.css?v=163-workspace-polish')
    s = s.replace('app.js?v=162-attachments', 'app.js?v=163-workspace-polish')
    s = s.replace('Current version: v1.6.2', 'Current version: v1.6.3')
    return s + '\n<!--ACE163_WORKSPACE_POLISH-->\n'


CSS163 = r'''
#ace163PaletteBackdrop{position:fixed;inset:0;z-index:2147483600;background:rgba(2,10,8,.48);backdrop-filter:blur(3px);display:flex;align-items:flex-start;justify-content:center;padding-top:min(16vh,150px)}
#ace163PaletteBackdrop[hidden]{display:none!important}
#ace163Palette{width:min(620px,calc(100vw - 32px));max-height:min(560px,72vh);overflow:hidden;background:rgba(13,31,27,.985);border:1px solid rgba(67,214,176,.30);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.52);color:#eef8f4;transform-origin:top center;animation:ace163PaletteIn .14s ease-out}
#ace163PaletteTop{display:flex;gap:10px;align-items:center;padding:14px 14px 10px;border-bottom:1px solid rgba(255,255,255,.08)}
#ace163PaletteInput{width:100%;box-sizing:border-box;border:0;outline:0;background:transparent;color:inherit;font:inherit;font-size:16px;padding:8px 6px}
#ace163PaletteInput::placeholder{color:rgba(238,248,244,.48)}
#ace163PaletteList{padding:8px;overflow:auto;max-height:420px}
.ace163Cmd{width:100%;display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;border:0;background:transparent;color:inherit;text-align:left;padding:11px 12px;border-radius:12px;font:inherit;cursor:pointer}
.ace163Cmd:hover,.ace163Cmd[data-active="1"]{background:rgba(67,214,176,.12)}
.ace163Cmd small{color:rgba(238,248,244,.48);font-size:12px;letter-spacing:.02em}
#ace163PaletteFoot{padding:9px 14px 12px;color:rgba(238,248,244,.45);font-size:11px;border-top:1px solid rgba(255,255,255,.06)}
.ace163-preview-resizer{position:absolute!important;top:0;bottom:0;width:10px;cursor:ew-resize;z-index:30;touch-action:none;background:transparent}
.ace163-preview-resizer::after{content:"";position:absolute;top:42%;bottom:42%;left:4px;width:2px;border-radius:2px;background:rgba(67,214,176,.35);transition:background .14s ease}
.ace163-preview-resizer:hover::after,.ace163-preview-resizer[data-dragging="1"]::after{background:rgba(67,214,176,.86)}
body.ace163-resizing-preview{user-select:none!important;cursor:ew-resize!important}
@keyframes ace163PaletteIn{from{opacity:0;transform:translateY(-6px) scale(.985)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){#ace163Palette{animation:none}.ace163-preview-resizer::after{transition:none}}
/*ACE163_WORKSPACE_POLISH*/
'''


JS163 = r'''
(function(){
  if(window.__ACE163_WORKSPACE_POLISH__)return;
  window.__ACE163_WORKSPACE_POLISH__=1;
  const $=id=>document.getElementById(id);
  const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
  const visible=e=>!!(e&&e.isConnected&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
  const clearAttachmentQueue=()=>{try{window.__ACE162_ATTACHMENT_QUEUE__=null;}catch(_){}};

  function controls(){
    return [...document.querySelectorAll('button,[role="button"],a')].filter(visible);
  }
  function labelsOf(e){
    if(!e)return [];
    return [...new Set([norm(e.getAttribute&&e.getAttribute('aria-label')),norm(e.title),norm(e.textContent)].filter(Boolean))];
  }
  function labelOf(e){return labelsOf(e)[0]||'';}
  function clickExact(labels,preferWorkspace=true){
    const wanted=new Set(labels.map(norm));
    const all=controls().filter(e=>labelsOf(e).some(x=>wanted.has(x)));
    if(!all.length)return false;
    const pick=(preferWorkspace&&all.find(e=>/ace16|workspace|drawer|rail/i.test(String(e.id||'')+' '+String(e.className||''))))||all[0];
    try{pick.click();return true;}catch(_){return false;}
  }
  function focusComposer(){
    const ta=$('chatInput')||document.querySelector('textarea');
    if(!ta)return false;
    try{ta.focus({preventScroll:false});return true;}catch(_){try{ta.focus();return true;}catch(__){return false;}}
  }
  function actionNewChat(){
    clearAttachmentQueue();
    return clickExact(['New chat','New Chat']);
  }
  function actionSearch(){
    clearAttachmentQueue();
    return clickExact(['AI Search','AI search']);
  }
  function actionLive(){return clickExact(['Live']);}
  function actionChat(){return clickExact(['Chat']);}
  function actionSidebar(){
    if(clickExact(['Toggle sidebar','Open sidebar','Close sidebar','Sidebar','Menu']))return true;
    const e=[...document.querySelectorAll('[id*="ace161" i][id*="rail" i] button,[class*="ace161" i][class*="rail" i] button')].find(visible);
    if(e){try{e.click();return true;}catch(_){}}
    return false;
  }
  function actionAttach(){return clickExact(['Attach files','Attach file','Attach','Add file']);}

  const actions=[
    {id:'new',label:'New chat',hint:'⌘⇧N',keys:'new chat conversation',run:actionNewChat},
    {id:'search',label:'AI Search',hint:'⌘⇧F',keys:'search research web ai',run:actionSearch},
    {id:'live',label:'Switch to Live',hint:'⌘⇧L',keys:'live preview mode',run:actionLive},
    {id:'chat',label:'Switch to Chat',hint:'',keys:'chat mode',run:actionChat},
    {id:'composer',label:'Focus message',hint:'⌘J',keys:'message composer prompt',run:focusComposer},
    {id:'attach',label:'Attach files',hint:'',keys:'attachment image file upload',run:actionAttach},
    {id:'sidebar',label:'Toggle sidebar',hint:'',keys:'menu drawer navigation sidebar',run:actionSidebar}
  ];

  function ensurePalette(){
    let back=$('ace163PaletteBackdrop');
    if(back)return back;
    back=document.createElement('div');
    back.id='ace163PaletteBackdrop';back.hidden=true;
    back.innerHTML='<div id="ace163Palette" role="dialog" aria-modal="true" aria-label="A.C.E. commands"><div id="ace163PaletteTop"><input id="ace163PaletteInput" autocomplete="off" spellcheck="false" placeholder="Search A.C.E. commands…" aria-label="Search A.C.E. commands"></div><div id="ace163PaletteList" role="listbox"></div><div id="ace163PaletteFoot">Enter to run · ↑↓ to move · Esc to close</div></div>';
    document.body.appendChild(back);
    back.addEventListener('mousedown',e=>{if(e.target===back)closePalette();});
    const input=$('ace163PaletteInput');
    input.addEventListener('input',()=>renderCommands(input.value));
    input.addEventListener('keydown',e=>{
      const rows=[...document.querySelectorAll('.ace163Cmd')];
      if(e.key==='Escape'){e.preventDefault();closePalette();return;}
      let at=rows.findIndex(x=>x.dataset.active==='1');
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){
        e.preventDefault();if(!rows.length)return;
        if(at<0)at=0;else at=(at+(e.key==='ArrowDown'?1:-1)+rows.length)%rows.length;
        rows.forEach((x,i)=>x.dataset.active=i===at?'1':'0');rows[at].scrollIntoView({block:'nearest'});return;
      }
      if(e.key==='Enter'){
        e.preventDefault();const row=rows[Math.max(0,at)];if(row)row.click();
      }
    });
    return back;
  }
  function filtered(q){
    q=norm(q);if(!q)return actions;
    const bits=q.split(' ').filter(Boolean);
    return actions.filter(a=>bits.every(b=>norm(a.label+' '+a.keys).includes(b)));
  }
  function renderCommands(q=''){
    const list=$('ace163PaletteList');if(!list)return;
    list.textContent='';
    filtered(q).forEach((a,i)=>{
      const b=document.createElement('button');b.type='button';b.className='ace163Cmd';b.dataset.active=i===0?'1':'0';b.setAttribute('role','option');
      b.innerHTML='<span></span><small></small>';b.querySelector('span').textContent=a.label;b.querySelector('small').textContent=a.hint||'';
      b.addEventListener('click',()=>{closePalette();setTimeout(()=>{try{a.run();}catch(_){ }},0);});
      list.appendChild(b);
    });
  }
  function openPalette(){
    const back=ensurePalette();back.hidden=false;renderCommands('');
    const input=$('ace163PaletteInput');if(input){input.value='';setTimeout(()=>input.focus(),0);}
  }
  function closePalette(){const back=$('ace163PaletteBackdrop');if(back)back.hidden=true;}

  function annotateShortcuts(){
    const pairs=[
      [['New chat','New Chat'],'Meta+Shift+N'],
      [['AI Search','AI search'],'Meta+Shift+F'],
      [['Live'],'Meta+Shift+L']
    ];
    for(const [labels,key] of pairs){
      const wanted=new Set(labels.map(norm));
      const e=controls().find(x=>labelsOf(x).some(v=>wanted.has(v)));
      if(e&&!e.getAttribute('aria-keyshortcuts'))e.setAttribute('aria-keyshortcuts',key);
    }
  }

  function bindPreviewResizer(){
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
    let startX=0,startW=0;
    const move=e=>{
      const dx=e.clientX-startX;const w=Math.max(320,Math.min(window.innerWidth*.72,startW+(onRight?-dx:dx)));
      panel.style.width=Math.round(w)+'px';panel.style.maxWidth='72vw';panel.style.flexBasis=Math.round(w)+'px';
    };
    const up=()=>{document.body.classList.remove('ace163-resizing-preview');h.dataset.dragging='0';window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);try{localStorage.setItem('ace163.livePreviewWidth',String(Math.round(panel.getBoundingClientRect().width)));}catch(_){ }};
    h.addEventListener('pointerdown',e=>{e.preventDefault();startX=e.clientX;startW=panel.getBoundingClientRect().width;h.dataset.dragging='1';document.body.classList.add('ace163-resizing-preview');try{h.setPointerCapture(e.pointerId);}catch(_){ }window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);});
    h.addEventListener('dblclick',()=>{panel.style.width='';panel.style.maxWidth='';panel.style.flexBasis='';try{localStorage.removeItem('ace163.livePreviewWidth');}catch(_){ }});
  }

  document.addEventListener('keydown',e=>{
    const mod=e.metaKey||e.ctrlKey;
    if(mod&&!e.shiftKey&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();return;}
    if(mod&&e.shiftKey&&e.key.toLowerCase()==='n'){e.preventDefault();actionNewChat();return;}
    if(mod&&e.shiftKey&&e.key.toLowerCase()==='f'){e.preventDefault();actionSearch();return;}
    if(mod&&e.shiftKey&&e.key.toLowerCase()==='l'){e.preventDefault();actionLive();return;}
    if(mod&&!e.shiftKey&&e.key.toLowerCase()==='j'){e.preventDefault();focusComposer();return;}
    if(e.key==='Escape'&&!($('ace163PaletteBackdrop')?.hidden)){closePalette();}
  },true);

  document.addEventListener('click',e=>{
    const b=e.target&&e.target.closest&&e.target.closest('button,[role="button"],a');if(!b)return;
    const ts=labelsOf(b);
    if(ts.some(t=>t==='new chat'||t==='ai search'||t==='projects'||t==='project'))clearAttachmentQueue();
  },true);

  const refresh=()=>{try{annotateShortcuts();bindPreviewResizer();}catch(_){ }};
  setTimeout(refresh,180);setInterval(refresh,1600);
})();
// ACE163_WORKSPACE_POLISH
'''


def app163(s):
    return s + '\n' + JS163 + '\n// ACE163\n'


patch(H / 'index.html', 'ACE163_WORKSPACE_POLISH', idx163)
patch(H / 'app.css', 'ACE163_WORKSPACE_POLISH', lambda s: s + '\n' + CSS163 + '\n')
patch(H / 'app.js', 'ACE163_WORKSPACE_POLISH', app163)

if __name__ == '__main__':
    ace.main()
