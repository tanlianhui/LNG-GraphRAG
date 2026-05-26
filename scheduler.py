"""
scheduler.py — Daily check for new LNG live stream replays at 08:00.

Health-checks Docker containers (Neo4j, MySQL, Adminer) and Ollama before
running a dry-run fetch. Lists any new videos found; does NOT auto-download.
User decides whether found videos should be whitelisted or ignored.
"""
import os
import sys
import subprocess
import time
import datetime
from pathlib import Path

try:
    import requests as _requests
except ImportError:
    _requests = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SCRIPT = Path(__file__).parent / 'fetch_new_vods.py'
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://0.0.0.0:11700')
CHECK_HOUR = 8

DOCKER_CONTAINERS = ['lng-neo4j', 'lng-mysql', 'lng-adminer']


def _tag(ok: bool) -> str:
    return 'OK  ' if ok else 'WARN'


def check_docker_containers() -> bool:
    if not _which('docker'):
        print('  [WARN] docker not found — skipping container checks')
        return False
    all_ok = True
    for name in DOCKER_CONTAINERS:
        result = subprocess.run(
            ['docker', 'inspect', '--format', '{{.State.Running}}', name],
            capture_output=True, text=True, timeout=10,
        )
        running = result.stdout.strip() == 'true'
        print(f'  [{_tag(running)}] Docker container: {name}')
        if not running:
            all_ok = False
    return all_ok


def check_ollama() -> bool:
    host = OLLAMA_HOST.replace('0.0.0.0', 'localhost')
    if not host.startswith('http'):
        host = f'http://{host}'
    url = f"{host.rstrip('/')}/api/tags"
    ok = False
    if _requests is not None:
        try:
            resp = _requests.get(url, timeout=5)
            ok = resp.status_code == 200
        except Exception:
            ok = False
    else:
        result = subprocess.run(
            ['curl', '-sf', url], capture_output=True, timeout=5
        )
        ok = result.returncode == 0
    print(f'  [{_tag(ok)}] Ollama: {url}')
    return ok


def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def run_daily_check():
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'\n[scheduler] ── Daily check  {ts} ──')

    docker_ok = check_docker_containers()
    if not docker_ok:
        print('[scheduler] One or more Docker containers are down — aborting check.')
        return

    ollama_ok = check_ollama()
    if not ollama_ok:
        print('[scheduler] Ollama not healthy — aborting check.')
        return

    print('[scheduler] All services healthy. Checking for new videos ...')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--dry-run'],
        check=False,
    )
    if result.returncode != 0:
        print(f'[scheduler] fetch_new_vods.py exited with code {result.returncode}')
    else:
        print('[scheduler] Check complete.')


def seconds_until_next_check() -> float:
    now = datetime.datetime.now()
    target = now.replace(hour=CHECK_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def main():
    print(f'[scheduler] Started — daily video check at {CHECK_HOUR:02d}:00')
    # Run once on startup to validate service health
    run_daily_check()
    while True:
        wait = seconds_until_next_check()
        next_dt = datetime.datetime.now() + datetime.timedelta(seconds=wait)
        print(f'[scheduler] Next check: {next_dt.strftime("%Y-%m-%d %H:%M:%S")}')
        time.sleep(wait)
        run_daily_check()


if __name__ == '__main__':
    main()
