#!/usr/bin/env python3
"""A.C.E. 1.5.5 runtime bridge.

Adds the v1.5.5 control/UX layer to the proven 1.5.x backend without replacing
A.C.E.'s large server file. On first launch after the GitHub patch is installed,
this bridge applies a small, idempotent UI patch to app.js/index.html/app.css,
then starts the normal backend.
"""
from pathlib import Path
import base64, importlib.util, platform, subprocess, tempfile, time

HERE=Path(__file__).resolve().parent
SERVER=HERE/'ACE Server.py'


def _patch_once(path, marker, transform):
    try:
        p=Path(path)
        text=p.read_text(encoding='utf-8')
        if marker in text:
            return True
        new=transform(text)
        if new==text:
            return False
        p.write_text(new,encoding='utf-8')
        return marker in new
    except Exception:
        return False


def _patch_index(text):
    text=text.replace('app.css?v=151-preview','app.css?v=155-controls')
    text=text.replace('app.js?v=151-preview','app.js?v=155-controls')
    text=text.replace('Current version: v1.5.4','Current version: v1.5.5')
    text=text.replace('Current version: v1.5.3','Current version: v1.5.5')
    if 'id="stopAceBtn"' not in text:
        text=text.replace(
            '<button class="update-chip hidden" id="updateChip" title="A.C.E. update available">UPDATE</button>',
            '<button class="update-chip hidden" id="updateChip" title="A.C.E. update available">UPDATE</button>\n'
            '    <button class="ace-stop hidden" id="stopAceBtn" title="Stop A.C.E."><span class="stop-square">■</span> Stop</button>',
            1,
        )
    if 'id="studioClose"' not in text:
        text=text.replace(
            '<a class="studio-download disabled" id="studioDownload" href="#">Download</a>',
            '<a class="studio-download disabled" id="studioDownload" href="#">Download</a>\n'
            '            <button class="studio-close" id="studioClose" title="Close Preview and cancel active generation" aria-label="Close Preview">×</button>',
            1,
        )
    return text+'\n<!-- ACE_UI_155 -->\n'


_CSS_155=r'''
/* ACE_UI_155: control refinements */
.ace-stop{border:1px solid rgba(255,98,98,.45);background:rgba(255,98,98,.10);color:#ff8c8c;height:32px;padding:0 11px;border-radius:999px;font-size:10px;font-weight:750;letter-spacing:.5px;cursor:pointer;white-space:nowrap}.ace-stop:hover{background:rgba(255,98,98,.18);border-color:#ff7777;color:#fff}.ace-stop.hidden{display:none}.stop-square{font-size:8px;margin-right:4px;vertical-align:1px}
.studio-close{border:0;background:transparent;color:#6b6e72;width:36px;height:36px;border-radius:10px;font-size:24px;line-height:1;cursor:pointer;flex:0 0 auto}.studio-close:hover{background:#ece9e2;color:#b63131}.studio-zoom-simple{min-width:126px}
.user-message-actions{display:flex;gap:5px;margin:5px 8px 0;opacity:0;transform:translateY(-2px);pointer-events:none;transition:opacity .12s ease,transform .12s ease}.msg.user:hover .user-message-actions,.user-message-actions:focus-within{opacity:1;transform:none;pointer-events:auto}.user-message-actions button{width:30px;height:30px;border:0;border-radius:8px;background:transparent;color:#8d9aa4;display:grid;place-items:center;cursor:pointer;padding:6px}.user-message-actions button:hover{background:rgba(255,255,255,.055);color:#eef8fb}.user-message-actions svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.user-message-actions button:last-child:hover{color:#ff8c8c}
.user-inline-editor{width:min(620px,82vw);padding:8px;border-radius:12px;background:var(--raised);border:1px solid var(--cyan2)}.user-inline-editor textarea{display:block;width:100%;min-height:74px;resize:vertical;background:#071019;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px 11px;font:inherit;line-height:1.5;outline:none}.user-inline-editor textarea:focus{border-color:var(--cyan)}.user-edit-buttons{display:flex;justify-content:flex-end;gap:7px;margin-top:7px}.user-edit-buttons .primary{padding:6px 10px;font-size:11px}
@media(hover:none){.user-message-actions{opacity:.8;transform:none;pointer-events:auto}}
'''


