#!/usr/bin/env python3
"""A.C.E. 1.5.4 runtime bridge.

Keeps the proven 1.5.3 backend intact while fixing PPTX-only poster previews.
This is intentionally small so it can be delivered through A.C.E.'s GitHub patch updater.
"""
from pathlib import Path
import base64, importlib.util, os, platform, subprocess, tempfile, time

HERE=Path(__file__).resolve().parent
SERVER=HERE/'ACE Server.py'
spec=importlib.util.spec_from_file_location('ace_server_runtime',str(SERVER))
ace=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ace)

ace.VERSION='1.5.4'
try: ace.UPDATE_STATE['current_version']='1.5.4'
except Exception: pass

_original_snapshot=ace._job_snapshot
_original_embedded=ace._pptx_embedded_thumbnail


def _quicklook_once(path):
    path=Path(path)
    if platform.system()!='Darwin' or not path.is_file() or not Path('/usr/bin/qlmanage').exists():
        return ''
    try:
        with tempfile.TemporaryDirectory(prefix='ace_preview_') as td:
            out=Path(td)
            subprocess.run(['/usr/bin/qlmanage','-t','-s','1400','-o',str(out),str(path)],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           timeout=12,check=False)
            imgs=[p for p in out.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg','.jpeg'}]
            if imgs:
                img=max(imgs,key=lambda p:p.stat().st_size)
                return base64.b64encode(img.read_bytes()).decode('ascii')
    except Exception:
        pass
    return ''


def _poster_preview_retry(job):
    if str(job.get('kind') or '')!='poster' or not job.get('pptx_rel'):
        return False
    if job.get('preview_rel') or job.get('daemon_preview_url') or job.get('rendered_pages'):
        return True
    tries=int(job.get('_ace_preview_tries') or 0)
    if tries>=5:
        return False
    job['_ace_preview_tries']=tries+1
    try:
        cwd=ace._project_cwd(str(job.get('project_id') or ''))
        rel=str(job.get('pptx_rel') or '')
        pptx=(cwd/rel).resolve() if cwd and rel else None
        if not pptx or not pptx.is_file() or pptx.stat().st_size<=0:
            return False
        # The package may have been discovered a fraction of a second before its
        # final write finished. Give it one cheap stability check.
        size=pptx.stat().st_size
        time.sleep(.28)
        if not pptx.is_file() or pptx.stat().st_size!=size:
            return False
        thumb=_original_embedded(pptx) or _quicklook_once(pptx)
        if thumb:
            job['rendered_pages']=[thumb]
            job['stage']='Ready'
            return True
    except Exception:
        pass
    return False


def _snapshot(job):
    # Retry preview generation on status polls.  1.5.1/1.5.3 tried only once;
    # if Quick Look had not noticed the new PPTX yet, the UI stayed on Ready.
    _poster_preview_retry(job)
    snap=_original_snapshot(job)
    if str(job.get('kind') or '')=='poster' and str(job.get('status') or '')=='done' and job.get('pptx_rel'):
        if job.get('rendered_pages'):
            snap['preview_ready']=True
            snap['rendered_count']=len(job.get('rendered_pages') or [])
            snap['rendered_base']='/api/opendesign/rendered?job='+ace.urllib.parse.quote(str(job.get('job_id')))+'&page='
            snap['stage']='Ready'
        elif int(job.get('_ace_preview_tries') or 0)>=5:
            snap['stage']='Poster ready — preview unavailable'
    return snap

ace._job_snapshot=_snapshot

if __name__=='__main__':
    ace.main()
