#!/usr/bin/env python3
"""A.C.E. 1.6.2 — attachment-aware chat and workspace reliability.

Loads 1.6.1 cumulatively. Text-bearing attachments now become hidden context for the
local chat model while the visible user message remains clean. DOCX, PPTX and XLSX
text is extracted locally with Python's standard library; PDF text is used when a
local pdftotext binary is available. Image attachments remain previewable but A.C.E.
does not invent visual understanding. Drag/drop and pasted files are supported.
"""
from pathlib import Path
import base64
import importlib.util
import io
import re
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.1.py'
spec = importlib.util.spec_from_file_location('ace_base_161', str(BASE))
b161 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b161)
ace = b161.ace

ace.VERSION = '1.6.2'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.2'
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


def idx162(s):
    s = s.replace('app.css?v=161-workspace', 'app.css?v=162-attachments')
    s = s.replace('app.js?v=161-workspace', 'app.js?v=162-attachments')
    s = s.replace('Current version: v1.6.1', 'Current version: v1.6.2')
    return s + '\n<!--ACE162_ATTACHMENTS-->\n'

CSS162 = '\n.composer-wrap.ace162-drop-active,.composer.ace162-drop-active{outline:2px solid rgba(67,214,176,.72);outline-offset:5px;border-radius:18px}\n.ace161-attachment-chip[data-processing="1"]{opacity:.76}\n.ace161-attachment-chip small{max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n#ace161AttachmentTray{transition:opacity .16s ease,transform .16s ease}\n#ace161AttachmentTray:not(.hidden){animation:ace162TrayIn .16s ease-out}\n@keyframes ace162TrayIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}\n@media (prefers-reduced-motion:reduce){#ace161AttachmentTray:not(.hidden){animation:none}}\n/*ACE162_ATTACHMENTS*/\n'

_JS162_HELPERS = "\n  async function ace162Thumb(f){\n    if(!f||!(f.type||'').startsWith('image/'))return '';\n    if(f.size>4500000)return '';\n    try{\n      const raw=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result||''));r.onerror=rej;r.readAsDataURL(f);});\n      const im=await new Promise((res,rej)=>{const x=new Image();x.onload=()=>res(x);x.onerror=rej;x.src=raw;});\n      const max=1100,scale=Math.min(1,max/Math.max(im.naturalWidth||1,im.naturalHeight||1));\n      const c=document.createElement('canvas');c.width=Math.max(1,Math.round((im.naturalWidth||1)*scale));c.height=Math.max(1,Math.round((im.naturalHeight||1)*scale));\n      c.getContext('2d').drawImage(im,0,0,c.width,c.height);\n      return c.toDataURL('image/jpeg',.8);\n    }catch(_){return '';}\n  }\n  function ace162B64(buf){\n    const a=new Uint8Array(buf);let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);\n  }\n  async function ace162Extract(f){\n    if(!f||f.size>4500000)return {text:'',note:f&&f.size>4500000?'File is too large for local text extraction (4.5 MB limit).':''};\n    if(!/\\.(docx|pptx|xlsx|pdf)$/i.test(f.name||''))return {text:'',note:''};\n    try{\n      const b64=ace162B64(await f.arrayBuffer());\n      const r=await fetch('/api/attachments/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name,type:f.type||'',data:b64})});\n      const d=await r.json();if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));\n      return {text:String(d.text||'').slice(0,22000),note:String(d.note||'')};\n    }catch(e){return {text:'',note:'Could not extract text locally: '+String(e&&e.message||e)};}\n  }\n  async function addPendingFile(f){\n    if(!f||ui.pending.length>=8)return;\n    const item={id:uid('att'),name:f.name||'attachment',size:f.size||0,type:f.type||'',kind:(f.type||'').startsWith('image/')?'image':'file',data:'',text:'',note:'',status:'Preparing…'};\n    ui.pending.push(item);renderPending();\n    const textLike=(f.type||'').startsWith('text/')||/\\.(txt|md|csv|json|jsonl|log|py|js|ts|tsx|jsx|css|html?|xml|ya?ml|toml|ini|sql|sh|r|java|c|cc|cpp|h|hpp)$/i.test(f.name||'');\n    if(item.kind==='image'){item.data=await ace162Thumb(f);item.status='Image';}\n    else if(textLike&&f.size<=650000){try{item.text=(await f.text()).slice(0,22000);item.status='Text ready';}catch(_){item.status='File';}}\n    else if(/\\.(docx|pptx|xlsx|pdf)$/i.test(f.name||'')){const x=await ace162Extract(f);item.text=x.text;item.note=x.note;item.status=item.text?'Text extracted':'File attached';}\n    else item.status='File attached';\n    renderPending();window.ace162AddPendingFile=addPendingFile;\n  }\n  window.ace162AddPendingFile=addPendingFile;\n"

