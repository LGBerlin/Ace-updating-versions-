#!/usr/bin/env python3
"""A.C.E. 1.5.6: composer Stop + PPTX-backed poster editor."""
from pathlib import Path
from copy import deepcopy
import base64,importlib.util,os,platform,subprocess,tempfile,time,zipfile
import xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent

def patch(p,m,f):
 try:
  p=Path(p);s=p.read_text('utf-8')
  if m in s:return
  n=f(s)
  if n!=s:p.write_text(n,'utf-8')
 except Exception:pass

def idx(s):
 return s.replace('app.css?v=155-controls','app.css?v=156-editor').replace('app.js?v=155-controls','app.js?v=156-editor').replace('Current version: v1.5.5','Current version: v1.5.6')+'\n<!--ACE156-->\n'
CSS=r'''#sendBtn.aceStop156{background:#f2f3f4!important;color:#111!important}#sendBtn .sq156{display:block;width:11px;height:11px;background:currentColor;border-radius:2px;margin:auto}.e156o{position:fixed;z-index:2147483000;border:1px solid #4ce0ff;pointer-events:auto}.e156s{position:absolute;box-sizing:border-box;border:1px dashed #4ce0ff;background:#4ce0ff08;cursor:move;min-width:5px;min-height:5px}.e156s.sel{border:2px solid #19cce9;background:#19cce918}.e156s.txt:after{content:'T';position:absolute;right:2px;top:2px;background:#071019cc;color:#dff8ff;padding:1px 3px;border-radius:3px;font:700 8px sans-serif}.e156s.inline{cursor:text;background:#fffffff2;color:#111;padding:4px;overflow:auto;white-space:pre-wrap;font:12px/1.2 sans-serif;outline:none}.e156p{position:fixed;z-index:2147483001;width:290px;max-height:75vh;overflow:auto;background:#0b131c;color:#e7f5fb;border:1px solid #4ce0ff44;border-radius:12px;box-shadow:0 15px 40px #0008;padding:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.e156p h3{margin:0 0 6px;font-size:13px}.e156p .note{font-size:10.5px;color:#91a7b5;line-height:1.4}.e156p .nm{font-size:10px;color:#4ce0ff;margin:8px 0 4px}.e156p textarea{width:100%;min-height:110px;box-sizing:border-box;background:#071019;color:#e7f5fb;border:1px solid #4ce0ff44;border-radius:7px;padding:7px}.e156p .a{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.e156p button{border:1px solid #4ce0ff44;background:#101c28;color:#dff3fb;border-radius:7px;padding:6px 8px;cursor:pointer}.e156p .save{background:#24cfe9;color:#061015;font-weight:700}.e156p .st{font-size:10px;color:#9ab0bc;min-height:14px;margin-top:6px}'''
JS=r'''(function(){if(window.ACE156)return;window.ACE156=1;const q=id=>document.getElementById(id);let old=null;function active(){try{return typeof aceWorkActive==='function'&&aceWorkActive()}catch(e){return false}}function sync(){let b=q('sendBtn');if(!b)return;if(old===null)old=b.innerHTML;if(active()){b.disabled=false;b.dataset.stop156=1;b.classList.add('aceStop156');b.innerHTML='<span class="sq156"></span>';b.title='Stop A.C.E.'}else if(b.dataset.stop156){delete b.dataset.stop156;b.classList.remove('aceStop156');b.innerHTML=old;b.title='Send'}}document.addEventListener('click',e=>{let b=e.target.closest&&e.target.closest('#sendBtn');if(b&&b.dataset.stop156){e.preventDefault();e.stopImmediatePropagation();try{stopAceEverything()}catch(x){try{cancelSpeech()}catch(y){}}}},true);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&active())try{stopAceEverything()}catch(x){}},true);setInterval(sync,100);sync();
let E={on:0,o:null,p:null,img:null,ss:[],sel:null,dirty:0,raf:0};function root(){return q('artifactStudio')||document.querySelector('.artifact-studio')||document.body}function img(){let a=[...root().querySelectorAll('img')].filter(x=>{let r=x.getBoundingClientRect();return r.width>80&&r.height>80});a.sort((x,y)=>{x=x.getBoundingClientRect();y=y.getBoundingClientRect();return y.width*y.height-x.width*x.height});return a[0]}function pos(){if(!E.on)return;let r=E.img.getBoundingClientRect();Object.assign(E.o.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});Object.assign(E.p.style,{left:Math.max(8,Math.min(innerWidth-302,r.right+10))+'px',top:Math.max(8,Math.min(innerHeight-250,r.top))+'px'})}function st(t,b){let x=E.p&&E.p.querySelector('.st');if(x){x.textContent=t;x.style.color=b?'#ff8c8c':'#9ab0bc'}}function box(s){let d=document.createElement('div');d.className='e156s'+(s.has_text?' txt':'');d.dataset.id=s.id;d.style.cssText+=`left:${s.x*100}%;top:${s.y*100}%;width:${s.w*100}%;height:${s.h*100}%`;d.onclick=e=>{e.stopPropagation();sel(s,d)};d.ondblclick=e=>{if(!s.has_text)return;e.stopPropagation();sel(s,d);d.className='e156s inline sel';d.contentEditable=true;d.textContent=s.text||'';d.focus();d.onblur=()=>{s.text=d.innerText.replace(/\r/g,'');E.dirty=1;d.contentEditable=false;d.textContent='';d.className='e156s txt sel';E.p.querySelector('textarea').value=s.text}};d.onpointerdown=e=>{if(d.isContentEditable)return;e.preventDefault();e.stopPropagation();sel(s,d);let r=E.o.getBoundingClientRect(),sx=e.clientX,sy=e.clientY,ox=s.x,oy=s.y;let mv=v=>{s.x=Math.max(0,Math.min(1-s.w,ox+(v.clientX-sx)/r.width));s.y=Math.max(0,Math.min(1-s.h,oy+(v.clientY-sy)/r.height));d.style.left=s.x*100+'%';d.style.top=s.y*100+'%';E.dirty=1},up=()=>{removeEventListener('pointermove',mv,true);removeEventListener('pointerup',up,true)};addEventListener('pointermove',mv,true);addEventListener('pointerup',up,true)};return d}function sel(s,d){E.sel=s;[...E.o.children].forEach(x=>x.classList.toggle('sel',x===d));E.p.querySelector('.nm').textContent=s.name||('Object '+s.id);let t=E.p.querySelector('textarea');t.disabled=!s.has_text;t.value=s.has_text?s.text||'':''}function panel(){let p=document.createElement('div');p.className='e156p';p.innerHTML='<h3>Edit poster</h3><div class="note">Drag outlined objects. Double-click text to type directly, or select it and rewrite it below. Save changes updates the actual PowerPoint used by Download/Export.</div><div class="nm">Select an object</div><textarea disabled></textarea><div class="a"><button class="save">Save changes</button><button class="apply">Apply text</button><button class="done">Done</button></div><div class="st"></div>';let t=p.querySelector('textarea');t.oninput=()=>{if(E.sel&&E.sel.has_text){E.sel.text=t.value;E.dirty=1}};p.querySelector('.apply').onclick=()=>{if(E.sel&&E.sel.has_text){E.sel.text=t.value;E.dirty=1;st('Text changed — save when ready.')}};p.querySelector('.save').onclick=save;p.querySelector('.done').onclick=async()=>{if(E.dirty&&confirm('Save your poster changes?'))await save();close()};return p}async function save(){if(typeof studioJob==='undefined'||!studioJob||!studioJob.job_id)return;st('Saving into PowerPoint…');try{let r=await fetch('/api/studio/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:studioJob.job_id,page:0,shapes:E.ss})}),d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Save failed');E.dirty=0;if(d.preview&&E.img)E.img.src=d.preview;st('Saved. Download/Export will use this edited poster.')}catch(e){st(e.message,1)}}function close(){E.on=0;if(E.raf)cancelAnimationFrame(E.raf);E.o&&E.o.remove();E.p&&E.p.remove();E={on:0,o:null,p:null,img:null,ss:[],sel:null,dirty:0,raf:0}}async function open(){if(E.on)return;E.img=img();if(!E.img)return alert('Poster preview is not ready yet.');try{if(typeof studioJob==='undefined'||!studioJob||!studioJob.job_id)throw Error('No editable poster is open.');let r=await fetch('/api/studio/shapes?job='+encodeURIComponent(studioJob.job_id)),d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Could not load poster objects');E.ss=d.shapes||[];if(!E.ss.length)throw Error('No editable objects were found.');try{disableStudioEditing()}catch(x){}E.o=document.createElement('div');E.o.className='e156o';E.ss.forEach(s=>E.o.appendChild(box(s)));E.p=panel();document.body.append(E.o,E.p);E.on=1;pos();let loop=()=>{if(E.on){pos();E.raf=requestAnimationFrame(loop)}};loop();st('Editing the real PowerPoint poster.')}catch(e){close();alert('Poster editor could not open: '+e.message)}}window.acePosterEdit156=open;document.addEventListener('click',e=>{let b=e.target.closest&&e.target.closest('button,a,[role=button]');if(!b||!root().contains(b))return;let t=((b.textContent||'')+' '+(b.title||'')+' '+(b.getAttribute('aria-label')||'')).trim();if(/^edit\b/i.test(t)){e.preventDefault();e.stopImmediatePropagation();open()}},true);addEventListener('resize',pos,true);addEventListener('scroll',pos,true)})();'''
patch(H/'index.html','ACE156',idx);patch(H/'app.css','ACE156',lambda s:s+'\n'+CSS+'\n/*ACE156*/\n');patch(H/'app.js','ACE156',lambda s:s+'\n'+JS+'\n//ACE156\n')

