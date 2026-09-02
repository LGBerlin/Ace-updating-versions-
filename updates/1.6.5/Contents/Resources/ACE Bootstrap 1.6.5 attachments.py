#!/usr/bin/env python3
"""A.C.E. 1.6.5 — real chat attachments.

Loads the validated 1.6.4 runtime. This update makes the existing attachment lane
explicitly useful for normal chat: Word, PowerPoint, PDF, Excel and text-bearing
files are extracted locally and supplied as hidden context, while PNG/JPG/WebP/GIF
images are inspected through the active local Ollama vision model before the normal
A.C.E. answer is generated. Attachment chips/history, drag/drop, paste, projects,
voice, Stop, Chat/Live, artifacts, Preview/Edit, downloads and research stay on the
1.6.4 cumulative runtime.
"""
from pathlib import Path
import base64
import importlib.util
import io
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.6.4.py'
spec = importlib.util.spec_from_file_location('ace_base_164', str(BASE))
b164 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b164)
ace = b164.ace

ace.VERSION = '1.6.5'
try:
    ace.UPDATE_STATE['current_version'] = '1.6.5'
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


def idx165(s):
    s = s.replace('app.css?v=164-final-qa', 'app.css?v=165-attachments')
    s = s.replace('app.js?v=164-integration-v1', 'app.js?v=165-attachments')
    s = s.replace('Current version: v1.6.4', 'Current version: v1.6.5')
    return s + '\n<!--ACE165_ATTACHMENTS-->\n'


CSS165 = r'''
.ace161-attachment-chip[data-ace165-vision="1"]{box-shadow:inset 0 0 0 1px rgba(67,214,176,.28)}
.ace161-attachment-chip[data-ace165-error="1"]{box-shadow:inset 0 0 0 1px rgba(255,175,91,.3)}
/*ACE165_ATTACHMENTS*/
'''


JS165 = r'''
(function(){
  if(window.__ACE165_ATTACHMENTS__)return;
  window.__ACE165_ATTACHMENTS__=1;

  const priorFetch=window.fetch.bind(window);
  const ACCEPT='.png,.jpg,.jpeg,.webp,.gif,.docx,.doc,.rtf,.pptx,.pdf,.xlsx,.txt,.md,.csv,.json,.html,.htm,.xml,.yaml,.yml,.log';

  function tuneAttachmentPicker(){
    try{
      const inputs=[...document.querySelectorAll('input[type="file"]')];
      for(const input of inputs){
        const key=[input.id||'',input.name||'',input.className||'',input.getAttribute('aria-label')||'',input.getAttribute('title')||''].join(' ');
        const nearComposer=!!input.closest?.('.composer,.composer-wrap,#ace161AttachmentTray');
        if(!nearComposer&&!/attach|upload|file/i.test(key))continue;
        input.accept=ACCEPT;
        input.multiple=true;
        input.setAttribute('aria-label','Attach images or files');
        input.title='Attach images or files';
      }
      const root=document.querySelector('.composer-wrap')||document.querySelector('.composer')||document;
      [...root.querySelectorAll('button,[role="button"]')].forEach(b=>{
        const key=[b.id||'',b.className||'',b.title||'',b.getAttribute('aria-label')||'',b.textContent||''].join(' ');
        if(/attach|upload|paperclip/i.test(key)){
          b.title='Attach images or files';
          b.setAttribute('aria-label','Attach images or files');
        }
      });
    }catch(_){ }
  }

  function requestMatchesQueue(q,input,init){
    try{
      if(!q||!Array.isArray(q.items)||!q.items.length)return null;
      if(Date.now()-Number(q.created||0)>=120000)return null;
      const u=new URL(typeof input==='string'?input:input.url,location.href);
      if(u.origin!==location.origin||!['/api/agent/fast-stream','/api/agent'].includes(u.pathname))return null;
      if(String(init?.method||'GET').toUpperCase()!=='POST'||typeof init?.body!=='string')return null;
      const body=JSON.parse(init.body);
      if(body?.message!==q.text)return null;
      return body;
    }catch(_){return null;}
  }

  async function prepareVision(q){
    if(!q||q.__ace165Vision==='done'||q.__ace165Vision==='failed')return;
    const images=q.items.filter(a=>String(a?.kind||'')==='image'&&String(a?.data||'').startsWith('data:image/')).slice(0,4);
    if(!images.length){q.__ace165Vision='done';return;}
    if(q.__ace165VisionPromise){await q.__ace165VisionPromise;return;}
    q.__ace165Vision='running';
    q.__ace165VisionPromise=(async()=>{
      try{
        const r=await priorFetch('/api/attachments/vision',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            prompt:String(q.text||'').slice(0,5000),
            images:images.map(a=>({name:String(a.name||'image'),type:String(a.type||''),data:String(a.data||'')}))
          })
        });
        const d=await r.json();
        if(!r.ok||d.error)throw new Error(d.error||('HTTP '+r.status));
        const description=String(d.description||'').trim();
        if(!description)throw new Error('The local vision model returned no image description.');
        // Existing 1.6.4 attachment-context logic already injects item.text into
        // the exact user request. Put the visual evidence there rather than
        // changing the proven chat transport or conversation state.
        images[0].text='Local visual analysis of attached image'+(images.length>1?'s':'')+':\n'+description;
        images[0].note='Analyzed locally with '+String(d.model||'the active vision model')+'.';
        for(let i=1;i<images.length;i++)images[i].note='Included in the local visual analysis above.';
        q.__ace165Vision='done';
      }catch(e){
        const msg='Image attached, but local visual analysis failed: '+String(e&&e.message||e);
        images[0].note=msg.slice(0,500);
        q.__ace165Vision='failed';
      }finally{
        q.__ace165VisionPromise=null;
      }
    })();
    await q.__ace165VisionPromise;
  }

  window.fetch=async function(input,init){
    try{
      const q=window.__ACE162_ATTACHMENT_QUEUE__;
      if(requestMatchesQueue(q,input,init))await prepareVision(q);
    }catch(_){ }
    return priorFetch(input,init);
  };

  const refresh=()=>{tuneAttachmentPicker();};
  setTimeout(refresh,80);
  setInterval(refresh,1500);
})();
// ACE165_ATTACHMENTS
'''