_JS162_CAPTURE = "  function capturePending(){\n    if(!ui.pending.length)return;const c=current();if(!c)return;\n    const ta=$('chatInput');if(ta&&!String(ta.value||'').trim())ta.value='Please review the attached file'+(ui.pending.length>1?'s':'')+'.';\n    const copy=ui.pending.map(a=>({...a}));window.__ACE162_ATTACHMENT_QUEUE__={chatId:c.id,items:copy,created:Date.now()};\n    ui.pending=[];renderPending();\n    const targetIndex=msgArray().filter(m=>m&&m.role==='user').length;\n    setTimeout(()=>{const map=attach[c.id]||(attach[c.id]={});map[String(targetIndex)]=copy;writeAttach(attach);syncAttachmentDecorations();persistCurrent();},220);\n  }\n  function syncAttachmentDecorations()"

JS162 = "\n(function(){\n  if(window.__ACE162_ATTACHMENTS__)return;window.__ACE162_ATTACHMENTS__=1;\n  const nativeFetch=window.fetch.bind(window);\n  const blocked=['/api/attachments/','/api/stop','/api/opendesign','/api/studio','/api/voice','/api/tts','/api/speech','/api/update','/api/download','/api/file','/api/memory'];\n  const escCtx=s=>String(s??'').replace(/\\u0000/g,'').trim();\n\n  function attachmentContext(items){\n    if(!Array.isArray(items)||!items.length)return '';\n    let budget=30000,out=['[ACE_ATTACHMENT_CONTEXT — internal context from files attached to this user message; do not quote this wrapper unless useful.]'];\n    for(const a of items){\n      if(budget<=0)break;\n      const name=String(a?.name||'attachment').slice(0,180);\n      const type=String(a?.type||'').slice(0,120);\n      const size=Math.max(0,Number(a?.size||0));\n      out.push(`\\nAttachment: ${name}${type?` (${type})`:''}, ${Math.max(1,Math.round(size/1024))} KB`);\n      const t=escCtx(a?.text||'');\n      if(t){\n        const take=t.slice(0,Math.min(16000,budget));\n        out.push('Extracted text:\\n'+take+(take.length<t.length?'\\n[Attachment text truncated]':''));\n        budget-=take.length;\n      }else if(String(a?.kind||'')==='image'){\n        out.push('Image preview is attached locally. Pixel-level visual understanding is not available to the local model in this release; do not invent image details.');\n      }else if(a?.note){\n        out.push('Attachment note: '+String(a.note).slice(0,500));\n      }\n    }\n    out.push('\\n[/ACE_ATTACHMENT_CONTEXT]');\n    return out.join('\\n');\n  }\n\n  function inject(obj,ctx){\n    if(!obj||typeof obj!=='object'||!ctx)return false;\n    if(Array.isArray(obj.messages)){\n      for(let i=obj.messages.length-1;i>=0;i--){\n        const m=obj.messages[i];\n        if(m&&String(m.role||'').toLowerCase()==='user'&&typeof m.content==='string'){\n          if(!m.content.includes('[ACE_ATTACHMENT_CONTEXT'))m.content=m.content+'\\n\\n'+ctx;\n          return true;\n        }\n      }\n    }\n    for(const k of ['message','prompt','input','text']){\n      if(typeof obj[k]==='string'&&obj[k].trim()){\n        if(!obj[k].includes('[ACE_ATTACHMENT_CONTEXT'))obj[k]=obj[k]+'\\n\\n'+ctx;\n        return true;\n      }\n    }\n    return false;\n  }\n\n  window.fetch=async function(input,init){\n    let nextInit=init;\n    try{\n      const q=window.__ACE162_ATTACHMENT_QUEUE__;\n      if(q&&Array.isArray(q.items)&&q.items.length&&Date.now()-Number(q.created||0)<8000){\n        const url=typeof input==='string'?input:(input&&input.url)||'';\n        const path=(()=>{try{return new URL(url,location.href).pathname.toLowerCase();}catch(_){return String(url||'').toLowerCase();}})();\n        const method=String((init&&init.method)||'GET').toUpperCase();\n        const body=init&&init.body;\n        if(method==='POST'&&typeof body==='string'&&!blocked.some(x=>path.includes(x))){\n          let d=null;try{d=JSON.parse(body);}catch(_){}\n          const ctx=attachmentContext(q.items);\n          if(d&&inject(d,ctx)){\n            nextInit={...(init||{}),body:JSON.stringify(d)};\n            window.__ACE162_ATTACHMENT_QUEUE__=null;\n          }\n        }\n      }\n    }catch(_){}\n    return nativeFetch(input,nextInit);\n  };\n\n  function bindDrop(){\n    const composer=document.querySelector('.composer-wrap')||document.querySelector('.composer');\n    if(!composer||composer.dataset.ace162Drop==='1')return;\n    composer.dataset.ace162Drop='1';\n    const on=()=>composer.classList.add('ace162-drop-active'),off=()=>composer.classList.remove('ace162-drop-active');\n    for(const ev of ['dragenter','dragover'])composer.addEventListener(ev,e=>{if(e.dataTransfer&&e.dataTransfer.types&&[...e.dataTransfer.types].includes('Files')){e.preventDefault();on();}});\n    for(const ev of ['dragleave','dragend'])composer.addEventListener(ev,off);\n    composer.addEventListener('drop',async e=>{\n      const fs=[...(e.dataTransfer?.files||[])];\n      if(!fs.length)return;e.preventDefault();off();\n      if(typeof window.ace162AddPendingFile==='function')for(const f of fs.slice(0,8))await window.ace162AddPendingFile(f);\n    });\n    const ta=document.getElementById('chatInput');\n    if(ta&&ta.dataset.ace162Paste!=='1'){\n      ta.dataset.ace162Paste='1';\n      ta.addEventListener('paste',async e=>{\n        const fs=[...(e.clipboardData?.files||[])];\n        if(!fs.length||typeof window.ace162AddPendingFile!=='function')return;\n        for(const f of fs.slice(0,8))await window.ace162AddPendingFile(f);\n      });\n    }\n  }\n  setInterval(bindDrop,1200);setTimeout(bindDrop,120);\n})();\n// ACE162_ATTACHMENTS\n"