def _patch_css(text):
    return text+'\n'+_CSS_155+'\n'


def _patch_js(text):
    # Zoom: simple 10% steps from 10% to 200%.
    text=text.replace("const z=Math.max(.5,Math.min(2,studioZoomValue));","const z=Math.max(.1,Math.min(2,studioZoomValue));",1)
    text=text.replace("studioZoomValue=Math.max(.5,Math.min(2,Math.round((studioZoomValue+delta)*10)/10));","studioZoomValue=Math.max(.1,Math.min(2,Math.round((studioZoomValue+delta)*10)/10));",1)
    text=text.replace("const z=Math.max(.5,studioZoomValue||1),dx=","const z=Math.max(.1,studioZoomValue||1),dx=",1)

    close_old="function closeStudio(){if(studioPollTimer){clearTimeout(studioPollTimer);studioPollTimer=null;}disableStudioEditing();$('artifactStudio').classList.add('hidden');$('chatWorkspace').classList.remove('with-studio');}"
    close_new="""function closeStudio(){if(studioPollTimer){clearTimeout(studioPollTimer);studioPollTimer=null;}disableStudioEditing();$('artifactStudio').classList.add('hidden');$('chatWorkspace').classList.remove('with-studio');updateStopControl();}\nasync function cancelAndCloseStudio(){\n  const job=studioJob;if(job&&job.job_id&&['queued','preparing','running'].includes(String(job.status||'').toLowerCase())){try{await api('/api/opendesign/cancel',{job_id:job.job_id});}catch(_){}}\n  studioJob=null;closeStudio();\n}\nfunction aceWorkActive(){const st=studioJob&&String(studioJob.status||'').toLowerCase();return !!(busy||isSpeaking||(studioJob&&['queued','preparing','running'].includes(st)));}\nfunction updateStopControl(){const b=$('stopAceBtn');if(!b)return;b.classList.toggle('hidden',!aceWorkActive());}\nasync function stopAceEverything(){\n  cancelSpeech();\n  if(activeRequest){try{activeRequest.controller.abort();}catch(_){}activeRequest=null;}\n  if(liveActive)endLive('Stopped.');\n  busy=false;$('sendBtn').disabled=false;removeThinking();\n  const job=studioJob;\n  try{await api('/api/stop',{job_id:job&&job.job_id||''});}catch(_){}\n  if(job&&['queued','preparing','running'].includes(String(job.status||'').toLowerCase())){if(studioPollTimer){clearTimeout(studioPollTimer);studioPollTimer=null;}updateStudio({status:'canceled',stage:'Canceled'});}\n  updateStopControl();\n}"""
    if close_old in text:
        text=text.replace(close_old,close_new,1)

    # Keep the global Stop button in sync with Preview Studio activity.
    text=text.replace("updateStudio(studioJob||{});}","updateStudio(studioJob||{});updateStopControl();}",1)
    text=text.replace("if(studioJob.status==='error')$('studioEmpty').classList.remove('hidden');updateStudioCommentUi();\n}","if(studioJob.status==='error')$('studioEmpty').classList.remove('hidden');updateStudioCommentUi();updateStopControl();\n}",1)

    helper_marker='function userActionIcon(kind)'
    if helper_marker not in text:
        helpers=r'''function userActionIcon(kind){
  if(kind==='edit')return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l11-11-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/></svg>';
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M7 7l1 13h8l1-13"/><path d="M10 11v5M14 11v5"/></svg>';
}
function editUserMessage(index,wrap){
  const m=messages[index];if(!m||m.role!=='user')return;
  if(index<messages.length-1&&!confirm('Editing this message will regenerate the conversation from here. Continue?'))return;
  if(aceWorkActive())stopAceEverything();
  const old=wrap.querySelector('.bubble');if(!old)return;
  const editor=document.createElement('div');editor.className='user-inline-editor';
  const ta=document.createElement('textarea');ta.value=m.content||'';ta.rows=Math.min(8,Math.max(2,String(m.content||'').split('\n').length+1));
  const row=document.createElement('div');row.className='user-edit-buttons';
  const cancel=document.createElement('button');cancel.className='tiny';cancel.textContent='Cancel';
  const saveBtn=document.createElement('button');saveBtn.className='primary';saveBtn.textContent='Save & resend';
  cancel.onclick=()=>renderChat();
  saveBtn.onclick=()=>{const v=ta.value.trim();if(!v)return;messages=messages.slice(0,index);save();renderChat();setTimeout(()=>send(v),0);};
  row.append(cancel,saveBtn);editor.append(ta,row);old.replaceWith(editor);ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length);
}
function deleteUserMessage(index){
  const m=messages[index];if(!m||m.role!=='user')return;
  const removeResponse=messages[index+1]&&messages[index+1].role==='assistant';
  const msg=removeResponse?'Delete this message and A.C.E.\'s response to it?':'Delete this message?';
  if(!confirm(msg))return;
  if(aceWorkActive())stopAceEverything();
  messages.splice(index,removeResponse?2:1);save();renderChat();
}
function addUserMessageActions(wrap,index){
  const actions=document.createElement('div');actions.className='user-message-actions';
  const edit=document.createElement('button');edit.type='button';edit.title='Edit message';edit.setAttribute('aria-label','Edit message');edit.innerHTML=userActionIcon('edit');
  const del=document.createElement('button');del.type='button';del.title='Delete message';del.setAttribute('aria-label','Delete message');del.innerHTML=userActionIcon('delete');
  edit.onclick=()=>editUserMessage(index,wrap);del.onclick=()=>deleteUserMessage(index);actions.append(edit,del);wrap.appendChild(actions);
}
'''
        text=text.replace('function renderMessage(m,index){',helpers+'function renderMessage(m,index){',1)
        text=text.replace("wrap.append(who,b);if(m.role!=='user'){","wrap.append(who,b);if(m.role==='user')addUserMessageActions(wrap,index);if(m.role!=='user'){",1)

    text=text.replace("busy=true;$('sendBtn').disabled=true;","busy=true;$('sendBtn').disabled=true;updateStopControl();",1)
    text=text.replace("busy=false;$('sendBtn').disabled=false;if(fromLive","busy=false;$('sendBtn').disabled=false;updateStopControl();if(fromLive",1)

    if "$('stopAceBtn').addEventListener('click',stopAceEverything);" not in text:
        text=text.replace("$('studioDownload').addEventListener", "$('stopAceBtn').addEventListener('click',stopAceEverything);$('studioClose').addEventListener('click',cancelAndCloseStudio);\n$('studioDownload').addEventListener",1)
    text=text.replace("updateTimer=setInterval(()=>refreshUpdateStatus(true),21600000);$('chatInput').focus();","updateTimer=setInterval(()=>refreshUpdateStatus(true),21600000);setInterval(updateStopControl,250);updateStopControl();$('chatInput').focus();",1)
    return text+'\n// ACE_UI_155\n'


