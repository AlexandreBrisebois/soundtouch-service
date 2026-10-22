import json
from types import SimpleNamespace

import pytest


def runner(stdout: str = '', *, returncode: int = 0):
    def run(*_args, **_kwargs):
        return SimpleNamespace(stdout=stdout, stderr='', returncode=returncode)
    return run


def test_explicit_private_origin_is_canonical_and_never_inspects_interfaces(monkeypatch):
    from scripts import startup_network

    def inspect(*_args, **_kwargs):
        pytest.fail('explicit configuration must not inspect interfaces')
    assert startup_network.resolve_base_url(
        'http://192.168.1.149:9001/', run=inspect, system='Darwin'
    ) == 'http://192.168.1.149:9001'


def test_explicit_rfc1918_bridge_range_is_an_operator_override_not_an_inference():
    from scripts import startup_network

    def inspect(*_args, **_kwargs):
        pytest.fail('explicit operator selection must not inspect interfaces')

    assert startup_network.resolve_base_url(
        'http://172.17.0.1:9001', run=inspect, system='Linux'
    ) == 'http://172.17.0.1:9001'


@pytest.mark.parametrize('value', [
    'http://localhost:9001', 'http://127.0.0.1:9001',
    'http://169.254.1.1:9001', 'http://8.8.8.8:9001',
    'https://192.168.1.2:9001', 'http://192.168.1.2:9002',
    'http://user:pass@192.168.1.2:9001', 'http://192.168.1.2:9001/path',
])
def test_explicit_origin_rejects_unsafe_values(value):
    from scripts import startup_network

    with pytest.raises(ValueError, match='WISP_BASE_URL=http://YOUR_LAN_IP:9001'):
        startup_network.resolve_base_url(value)


def test_macos_single_private_address_is_inferred_and_duplicates_are_deduplicated():
    from scripts import startup_network

    output = '''lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING> mtu 1500
\tinet 192.168.1.149 netmask 0xffffff00 broadcast 192.168.1.255
en1: flags=8863<UP,BROADCAST,SMART,RUNNING> mtu 1500
\tinet 192.168.1.149 netmask 0xffffff00 broadcast 192.168.1.255
bridge100: flags=4099<UP,BROADCAST,MULTICAST> mtu 1500
\tinet 172.17.0.1 netmask 0xffff0000
'''
    assert startup_network.resolve_base_url('', run=runner(output), system='Darwin') == (
        'http://192.168.1.149:9001'
    )


def test_linux_single_private_address_is_inferred():
    from scripts import startup_network

    output = json.dumps([
        {'ifname': 'lo', 'addr_info': [{'family': 'inet', 'local': '127.0.0.1'}]},
        {'ifname': 'eth0', 'addr_info': [{'family': 'inet', 'local': '10.0.0.8'}]},
        {'ifname': 'docker0', 'addr_info': [{'family': 'inet', 'local': '172.17.0.1'}]},
    ])
    assert startup_network.resolve_base_url('', run=runner(output), system='Linux') == (
        'http://10.0.0.8:9001'
    )


@pytest.mark.parametrize('output', [
    '',
    'en0: flags=1<UP> mtu 1500\n\tinet 192.168.1.2\n'
    'en1: flags=1<UP> mtu 1500\n\tinet 10.0.0.2\n',
    'not interface data',
])
def test_macos_missing_ambiguous_or_malformed_output_fails_closed(output):
    from scripts import startup_network

    with pytest.raises(ValueError, match='WISP_BASE_URL=http://YOUR_LAN_IP:9001'):
        startup_network.resolve_base_url('', run=runner(output), system='Darwin')


def test_platform_command_failure_fails_closed():
    from scripts import startup_network

    with pytest.raises(ValueError, match='WISP_BASE_URL=http://YOUR_LAN_IP:9001'):
        startup_network.resolve_base_url('', run=runner(returncode=1), system='Linux')