def app162(s):
    # Upgrade the private 1.6.1 attachment implementation in place. Exact anchors
    # make this fail closed if the expected 1.6.1 source is not present.
    m = re.search(r"  async function addPendingFile\(f\)\{[\s\S]*?\n  \}\n  function renderPending\(\)", s)
    if not m:
        return s
    s = s[:m.start()] + _JS162_HELPERS + "\n  function renderPending()" + s[m.end():]

    s = s.replace(
        "${a.kind==='image'?'Image':'File'} · ${Math.max(1,Math.round((a.size||0)/1024))} KB",
        "${esc(a.status||(a.kind==='image'?'Image':'File'))} · ${Math.max(1,Math.round((a.size||0)/1024))} KB",
        1,
    )
    s = s.replace(
        "x.className='ace161-attachment-chip';x.innerHTML=",
        "x.className='ace161-attachment-chip';if(a.status==='Preparing…')x.dataset.processing='1';if(a.note)x.title=a.note;x.innerHTML=",
        1,
    )

    m = re.search(r"  function capturePending\(\)\{[\s\S]*?\n  \}\n  function syncAttachmentDecorations\(\)", s)
    if not m:
        return s
    s = s[:m.start()] + _JS162_CAPTURE + s[m.end():]
    return s + '\n' + JS162 + '\n// ACE162\n'


def _local(tag):
    return str(tag or '').rsplit('}', 1)[-1]


def _texts_in(node):
    out = []
    for e in node.iter():
        if _local(e.tag) == 't' and e.text:
            out.append(e.text)
    return ''.join(out)


def _extract_docx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    paras = []
    for e in root.iter():
        if _local(e.tag) == 'p':
            t = _texts_in(e).strip()
            if t:
                paras.append(t)
    return '\n'.join(paras)


def _num_key(name):
    m = re.search(r'(\d+)(?=\.xml$)', name)
    return int(m.group(1)) if m else 10**9