_patch_once(HERE/'index.html','ACE_UI_155',_patch_index)
_patch_once(HERE/'app.css','ACE_UI_155',_patch_css)
_patch_once(HERE/'app.js','ACE_UI_155',_patch_js)

spec=importlib.util.spec_from_file_location('ace_server_runtime',str(SERVER))
ace=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ace)
ace.VERSION='1.5.5'
try: ace.UPDATE_STATE['current_version']='1.5.5'
except Exception: pass

_original_snapshot=ace._job_snapshot
_original_embedded=ace._pptx_embedded_thumbnail
_original_do_post=ace.H.do_POST


def _quicklook_once(path):
    path=Path(path)
    if platform.system()!='Darwin' or not path.is_file() or not Path('/usr/bin/qlmanage').exists():
        return ''
    try:
        with tempfile.TemporaryDirectory(prefix='ace_preview_') as td:
            out=Path(td)
            subprocess.run(['/usr/bin/qlmanage','-t','-s','1400','-o',str(out),str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12,check=False)
            imgs=[p for p in out.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg','.jpeg'}]
            if imgs:
                img=max(imgs,key=lambda p:p.stat().st_size)
                return base64.b64encode(img.read_bytes()).decode('ascii')
    except Exception:pass
    return ''


def _poster_preview_retry(job):
    if str(job.get('kind') or '')!='poster' or not job.get('pptx_rel'):return False
    if job.get('preview_rel') or job.get('daemon_preview_url') or job.get('rendered_pages'):return True
    tries=int(job.get('_ace_preview_tries') or 0)
    if tries>=5:return False
    job['_ace_preview_tries']=tries+1
    try:
        cwd=ace._project_cwd(str(job.get('project_id') or ''));rel=str(job.get('pptx_rel') or '')
        pptx=(cwd/rel).resolve() if cwd and rel else None
        if not pptx or not pptx.is_file() or pptx.stat().st_size<=0:return False
        size=pptx.stat().st_size;time.sleep(.28)
        if not pptx.is_file() or pptx.stat().st_size!=size:return False
        thumb=_original_embedded(pptx) or _quicklook_once(pptx)
        if thumb:job['rendered_pages']=[thumb];job['stage']='Ready';return True
    except Exception:pass
    return False


def _snapshot(job):
    _poster_preview_retry(job);snap=_original_snapshot(job)
    if str(job.get('kind') or '')=='poster' and str(job.get('status') or '')=='done' and job.get('pptx_rel'):
        if job.get('rendered_pages'):
            snap['preview_ready']=True;snap['rendered_count']=len(job.get('rendered_pages') or [])
            snap['rendered_base']='/api/opendesign/rendered?job='+ace.urllib.parse.quote(str(job.get('job_id')))+'&page=';snap['stage']='Ready'
        elif int(job.get('_ace_preview_tries') or 0)>=5:snap['stage']='Poster ready — preview unavailable'
    return snap


def _cancel_opendesign_job(job_id):
    with ace.OPEN_DESIGN_LOCK:job=ace.OPEN_DESIGN_JOBS.get(str(job_id or ''))
    if not job:return {'ok':True,'status':'not-found'}
    job['cancel_requested']=True;run_ids=[]
    for key in ('run_id','persist_run_id','export_run_id'):
        rid=str(job.get(key) or '')
        if rid and rid not in run_ids:run_ids.append(rid)
    for rid in run_ids:
        try:ace._od_http_json('POST','/api/runs/'+ace.urllib.parse.quote(rid,safe='')+'/cancel',{},timeout=8)
        except Exception:pass
    job['status']='canceled';job['stage']='Canceled';job['error']=''
    return {'ok':True,'status':'canceled','job_id':job.get('job_id')}


def _stop_local_model():
    try:
        model=ace.choose_model(ace.ollama_models());binary=ace.ollama_binary()
        if model and binary:subprocess.Popen([binary,'stop',model],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception:pass


def _patched_do_post(self):
    if self.path in {'/api/opendesign/cancel','/api/stop'}:
        try:
            d=ace.parse_json(self);jid=str(d.get('job_id') or '')
            if jid:_cancel_opendesign_job(jid)
            if self.path=='/api/stop':_stop_local_model()
            self.json_out({'ok':True});return
        except Exception as e:self.json_out({'error':str(e)},500);return
    return _original_do_post(self)

ace._job_snapshot=_snapshot
ace.H.do_POST=_patched_do_post

if __name__=='__main__':ace.main()
