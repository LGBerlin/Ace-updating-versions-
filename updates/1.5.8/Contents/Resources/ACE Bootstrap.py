#!/usr/bin/env python3
"""A.C.E. 1.5.8 cumulative bridge for direct upgrade from 1.5.6.

Loads the bundled 1.5.7 runtime first (which applies the intent-first chat update and
carries forward 1.5.6 Stop/Preview services), then applies the 1.5.8 poster Edit fix.
"""
from pathlib import Path
import importlib.util

H = Path(__file__).resolve().parent
BASE = H / 'ACE Base 1.5.7.py'

spec = importlib.util.spec_from_file_location('ace_base_157', str(BASE))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


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


def idx158(s):
    s = s.replace('app.css?v=157-intent', 'app.css?v=158-editfix')
    s = s.replace('app.js?v=157-intent', 'app.js?v=158-editfix')
    s = s.replace('app.css?v=156-editor', 'app.css?v=158-editfix')
    s = s.replace('app.js?v=156-editor', 'app.js?v=158-editfix')
    s = s.replace('Current version: v1.5.7', 'Current version: v1.5.8')
    s = s.replace('Current version: v1.5.6', 'Current version: v1.5.8')
    return s + '\n<!--ACE158-->\n'


JS158 = r'''
(function(){
  if(window.__ACE158_EDIT_FIX__)return;window.__ACE158_EDIT_FIX__=1;
  function root158(){return document.getElementById('artifactStudio')||document.querySelector('.artifact-studio')||document.body;}
  function isEdit158(el){try{const t=((el.textContent||'')+' '+(el.title||'')+' '+(el.getAttribute('aria-label')||'')).toLowerCase();return /\bedit\b/.test(t);}catch(_){return false;}}
  function canEdit158(){try{return typeof studioJob!=='undefined'&&studioJob&&studioJob.job_id&&typeof window.acePosterEdit156==='function';}catch(_){return false;}}
  function legacy158(msg){return String(msg||'').toLowerCase().includes('direct layout editing is available for presentation slides in this version');}
  if(!window.__ACE158_ORIG_ALERT__){
    window.__ACE158_ORIG_ALERT__=window.alert;
    window.alert=function(msg){
      if(legacy158(msg)&&canEdit158()){try{window.acePosterEdit156();}catch(_){}return;}
      return window.__ACE158_ORIG_ALERT__.call(window,msg);
    };
  }
  function bind158(){
    const root=root158();
    [...root.querySelectorAll('button,a,[role="button"]')].filter(isEdit158).forEach(old=>{
      if(old.dataset.ace158==='1')return;
      const b=old.cloneNode(true);b.dataset.ace158='1';
      b.addEventListener('click',e=>{
        e.preventDefault();e.stopPropagation();if(e.stopImmediatePropagation)e.stopImmediatePropagation();
        if(canEdit158()){window.acePosterEdit156();return false;}
        window.__ACE158_ORIG_ALERT__.call(window,'The poster preview is not ready yet.');return false;
      },true);
      old.replaceWith(b);
    });
  }
  const mo=new MutationObserver(bind158);try{mo.observe(document.body,{childList:true,subtree:true});}catch(_){}
  setInterval(bind158,350);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind158,{once:true});else bind158();
})();
// ACE158
'''


patch(H / 'index.html', 'ACE158', idx158)
patch(H / 'app.css', 'ACE158', lambda s: s + '\n/*ACE158*/\n')
patch(H / 'app.js', 'ACE158', lambda s: s + '\n' + JS158 + '\n// ACE158\n')

base.ace.VERSION = '1.5.8'
try:
    base.ace.UPDATE_STATE['current_version'] = '1.5.8'
except Exception:
    pass

if __name__ == '__main__':
    base.ace.main()
