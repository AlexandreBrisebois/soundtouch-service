"""Resolve Wisp's speaker-reachable callback origin without probing the LAN."""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

PORT = 9001
MAX_INTERFACE_OUTPUT = 1_000_000
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
))
IGNORED_INTERFACE_PREFIXES = ('lo', 'docker', 'bridge', 'br-', 'veth')
Run = Callable[..., Any]


def private_ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError('Use a private LAN IPv4 address.') from None
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError('Use a private LAN IPv4 address.')
    return str(address)


def validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        parsed, port = None, None
    if (parsed is None or parsed.scheme != 'http' or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment or port != PORT):
        raise ValueError('Set WISP_BASE_URL=http://YOUR_LAN_IP:9001 before starting.')
    try:
        host = private_ipv4(parsed.hostname)
    except ValueError:
        raise ValueError('Set WISP_BASE_URL=http://YOUR_LAN_IP:9001 before starting.') from None
    return f'http://{host}:{PORT}'


def _eligible_interface(name: str) -> bool:
    lowered = name.lower()
    return bool(name) and not lowered.startswith(IGNORED_INTERFACE_PREFIXES)


def _macos_addresses(output: str) -> list[str]:
    current = ''
    result = []
    for line in output.splitlines():
        match = re.match(r'^([^\s:]+):', line)
        if match:
            current = match.group(1)
            continue
        match = re.match(r'^\s+inet\s+(\d+\.\d+\.\d+\.\d+)(?:\s|$)', line)
        if match and _eligible_interface(current):
            result.append(match.group(1))
    return result


def _linux_addresses(output: str) -> list[str]:
    try:
        interfaces = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(interfaces, list):
        return []
    result = []
    for interface in interfaces:
        if not isinstance(interface, dict) or not _eligible_interface(str(interface.get('ifname', ''))):
            continue
        entries = interface.get('addr_info', [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get('family') == 'inet' and isinstance(entry.get('local'), str):
                result.append(entry['local'])
    return result


def interface_ipv4s(*, run: Run = subprocess.run, system: str | None = None) -> list[str]:
    host = system or platform.system()
    command = ['ifconfig'] if host in {'Darwin', 'FreeBSD', 'OpenBSD'} else (
        ['ip', '-json', '-4', 'addr', 'show'] if host == 'Linux' else None
    )
    if command is None:
        return []
    try:
        completed = run(command, check=False, text=True, capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return []
    output = completed.stdout
    if completed.returncode != 0 or not isinstance(output, str) or len(output) > MAX_INTERFACE_OUTPUT:
        return []
    raw = _macos_addresses(output) if host != 'Linux' else _linux_addresses(output)
    valid = []
    for value in raw:
        try:
            valid.append(private_ipv4(value))
        except ValueError:
            continue
    return list(dict.fromkeys(valid))


def resolve_base_url(explicit: str | None = None, *, run: Run = subprocess.run,
                     system: str | None = None) -> str:
    value = explicit if explicit is not None else os.getenv('WISP_BASE_URL', '')
    if value:
        return validate_base_url(value)
    candidates = interface_ipv4s(run=run, system=system)
    if len(candidates) != 1:
        raise ValueError('Could not choose one speaker-reachable LAN address. '
                         'Set WISP_BASE_URL=http://YOUR_LAN_IP:9001 before starting.')
    return f'http://{candidates[0]}:{PORT}'


def main() -> int:
    try:
        print(resolve_base_url())
        return 0
    except ValueError as exc:
        print(f'Wisp startup: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
