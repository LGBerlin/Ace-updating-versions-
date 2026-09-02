"""Strict, idempotent repairs for the 1.6.4 cumulative UI; no import side effects."""
from pathlib import Path
import re

MARKER = 'ACE164_INTEGRATION_V1'


def once(source, old, new):
    count = source.count(old)
    if count != 1:
        raise ValueError('A.C.E. integration anchor count %s: %s' % (count, old[:90]))
    return source.replace(old, new, 1)


def pattern_once(source, pattern, replacement):
    result, count = re.subn(pattern, lambda _: replacement, source, count=0)
    if count != 1:
        raise ValueError('A.C.E. integration pattern count %s: %s' % (count, pattern[:90]))
    return result


def integrate(source):
    if MARKER in source:
        return source
    if not source.startswith('(()=>{') or 'ACE164_FINAL_QA' not in source:
        raise ValueError('Expected the complete A.C.E. 1.6.4 UI before integration')
    # The original app owns messages/send/studioJob in this closure. Extend that
    # existing scope around its cumulative UI extensions, keeping state private.
    source = once(source, '\n})();\n\n// ACE_UI_155\n',
                  '\n// Core closure continues around cumulative UI extensions.\n// ACE_UI_155\n')
    source = pattern_once(source, r'  function isEditButton\(b\)\{[\s\S]*?\n  \}',
                          "  function isEditButton(b){return !!b&&b.id==='studioEdit';}")
    source = once(source, "    if(!previewReady()){toast('The preview is still loading. Try Edit again in a moment.');return;}",
                  "    if(studioJob.kind==='presentation'){toggleStudioEditing();return;}\n"
                  "    if(studioJob.kind!=='poster'){toast('This artifact does not have a poster editor.');return;}\n"
                  "    if(!previewReady()){toast('The preview is still loading. Try Edit again in a moment.');return;}")
    # Dirty poster edits must not silently move to another chat/job. This helper
    # closes the real editor state, not merely its DOM overlay.
    source = once(source, 'window.acePosterEdit156=open;',
                  "window.aceClosePosterEditor164=()=>{if(E.on&&E.dirty&&!confirm('Discard unsaved poster edits before changing chats?'))return false;close();return true;};window.acePosterEdit156=open;")
    # Keep unsaved edits when Save fails and Done is clicked.
    source = once(source, "if(E.dirty&&confirm('Save your poster changes?'))await save();close()",
                  "if(E.dirty){if(confirm('Save your poster changes?')){await save();if(E.dirty)return;}else if(!confirm('Discard unsaved poster changes?'))return;}close()")
    source = pattern_once(source, r'  function stopWork\(\)\{[^\n]+', r'''  async function stopWork(){
    if(typeof window.aceClosePosterEditor164==='function'&&!window.aceClosePosterEditor164())return false;
    if((aceWorkActive()||liveActive)&&typeof stopAceEverything==='function')await stopAceEverything();
    window.__ACE162_ATTACHMENT_QUEUE__=null;ui.pending=[];renderPending();return true;
  }''')
    source = once(source, '  function switchChat(id){', '  async function switchChat(id){')
    source = once(source, 'persistCurrent();stopWork();const c=store.chats.find(x=>x.id===id);if(!c)return;',
                  'if(!store.chats.some(x=>x.id===id)||!await stopWork())return;persistCurrent();const c=store.chats.find(x=>x.id===id);')
    source = once(source, '  function newChat(projectId){', '  async function newChat(projectId){')
    source = once(source, 'persistCurrent();stopWork();const c={id:',
                  'if(!await stopWork())return false;persistCurrent();const c={id:')
    source = once(source, "    renderDrawer();syncLiveMeta();closeDrawer();setTimeout(()=>{try{$('chatInput').focus();}catch(_){}},80);\n  }",
                  "    renderDrawer();syncLiveMeta();closeDrawer();setTimeout(()=>{try{$('chatInput').focus();}catch(_){}},80);return true;\n  }")
    source = pattern_once(source, r'  function removeChat\(id\)\{[\s\S]*?\n  \}', r'''  async function removeChat(id){
    if(!store.chats.some(c=>c.id===id)||!confirm('Delete this chat and its attachment history?'))return;
    const was=id===store.currentChatId;
    if(was&&!await stopWork())return;
    store.chats=store.chats.filter(c=>c.id!==id);delete attach[id];writeAttach(attach);
    if(was){
      if(!store.chats.length)store.chats.push({id:uid('chat'),title:'New chat',projectId:'',created:Date.now(),updated:Date.now(),messages:[]});
      store.currentChatId=store.chats[0].id;setMsgArray(store.chats[0].messages.map(m=>({...m})));callSaveRender();
      studioJob=null;closeStudio();
    }
    writeStore(store);renderDrawer();syncAttachmentDecorations();syncLiveMeta();
  }''')
    source = once(source, "const doSearch=()=>{const q=", "const doSearch=async()=>{const q=")
    source = once(source, "if(!q)return;newChat(store.filterProjectId||'');$('ace161SearchInput').value='';",
                  "if(!q||!await newChat(store.filterProjectId||''))return;$('ace161SearchInput').value='';")
    source = once(source, "row.className='ace161-chat-row'+(c.id===store.currentChatId?' current':'');",
                  "row.className='ace161-chat-row'+(c.id===store.currentChatId?' current':'');row.dataset.chatId=c.id;row.setAttribute('aria-current',String(c.id===store.currentChatId));")
    source = once(source, 'store.chats.length&&msgArray().length===0&&Array.isArray(c.messages)&&c.messages.length',
                  'store.chats.length&&Array.isArray(c.messages)&&c.messages.length')
    source = once(source, '    const log=$(\'chatLog\');if(log){new MutationObserver',
                  "    const coreSave164=save;save=function(){coreSave164();persistCurrent();};\n    const log=$('chatLog');if(log){new MutationObserver")
    # Preparing files cannot be consumed by Send/Enter or by the Stop button.
    source = once(source, '  function capturePending(){\n    if(!ui.pending.length)return;',
                  "  function capturePending(e){\n    if(busy||isSpeaking||$('sendBtn')?.dataset.stop156)return;\n    if(!ui.pending.length)return;\n    if(ui.pending.some(a=>a.status==='Preparing…')){e?.preventDefault();e?.stopImmediatePropagation();return;}")
    source = once(source, "if(e.key==='Enter'&&!e.shiftKey)capturePending();", "if(e.key==='Enter'&&!e.shiftKey)capturePending(e);")
    source = once(source, 'async function cancelAndCloseStudio(){\n  const job=studioJob;',
                  "async function cancelAndCloseStudio(){\n  if(typeof window.aceClosePosterEditor164==='function'&&!window.aceClosePosterEditor164())return;\n  const job=studioJob;")
    source = once(source, "items:copy,created:Date.now()};", "items:copy,created:Date.now(),text:ta.value};")
    # Keep hidden attachment context across the fast-lane 409 -> full-lane retry,
    # while requiring exact message/chat ownership. Never decorate operations.
    source = pattern_once(source, r'  window.fetch=async function\(input,init\)\{[\s\S]*?\n  \};\n\n  function bindDrop', FETCH + '\n\n  function bindDrop')
    source = once(source, 'age>=8000', 'age>=120000')
    # Do not rebuild the Live iframe every 1.4 s (navigation/playback resets).
    source = once(source, "stage.innerHTML=html||'<div class=\"ace161-live-preview-empty\">No active preview</div>';",
                  "const signature=html+'|'+srcdoc;if(stage.__ace164Preview===signature)return;stage.__ace164Preview=signature;stage.innerHTML=html||'<div class=\"ace161-live-preview-empty\">No active preview</div>';")
    return source + '\n})();\n// ' + MARKER + '\n'