def app165(s):
    # Lift the former 4.5 MB preparation ceiling for normal local documents/images.
    # The backend still enforces a bounded 12 MB request limit.
    s = s.replace("if(f.size>4500000)return '';", "if(f.size>12000000)return '';", 1)
    s = s.replace(
        "if(!f||f.size>4500000)return {text:'',note:f&&f.size>4500000?'File is too large for local text extraction (4.5 MB limit).':''};",
        "if(!f||f.size>12000000)return {text:'',note:f&&f.size>12000000?'File is too large for local text extraction (12 MB limit).':''};",
        1,
    )
    s = s.replace("if(!/\\.(docx|pptx|xlsx|pdf)$/i.test(f.name||''))return {text:'',note:''};",
                  "if(!/\\.(docx|doc|rtf|pptx|xlsx|pdf)$/i.test(f.name||''))return {text:'',note:''};", 1)
    s = s.replace("else if(/\\.(docx|pptx|xlsx|pdf)$/i.test(f.name||'')){const x=await ace162Extract(f);",
                  "else if(/\\.(docx|doc|rtf|pptx|xlsx|pdf)$/i.test(f.name||'')){const x=await ace162Extract(f);", 1)
    s = s.replace('const max=1100,scale=', 'const max=1600,scale=', 1)
    s = s.replace("return c.toDataURL('image/jpeg',.8);", "return c.toDataURL('image/jpeg',.84);", 1)
    return s + '\n' + JS165 + '\n// ACE165\n'


# ----------------------------- local file extraction -----------------------------
def _local(tag):
    return str(tag or '').rsplit('}', 1)[-1]


def _texts_in(node):
    out = []
    for e in node.iter():
        if _local(e.tag) == 't' and e.text:
            out.append(e.text)
    return ''.join(out)


def _num_key(name):
    m = re.search(r'(\d+)(?=\.xml$)', str(name or ''))
    return int(m.group(1)) if m else 10**9


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


