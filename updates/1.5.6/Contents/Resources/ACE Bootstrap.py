#!/usr/bin/env python3
"""A.C.E. 1.5.6 runtime bridge.

Adds two focused improvements to the proven 1.5.x application:
1) ChatGPT-style composer Stop control that immediately cuts speech and active work.
2) Real poster Preview editing backed by the editable PPTX: drag objects, rewrite text,
   save changes into the PowerPoint, then download/export the edited file.

The patch is idempotent and intentionally leaves the large A.C.E. backend intact.
"""
from pathlib import Path
from copy import deepcopy
import base64, importlib.util, os, platform, subprocess, tempfile, time, zipfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SERVER = HERE / 'ACE Server.py'


def _patch_once(path, marker, transform):
    try:
        p = Path(path)
        text = p.read_text(encoding='utf-8')
        if marker in text:
            return True
        new = transform(text)
        if new == text:
            return False
        p.write_text(new, encoding='utf-8')
        return marker in new
    except Exception:
        return False


def _patch_index(text):
    text = text.replace('app.css?v=155-controls', 'app.css?v=156-editor')
    text = text.replace('app.js?v=155-controls', 'app.js?v=156-editor')
    text = text.replace('Current version: v1.5.5', 'Current version: v1.5.6')
    text = text.replace('Current version: v1.5.4', 'Current version: v1.5.6')
    return text + '\n<!-- ACE_UI_156 -->\n'


_CSS_156 = r'''
/* ACE_UI_156: composer stop + real poster editor */
#sendBtn.ace-composer-stop{background:#f1f3f5!important;color:#12161b!important;border-color:#d8dde2!important;box-shadow:none!important}
#sendBtn.ace-composer-stop:hover{background:#fff!important;border-color:#c5ccd3!important}
#sendBtn .ace-stop-glyph{display:block;width:11px;height:11px;background:currentColor;border-radius:2px;margin:auto}
.ace-pptx-edit-overlay{position:fixed;z-index:2147483000;pointer-events:auto;overflow:hidden;border:1px solid rgba(76,224,255,.52);box-shadow:0 0 0 1px rgba(0,0,0,.22),0 8px 28px rgba(0,0,0,.20)}
.ace-pptx-edit-shape{position:absolute;box-sizing:border-box;border:1px dashed rgba(76,224,255,.70);background:rgba(76,224,255,.025);cursor:move;min-width:5px;min-height:5px;user-select:none}
.ace-pptx-edit-shape:hover{border-style:solid;background:rgba(76,224,255,.07)}
.ace-pptx-edit-shape.selected{border:2px solid #24cfee;background:rgba(36,207,238,.09);box-shadow:0 0 0 2px rgba(36,207,238,.12)}
.ace-pptx-edit-shape.text-shape:after{content:'T';position:absolute;right:2px;top:2px;padding:1px 4px;border-radius:4px;background:rgba(7,16,25,.72);color:#dff8ff;font:700 8px/1.35 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;pointer-events:none}
.ace-pptx-edit-shape.inline-text{cursor:text;background:rgba(248,249,250,.96);color:#111;border:2px solid #24cfee;padding:4px;overflow:auto;white-space:pre-wrap;user-select:text;font:500 12px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;outline:none}
.ace-pptx-editor-panel{position:fixed;z-index:2147483001;width:300px;max-height:min(560px,78vh);overflow:auto;background:#0b131c;color:#e7f5fb;border:1px solid rgba(76,224,255,.26);border-radius:14px;box-shadow:0 18px 45px rgba(0,0,0,.38);padding:13px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.ace-pptx-editor-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px}.ace-pptx-editor-head strong{font-size:13px}.ace-pptx-editor-close{border:0;background:transparent;color:#8193a1;font-size:20px;cursor:pointer}.ace-pptx-editor-close:hover{color:#fff}
.ace-pptx-editor-note{font-size:10.5px;color:#8fa7b7;line-height:1.45;margin-bottom:10px}.ace-pptx-selected-name{font-size:10px;color:#4ce0ff;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ace-pptx-text-label{display:block;font-size:10px;color:#9aafbc;margin:7px 0 4px}.ace-pptx-textarea{width:100%;min-height:115px;resize:vertical;background:#071019;color:#e7f5fb;border:1px solid rgba(76,224,255,.18);border-radius:8px;padding:8px;font:12px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;outline:none}.ace-pptx-textarea:focus{border-color:#4ce0ff}.ace-pptx-textarea:disabled{opacity:.38}
.ace-pptx-editor-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.ace-pptx-editor-actions button{border:1px solid rgba(76,224,255,.22);background:#101c28;color:#dff3fb;border-radius:8px;padding:7px 9px;font-size:10.5px;cursor:pointer}.ace-pptx-editor-actions button:hover{border-color:#4ce0ff}.ace-pptx-editor-actions .save{background:#1dabc6;color:#031016;border-color:#43dff7;font-weight:750}.ace-pptx-editor-status{min-height:16px;margin-top:8px;font-size:10px;color:#96aebb}
.ace-pptx-edit-help{position:fixed;z-index:2147483001;background:rgba(5,10,15,.88);color:#dcecf3;border:1px solid rgba(76,224,255,.24);border-radius:8px;padding:5px 8px;font:10px/1.3 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;pointer-events:none}
'''