FETCH = r'''  window.fetch=async function(input,init){
    const q=window.__ACE162_ATTACHMENT_QUEUE__;
    let nextInit=init,used=false;
    try{
      const u=new URL(typeof input==='string'?input:input.url,location.href);
      const body=typeof init?.body==='string'?JSON.parse(init.body):null;
      if(q&&Date.now()-q.created<120000&&u.origin===location.origin&&
         ['/api/agent/fast-stream','/api/agent'].includes(u.pathname)&&
         String(init?.method||'GET').toUpperCase()==='POST'&&body?.message===q.text){
        const ctx=attachmentContext(q.items);
        if(ctx&&inject(body,ctx)){nextInit={...init,body:JSON.stringify(body)};used=true;}
      }
    }catch(_){}
    try{
      const response=await nativeFetch(input,nextInit);
      if(used&&response.status!==409&&window.__ACE162_ATTACHMENT_QUEUE__===q)window.__ACE162_ATTACHMENT_QUEUE__=null;
      return response;
    }catch(e){if(used&&window.__ACE162_ATTACHMENT_QUEUE__===q)window.__ACE162_ATTACHMENT_QUEUE__=null;throw e;}
  };'''


def repair_resources(directory):
    root = Path(directory)
    js_path, index_path = root / 'app.js', root / 'index.html'
    original = js_path.read_text(encoding='utf-8')
    repaired = integrate(original)
    index = index_path.read_text(encoding='utf-8')
    updated = index.replace('app.js?v=164-final-qa', 'app.js?v=164-integration-v1')
    if repaired != original:
        backup = root / 'app.js.pre-164-integration'
        if not backup.exists():
            backup.write_text(original, encoding='utf-8')
        temporary = root / 'app.js.integration-tmp'
        temporary.write_text(repaired, encoding='utf-8')
        temporary.replace(js_path)
    if updated != index:
        temporary = root / 'index.html.integration-tmp'
        temporary.write_text(updated, encoding='utf-8')
        temporary.replace(index_path)
