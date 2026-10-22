"""Checkout-scoped, persistent Docker test runner. Never operates speakers directly."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

LABEL = 'dev.wisp.checkout'
ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['docker', *args], check=check, text=True,
                          capture_output=capture)


def name_for(root: Path) -> str:
    return 'wisp-test-' + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]


def private_ipv4(value: str) -> str:
    address = ipaddress.IPv4Address(value)
    if not any(address in ipaddress.ip_network(net) for net in
               ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Use a private LAN IPv4 address, not localhost or a container address.')
    return str(address)


def settings() -> tuple[str, str, str]:
    base = os.getenv('WISP_BASE_URL', '')
    parsed = urlsplit(base)
    if (parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port != 9001):
        raise ValueError('Set WISP_BASE_URL=http://YOUR_MAC_LAN_IP:9001 before starting.')
    private_ipv4(parsed.hostname)
    parts = os.getenv('WISP_SPEAKER_IPS', '').split(',')
    if not 1 <= len(parts) <= 8 or any(not part.strip() for part in parts):
        raise ValueError('Provide SPEAKER_IPS as one to eight comma-separated speaker LAN IPs.')
    ips = ','.join(dict.fromkeys(private_ipv4(part.strip()) for part in parts))
    zone = os.getenv('TZ', 'America/Toronto')
    return base.rstrip('/'), ips, zone


def paused_config(source: Path) -> dict:
    if not source.exists():
        return {'version': 1, 'schedules': {}}
    raw = json.loads(source.read_text())
    if not isinstance(raw, dict):
        raise ValueError('Local config must contain an object; refusing to copy it.')
    schedules = raw.get('schedules', raw)
    if not isinstance(schedules, dict):
        raise ValueError('Local schedules must contain an object; refusing to copy them.')
    for entries in schedules.values():
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError('Invalid local schedule entry; refusing to copy it.')
        for item in entries:
            item['paused'] = True
    return {'version': 1, 'schedules': schedules}


def prepare_state(root: Path) -> Path:
    state = root / '.wisp-container'
    if state.is_symlink():
        raise ValueError('Test state directory must not be a symbolic link.')
    state.mkdir(exist_ok=True)
    config = state / 'config.json'
    favorites = state / 'favorites.json'
    for path in (config, favorites):
        if path.is_symlink():
            raise ValueError('Test state files must not be symbolic links.')
    source = Path(os.getenv('CONFIG_FILE', str(root / '.wisp-dev.json')))
    if not config.exists():
        content = paused_config(source)
        with config.open('x') as stream:
            json.dump(content, stream, indent=2)
    source_favorites = Path(os.getenv('FAVORITES_FILE', str(source.with_name('favorites.json'))))
    if not favorites.exists() and source_favorites.is_file():
        # Validate before copying. Atomic favorites replacement requires a directory mount.
        json.loads(source_favorites.read_text())
        with favorites.open('xb') as stream:
            stream.write(source_favorites.read_bytes())
    return state


def owned_container(root: Path, name: str) -> dict | None:
    result = docker('container', 'inspect', name, capture=True, check=False)
    if result.returncode:
        # Daemon health was checked first; do not treat other inspection errors as absence.
        if 'No such container' in result.stderr or 'No such object' in result.stderr:
            return None
        raise ValueError('Docker could not inspect the test container. No changes made.')
    info = json.loads(result.stdout)[0]
    if info.get('Config', {}).get('Labels', {}).get(LABEL) != str(root.resolve()):
        raise ValueError('Container ownership does not match this checkout. Refusing to touch it.')
    return info



def check_local_engine() -> None:
    """Bind mounts and callback addresses must belong to this computer, not a remote daemon."""
    host = None if os.getenv('DOCKER_CONTEXT') else os.getenv('DOCKER_HOST')
    if not host:
        contexts = json.loads(docker('context', 'inspect', capture=True).stdout)
        host = contexts[0]['Endpoints']['docker']['Host']
    if not isinstance(host, str) or not host.startswith('unix://'):
        raise ValueError('Use a local Docker Desktop/Engine context, not a remote Docker host.')

def up(root: Path, name: str) -> None:
    base, ips, zone = settings()
    if owned_container(root, name) is not None:
        raise ValueError('Test container already exists. Run task container:down before rebuilding.')
    # Do not stop an unrelated process or silently compete with task up.
    with socket.socket() as probe:
        try:
            probe.bind(('0.0.0.0', 9001))
        except OSError as exc:
            raise ValueError('Port 9001 is occupied. Run task down first if native Wisp is running.') from exc
    if ',' in str(root.resolve()):
        raise ValueError('Docker mount paths cannot contain commas. Use another checkout path.')
    state = prepare_state(root)
    image = name + ':local'
    docker('build', '--tag', image, str(root))
    optional_env = []
    if 'WISP_ENABLE_HLS_RADIO' in os.environ:
        optional_env = ['--env', 'WISP_ENABLE_HLS_RADIO=' + os.environ['WISP_ENABLE_HLS_RADIO']]
    docker('run', '--detach', '--name', name, '--label', f'{LABEL}={root.resolve()}',
           '--init', '--publish', '9001:9001',
           '--mount', f'type=bind,source={state},target=/workspace/state',
           '--env', 'PORT=9001', '--env', 'CONFIG_FILE=/workspace/state/config.json',
           '--env', 'FAVORITES_FILE=/workspace/state/favorites.json',
           '--env', f'WISP_BASE_URL={base}', '--env', f'WISP_SPEAKER_IPS={ips}',
           '--env', f'TZ={zone}', *optional_env, image)
    print('Wisp test container started: http://localhost:9001')
    print('First-run schedules are copied paused; existing test state is retained on later starts.')
    print('Logs: task container:logs | Stop: task container:down')
    print('Confirm devices appear before testing audio. Docker Desktop relay delivery needs verification.')


def main() -> int:
    try:
        action = sys.argv[1] if len(sys.argv) == 2 else ''
        if action not in ('up', 'down', 'logs'):
            raise ValueError('Use up, down or logs.')
        if not shutil.which('docker'):
            raise ValueError('Docker is not installed or not on PATH. Start Docker Desktop first.')
        check_local_engine()
        docker('info', capture=True)
        name = name_for(ROOT)
        if action == 'up':
            up(ROOT, name)
        else:
            info = owned_container(ROOT, name)
            if info is None:
                print('No test container for this checkout.')
                return 0
            if action == 'logs':
                docker('logs', '--follow', '--tail', '100', info['Id'])
            else:
                docker('stop', '--time', '15', info['Id'])
                docker('rm', info['Id'])
                print('Test container stopped; .wisp-container data is retained.')
        return 0
    except (ValueError, KeyError, TypeError, IndexError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Container task: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