def _patch_css(text):
    return text + '\n' + _CSS_156 + '\n'


_JS_156 = r'''
// ACE_UI_156: ChatGPT-style composer stop + PPTX-backed poster editing.
(function(){
  if(window.__ACE_UI_156__)return;window.__ACE_UI_156__=true;
  const $156=id=>document.getElementById(id);
  let composerOriginal=null;
  function active156(){try{return typeof aceWorkActive==='function'?aceWorkActive():!!(window.busy||window.isSpeaking);}catch(_){return false;}}
  function syncComposerStop156(){const b=$156('sendBtn');if(!b)return;if(composerOriginal===null)composerOriginal=b.innerHTML;const on=active156();if(on){b.disabled=false;b.dataset.aceStop156='1';b.classList.add('ace-composer-stop');b.title='Stop A.C.E.';b.setAttribute('aria-label','Stop A.C.E.');b.innerHTML='<span class="ace-stop-glyph" aria-hidden="true"></span>';}else if(b.dataset.aceStop156==='1'){delete b.dataset.aceStop156;b.classList.remove('ace-composer-stop');b.title='Send';b.setAttribute('aria-label','Send');b.innerHTML=composerOriginal||'Send';}}
  document.addEventListener('click',function(e){const b=e.target&&e.target.closest?e.target.closest('#sendBtn'):null;if(b&&b.dataset.aceStop156==='1'){e.preventDefault();e.stopPropagation();if(e.stopImmediatePropagation)e.stopImmediatePropagation();try{if(typeof stopAceEverything==='function')stopAceEverything();else if(typeof cancelSpeech==='function')cancelSpeech();}catch(_){}setTimeout(syncComposerStop156,0);}},true);
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&active156()){try{if(typeof stopAceEverything==='function')stopAceEverything();else if(typeof cancelSpeech==='function')cancelSpeech();}catch(_){}}},true);
  setInterval(syncComposerStop156,100);syncComposerStop156();
  const ed={open:false,overlay:null,panel:null,help:null,img:null,shapes:[],selected:null,dirty:false,raf:0,page:0};
  function studioRoot156(){return $156('artifactStudio')||document.querySelector('.artifact-studio')||document.body;}
  function previewImage156(){const root=studioRoot156();const imgs=[...root.querySelectorAll('img')].filter(i=>{const r=i.getBoundingClientRect();return r.width>80&&r.height>80&&getComputedStyle(i).display!=='none';});imgs.sort((a,b)=>{const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();return br.width*br.height-ar.width*ar.height;});return imgs[0]||null;}
  async function getShapes156(){if(!window.studioJob||!studioJob.job_id)throw new Error('No editable poster is open.');const u='/api/studio/shapes?job='+encodeURIComponent(studioJob.job_id)+'&page='+ed.page+'&_='+(Date.now());const r=await fetch(u,{cache:'no-store'});const d=await r.json();if(!r.ok||d.error)throw new Error(d.error||('Editor request failed ('+r.status+')'));return d;}
  function positionEditor156(){if(!ed.open||!ed.img||!ed.overlay)return;const r=ed.img.getBoundingClientRect();Object.assign(ed.overlay.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});if(ed.help)Object.assign(ed.help.style,{left:(r.left+8)+'px',top:(r.top+8)+'px'});if(ed.panel){let left=Math.min(window.innerWidth-312,r.right+12);if(left<8)left=8;let top=Math.max(8,Math.min(window.innerHeight-260,r.top));Object.assign(ed.panel.style,{left:left+'px',top:top+'px'});}}
  function shapeLabel156(s){let t=(s.text||s.name||s.type||'Object').replace(/\s+/g,' ').trim();return t.length>36?t.slice(0,33)+'…':t;}
  function styleShape156(el,s){el.style.left=(s.x*100)+'%';el.style.top=(s.y*100)+'%';el.style.width=(s.w*100)+'%';el.style.height=(s.h*100)+'%';}
  function selectShape156(s,el){ed.selected=s;[...ed.overlay.querySelectorAll('.ace-pptx-edit-shape')].forEach(x=>x.classList.toggle('selected',x===el));const name=ed.panel.querySelector('.ace-pptx-selected-name'),ta=ed.panel.querySelector('.ace-pptx-textarea');name.textContent=s.name||('Object '+s.id);ta.disabled=!s.has_text;ta.value=s.has_text?(s.text||''):'';ta.placeholder=s.has_text?'Rewrite this text…':'This object has no editable text.';}
  function beginInlineText156(s,el){if(!s.has_text)return;selectShape156(s,el);el.classList.add('inline-text');el.classList.remove('text-shape');el.textContent=s.text||'';el.contentEditable='true';el.focus();try{const range=document.createRange();range.selectNodeContents(el);const sel=getSelection();sel.removeAllRanges();sel.addRange(range);}catch(_){}const finish=()=>{s.text=el.innerText.replace(/\r/g,'');ed.dirty=true;el.contentEditable='false';el.classList.remove('inline-text');el.classList.add('text-shape');el.textContent='';const ta=ed.panel.querySelector('.ace-pptx-textarea');if(ed.selected===s)ta.value=s.text||'';};el.addEventListener('blur',finish,{once:true});el.addEventListener('keydown',ev=>{if(ev.key==='Escape'){ev.preventDefault();el.blur();}},{once:true});}
  function makeShape156(s){const el=document.createElement('div');el.className='ace-pptx-edit-shape'+(s.has_text?' text-shape':'');el.dataset.sid=s.id;el.title=(s.has_text?'Drag to move • double-click to edit text • ':'Drag to move • ')+(s.name||s.type||'object');styleShape156(el,s);el.addEventListener('click',ev=>{ev.stopPropagation();selectShape156(s,el);});el.addEventListener('dblclick',ev=>{ev.preventDefault();ev.stopPropagation();beginInlineText156(s,el);});el.addEventListener('pointerdown',ev=>{if(el.isContentEditable)return;ev.preventDefault();ev.stopPropagation();selectShape156(s,el);el.setPointerCapture&&el.setPointerCapture(ev.pointerId);const r=ed.overlay.getBoundingClientRect(),sx=ev.clientX,sy=ev.clientY,ox=s.x,oy=s.y;const move=mv=>{s.x=Math.max(0,Math.min(1-s.w,ox+(mv.clientX-sx)/Math.max(1,r.width)));s.y=Math.max(0,Math.min(1-s.h,oy+(mv.clientY-sy)/Math.max(1,r.height)));styleShape156(el,s);ed.dirty=true;};const up=()=>{window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerup',up,true);};window.addEventListener('pointermove',move,true);window.addEventListener('pointerup',up,true);});return el;}
  function makePanel156(){const p=document.createElement('div');p.className='ace-pptx-editor-panel';p.innerHTML='<div class="ace-pptx-editor-head"><strong>Edit poster</strong><button class="ace-pptx-editor-close" title="Exit edit mode">×</button></div><div class="ace-pptx-editor-note">Drag any outlined object to move it. Double-click a text object to type directly, or select it and rewrite the text below. Save writes the changes into the actual PowerPoint you will download/export.</div><div class="ace-pptx-selected-name">Select an object</div><label class="ace-pptx-text-label">Text</label><textarea class="ace-pptx-textarea" disabled></textarea><div class="ace-pptx-editor-actions"><button class="save">Save changes</button><button class="apply">Apply text</button><button class="exit">Done</button></div><div class="ace-pptx-editor-status"></div>';const ta=p.querySelector('.ace-pptx-textarea');p.querySelector('.apply').onclick=()=>{if(ed.selected&&ed.selected.has_text){ed.selected.text=ta.value;ed.dirty=true;status156('Text changed — save when ready.');}};ta.addEventListener('input',()=>{if(ed.selected&&ed.selected.has_text){ed.selected.text=ta.value;ed.dirty=true;}});p.querySelector('.save').onclick=saveEditor156;p.querySelector('.exit').onclick=async()=>{if(ed.dirty){const ok=confirm('Save your poster changes before leaving edit mode?');if(ok)await saveEditor156();}closeEditor156();};p.querySelector('.ace-pptx-editor-close').onclick=()=>closeEditor156();return p;}
  function status156(t,bad){if(!ed.panel)return;const s=ed.panel.querySelector('.ace-pptx-editor-status');s.textContent=t||'';s.style.color=bad?'#ff8c8c':'#96aebb';}
  async function saveEditor156(){if(!window.studioJob||!studioJob.job_id)return;status156('Saving into PowerPoint…');const changes=ed.shapes.map(s=>({id:s.id,x:s.x,y:s.y,w:s.w,h:s.h,text:s.has_text?s.text:undefined}));try{const r=await fetch('/api/studio/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:studioJob.job_id,page:ed.page,shapes:changes})});const d=await r.json();if(!r.ok||d.error)throw new Error(d.error||'Save failed');ed.dirty=false;if(d.preview_data_url&&ed.img)ed.img.src=d.preview_data_url;if(d.preview_data_url)setTimeout(positionEditor156,60);status156('Saved. Download/export will use this edited poster.');}catch(e){status156(e.message||String(e),true);}}
  function closeEditor156(){ed.open=false;if(ed.raf)cancelAnimationFrame(ed.raf);ed.raf=0;ed.overlay&&ed.overlay.remove();ed.panel&&ed.panel.remove();ed.help&&ed.help.remove();ed.overlay=ed.panel=ed.help=ed.img=null;ed.shapes=[];ed.selected=null;ed.dirty=false;try{if(typeof disableStudioEditing==='function')disableStudioEditing();}catch(_){}}
  async function openEditor156(){if(ed.open)return;ed.img=previewImage156();if(!ed.img){alert('The poster preview is not ready yet.');return;}try{const d=await getShapes156();ed.shapes=d.shapes||[];if(!ed.shapes.length)throw new Error('No editable PowerPoint objects were found in this poster.');try{if(typeof disableStudioEditing==='function')disableStudioEditing();}catch(_){}ed.overlay=document.createElement('div');ed.overlay.className='ace-pptx-edit-overlay';ed.overlay.addEventListener('click',()=>{ed.selected=null;[...ed.overlay.querySelectorAll('.ace-pptx-edit-shape')].forEach(x=>x.classList.remove('selected'));});ed.shapes.forEach(s=>ed.overlay.appendChild(makeShape156(s)));ed.panel=makePanel156();ed.help=document.createElement('div');ed.help.className='ace-pptx-edit-help';ed.help.textContent='Drag objects • double-click text';document.body.append(ed.overlay,ed.panel,ed.help);ed.open=true;positionEditor156();const loop=()=>{if(!ed.open)return;positionEditor156();ed.raf=requestAnimationFrame(loop);};ed.raf=requestAnimationFrame(loop);status156('Editing the real PPTX poster.');}catch(e){closeEditor156();alert('Poster editor could not open: '+(e.message||e));}}
  window.aceOpenStudioEditor156=openEditor156;
  document.addEventListener('click',function(e){const target=e.target&&e.target.closest?e.target.closest('button,a,[role="button"]'):null;if(!target)return;const root=studioRoot156();if(!root.contains(target))return;const txt=((target.textContent||'')+' '+(target.title||'')+' '+(target.getAttribute('aria-label')||'')).trim();if(/^edit\b/i.test(txt)||/\bedit (poster|preview|artifact)\b/i.test(txt)){e.preventDefault();e.stopPropagation();if(e.stopImmediatePropagation)e.stopImmediatePropagation();openEditor156();}},true);
  window.addEventListener('resize',positionEditor156,true);window.addEventListener('scroll',positionEditor156,true);
})();
'''


