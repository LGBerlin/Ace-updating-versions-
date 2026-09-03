#!/usr/bin/env python3
"""A.C.E. 1.6.6 artifact regression guard.

Restores the proven PPTX-backed poster preview/editor path without replacing the
current A.C.E. UI or research stack. It also makes the existing OpenDesign
transport self-heal by launching the user's local Open Design app headlessly when
its sidecar socket is absent.
"""
from pathlib import Path
from copy import deepcopy
import base64
import json
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

MARKER = 'ACE166_ARTIFACT_GUARD'
APP = Path(os.environ.get('ACE_OPEN_DESIGN_APP', '/Applications/Open Design.app'))
SOCKET = Path(os.environ.get('OD_SIDECAR_IPC_PATH', '/tmp/open-design/ipc/release-stable/daemon.sock'))
LOG = Path.home() / 'Library' / 'Logs' / 'ACE-OpenDesign.log'

_OD_LOCK = threading.Lock()
_OD_LAST_LAUNCH = 0.0

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
N = {'p': P, 'a': A}


def _log(message):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}\n')
    except Exception:
        pass


def ensure_open_design(wait=3.5):
    """Best-effort local OpenDesign startup. Never changes MCP configuration."""
    global _OD_LAST_LAUNCH
    if platform.system() != 'Darwin':
        return False
    if SOCKET.exists():
        return True
    if not APP.exists():
        _log(f'Open Design app not found: {APP}')
        return False
    now = time.monotonic()
    with _OD_LOCK:
        if SOCKET.exists():
            return True
        if now - _OD_LAST_LAUNCH > 10.0:
            _OD_LAST_LAUNCH = now
            try:
                subprocess.Popen(
                    ['/usr/bin/open', '-g', '-j', str(APP), '--args', '--headless'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                _log('Requested headless Open Design startup')
            except Exception as e:
                _log('Open Design startup failed: ' + str(e))
                return False
    deadline = time.monotonic() + max(0.0, float(wait))
    while time.monotonic() < deadline:
        if SOCKET.exists():
            _log('Open Design sidecar is ready')
            return True
        time.sleep(0.12)
    return SOCKET.exists()


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _presentation_size(z):
    root = ET.fromstring(z.read('ppt/presentation.xml'))
    s = root.find('.//p:sldSz', N)
    if s is None:
        return 12192000, 6858000
    return int(s.get('cx') or 12192000), int(s.get('cy') or 6858000)


def _nv(shape):
    return next((e for e in shape.iter() if _local(e.tag) == 'cNvPr'), None)


def _xfrm(shape):
    for e in shape.iter():
        if _local(e.tag) != 'xfrm':
            continue
        off = next((x for x in e if _local(x.tag) == 'off'), None)
        ext = next((x for x in e if _local(x.tag) == 'ext'), None)
        if off is not None and ext is not None:
            return off, ext
    return None, None


def _shape_text(shape):
    if _local(shape.tag) != 'sp':
        return None
    body = next((x for x in shape if _local(x.tag) == 'txBody'), None)
    if body is None:
        return None
    return '\n'.join(
        ''.join((x.text or '') for x in p.findall('.//a:t', N))
        for p in body.findall('a:p', N)
    ).rstrip('\n')


def _set_shape_text(shape, value):
    if _local(shape.tag) != 'sp':
        return
    body = next((x for x in shape if _local(x.tag) == 'txBody'), None)
    paragraphs = body.findall('a:p', N) if body is not None else []
    if not paragraphs:
        return
    base = paragraphs[0]
    for p in paragraphs[1:]:
        body.remove(p)
    for i, line in enumerate(str(value or '').split('\n')):
        p = base if i == 0 else deepcopy(base)
        if i:
            body.append(p)
        texts = p.findall('.//a:t', N)
        if texts:
            texts[0].text = line
            for extra in texts[1:]:
                extra.text = ''


def poster_shapes(path):
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        width, height = _presentation_size(z)
        root = ET.fromstring(z.read('ppt/slides/slide1.xml'))
    tree = root.find('.//p:spTree', N)
    out = []
    for zindex, shape in enumerate(list(tree or [])):
        if _local(shape.tag) not in {'sp', 'pic', 'graphicFrame', 'grpSp'}:
            continue
        nv = _nv(shape)
        off, ext = _xfrm(shape)
        if nv is None or off is None or ext is None:
            continue
        try:
            x = int(off.get('x') or 0)
            y = int(off.get('y') or 0)
            w = int(ext.get('cx') or 1)
            h = int(ext.get('cy') or 1)
        except Exception:
            continue
        text = _shape_text(shape)
        out.append({
            'id': str(nv.get('id') or ''),
            'name': nv.get('name') or _local(shape.tag),
            'x': x / width,
            'y': y / height,
            'w': w / width,
            'h': h / height,
            'text': text or '',
            'has_text': text is not None,
            'z': zindex,
        })
    return out


def write_poster(path, changes):
    path = Path(path)
    change_map = {str(c.get('id')): c for c in changes or [] if c.get('id')}
    temp = Path(str(path) + '.ace166.tmp')
    with zipfile.ZipFile(path) as zin:
        width, height = _presentation_size(zin)
        root = ET.fromstring(zin.read('ppt/slides/slide1.xml'))
    tree = root.find('.//p:spTree', N)
    for shape in list(tree or []):
        nv = _nv(shape)
        change = change_map.get(str(nv.get('id') or '')) if nv is not None else None
        if not change:
            continue
        off, ext = _xfrm(shape)
        if off is not None and ext is not None:
            w = max(0.001, min(1.0, float(change.get('w', 0.01))))
            h = max(0.001, min(1.0, float(change.get('h', 0.01))))
            x = max(0.0, min(1.0 - w, float(change.get('x', 0.0))))
            y = max(0.0, min(1.0 - h, float(change.get('y', 0.0))))
            off.set('x', str(round(x * width)))
            off.set('y', str(round(y * height)))
            ext.set('cx', str(max(1, round(w * width))))
            ext.set('cy', str(max(1, round(h * height))))
        if change.get('has_text') or 'text' in change:
            _set_shape_text(shape, change.get('text'))
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = xml if info.filename == 'ppt/slides/slide1.xml' else zin.read(info.filename)
            zout.writestr(info, data)
    os.replace(temp, path)


def _quicklook(path):
    try:
        if platform.system() != 'Darwin' or not Path('/usr/bin/qlmanage').exists():
            return ''
        with tempfile.TemporaryDirectory(prefix='ace166-preview-') as td:
            subprocess.run(
                ['/usr/bin/qlmanage', '-t', '-s', '1400', '-o', td, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
            imgs = [p for p in Path(td).iterdir() if p.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
            if imgs:
                return base64.b64encode(max(imgs, key=lambda p: p.stat().st_size).read_bytes()).decode('ascii')
    except Exception:
        pass
    return ''


def _job_file(ace, job_id):
    with ace.OPEN_DESIGN_LOCK:
        job = ace.OPEN_DESIGN_JOBS.get(str(job_id or ''))
    if not job:
        raise ValueError('Poster job is no longer available.')
    rel = str(job.get('pptx_rel') or '')
    path = (ace._project_cwd(str(job.get('project_id') or '')) / rel).resolve()
    if not path.is_file():
        raise ValueError('Editable PowerPoint could not be found.')
    return job, path


def _refresh_preview(ace, job, path):
    b64 = ''
    try:
        b64 = ace._pptx_embedded_thumbnail(path) or ''
    except Exception:
        pass
    if not b64:
        b64 = _quicklook(path)
    job['_ace166_edit_revision'] = int(job.get('_ace166_edit_revision') or 0) + 1
    if b64:
        job['rendered_pages'] = [b64]
        job['stage'] = 'Ready'
        return 'data:image/png;base64,' + b64
    return ''


def install_backend(ace):
    """Install narrow, route-specific wrappers on the current A.C.E. runtime."""
    original_snapshot = ace._job_snapshot
    original_get = ace.H.do_GET
    original_post = ace.H.do_POST
    original_od = getattr(ace, '_od_http_json', None)

    def snapshot(job):
        if str(job.get('kind') or '') == 'poster' and job.get('pptx_rel') and not (
            job.get('rendered_pages') or job.get('preview_rel') or job.get('daemon_preview_url')
        ):
            try:
                path = (ace._project_cwd(str(job.get('project_id') or '')) / str(job.get('pptx_rel'))).resolve()
                if path.is_file():
                    _refresh_preview(ace, job, path)
            except Exception:
                pass
        out = original_snapshot(job)
        out['edit_revision'] = int(job.get('_ace166_edit_revision') or job.get('_ace_edit_revision') or 0)
        return out

    def GET(self):
        try:
            parsed = ace.urllib.parse.urlparse(self.path)
            if parsed.path == '/api/studio/shapes':
                job_id = (ace.urllib.parse.parse_qs(parsed.query).get('job') or [''])[0]
                _job, path = _job_file(ace, job_id)
                self.json_out({'ok': True, 'shapes': poster_shapes(path)})
                return
        except Exception as e:
            try:
                if ace.urllib.parse.urlparse(self.path).path == '/api/studio/shapes':
                    self.json_out({'error': str(e)}, 500)
                    return
            except Exception:
                pass
        return original_get(self)

    def POST(self):
        if self.path == '/api/studio/save':
            try:
                data = ace.parse_json(self)
                job, path = _job_file(ace, data.get('job_id'))
                write_poster(path, data.get('shapes') or [])
                self.json_out({'ok': True, 'preview': _refresh_preview(ace, job, path)})
                return
            except Exception as e:
                self.json_out({'error': str(e)}, 500)
                return
        return original_post(self)

    ace._job_snapshot = snapshot
    ace.H.do_GET = GET
    ace.H.do_POST = POST

    if callable(original_od):
        def od_http_json(*args, **kwargs):
            ensure_open_design(wait=3.5)
            return original_od(*args, **kwargs)
        ace._od_http_json = od_http_json

    # Start OpenDesign opportunistically, but never block normal chat startup.
    threading.Thread(target=ensure_open_design, kwargs={'wait': 0.0}, name='ACE-OpenDesign-166', daemon=True).start()


CSS = r'''
/* ACE166_ARTIFACT_GUARD */
.ace166-poster-overlay{position:fixed;z-index:2147483000;border:1px solid #6FAE42;pointer-events:auto}
.ace166-poster-shape{position:absolute;box-sizing:border-box;border:1px dashed #85B764;background:#6FAE420d;cursor:move;min-width:5px;min-height:5px}
.ace166-poster-shape.sel{border:2px solid #6FAE42;background:#6FAE4222}
.ace166-poster-shape.txt:after{content:'T';position:absolute;right:2px;top:2px;background:#0E1A08dd;color:#E7E2D3;padding:1px 3px;border-radius:3px;font:700 8px sans-serif}
.ace166-poster-shape.inline{cursor:text;background:#E7E2D3;color:#0E1A08;padding:4px;overflow:auto;white-space:pre-wrap;font:12px/1.2 sans-serif;outline:none}
.ace166-poster-panel{position:fixed;z-index:2147483001;width:290px;max-height:75vh;overflow:auto;background:#132C0A;color:#E7E2D3;border:1px solid #6FAE4266;border-radius:12px;box-shadow:0 15px 40px #0008;padding:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.ace166-poster-panel h3{margin:0 0 6px;font-size:13px}.ace166-poster-panel .note{font-size:10.5px;color:#A5BE88;line-height:1.4}.ace166-poster-panel .nm{font-size:10px;color:#85B764;margin:8px 0 4px}
.ace166-poster-panel textarea{width:100%;min-height:110px;box-sizing:border-box;background:#0E2308;color:#E7E2D3;border:1px solid #6FAE4266;border-radius:7px;padding:7px}
.ace166-poster-panel .a{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.ace166-poster-panel button{border:1px solid #6FAE4266;background:#0E2308;color:#E7E2D3;border-radius:7px;padding:6px 8px;cursor:pointer}.ace166-poster-panel .save{background:#6FAE42;color:#0E1A08;font-weight:700}.ace166-poster-panel .st{font-size:10px;color:#A5BE88;min-height:14px;margin-top:6px}
'''

JS = r'''
(function(){
  if(window.__ACE166_POSTER_GUARD__)return;window.__ACE166_POSTER_GUARD__=1;
  const q=id=>document.getElementById(id);
  let E={on:false,o:null,p:null,img:null,ss:[],sel:null,dirty:false,raf:0};
  function root(){return q('artifactStudio')||document.querySelector('.artifact-studio')||document.body;}
  function currentPoster(){try{return typeof studioJob!=='undefined'&&studioJob&&studioJob.job_id&&String(studioJob.kind||'')==='poster';}catch(_){return false;}}
  function previewImage(){const a=[...root().querySelectorAll('img')].filter(x=>{const r=x.getBoundingClientRect();return r.width>80&&r.height>80;});a.sort((x,y)=>{x=x.getBoundingClientRect();y=y.getBoundingClientRect();return y.width*y.height-x.width*x.height;});return a[0]||null;}
  async function waitImage(){for(let i=0;i<16;i++){const x=previewImage();if(x)return x;await new Promise(r=>setTimeout(r,180));}return null;}
  function pos(){if(!E.on||!E.img)return;const r=E.img.getBoundingClientRect();Object.assign(E.o.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});Object.assign(E.p.style,{left:Math.max(8,Math.min(innerWidth-302,r.right+10))+'px',top:Math.max(8,Math.min(innerHeight-250,r.top))+'px'});}
  function status(t,bad){const x=E.p&&E.p.querySelector('.st');if(x){x.textContent=t;x.style.color=bad?'#ff8c8c':'#A5BE88';}}
  function select(s,d){E.sel=s;[...E.o.children].forEach(x=>x.classList.toggle('sel',x===d));E.p.querySelector('.nm').textContent=s.name||('Object '+s.id);const t=E.p.querySelector('textarea');t.disabled=!s.has_text;t.value=s.has_text?s.text||'':'';}
  function box(s){const d=document.createElement('div');d.className='ace166-poster-shape'+(s.has_text?' txt':'');d.dataset.id=s.id;d.style.cssText+=`left:${s.x*100}%;top:${s.y*100}%;width:${s.w*100}%;height:${s.h*100}%`;d.onclick=e=>{e.stopPropagation();select(s,d);};d.ondblclick=e=>{if(!s.has_text)return;e.stopPropagation();select(s,d);d.className='ace166-poster-shape inline sel';d.contentEditable=true;d.textContent=s.text||'';d.focus();d.onblur=()=>{s.text=d.innerText.replace(/\r/g,'');E.dirty=true;d.contentEditable=false;d.textContent='';d.className='ace166-poster-shape txt sel';E.p.querySelector('textarea').value=s.text;};};d.onpointerdown=e=>{if(d.isContentEditable)return;e.preventDefault();e.stopPropagation();select(s,d);const r=E.o.getBoundingClientRect(),sx=e.clientX,sy=e.clientY,ox=s.x,oy=s.y;const mv=v=>{s.x=Math.max(0,Math.min(1-s.w,ox+(v.clientX-sx)/r.width));s.y=Math.max(0,Math.min(1-s.h,oy+(v.clientY-sy)/r.height));d.style.left=s.x*100+'%';d.style.top=s.y*100+'%';E.dirty=true;};const up=()=>{removeEventListener('pointermove',mv,true);removeEventListener('pointerup',up,true);};addEventListener('pointermove',mv,true);addEventListener('pointerup',up,true);};return d;}
  function panel(){const p=document.createElement('div');p.className='ace166-poster-panel';p.innerHTML='<h3>Edit poster</h3><div class="note">Drag outlined objects. Double-click text to type directly, or select it and rewrite it below. Save changes updates the PowerPoint used by Download/Export.</div><div class="nm">Select an object</div><textarea disabled></textarea><div class="a"><button class="save">Save changes</button><button class="apply">Apply text</button><button class="done">Done</button></div><div class="st"></div>';const t=p.querySelector('textarea');t.oninput=()=>{if(E.sel&&E.sel.has_text){E.sel.text=t.value;E.dirty=true;}};p.querySelector('.apply').onclick=()=>{if(E.sel&&E.sel.has_text){E.sel.text=t.value;E.dirty=true;status('Text changed — save when ready.');}};p.querySelector('.save').onclick=save;p.querySelector('.done').onclick=async()=>{if(E.dirty&&confirm('Save your poster changes?')){await save();if(E.dirty)return;}close();};return p;}
  async function save(){if(!currentPoster())return;status('Saving into PowerPoint…');try{const r=await fetch('/api/studio/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:studioJob.job_id,page:0,shapes:E.ss})}),d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Save failed');E.dirty=false;if(d.preview&&E.img)E.img.src=d.preview;status('Saved. Download/Export will use this edited poster.');}catch(e){status(e.message||String(e),true);}}
  function close(){E.on=false;if(E.raf)cancelAnimationFrame(E.raf);E.o&&E.o.remove();E.p&&E.p.remove();E={on:false,o:null,p:null,img:null,ss:[],sel:null,dirty:false,raf:0};}
  async function open(){if(E.on||!currentPoster())return;E.img=await waitImage();if(!E.img)return alert('Poster preview is not ready yet.');try{const r=await fetch('/api/studio/shapes?job='+encodeURIComponent(studioJob.job_id)),d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Could not load poster objects');E.ss=d.shapes||[];if(!E.ss.length)throw Error('No editable objects were found.');try{if(typeof disableStudioEditing==='function')disableStudioEditing();}catch(_){}E.o=document.createElement('div');E.o.className='ace166-poster-overlay';E.ss.forEach(s=>E.o.appendChild(box(s)));E.p=panel();document.body.append(E.o,E.p);E.on=true;pos();const loop=()=>{if(E.on){pos();E.raf=requestAnimationFrame(loop);}};loop();status('Editing the real PowerPoint poster.');}catch(e){close();alert('Poster editor could not open: '+(e.message||e));}}
  window.acePosterEdit166=open;
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('#studioEdit');if(!b||!currentPoster())return;e.preventDefault();e.stopImmediatePropagation();open();},true);
  addEventListener('resize',pos,true);addEventListener('scroll',pos,true);
})();
// ACE166_ARTIFACT_GUARD
'''


def patch_frontend(directory):
    root = Path(directory)
    js = root / 'app.js'
    css = root / 'app.css'
    index = root / 'index.html'
    if js.is_file():
        source = js.read_text(encoding='utf-8')
        if MARKER not in source:
            js.write_text(source + '\n' + JS + '\n', encoding='utf-8')
    if css.is_file():
        source = css.read_text(encoding='utf-8')
        if MARKER not in source:
            css.write_text(source + '\n' + CSS + '\n', encoding='utf-8')
    if index.is_file():
        source = index.read_text(encoding='utf-8')
        source = re.sub(r'app\.js\?v=[^"\']+', 'app.js?v=166-regression', source, count=1)
        source = re.sub(r'app\.css\?v=[^"\']+', 'app.css?v=166-regression', source, count=1)
        source = re.sub(r'Current version: v1\.6\.[0-9]+', 'Current version: v1.6.6', source, count=1)
        if '<!--ACE166_REGRESSION-->' not in source:
            source += '\n<!--ACE166_REGRESSION-->\n'
        index.write_text(source, encoding='utf-8')