def _extract_pptx(raw):
    out = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = sorted(
            [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)],
            key=_num_key,
        )
        for i, name in enumerate(names, 1):
            root = ET.fromstring(z.read(name))
            lines = []
            for e in root.iter():
                if _local(e.tag) == 'p':
                    t = _texts_in(e).strip()
                    if t:
                        lines.append(t)
            if lines:
                out.append('Slide %d\n%s' % (i, '\n'.join(lines)))
    return '\n\n'.join(out)


def _extract_xlsx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.iter():
                if _local(si.tag) == 'si':
                    shared.append(_texts_in(si))
        sheets = sorted(
            [n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)],
            key=_num_key,
        )
        out = []
        for si, name in enumerate(sheets, 1):
            root = ET.fromstring(z.read(name))
            rows = []
            for row in root.iter():
                if _local(row.tag) != 'row':
                    continue
                vals = []
                for c in row:
                    if _local(c.tag) != 'c':
                        continue
                    ref = c.get('r') or ''
                    typ = c.get('t') or ''
                    v = next((x for x in c if _local(x.tag) == 'v'), None)
                    f = next((x for x in c if _local(x.tag) == 'f'), None)
                    value = ''
                    if typ == 'inlineStr':
                        value = _texts_in(c)
                    elif v is not None and v.text is not None:
                        value = v.text
                        if typ == 's':
                            try:
                                value = shared[int(value)]
                            except Exception:
                                pass
                        elif typ == 'b':
                            value = 'TRUE' if value == '1' else 'FALSE'
                    if f is not None and f.text:
                        value = '=' + f.text + ((' => ' + value) if value else '')
                    if value != '':
                        vals.append((ref + ': ' if ref else '') + value)
                if vals:
                    rows.append(' | '.join(vals))
            if rows:
                out.append('Sheet %d\n%s' % (si, '\n'.join(rows)))
    return '\n\n'.join(out)


def _extract_pdf(raw):
    exe = next((p for p in (
        '/opt/homebrew/bin/pdftotext',
        '/usr/local/bin/pdftotext',
        '/usr/bin/pdftotext',
    ) if Path(p).is_file()), '')
    if not exe:
        return '', 'PDF attached; local PDF text extraction is unavailable on this Mac.'
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
            f.write(raw)
            f.flush()
            p = subprocess.run(
                [exe, '-layout', f.name, '-'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
            )
        text = p.stdout.decode('utf-8', 'replace').strip()
        return text, '' if text else 'PDF attached, but no extractable text was found.'
    except Exception:
        return '', 'PDF attached, but local text extraction failed.'


def extract_attachment(name, raw):
    ext = Path(str(name or '')).suffix.lower()
    if ext == '.docx':
        return _extract_docx(raw), ''
    if ext == '.pptx':
        return _extract_pptx(raw), ''
    if ext == '.xlsx':
        return _extract_xlsx(raw), ''
    if ext == '.pdf':
        return _extract_pdf(raw)
    return '', 'This file type is attached but has no local text extractor.'


_post161 = ace.H.do_POST


def POST162(self):
    try:
        path = ace.urllib.parse.urlparse(self.path).path
    except Exception:
        path = self.path
    if path == '/api/attachments/extract':
        try:
            d = ace.parse_json(self)
            name = str(d.get('name') or 'attachment')
            enc = str(d.get('data') or '')
            if not enc:
                raise ValueError('No attachment data received.')
            raw = base64.b64decode(enc.encode('ascii'), validate=True)
            if len(raw) > 4_500_000:
                self.json_out({'error': 'Attachment exceeds the 4.5 MB local extraction limit.'}, 413)
                return
            text, note = extract_attachment(name, raw)
            self.json_out({
                'ok': True,
                'text': str(text or '')[:22000],
                'note': str(note or '')[:500],
            })
            return
        except Exception as e:
            self.json_out({'error': str(e)}, 400)
            return
    return _post161(self)


patch(H / 'index.html', 'ACE162_ATTACHMENTS', idx162)
patch(H / 'app.css', 'ACE162_ATTACHMENTS', lambda s: s + '\n' + CSS162 + '\n')
patch(H / 'app.js', 'ACE162_ATTACHMENTS', app162)
ace.H.do_POST = POST162

if __name__ == '__main__':
    ace.main()
