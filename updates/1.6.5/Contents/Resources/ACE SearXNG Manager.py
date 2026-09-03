#!/usr/bin/env python3
"""A.C.E. managed private SearXNG runtime.

This helper uses only the Python standard library. On first launch it creates a
private virtual environment under ~/Library/Application Support/A.C.E, downloads
a pinned SearXNG source release, installs that release's pinned dependencies,
and starts the source directly on 127.0.0.1:8888.

No Docker, Terminal interaction, system daemon, or separately launched app is
required. The installed runtime is owned by A.C.E. and can be rebuilt safely if
its pinned version changes.
"""
from pathlib import Path
import atexit
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

PIN = '8f452ee89293d9a752a776f4c33f5a5f124fff97'
SOURCE_URL = f'https://github.com/searxng/searxng/archive/{PIN}.tar.gz'
LOCAL_URL = 'http://127.0.0.1:8888'
ROOT = Path.home() / 'Library' / 'Application Support' / 'A.C.E' / 'searxng'
VENV = ROOT / 'venv'
PY = VENV / 'bin' / 'python3'
SOURCE = ROOT / 'source'
SETTINGS = ROOT / 'settings.yml'
READY = ROOT / 'ready.json'
PIDFILE = ROOT / 'searxng.pid'
LOG = Path.home() / 'Library' / 'Logs' / 'ACE-SearXNG.log'
INSTALL_LOCK = ROOT / 'install.lock'

_LOCK = threading.RLock()
_INSTALL_THREAD = None
_OWNED_PID = None
_LAST_ERROR = ''


def _log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')
    except Exception:
        pass