spec=importlib.util.spec_from_file_location('ace_server_runtime',str(H/'ACE Server.py'));ace=importlib.util.module_from_spec(spec);spec.loader.exec_module(ace);ace.VERSION='1.5.6'
try:ace.UPDATE_STATE['current_version']='1.5.6'
except Exception:pass
snap0=ace._job_snapshot;emb=ace._pptx_embedded_thumbnail;post0=ace.H.do_POST;get0=ace.H.do_GET

def ql(p):
 try:
  if platform.system()!='Darwin':return''
  with tempfile.TemporaryDirectory() as td:
   subprocess.run(['/usr/bin/qlmanage','-t','-s','1400','-o',td,str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12)
   a=[x for x in Path(td).iterdir() if x.suffix.lower() in {'.png','.jpg','.jpeg'}]
   return base64.b64encode(max(a,key=lambda x:x.stat().st_size).read_bytes()).decode() if a else''
 except Exception:return''
def refresh(j,p):
 b=emb(p) or ql(p);j['_ace_edit_revision']=int(j.get('_ace_edit_revision') or 0)+1
 if b:j['rendered_pages']=[b];j['stage']='Ready';return'data:image/png;base64,'+b
 return''
def snap(j):
 if str(j.get('kind')or'')=='poster' and j.get('pptx_rel') and not(j.get('rendered_pages')or j.get('preview_rel')or j.get('daemon_preview_url')):
  try:
   p=(ace._project_cwd(str(j.get('project_id')or''))/str(j.get('pptx_rel'))).resolve();b=emb(p) or ql(p)
   if b:j['rendered_pages']=[b];j['stage']='Ready'
  except Exception:pass
 s=snap0(j);s['edit_revision']=int(j.get('_ace_edit_revision')or 0);return s
def stopjob(i):
 try:
  with ace.OPEN_DESIGN_LOCK:j=ace.OPEN_DESIGN_JOBS.get(str(i or''))
  if not j:return
  for k in('run_id','persist_run_id','export_run_id'):
   r=str(j.get(k)or'')
   if r:
    try:ace._od_http_json('POST','/api/runs/'+ace.urllib.parse.quote(r,safe='')+'/cancel',{},timeout=8)
    except Exception:pass
  j['status']='canceled';j['stage']='Canceled';j['error']=''
 except Exception:pass
def stopmodel():
 try:
  m=ace.choose_model(ace.ollama_models());b=ace.ollama_binary()
  if m and b:subprocess.Popen([b,'stop',m],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 except Exception:pass
P='http://schemas.openxmlformats.org/presentationml/2006/main';A='http://schemas.openxmlformats.org/drawingml/2006/main';N={'p':P,'a':A}
def loc(t):return t.rsplit('}',1)[-1]
def jobfile(i):
 with ace.OPEN_DESIGN_LOCK:j=ace.OPEN_DESIGN_JOBS.get(str(i or''))
 if not j:raise ValueError('Poster job is no longer available.')
 p=(ace._project_cwd(str(j.get('project_id')or''))/str(j.get('pptx_rel')or'')).resolve()
 if not p.is_file():raise ValueError('Editable PowerPoint could not be found.')
 return j,p
def size(z):
 r=ET.fromstring(z.read('ppt/presentation.xml'));s=r.find('.//p:sldSz',N);return(int(s.get('cx')),int(s.get('cy'))) if s is not None else(12192000,6858000)
def nv(s):return next((e for e in s.iter() if loc(e.tag)=='cNvPr'),None)
def xf(s):
 for e in s.iter():
  if loc(e.tag)=='xfrm':
   o=next((x for x in e if loc(x.tag)=='off'),None);x=next((x for x in e if loc(x.tag)=='ext'),None)
   if o is not None and x is not None:return o,x
 return None,None
def text(s):
 if loc(s.tag)!='sp':return None
 t=next((x for x in s if loc(x.tag)=='txBody'),None)
 if t is None:return None
 return'\n'.join(''.join((x.text or'') for x in p.findall('.//a:t',N)) for p in t.findall('a:p',N)).rstrip('\n')
def settext(s,v):
 if loc(s.tag)!='sp':return
 t=next((x for x in s if loc(x.tag)=='txBody'),None);ps=t.findall('a:p',N) if t is not None else[]
 if not ps:return
 b=ps[0]
 for p in ps[1:]:t.remove(p)
 for i,line in enumerate(str(v or'').split('\n')):
  p=b if i==0 else deepcopy(b)
  if i:t.append(p)
  ts=p.findall('.//a:t',N)
  if ts:
   ts[0].text=line
   for x in ts[1:]:x.text=''
def shapes(p):
 with zipfile.ZipFile(p) as z:w,h=size(z);r=ET.fromstring(z.read('ppt/slides/slide1.xml'))
 tr=r.find('.//p:spTree',N);out=[]
 for k,s in enumerate(list(tr or[])):
  if loc(s.tag) not in{'sp','pic','graphicFrame','grpSp'}:continue
  n=nv(s);o,x=xf(s)
  if n is None or o is None:continue
  try:a,b,c,d=int(o.get('x') or 0),int(o.get('y') or 0),int(x.get('cx') or 1),int(x.get('cy') or 1)
  except Exception:continue
  t=text(s);out.append({'id':str(n.get('id')or''),'name':n.get('name')or loc(s.tag),'x':a/w,'y':b/h,'w':c/w,'h':d/h,'text':t or'','has_text':t is not None,'z':k})
 return out
def write(p,cs):
 C={str(c.get('id')):c for c in cs if c.get('id')};tmp=Path(str(p)+'.tmp')
 with zipfile.ZipFile(p) as zin:w,h=size(zin);r=ET.fromstring(zin.read('ppt/slides/slide1.xml'));tr=r.find('.//p:spTree',N)
 for s in list(tr or[]):
  n=nv(s);c=C.get(str(n.get('id')or'')) if n is not None else None
  if not c:continue
  o,x=xf(s)
  if o is not None:
   X=max(0,min(1-float(c.get('w',.01)),float(c.get('x',0))));Y=max(0,min(1-float(c.get('h',.01)),float(c.get('y',0))));o.set('x',str(round(X*w)));o.set('y',str(round(Y*h)));x.set('cx',str(max(1,round(float(c.get('w',.01))*w))));x.set('cy',str(max(1,round(float(c.get('h',.01))*h))))
  if c.get('has_text') or 'text'in c:settext(s,c.get('text'))
 xml=ET.tostring(r,encoding='utf-8',xml_declaration=True)
 with zipfile.ZipFile(p) as zin,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as zout:
  for i in zin.infolist():zout.writestr(i,xml if i.filename=='ppt/slides/slide1.xml' else zin.read(i.filename))
 os.replace(tmp,p)
def GET(self):
 try:
  u=ace.urllib.parse.urlparse(self.path)
  if u.path=='/api/studio/shapes':
   i=(ace.urllib.parse.parse_qs(u.query).get('job')or[''])[0];j,p=jobfile(i);self.json_out({'ok':True,'shapes':shapes(p)});return
 except Exception as e:
  if ace.urllib.parse.urlparse(self.path).path=='/api/studio/shapes':self.json_out({'error':str(e)},500);return
 return get0(self)
def POST(self):
 if self.path in{'/api/stop','/api/opendesign/cancel'}:
  try:d=ace.parse_json(self);stopjob(d.get('job_id'));stopmodel() if self.path=='/api/stop' else None;self.json_out({'ok':True});return
  except Exception as e:self.json_out({'error':str(e)},500);return
 if self.path=='/api/studio/save':
  try:d=ace.parse_json(self);j,p=jobfile(d.get('job_id'));write(p,d.get('shapes')or[]);self.json_out({'ok':True,'preview':refresh(j,p)});return
  except Exception as e:self.json_out({'error':str(e)},500);return
 return post0(self)
ace._job_snapshot=snap;ace.H.do_GET=GET;ace.H.do_POST=POST
if __name__=='__main__':ace.main()