def _extract_textutil(raw, suffix):
    exe = '/usr/bin/textutil'
    if not Path(exe).is_file():
        return '', 'This Word/RTF file is attached, but macOS text conversion is unavailable.'
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix) as f:
            f.write(raw)
            f.flush()
            p = subprocess.run(
                [exe, '-convert', 'txt', '-stdout', f.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
        text = p.stdout.decode('utf-8', 'replace').strip()
        return text, '' if text else 'The file was attached, but no extractable text was found.'
    except Exception:
        return '', 'The file was attached, but local Word/RTF text extraction failed.'


def _pdfkit_text(path):
    exe = '/usr/bin/osascript'
    if not Path(exe).is_file():
        return ''
    # PDFKit is built into macOS. JXA avoids adding a Python/PyObjC dependency.
    pjson = json.dumps(str(path))
    script = """ObjC.import('Foundation');ObjC.import('PDFKit');
const p=%s;
const u=$.NSURL.fileURLWithPath(p);
const d=$.PDFDocument.alloc.initWithURL(u);
if(!d){throw new Error('PDFDocument could not be opened');}
const s=d.string;
if(s){console.log(ObjC.unwrap(s));}
""" % pjson
    try:
        p = subprocess.run(
            [exe, '-l', 'JavaScript', '-e', script],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        return p.stdout.decode('utf-8', 'replace').strip()
    except Exception:
        return ''


def _extract_pdf(raw):
    pdftotext = next((p for p in (
        '/opt/homebrew/bin/pdftotext',
        '/usr/local/bin/pdftotext',
        '/usr/bin/pdftotext',
    ) if Path(p).is_file()), '')
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
            f.write(raw)
            f.flush()
            text = ''
            if pdftotext:
                p = subprocess.run(
                    [pdftotext, '-layout', f.name, '-'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=12,
                    check=False,
                )
                text = p.stdout.decode('utf-8', 'replace').strip()
            if not text:
                text = _pdfkit_text(f.name)
        if text:
            return text, ''
        return '', 'PDF attached, but no extractable text was found.'
    except Exception:
        return '', 'PDF attached, but local text extraction failed.'


def extract_attachment(name, raw):
    ext = Path(str(name or '')).suffix.lower()
    if ext == '.docx':
        return _extract_docx(raw), ''
    if ext in {'.doc', '.rtf'}:
        return _extract_textutil(raw, ext)
    if ext == '.pptx':
        return _extract_pptx(raw), ''
    if ext == '.xlsx':
        return _extract_xlsx(raw), ''
    if ext == '.pdf':
        return _extract_pdf(raw)
    return '', 'This file type is attached but has no local text extractor.'


# ----------------------------- local Ollama vision -----------------------------
def _ollama_json(path, payload, timeout=30):
    req = urllib.request.Request(
        'http://127.0.0.1:11434' + path,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(8_000_000).decode('utf-8', 'replace'))


def _active_model():
    try:
        model = ace.choose_model(ace.ollama_models())
        if model:
            return str(model)
    except Exception:
        pass
    return 'qwen3.5:4b'


def _vision_description(prompt, images):
    model = _active_model()
    try:
        info = _ollama_json('/api/show', {'model': model}, timeout=8)
        capabilities = {str(x).lower() for x in (info.get('capabilities') or [])}
        if capabilities and 'vision' not in capabilities:
            raise ValueError('The active Ollama model %s does not advertise vision support.' % model)
    except urllib.error.URLError:
        raise ValueError('Ollama is not reachable on this Mac.')

    cleaned = []
    names = []
    for item in list(images or [])[:4]:
        data = str((item or {}).get('data') or '')
        if ',' in data and data.lower().startswith('data:image/'):
            data = data.split(',', 1)[1]
        if not data:
            continue
        # Validate client data before forwarding it to Ollama.
        raw = base64.b64decode(data.encode('ascii'), validate=True)
        if len(raw) > 4_000_000:
            raise ValueError('Prepared image exceeds the local vision request limit.')
        cleaned.append(base64.b64encode(raw).decode('ascii'))
        names.append(str((item or {}).get('name') or ('Image %d' % len(cleaned)))[:180])
    if not cleaned:
        raise ValueError('No usable image data was received.')

    user_prompt = str(prompt or '').strip()[:5000]
    instruction = (
        'Inspect the attached image%s carefully for another A.C.E. response. '
        'Return factual visual evidence only: visible objects/people, readable text, '
        'tables/charts, UI state, layout and any details relevant to the user request. '
        'Do not invent content that is not visible. Image names in order: %s. '
        'User request: %s'
    ) % ('s' if len(cleaned) != 1 else '', ', '.join(names), user_prompt or 'Review the attachment.')
    result = _ollama_json('/api/chat', {
        'model': model,
        'messages': [{'role': 'user', 'content': instruction, 'images': cleaned}],
        'stream': False,
        'think': False,
        'options': {'temperature': 0.1},
    }, timeout=40)
    msg = result.get('message') or {}
    text = str(msg.get('content') or '').strip()
    if not text:
        raise ValueError('The local vision model returned no visual analysis.')
    return model, text[:12000]


_post164 = ace.H.do_POST


def POST165(self):
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
            if len(raw) > 12_000_000:
                self.json_out({'error': 'Attachment exceeds the 12 MB local extraction limit.'}, 413)
                return
            text, note = extract_attachment(name, raw)
            self.json_out({
                'ok': True,
                'text': str(text or '')[:50000],
                'note': str(note or '')[:500],
            })
            return
        except Exception as e:
            self.json_out({'error': str(e)}, 400)
            return

    if path == '/api/attachments/vision':
        try:
            d = ace.parse_json(self)
            model, description = _vision_description(d.get('prompt'), d.get('images'))
            self.json_out({'ok': True, 'model': model, 'description': description})
            return
        except Exception as e:
            self.json_out({'error': str(e)}, 400)
            return

    return _post164(self)


patch(H / 'index.html', 'ACE165_ATTACHMENTS', idx165)
patch(H / 'app.css', 'ACE165_ATTACHMENTS', lambda s: s + '\n' + CSS165 + '\n')
patch(H / 'app.js', 'ACE165_ATTACHMENTS', app165)
ace.H.do_POST = POST165

if __name__ == '__main__':
    ace.main()
