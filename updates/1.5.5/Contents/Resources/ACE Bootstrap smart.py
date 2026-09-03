#!/usr/bin/env python3
"""A.C.E. version-aware safe updater.

This layer persists across release updates. It reads upgrade-index.json, selects
only the next compatible manifest for the running version, verifies every
SHA-256, installs the patch while preserving this wrapper, and restarts A.C.E.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

INDEX_URL = 'https://raw.githubusercontent.com/LGBerlin/Ace-updating-versions-/main/upgrade-index.json'
REPO_RAW = 'https://raw.githubusercontent.com/LGBerlin/Ace-updating-versions-/main'
CORE_REL = 'Contents/Resources/ACE Release Core.py'
BOOTSTRAP_REL = 'Contents/Resources/ACE Bootstrap.py'
MARKER = 'ACE_SMART_UPDATER_V1'

SMART_JS = r'''(function(){
  if(window.__ACE_SMART_UPDATER_V1__) return;
  window.__ACE_SMART_UPDATER_V1__ = 1;
  let available = null;
  let checking = false;

  function chip(){ return document.getElementById('updateChip'); }

  function addStyle(){
    if(document.getElementById('aceSmartUpdateStyle')) return;
    const s=document.createElement('style');
    s.id='aceSmartUpdateStyle';
    s.textContent=`
      #aceSmartUpdateBackdrop{position:fixed;inset:0;z-index:2147483646;background:rgba(2,10,3,.78);display:grid;place-items:center;padding:24px}
      #aceSmartUpdateBackdrop.hidden{display:none}
      #aceSmartUpdateCard{width:min(560px,92vw);background:#0b1d0b;color:#e8f7dc;border:1px solid #355f31;border-radius:16px;box-shadow:0 24px 70px rgba(0,0,0,.55);padding:22px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      #aceSmartUpdateCard h2{margin:0 0 8px;font-size:21px}
      #aceSmartUpdateCard .aceSuVersion{color:#9adf59;font-weight:750;margin:0 0 12px}
      #aceSmartUpdateCard .aceSuNotes{color:#bdd4ae;line-height:1.45;white-space:pre-wrap;max-height:240px;overflow:auto}
      #aceSmartUpdateCard .aceSuStatus{margin-top:14px;color:#a9c49a;min-height:20px}
      #aceSmartUpdateCard .aceSuActions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}
      #aceSmartUpdateCard button{border:1px solid #466f40;background:#132b13;color:#e7f7df;border-radius:9px;padding:9px 13px;cursor:pointer;font-weight:650}
      #aceSmartUpdateCard button.aceSuPrimary{background:#8bd34a;color:#071306;border-color:#8bd34a}
      #aceSmartUpdateCard button:disabled{opacity:.55;cursor:default}
    `;
    document.head.appendChild(s);
  }

  function modal(){
    let b=document.getElementById('aceSmartUpdateBackdrop');
    if(b) return b;
    addStyle();
    b=document.createElement('div');
    b.id='aceSmartUpdateBackdrop';
    b.className='hidden';
    b.innerHTML=`<div id="aceSmartUpdateCard" role="dialog" aria-modal="true" aria-label="A.C.E. update">
      <h2>A.C.E. Update</h2>
      <div class="aceSuVersion" id="aceSuVersion"></div>
      <div class="aceSuNotes" id="aceSuNotes"></div>
      <div class="aceSuStatus" id="aceSuStatus"></div>
      <div class="aceSuActions"><button id="aceSuClose">Close</button><button class="aceSuPrimary" id="aceSuInstall">Update A.C.E.</button></div>
    </div>`;
    document.body.appendChild(b);
    b.querySelector('#aceSuClose').onclick=()=>b.classList.add('hidden');
    b.addEventListener('click',e=>{if(e.target===b)b.classList.add('hidden')});
    b.querySelector('#aceSuInstall').onclick=installUpdate;
    return b;
  }

  function renderModal(){
    const b=modal(),v=b.querySelector('#aceSuVersion'),n=b.querySelector('#aceSuNotes'),st=b.querySelector('#aceSuStatus'),ib=b.querySelector('#aceSuInstall');
    if(available && available.available){
      v.textContent='A.C.E. '+available.version+' is ready';
      n.textContent=available.notes||'';
      st.textContent='Compatible with your installed A.C.E. '+available.current+'.';
      ib.disabled=false;
    }else{
      v.textContent='A.C.E. is up to date';
      n.textContent='';
      st.textContent=available && available.error ? available.error : 'No compatible update is currently published.';
      ib.disabled=true;
    }
    b.classList.remove('hidden');
  }

  async function checkUpdate(){
    if(checking) return available;
    checking=true;
    try{
      const r=await fetch('/api/smart-update/check?ts='+Date.now(),{cache:'no-store'});
      const d=await r.json();
      if(!r.ok || !d.ok) throw new Error(d.error||'Update check failed');
      available=d;
      const c=chip();
      if(c){
        c.classList.toggle('hidden',!d.available);
        c.title=d.available ? ('A.C.E. '+d.version+' available') : 'A.C.E. is up to date';
        if(d.available) c.textContent='UPDATE';
      }
      return d;
    }catch(e){
      available={ok:false,available:false,error:String(e.message||e)};
      return available;
    }finally{checking=false;}
  }

  async function installUpdate(){
    const b=modal(),ib=b.querySelector('#aceSuInstall'),st=b.querySelector('#aceSuStatus');
    ib.disabled=true;st.textContent='Downloading and verifying update…';
    try{
      const r=await fetch('/api/smart-update/install',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const d=await r.json();
      if(!r.ok || !d.ok) throw new Error(d.error||'Update failed');
      st.textContent='A.C.E. '+d.version+' installed. Restarting…';
    }catch(e){st.textContent='Update failed: '+String(e.message||e);ib.disabled=false;}
  }

  document.addEventListener('click',async e=>{
    const b=e.target && e.target.closest ? e.target.closest('#updateChip') : null;
    if(!b) return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    await checkUpdate();renderModal();
  },true);

  window.aceSmartUpdateCheck=checkUpdate;
  setTimeout(checkUpdate,900);
  setTimeout(checkUpdate,3500);
  setInterval(checkUpdate,60000);
})();
// ACE_SMART_UPDATER_V1
'''


def _send_json(handler, status, data):
    body=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type','application/json; charset=utf-8')
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate')
    handler.send_header('Content-Length',str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _fetch_bytes(url, timeout=20):
    sep='&' if '?' in url else '?'
    req=urllib.request.Request(url+sep+'_ace_ts='+str(int(time.time()*1000)),headers={'User-Agent':'A.C.E.-Updater/1','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()


def _fetch_json(url, timeout=20):
    return json.loads(_fetch_bytes(url,timeout=timeout).decode('utf-8'))


def _safe_rel(rel):
    rel=str(rel or '').replace('\\','/')
    if not rel.startswith('Contents/') or rel.startswith('/') or '..' in Path(rel).parts:
        raise ValueError('Unsafe update path: '+rel)
    return rel


def _resolve_file_url(value):
    value=str(value or '')
    if value.startswith('https://') or value.startswith('http://'):
        return value
    return REPO_RAW.rstrip('/')+'/'+value.lstrip('/')


def _route_for(current):
    index=_fetch_json(INDEX_URL)
    return (index.get('routes') or {}).get(str(current))


def _manifest_for(current):
    route=_route_for(current)
    if not route:
        return None,None
    manifest_url=str(route.get('manifest_url') or '')
    if not manifest_url:
        raise ValueError('Upgrade route has no manifest URL.')
    manifest=_fetch_json(manifest_url)
    expected=str(route.get('version') or '')
    actual=str(manifest.get('version') or '')
    base=str((manifest.get('patch') or {}).get('base') or '')
    if not expected or actual!=expected:
        raise ValueError('Upgrade route version does not match its manifest.')
    if base!=str(current):
        raise ValueError('Update package expects A.C.E. '+base+', but this copy is '+str(current)+'.')
    return route,manifest


def _install_manifest(manifest, resources_dir):
    app_root=resources_dir.parent.parent
    files=(manifest.get('patch') or {}).get('files') or []
    if not files:
        raise ValueError('Update package contains no files.')
    with tempfile.TemporaryDirectory(prefix='ace_smart_update_') as td:
        td=Path(td);staged=[]
        for i,item in enumerate(files):
            rel=_safe_rel(item.get('path'))
            target_rel=CORE_REL if rel==BOOTSTRAP_REL else rel
            expected=str(item.get('sha256') or '').lower()
            if len(expected)!=64: raise ValueError('Update package has an invalid SHA-256.')
            data=_fetch_bytes(_resolve_file_url(item.get('url')),timeout=45)
            if hashlib.sha256(data).hexdigest()!=expected:
                raise ValueError('Integrity check failed for '+Path(rel).name+'.')
            p=td/('file-%03d'%i);p.write_bytes(data);staged.append((p,target_rel,item.get('mode')))
        backups=[]
        try:
            for src,rel,mode in staged:
                dest=app_root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
                existed=dest.exists();old=dest.read_bytes() if existed and dest.is_file() else None;old_mode=(dest.stat().st_mode&0o777) if existed else None
                backups.append((dest,existed,old,old_mode))
                temp_dest=dest.with_name(dest.name+'.ace-new');temp_dest.write_bytes(src.read_bytes())
                try: os.chmod(temp_dest,int(str(mode or '644'),8))
                except Exception: os.chmod(temp_dest,0o644)
                os.replace(temp_dest,dest)
        except Exception:
            for dest,existed,old,old_mode in reversed(backups):
                try:
                    if existed:
                        dest.write_bytes(old or b'')
                        if old_mode is not None: os.chmod(dest,old_mode)
                    elif dest.exists(): dest.unlink()
                except Exception: pass
            raise
    pc=resources_dir/'__pycache__'
    if pc.exists(): shutil.rmtree(pc,ignore_errors=True)
    try: subprocess.run(['/usr/bin/xattr','-dr','com.apple.quarantine',str(app_root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
    except Exception: pass
    return app_root


def _restart(app_root):
    time.sleep(1.2)
    try: subprocess.Popen(['/usr/bin/open','-n',str(app_root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception: pass


def _patch_js(resources_dir):
    p=resources_dir/'app.js'
    try:
        text=p.read_text(encoding='utf-8')
        if MARKER not in text: p.write_text(text+'\n'+SMART_JS+'\n',encoding='utf-8')
    except Exception: pass


def install(ace, resources_dir):
    resources_dir=Path(resources_dir);_patch_js(resources_dir)
    old_get=ace.H.do_GET;old_post=ace.H.do_POST

    def do_get(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/smart-update/check':
            current=str(getattr(ace,'VERSION','') or '')
            try:
                route,manifest=_manifest_for(current)
                if not route: return _send_json(self,200,{'ok':True,'current':current,'available':False})
                return _send_json(self,200,{'ok':True,'current':current,'available':True,'version':str(manifest.get('version') or ''),'notes':str(manifest.get('notes') or '')})
            except Exception as e: return _send_json(self,500,{'ok':False,'current':current,'available':False,'error':str(e)})
        return old_get(self)

    def do_post(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/smart-update/install':
            try:
                length=int(self.headers.get('Content-Length') or 0)
                if length: self.rfile.read(length)
            except Exception: pass
            current=str(getattr(ace,'VERSION','') or '')
            try:
                route,manifest=_manifest_for(current)
                if not route or not manifest: return _send_json(self,409,{'ok':False,'error':'No compatible update is published for A.C.E. '+current+'.'})
                app_root=_install_manifest(manifest,resources_dir);version=str(manifest.get('version') or '')
                _send_json(self,200,{'ok':True,'version':version,'restarting':True})
                threading.Thread(target=_restart,args=(app_root,),daemon=True).start();return
            except Exception as e: return _send_json(self,500,{'ok':False,'error':str(e)})
        return old_post(self)

    ace.H.do_GET=do_get;ace.H.do_POST=do_post


H = Path(__file__).resolve().parent
CORE = H / "ACE Release Core.py"
import importlib.util as _importlib_util
_spec = _importlib_util.spec_from_file_location("ace_release_core", str(CORE))
_core = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
ace = _core.ace
install(ace, H)

if __name__ == "__main__":
    ace.main()
