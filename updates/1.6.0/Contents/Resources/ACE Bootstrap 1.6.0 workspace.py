#!/usr/bin/env python3
"""A.C.E. 1.6.0 — workspace navigation, persistence, attachments and Live context.

Loads the verified 1.5.9 research runtime, then applies one idempotent UI layer. The
existing Chat/Live, updater, voice, Stop, artifact generation, downloads and editor
services remain authoritative; this release adds workspace organization around them.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.5.9.py'

spec = importlib.util.spec_from_file_location('ace_base_159', str(BASE))
b159 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b159)
ace = b159.ace

# Keep 1.5.9's three-engine/six-domain research design, but bound slow page hosts
# more tightly. Discovery remains parallel and source fetching now spends at most
# six seconds on any one page instead of ten.
_research_get_159 = b159._get


def _research_get_160(url, timeout=9, limit=600_000):
    return _research_get_159(url, timeout=min(float(timeout), 6.0), limit=limit)


b159._get = _research_get_160


def patch(path, marker, transform):
    try:
        p = Path(path)
        source = p.read_text(encoding='utf-8')
        if marker in source:
            return True
        updated = transform(source)
        if updated != source:
            p.write_text(updated, encoding='utf-8')
        return marker in updated
    except Exception:
        return False


def patch_index(source):
    source = source.replace('app.css?v=159-research', 'app.css?v=160-workspace')
    source = source.replace('app.js?v=159-research', 'app.js?v=160-workspace')
    source = source.replace('Current version: v1.5.9', 'Current version: v1.6.0')
    return source + '\n<!--ACE160_WORKSPACE-->\n'


CSS = r'''
:root{--ace-rail:66px;--ace-deck:292px;--ace-green:#57e29a;--ace-green2:#17b86a;--ace-ink:#07110e;--ace-panel:rgba(11,25,21,.96)}
body.ace160-ready .app-shell{padding-left:var(--ace-rail);transition:padding-left .24s cubic-bezier(.2,.8,.2,1)}
body.ace160-open .app-shell{padding-left:calc(var(--ace-rail) + var(--ace-deck))}
.ace160-rail{position:fixed;z-index:80;inset:0 auto 0 0;width:var(--ace-rail);background:linear-gradient(180deg,#07130f,#0b1d17);border-right:1px solid rgba(87,226,154,.16);display:flex;flex-direction:column;align-items:center;padding:14px 9px;gap:9px;box-sizing:border-box}
.ace160-mark,.ace160-icon{width:46px;height:46px;border:0;border-radius:14px;color:#dfffee;background:transparent;display:grid;place-items:center;cursor:pointer;font:600 19px/1 system-ui;transition:transform .16s,background .16s,color .16s}
.ace160-mark{background:radial-gradient(circle at 35% 30%,#75f4b2,#16a963 52%,#0a472e);box-shadow:0 0 24px rgba(64,222,141,.28);font-weight:900;color:#03120b}
.ace160-icon:hover,.ace160-icon.active{background:rgba(87,226,154,.13);color:var(--ace-green);transform:translateY(-1px)}
.ace160-spacer{flex:1}.ace160-deck{position:fixed;z-index:75;left:var(--ace-rail);top:0;bottom:0;width:var(--ace-deck);background:var(--ace-panel);backdrop-filter:blur(18px);border-right:1px solid rgba(87,226,154,.13);transform:translateX(-105%);transition:transform .24s cubic-bezier(.2,.8,.2,1);padding:18px 14px;box-sizing:border-box;overflow:auto}
body.ace160-open .ace160-deck{transform:none}.ace160-deck h2{margin:3px 7px 15px;font:750 19px/1.2 system-ui;color:#effff6}.ace160-action{width:100%;border:1px solid rgba(87,226,154,.15);border-radius:12px;background:rgba(255,255,255,.035);color:#e7fff2;padding:11px 12px;text-align:left;cursor:pointer;margin:0 0 7px;font:600 13px system-ui}.ace160-action:hover{background:rgba(87,226,154,.1);border-color:rgba(87,226,154,.3)}
.ace160-section{display:flex;align-items:center;justify-content:space-between;margin:20px 7px 8px;color:#78998a;font:700 10px system-ui;letter-spacing:.13em;text-transform:uppercase}.ace160-add{border:0;background:transparent;color:#8ebda5;cursor:pointer;font-size:19px}.ace160-list{display:grid;gap:4px}.ace160-row{position:relative;border-radius:10px;color:#b9cec3;padding:9px 30px 9px 10px;cursor:pointer;font:500 12px/1.3 system-ui;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ace160-row:hover,.ace160-row.active{background:rgba(87,226,154,.09);color:#edfff5}.ace160-row button{position:absolute;right:5px;top:5px;border:0;background:transparent;color:#6f8c7e;cursor:pointer;font-size:15px}.ace160-empty{padding:8px;color:#668075;font:12px system-ui}
.ace160-project-chip{display:inline-flex;align-items:center;gap:7px;max-width:240px;padding:7px 10px;border:1px solid rgba(87,226,154,.16);border-radius:999px;color:#aee8c9;background:rgba(87,226,154,.055);font:600 11px system-ui;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ace160-tools{display:flex;align-items:center;gap:7px;margin:7px 0 0}.ace160-attach{width:34px;height:34px;border-radius:10px;border:1px solid rgba(87,226,154,.17);background:rgba(255,255,255,.035);color:#bcebd1;cursor:pointer;font-size:18px}.ace160-attach:hover{background:rgba(87,226,154,.12)}.ace160-files{display:flex;gap:6px;flex-wrap:wrap;min-height:0}.ace160-file{display:flex;align-items:center;gap:6px;max-width:210px;padding:6px 8px;border-radius:9px;background:rgba(87,226,154,.09);color:#bde7d2;font:11px system-ui}.ace160-file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ace160-file button{border:0;background:transparent;color:#829d90;cursor:pointer;padding:0}
.ace160-searching .composer{box-shadow:0 0 0 1px rgba(87,226,154,.65),0 0 34px rgba(36,200,119,.13)!important}.ace160-search-badge{display:none;color:var(--ace-green);font:700 10px system-ui;letter-spacing:.08em}.ace160-searching .ace160-search-badge{display:inline}
.ace160-live-context{margin-top:15px;padding:14px;border:1px solid rgba(87,226,154,.14);border-radius:15px;background:rgba(5,18,13,.46);color:#cce9da;font:12px/1.45 system-ui}.ace160-live-context h3{margin:0 0 10px;color:#effff6;font-size:13px}.ace160-live-grid{display:grid;grid-template-columns:90px 1fr;gap:6px;color:#7e9b8d}.ace160-live-grid strong{color:#c9ebd9;overflow:hidden;text-overflow:ellipsis}.ace160-live-preview{margin-top:12px;border-radius:11px;overflow:hidden;background:#07100d;min-height:90px;display:grid;place-items:center;color:#607c6d}.ace160-live-preview img{display:block;width:100%;max-height:260px;object-fit:contain}
.ace160-toast{position:fixed;z-index:120;left:50%;bottom:28px;transform:translate(-50%,14px);opacity:0;padding:10px 14px;border-radius:11px;background:#173c2d;color:#eafff2;box-shadow:0 10px 35px #0008;font:600 12px system-ui;transition:.2s;pointer-events:none}.ace160-toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:880px){body.ace160-open .app-shell{padding-left:var(--ace-rail)}.ace160-deck{box-shadow:20px 0 55px #000b}.ace160-project-chip{display:none}}
/*ACE160_WORKSPACE*/
'''


JS = r'''
(function(){
if(window.__ACE160_WORKSPACE__)return;window.__ACE160_WORKSPACE__=1;
const $=id=>document.getElementById(id), KEY='ace.workspace.160';
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2,8);
let attachments=[], searchMode=false, switching=false;
function state(){try{const x=JSON.parse(localStorage.getItem(KEY)||'null');if(x&&x.chats&&x.projects)return x}catch(_){}return{projects:[],chats:[],activeChat:'',activeProject:''}}
let ws=state();
function persist(){try{localStorage.setItem(KEY,JSON.stringify(ws))}catch(_){}}
function toast(t){let e=$('ace160Toast');if(!e){e=document.createElement('div');e.id='ace160Toast';e.className='ace160-toast';document.body.appendChild(e)}e.textContent=t;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),2200)}
function titleFrom(ms){const m=(ms||[]).find(x=>x&&x.role==='user');return String(m&&m.content||'New chat').replace(/\[Attached[\s\S]*$/,'').trim().slice(0,45)||'New chat'}
function current(){return ws.chats.find(x=>x.id===ws.activeChat)}
function capture(){if(switching)return;try{let c=current();if(!c){c={id:uid(),projectId:ws.activeProject||'',title:'New chat',messages:[],updated:Date.now()};ws.chats.unshift(c);ws.activeChat=c.id}if(typeof messages!=='undefined'&&Array.isArray(messages)){c.messages=JSON.parse(JSON.stringify(messages));c.title=titleFrom(c.messages);c.updated=Date.now()}persist();renderDeck();renderContext()}catch(_){}}
function loadChat(id){capture();const c=ws.chats.find(x=>x.id===id);if(!c)return;switching=true;ws.activeChat=id;ws.activeProject=c.projectId||'';try{if(typeof cancelSpeech==='function')cancelSpeech();if(typeof messages!=='undefined'){messages=JSON.parse(JSON.stringify(c.messages||[]));if(typeof save==='function')save();if(typeof renderChat==='function')renderChat()}}catch(_){}switching=false;persist();renderDeck();renderContext();$('chatInput')&&$('chatInput').focus()}
function newChat(projectId){capture();const c={id:uid(),projectId:projectId===undefined?(ws.activeProject||''):projectId,title:'New chat',messages:[],updated:Date.now()};ws.chats.unshift(c);ws.activeChat=c.id;ws.activeProject=c.projectId;switching=true;try{if(typeof messages!=='undefined'){messages=[];if(typeof save==='function')save();if(typeof renderChat==='function')renderChat()}}catch(_){}switching=false;persist();renderDeck();renderContext();$('chatInput')&&$('chatInput').focus()}
function addProject(){const name=prompt('Project name');if(!name||!name.trim())return;const p={id:uid(),name:name.trim().slice(0,60)};ws.projects.push(p);ws.activeProject=p.id;persist();newChat(p.id)}
function removeChat(id,e){e&&e.stopPropagation();if(!confirm('Delete this chat from A.C.E. history?'))return;ws.chats=ws.chats.filter(x=>x.id!==id);if(ws.activeChat===id){ws.activeChat='';newChat(ws.activeProject)}persist();renderDeck()}
function renderDeck(){const p=$('ace160Projects'),c=$('ace160Chats');if(!p||!c)return;p.innerHTML=ws.projects.length?ws.projects.map(x=>`<div class="ace160-row ${x.id===ws.activeProject?'active':''}" data-project="${x.id}">▣ ${esc(x.name)}</div>`).join(''):'<div class="ace160-empty">No projects yet</div>';const list=ws.chats.slice().sort((a,b)=>(b.updated||0)-(a.updated||0));c.innerHTML=list.length?list.map(x=>`<div class="ace160-row ${x.id===ws.activeChat?'active':''}" data-chat="${x.id}">${esc(x.title)}<button data-delete="${x.id}" title="Delete chat">×</button></div>`).join(''):'<div class="ace160-empty">No chats yet</div>';p.querySelectorAll('[data-project]').forEach(e=>e.onclick=()=>{ws.activeProject=e.dataset.project;const found=ws.chats.find(x=>x.projectId===ws.activeProject);found?loadChat(found.id):newChat(ws.activeProject)});c.querySelectorAll('[data-chat]').forEach(e=>e.onclick=()=>loadChat(e.dataset.chat));c.querySelectorAll('[data-delete]').forEach(e=>e.onclick=v=>removeChat(e.dataset.delete,v));renderContext()}
function renderContext(){const p=ws.projects.find(x=>x.id===ws.activeProject),c=current(),chip=$('ace160ProjectChip');if(chip)chip.textContent='● '+(p?p.name:'No project')+' · '+(c?c.title:'New chat');const lp=$('ace160LiveProject'),lc=$('ace160LiveChat'),lw=$('ace160LiveWork');if(lp)lp.textContent=p?p.name:'Unfiled';if(lc)lc.textContent=c?c.title:'New chat';if(lw){let work='Ready';try{if(typeof studioJob!=='undefined'&&studioJob)work=studioJob.stage||studioJob.status||'Artifact work';else if(typeof aceWorkActive==='function'&&aceWorkActive())work='A.C.E. is working'}catch(_){}lw.textContent=work}const src=$('studioImage'),dst=$('ace160LivePreview');if(dst){if(src&&!src.classList.contains('hidden')&&src.src)dst.innerHTML=`<img src="${src.src}" alt="Current artifact preview">`;else dst.textContent='Preview will appear here when an artifact is open.'}}
function addFiles(files){[...files].slice(0,8).forEach(f=>{if(f.size>12*1024*1024){toast(f.name+' is larger than 12 MB');return}const item={id:uid(),name:f.name,type:f.type||'file',size:f.size,text:''};attachments.push(item);if(/^text\/(plain|csv|markdown)|application\/(json|xml)/.test(item.type)||/\.(txt|md|csv|json|xml|js|py|html|css)$/i.test(item.name)){const r=new FileReader();r.onload=()=>item.text=String(r.result||'').slice(0,30000);r.readAsText(f)}renderFiles()})}
function renderFiles(){const box=$('ace160Files');if(!box)return;box.innerHTML=attachments.map(x=>`<div class="ace160-file"><span>${/^image\//.test(x.type)?'▧':'▤'} ${esc(x.name)}</span><button data-file="${x.id}">×</button></div>`).join('');box.querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>{attachments=attachments.filter(x=>x.id!==b.dataset.file);renderFiles()})}
function injectAttachments(){const input=$('chatInput');if(!input)return;if(searchMode&&!/^\s*(search|research|look up)\b/i.test(input.value))input.value='Research this using multiple reliable sources: '+input.value;if(attachments.length){let block='\n\n[Attached files]\n'+attachments.map(x=>`- ${x.name} (${x.type}, ${x.size} bytes)${x.text?'\nContents:\n'+x.text:''}`).join('\n');input.value+=block;attachments=[];renderFiles()}setTimeout(capture,500)}
function shell(){if($('ace160Rail'))return;document.body.classList.add('ace160-ready');const rail=document.createElement('aside');rail.id='ace160Rail';rail.className='ace160-rail';rail.innerHTML='<button class="ace160-mark" id="ace160Menu" title="Open A.C.E. workspace">A</button><button class="ace160-icon" id="ace160New" title="Quick new chat">＋</button><button class="ace160-icon" id="ace160Search" title="AI web search">⌕</button><button class="ace160-icon" id="ace160History" title="Chat history">☰</button><div class="ace160-spacer"></div><button class="ace160-icon" id="ace160Close" title="Close sidebar">‹</button>';const deck=document.createElement('aside');deck.className='ace160-deck';deck.id='ace160Deck';deck.innerHTML='<h2>A.C.E. Workspace</h2><button class="ace160-action" id="ace160DeckNew">＋ New chat</button><button class="ace160-action" id="ace160DeckSearch">⌕ AI web search</button><div class="ace160-section"><span>Projects</span><button class="ace160-add" id="ace160AddProject" title="New project">＋</button></div><div class="ace160-list" id="ace160Projects"></div><div class="ace160-section"><span>Recent chats</span></div><div class="ace160-list" id="ace160Chats"></div>';document.body.prepend(deck);document.body.prepend(rail);$('ace160Menu').onclick=()=>$('ace160Deck')&&document.body.classList.toggle('ace160-open');$('ace160History').onclick=()=>document.body.classList.add('ace160-open');$('ace160Close').onclick=()=>document.body.classList.remove('ace160-open');$('ace160New').onclick=$('ace160DeckNew').onclick=()=>newChat();const toggleSearch=()=>{searchMode=!searchMode;document.body.classList.toggle('ace160-searching',searchMode);$('ace160Search').classList.toggle('active',searchMode);toast(searchMode?'AI web search on':'AI web search off');$('chatInput')&&$('chatInput').focus()};$('ace160Search').onclick=$('ace160DeckSearch').onclick=toggleSearch;$('ace160AddProject').onclick=addProject;
const top=document.querySelector('.brand-wrap')||document.querySelector('.topbar');if(top){const chip=document.createElement('div');chip.id='ace160ProjectChip';chip.className='ace160-project-chip';top.appendChild(chip)}const comp=document.querySelector('.composer');if(comp&&$('chatInput')){const tools=document.createElement('div');tools.className='ace160-tools';tools.innerHTML='<button class="ace160-attach" id="ace160Attach" title="Attach images or files">＋</button><span class="ace160-search-badge">AI SEARCH</span><div class="ace160-files" id="ace160Files"></div><input id="ace160FileInput" type="file" multiple hidden>';comp.parentNode.insertBefore(tools,comp);$('ace160Attach').onclick=()=>$('ace160FileInput').click();$('ace160FileInput').onchange=e=>{addFiles(e.target.files);e.target.value=''}}const right=document.querySelector('.live-right');if(right){const ctx=document.createElement('div');ctx.className='ace160-live-context';ctx.innerHTML='<h3>Current workspace</h3><div class="ace160-live-grid"><span>Project</span><strong id="ace160LiveProject">Unfiled</strong><span>Chat</span><strong id="ace160LiveChat">New chat</strong><span>Current work</span><strong id="ace160LiveWork">Ready</strong></div><div class="ace160-live-preview" id="ace160LivePreview">Preview will appear here when an artifact is open.</div>';right.prepend(ctx)}
document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('#sendBtn'))injectAttachments()},true);document.addEventListener('keydown',e=>{if(e.target===$('chatInput')&&e.key==='Enter'&&!e.shiftKey)injectAttachments()},true);setInterval(()=>{capture();renderContext();fixEdit()},1200);renderDeck();renderFiles();renderContext()}
function openEditor(){try{if(typeof window.acePosterEdit156==='function'){window.acePosterEdit156();return}if(typeof window.aceOpenStudioEditor156==='function'){window.aceOpenStudioEditor156();return}}catch(x){toast('Editor could not open: '+x.message);return}toast('The editable poster preview is not ready yet.')}
function fixEdit(){const old=$('studioEdit');if(!old||old.dataset.ace160==='1')return;const b=old.cloneNode(true);b.dataset.ace160='1';b.dataset.ace158final='1';b.onclick=null;b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();openEditor()},true);old.replaceWith(b)}
function start(){try{if(!ws.activeChat)newChat('');else{const c=current();if(c&&typeof messages!=='undefined'&&Array.isArray(messages)&&messages.length&&!c.messages.length){c.messages=JSON.parse(JSON.stringify(messages));c.title=titleFrom(c.messages);persist()}}}catch(_){}shell();fixEdit()}
window.addEventListener('click',e=>{const b=e.target&&e.target.closest&&e.target.closest('#studioEdit');if(!b)return;e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();openEditor()},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
// ACE160_WORKSPACE
'''

patch(H / 'index.html', 'ACE160_WORKSPACE', patch_index)
patch(H / 'app.css', 'ACE160_WORKSPACE', lambda s: s + '\n' + CSS + '\n')
patch(H / 'app.js', 'ACE160_WORKSPACE', lambda s: s + '\n' + JS + '\n')

ace.VERSION = '1.6.0'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.0'
except Exception:
    pass

if __name__ == '__main__':
    ace.main()