def _patch_js(text):
    return text + '\n' + _JS_156 + '\n// ACE_UI_156\n'


_patch_once(HERE / 'index.html', 'ACE_UI_156', _patch_index)
_patch_once(HERE / 'app.css', 'ACE_UI_156', _patch_css)
_patch_once(HERE / 'app.js', 'ACE_UI_156', _patch_js)

spec = importlib.util.spec_from_file_location('ace_server_runtime', str(SERVER))
ace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ace)
ace.VERSION = '1.5.6'
try:
    ace.UPDATE_STATE['current_version'] = '1.5.6'
except Exception:
    pass

_original_snapshot = ace._job_snapshot
_original_embedded = ace._pptx_embedded_thumbnail
_original_do_post = ace.H.do_POST
_original_do_get = ace.H.do_GET


def _quicklook_once(path):
    path = Path(path)
    if platform.system() != 'Darwin' or not path.is_file() or not Path('/usr/bin/qlmanage').exists():
        return ''
    try:
        with tempfile.TemporaryDirectory(prefix='ace_preview_') as td:
            out = Path(td)
            subprocess.run(['/usr/bin/qlmanage', '-t', '-s', '1400', '-o', str(out), str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12, check=False)
            imgs = [p for p in out.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
            if imgs:
                img = max(imgs, key=lambda p: p.stat().st_size)
                return base64.b64encode(img.read_bytes()).decode('ascii')
    except Exception:
        pass
    return ''


def _poster_preview_retry(job):
    if str(job.get('kind') or '') != 'poster' or not job.get('pptx_rel'):
        return False
    if job.get('preview_rel') or job.get('daemon_preview_url') or job.get('rendered_pages'):
        return True
    tries = int(job.get('_ace_preview_tries') or 0)
    if tries >= 5:
        return False
    job['_ace_preview_tries'] = tries + 1
    try:
        cwd = ace._project_cwd(str(job.get('project_id') or ''))
        rel = str(job.get('pptx_rel') or '')
        pptx = (cwd / rel).resolve() if cwd and rel else None
        if not pptx or not pptx.is_file() or pptx.stat().st_size <= 0:
            return False
        size = pptx.stat().st_size
        time.sleep(.28)
        if not pptx.is_file() or pptx.stat().st_size != size:
            return False
        thumb = _original_embedded(pptx) or _quicklook_once(pptx)
        if thumb:
            job['rendered_pages'] = [thumb]
            job['stage'] = 'Ready'
            return True
    except Exception:
        pass
    return False


def _snapshot(job):
    _poster_preview_retry(job)
    snap = _original_snapshot(job)
    if str(job.get('kind') or '') == 'poster' and str(job.get('status') or '') == 'done' and job.get('pptx_rel'):
        if job.get('rendered_pages'):
            snap['preview_ready'] = True
            snap['rendered_count'] = len(job.get('rendered_pages') or [])
            snap['rendered_base'] = '/api/opendesign/rendered?job=' + ace.urllib.parse.quote(str(job.get('job_id'))) + '&page='
            snap['stage'] = 'Ready'
        elif int(job.get('_ace_preview_tries') or 0) >= 5:
            snap['stage'] = 'Poster ready — preview unavailable'
    snap['edit_revision'] = int(job.get('_ace_edit_revision') or 0)
    return snap


def _cancel_opendesign_job(job_id):
    with ace.OPEN_DESIGN_LOCK:
        job = ace.OPEN_DESIGN_JOBS.get(str(job_id or ''))
    if not job:
        return {'ok': True, 'status': 'not-found'}
    job['cancel_requested'] = True
    run_ids = []
    for key in ('run_id', 'persist_run_id', 'export_run_id'):
        rid = str(job.get(key) or '')
        if rid and rid not in run_ids:
            run_ids.append(rid)
    for rid in run_ids:
        try:
            ace._od_http_json('POST', '/api/runs/' + ace.urllib.parse.quote(rid, safe='') + '/cancel', {}, timeout=8)
        except Exception:
            pass
    job['status'] = 'canceled'; job['stage'] = 'Canceled'; job['error'] = ''
    return {'ok': True, 'status': 'canceled', 'job_id': job.get('job_id')}


def _stop_local_model():
    try:
        model = ace.choose_model(ace.ollama_models()); binary = ace.ollama_binary()
        if model and binary:
            subprocess.Popen([binary, 'stop', model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


P_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS = {'p': P_NS, 'a': A_NS}


def _local(tag): return tag.rsplit('}', 1)[-1]


def _job_and_pptx(job_id):
    with ace.OPEN_DESIGN_LOCK:
        job = ace.OPEN_DESIGN_JOBS.get(str(job_id or ''))
    if not job: raise ValueError('The poster job is no longer available.')
    cwd = ace._project_cwd(str(job.get('project_id') or '')); rel = str(job.get('pptx_rel') or '')
    pptx = (cwd / rel).resolve() if cwd and rel else None
    if not pptx or not pptx.is_file(): raise ValueError('The editable PowerPoint file could not be found.')
    return job, pptx


def _slide_size(z):
    try:
        root = ET.fromstring(z.read('ppt/presentation.xml')); s = root.find('.//p:sldSz', NS)
        if s is not None: return max(1, int(s.get('cx') or 1)), max(1, int(s.get('cy') or 1))
    except Exception: pass
    return 12192000, 6858000


def _shape_nv(shape):
    for el in shape.iter():
        if _local(el.tag) == 'cNvPr': return el
    return None


def _shape_xfrm(shape):
    for el in shape.iter():
        if _local(el.tag) == 'xfrm':
            off = ext = None
            for c in list(el):
                if _local(c.tag) == 'off': off = c
                elif _local(c.tag) == 'ext': ext = c
            if off is not None and ext is not None: return el, off, ext
    return None, None, None


def _shape_text(shape):
    if _local(shape.tag) != 'sp': return None
    tx = next((c for c in list(shape) if _local(c.tag) == 'txBody'), None)
    if tx is None: return None
    return '\n'.join(''.join((t.text or '') for t in p.findall('.//a:t', NS)) for p in tx.findall('a:p', NS)).rstrip('\n')


def _set_shape_text(shape, value):
    if _local(shape.tag) != 'sp': return False
    tx = next((c for c in list(shape) if _local(c.tag) == 'txBody'), None)
    if tx is None: return False
    paras = tx.findall('a:p', NS)
    if not paras: return False
    base = paras[0]
    for p in paras[1:]: tx.remove(p)
    lines = str(value if value is not None else '').split('\n') or ['']
    for i, line in enumerate(lines):
        p = base if i == 0 else deepcopy(base)
        if i > 0: tx.append(p)
        texts = p.findall('.//a:t', NS)
        if texts:
            texts[0].text = line
            for extra in texts[1:]: extra.text = ''
        else:
            r = ET.Element('{%s}r' % A_NS); t = ET.SubElement(r, '{%s}t' % A_NS); t.text = line; p.insert(max(0, len(list(p)) - 1), r)
    return True


def _slide_shapes(pptx, page=0):
    page = max(0, int(page or 0)); slide_name = 'ppt/slides/slide%d.xml' % (page + 1)
    with zipfile.ZipFile(pptx, 'r') as z:
        if slide_name not in z.namelist(): raise ValueError('That poster page does not exist.')
        sw, sh = _slide_size(z); root = ET.fromstring(z.read(slide_name))
    tree = root.find('.//p:spTree', NS); out = []
    if tree is None: return out
    for zidx, shape in enumerate(list(tree)):
        typ = _local(shape.tag)
        if typ not in {'sp', 'pic', 'graphicFrame', 'grpSp'}: continue
        nv = _shape_nv(shape); xf, off, ext = _shape_xfrm(shape)
        if nv is None or off is None or ext is None: continue
        try:
            x, y = int(off.get('x') or 0), int(off.get('y') or 0); w, h = max(1, int(ext.get('cx') or 1)), max(1, int(ext.get('cy') or 1))
        except Exception: continue
        text = _shape_text(shape)
        out.append({'id':str(nv.get('id') or ''),'name':str(nv.get('name') or typ),'type':typ,'x':x/sw,'y':y/sh,'w':w/sw,'h':h/sh,'text':text or '','has_text':text is not None,'z':zidx})
    return out


def _write_slide_edits(pptx, page, changes):
    page = max(0, int(page or 0)); slide_name = 'ppt/slides/slide%d.xml' % (page + 1); changes = {str(c.get('id')):c for c in (changes or []) if str(c.get('id') or '')}
    if not changes: return 0
    tmp = Path(str(pptx) + '.ace156.tmp'); changed = 0
    with zipfile.ZipFile(pptx, 'r') as zin:
        sw, sh = _slide_size(zin)
        if slide_name not in zin.namelist(): raise ValueError('That poster page does not exist.')
        root = ET.fromstring(zin.read(slide_name)); tree = root.find('.//p:spTree', NS)
        if tree is not None:
            for shape in list(tree):
                nv = _shape_nv(shape)
                if nv is None: continue
                c = changes.get(str(nv.get('id') or ''))
                if not c: continue
                xf, off, ext = _shape_xfrm(shape)
                if off is not None and ext is not None:
                    try:
                        x=max(0.0,min(1.0,float(c.get('x',0)))); y=max(0.0,min(1.0,float(c.get('y',0)))); w=max(.0001,min(1.0,float(c.get('w',.01)))); h=max(.0001,min(1.0,float(c.get('h',.01)))); x=min(x,max(0.0,1.0-w)); y=min(y,max(0.0,1.0-h)); off.set('x',str(int(round(x*sw)))); off.set('y',str(int(round(y*sh)))); ext.set('cx',str(max(1,int(round(w*sw))))); ext.set('cy',str(max(1,int(round(h*sh)))))
                    except Exception: pass
                if 'text' in c and c.get('text') is not None: _set_shape_text(shape,c.get('text'))
                changed += 1
        xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(tmp, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist(): zout.writestr(info, xml if info.filename == slide_name else zin.read(info.filename))
    os.replace(tmp, pptx); return changed


def _refresh_preview(job, pptx):
    try: thumb = _original_embedded(pptx) or _quicklook_once(pptx)
    except Exception: thumb = ''
    job['_ace_edit_revision'] = int(job.get('_ace_edit_revision') or 0) + 1
    if thumb:
        job['rendered_pages']=[thumb]; job['stage']='Ready'; return 'data:image/png;base64,'+thumb
    return ''


def _patched_do_get(self):
    try:
        parsed=ace.urllib.parse.urlparse(self.path)
        if parsed.path=='/api/studio/shapes':
            q=ace.urllib.parse.parse_qs(parsed.query); jid=str((q.get('job') or [''])[0]); page=int((q.get('page') or ['0'])[0] or 0); job,pptx=_job_and_pptx(jid); self.json_out({'ok':True,'job_id':jid,'page':page,'shapes':_slide_shapes(pptx,page)}); return
    except Exception as e:
        if ace.urllib.parse.urlparse(self.path).path=='/api/studio/shapes': self.json_out({'error':str(e)},500); return
    return _original_do_get(self)


def _patched_do_post(self):
    if self.path in {'/api/opendesign/cancel','/api/stop'}:
        try:
            d=ace.parse_json(self); jid=str(d.get('job_id') or '')
            if jid: _cancel_opendesign_job(jid)
            if self.path=='/api/stop': _stop_local_model()
            self.json_out({'ok':True}); return
        except Exception as e: self.json_out({'error':str(e)},500); return
    if self.path=='/api/studio/save':
        try:
            d=ace.parse_json(self); jid=str(d.get('job_id') or ''); page=int(d.get('page') or 0); job,pptx=_job_and_pptx(jid); n=_write_slide_edits(pptx,page,d.get('shapes') or []); preview=_refresh_preview(job,pptx); self.json_out({'ok':True,'saved':n,'preview_data_url':preview,'revision':int(job.get('_ace_edit_revision') or 0)}); return
        except Exception as e: self.json_out({'error':str(e)},500); return
    return _original_do_post(self)


ace._job_snapshot = _snapshot
ace.H.do_GET = _patched_do_get
ace.H.do_POST = _patched_do_post

if __name__ == '__main__':
    ace.main()