def _health(timeout=0.8):
    try:
        req = urllib.request.Request(
            LOCAL_URL + '/config',
            headers={'User-Agent': 'A.C.E./1.6.5', 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if int(getattr(r, 'status', 200) or 200) != 200:
                return False
            data = json.loads(r.read(180_000).decode('utf-8', errors='replace'))
            return isinstance(data, dict) and isinstance(data.get('engines'), list)
    except Exception:
        return False


def healthy():
    return _health()


def _ready_for_pin():
    try:
        if not PY.is_file() or not (SOURCE / 'searx' / 'webapp.py').is_file() or not READY.is_file():
            return False
        d = json.loads(READY.read_text(encoding='utf-8'))
        return d.get('pin') == PIN
    except Exception:
        return False


def _settings_text():
    secret = ''
    try:
        if SETTINGS.is_file():
            old = SETTINGS.read_text(encoding='utf-8')
            for line in old.splitlines():
                if line.strip().startswith('secret_key:'):
                    secret = line.split(':', 1)[1].strip().strip('"\'')
                    break
    except Exception:
        pass
    if not secret or secret == 'ultrasecretkey':
        secret = secrets.token_hex(32)
    return f'''use_default_settings: true\n\ngeneral:\n  debug: false\n  instance_name: "A.C.E. Search"\n  enable_metrics: false\n\nsearch:\n  safe_search: 0\n  autocomplete: ""\n  formats:\n    - html\n    - json\n\nserver:\n  bind_address: "127.0.0.1"\n  port: 8888\n  secret_key: "{secret}"\n  limiter: false\n  public_instance: false\n  image_proxy: false\n\nvalkey:\n  url: false\n\noutgoing:\n  request_timeout: 2.0\n  max_request_timeout: 3.0\n  enable_http2: true\n'''


def _write_settings():
    ROOT.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(_settings_text(), encoding='utf-8')


def _run(cmd, timeout, cwd=None, env=None):
    _log('RUN ' + ' '.join(str(x) for x in cmd))
    return subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def _download(url, dest, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': 'A.C.E./1.6.5'})
    with urllib.request.urlopen(req, timeout=timeout) as r, dest.open('wb') as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def _safe_extract(archive, dest):
    dest = dest.resolve()
    with tarfile.open(archive, 'r:gz') as tf:
        members = tf.getmembers()
        for m in members:
            target = (dest / m.name).resolve()
            if target != dest and dest not in target.parents:
                raise RuntimeError('Unsafe path in SearXNG source archive')
        tf.extractall(dest, members=members)
    dirs = [p for p in dest.iterdir() if p.is_dir()]
    if len(dirs) != 1 or not (dirs[0] / 'requirements.txt').is_file():
        raise RuntimeError('Unexpected SearXNG source archive layout')
    return dirs[0]


def _install_runtime():
    global _LAST_ERROR
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        INSTALL_LOCK.write_text(str(os.getpid()), encoding='utf-8')
    except Exception:
        pass
    archive = ROOT / f'searxng-{PIN}.tar.gz'
    stage = ROOT / 'source-stage'
    try:
        if _ready_for_pin():
            _write_settings()
            return True

        _log(f'Installing private SearXNG runtime at pin {PIN}')
        for p in (VENV, SOURCE, stage):
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass

        r = _run([sys.executable, '-m', 'venv', str(VENV)], timeout=120)
        if r.returncode != 0 or not PY.is_file():
            raise RuntimeError('Could not create private Python environment: ' + (r.stdout or '')[-1200:])

        _log('Downloading pinned SearXNG source')
        _download(SOURCE_URL, archive, timeout=90)
        stage.mkdir(parents=True, exist_ok=True)
        extracted = _safe_extract(archive, stage)

        env = dict(os.environ)
        env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
        env['PIP_NO_INPUT'] = '1'
        r = _run(
            [PY, '-m', 'pip', 'install', '--prefer-binary', '--no-input', '-r', extracted / 'requirements.txt'],
            timeout=420,
            env=env,
        )
        if r.returncode != 0:
            raise RuntimeError('SearXNG dependency installation failed: ' + (r.stdout or '')[-1800:])

        shutil.move(str(extracted), str(SOURCE))
        shutil.rmtree(stage, ignore_errors=True)
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass

        verify = (
            'import sys; '
            f'sys.path.insert(0,{str(SOURCE)!r}); '
            'import searx; print(searx.__file__)'
        )
        r = _run([PY, '-c', verify], timeout=25, env=env)
        if r.returncode != 0:
            raise RuntimeError('Installed SearXNG source could not be imported: ' + (r.stdout or '')[-1000:])

        _write_settings()
        READY.write_text(
            json.dumps({'pin': PIN, 'installed_at': time.time(), 'source_url': SOURCE_URL}, indent=2),
            encoding='utf-8',
        )
        _log('Private SearXNG runtime installation complete')
        return True
    except Exception as e:
        _LAST_ERROR = str(e)
        _log('INSTALL ERROR ' + _LAST_ERROR)
        return False
    finally:
        try:
            INSTALL_LOCK.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _read_pid():
    try:
        return int(PIDFILE.read_text(encoding='utf-8').strip())
    except Exception:
        return 0


def _pid_is_ours(pid):
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    try:
        r = subprocess.run(
            ['/bin/ps', '-p', str(pid), '-o', 'command='],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
        cmd = r.stdout or ''
        return 'searx.webapp' in cmd and str(VENV) in cmd
    except Exception:
        return False


def _stop_stale_owned_process():
    pid = _read_pid()
    if not _pid_is_ours(pid):
        try:
            PIDFILE.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if _health(timeout=0.35):
        return
    try:
        os.kill(pid, 15)
        time.sleep(0.35)
    except Exception:
        pass


def _start_service():
    global _OWNED_PID, _LAST_ERROR
    if _health():
        return True
    if not _ready_for_pin() and not _install_runtime():
        return False
    _write_settings()
    _stop_stale_owned_process()
    if _health():
        return True

    env = dict(os.environ)
    env.update({
        'SEARXNG_SETTINGS_PATH': str(SETTINGS),
        'SEARXNG_BIND_ADDRESS': '127.0.0.1',
        'SEARXNG_PORT': '8888',
        'SEARXNG_LIMITER': 'false',
        'SEARXNG_PUBLIC_INSTANCE': 'false',
        'SEARXNG_IMAGE_PROXY': 'false',
        'PYTHONPATH': str(SOURCE),
        'PYTHONUNBUFFERED': '1',
    })
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        out = LOG.open('a', encoding='utf-8')
        p = subprocess.Popen(
            [str(PY), '-m', 'searx.webapp'],
            cwd=str(SOURCE),
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _OWNED_PID = p.pid
        PIDFILE.write_text(str(p.pid), encoding='utf-8')
        _log(f'Started private SearXNG as PID {p.pid}')
    except Exception as e:
        _LAST_ERROR = str(e)
        _log('START ERROR ' + _LAST_ERROR)
        return False

    deadline = time.monotonic() + 18.0
    while time.monotonic() < deadline:
        if p.poll() is not None:
            _LAST_ERROR = f'SearXNG exited during startup with code {p.returncode}'
            _log(_LAST_ERROR)
            return False
        if _health(timeout=0.5):
            _log('Private SearXNG is healthy on 127.0.0.1:8888')
            return True
        time.sleep(0.35)
    _LAST_ERROR = 'SearXNG did not become healthy within 18 seconds'
    _log(_LAST_ERROR)
    return False


def _worker():
    global _INSTALL_THREAD
    try:
        with _LOCK:
            _start_service()
    finally:
        with _LOCK:
            _INSTALL_THREAD = None


def ensure_started_async():
    global _INSTALL_THREAD
    if _health(timeout=0.25):
        return True
    with _LOCK:
        if _INSTALL_THREAD and _INSTALL_THREAD.is_alive():
            return False
        _INSTALL_THREAD = threading.Thread(target=_worker, name='ACE-SearXNG', daemon=True)
        _INSTALL_THREAD.start()
    return False


def ensure_started(block=False, timeout=3.0):
    if _health(timeout=0.3):
        return True
    ensure_started_async()
    if not block:
        return False
    # If the private runtime is already installed, startup is normally quick.
    # On the very first launch, do not freeze A.C.E. while dependencies prepare.
    if not _ready_for_pin():
        return False
    deadline = time.monotonic() + max(0.0, float(timeout))
    while time.monotonic() < deadline:
        if _health(timeout=0.35):
            return True
        time.sleep(0.15)
    return False


def status():
    t = _INSTALL_THREAD
    return {
        'healthy': _health(timeout=0.25),
        'installed': _ready_for_pin(),
        'installing': bool(t and t.is_alive()),
        'pin': PIN,
        'url': LOCAL_URL,
        'last_error': _LAST_ERROR,
    }


def stop_owned():
    global _OWNED_PID
    pid = int(_OWNED_PID or _read_pid() or 0)
    if not _pid_is_ours(pid):
        return
    try:
        os.kill(pid, 15)
        _log(f'Stopped private SearXNG PID {pid}')
    except Exception:
        pass


# Best-effort cleanup if the A.C.E. backend exits normally. In normal use the
# service remains idle and lightweight for the lifetime of the A.C.E. backend.
atexit.register(stop_owned)
