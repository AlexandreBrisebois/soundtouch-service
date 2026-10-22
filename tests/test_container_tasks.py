import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import container_dev as dev
from app.core import discovery, status


@pytest.mark.parametrize('value', ['127.0.0.1', '8.8.8.8', '169.254.1.1', '224.0.0.1',
                                   'http://192.168.1.2', '192.168.1.2:8090', 'host.lan', '::1'])
def test_explicit_addresses_reject_non_private_literals(value):
    with pytest.raises(ValueError):
        discovery.configured_speaker_ips(value)
    with pytest.raises(ValueError):
        dev.private_ipv4(value)


def test_explicit_addresses_bounded_and_deduplicated():
    assert discovery.configured_speaker_ips(' 192.168.1.2,192.168.1.2,10.0.0.2 ') == [
        '192.168.1.2', '10.0.0.2']
    with pytest.raises(ValueError):
        discovery.configured_speaker_ips(','.join(['10.0.0.2'] * 9))
    assert discovery.configured_speaker_ips('') == []


def test_explicit_mode_reads_info_without_mdns(monkeypatch):
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2,192.168.1.3')
    expected = {'name': 'Office', 'ip': '192.168.1.2', 'device_id': 'ID'}
    monkeypatch.setattr(status, 'get_device_info', lambda ip: expected if ip.endswith('.2') else None)
    assert discovery.discover_systems() == [expected]


def test_failed_read_is_not_cached_as_device(monkeypatch):
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2')
    monkeypatch.setattr(status, 'get_device_info', lambda ip: (_ for _ in ()).throw(ValueError()))
    assert discovery.discover_systems() == []


def test_info_requires_name_and_identity(monkeypatch):
    from xml.etree.ElementTree import fromstring
    for xml in ('<info/>', '<info deviceID="ID"/>', '<info><name>A</name></info>'):
        monkeypatch.setattr(status, '_get_xml', lambda *a, xml=xml: fromstring(xml))
        assert status.get_device_info('192.168.1.2') is None
    monkeypatch.setattr(status, '_get_xml', lambda *a: fromstring(
        '<info deviceID="ID"><name>Office</name></info>'))
    assert status.get_device_info('192.168.1.2') == {
        'name': 'Office', 'ip': '192.168.1.2', 'device_id': 'ID'}


def test_identity_conflicts_remain_ambiguous(monkeypatch):
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2,192.168.1.3')
    monkeypatch.setattr(status, 'get_device_info', lambda ip: {
        'name': 'Office', 'ip': ip, 'device_id': 'SAME'})
    for name in ('_device_cache', '_devices_by_name', '_devices_by_id'):
        monkeypatch.setattr(discovery, name, {})
    monkeypatch.setattr(discovery, '_cached_devices', [])
    monkeypatch.setattr(discovery, '_ambiguous_names', set())
    monkeypatch.setattr(discovery, '_ambiguous_ids', set())
    discovery.refresh_cache()
    assert discovery._cached_resolution('Office', None) == (None, True)
    assert discovery._cached_resolution('Office', 'SAME') == (None, True)


@pytest.mark.parametrize('legacy', [False, True])
def test_state_copies_paused_and_preserves_original(tmp_path, monkeypatch, legacy):
    schedules = {'R': [{'name': 'Morning', 'paused': False}, {'name': 'Evening'}]}
    original = schedules if legacy else {'version': 1, 'schedules': schedules}
    source = tmp_path / '.wisp-dev.json'
    source.write_text(json.dumps(original))
    favorites = tmp_path / 'favorites.json'
    favorites.write_text('{"stations": []}')
    monkeypatch.setenv('CONFIG_FILE', str(source))
    monkeypatch.delenv('FAVORITES_FILE', raising=False)
    state = dev.prepare_state(tmp_path)
    assert all(item['paused'] for item in json.loads((state / 'config.json').read_text())['schedules']['R'])
    assert json.loads(source.read_text()) == original
    assert (state / 'favorites.json').read_bytes() == favorites.read_bytes()
    (state / 'config.json').write_text('{"my":"later test edits"}')
    (state / 'favorites.json').write_text('{"my":"library"}')
    dev.prepare_state(tmp_path)
    assert json.loads((state / 'config.json').read_text()) == {'my': 'later test edits'}
    assert json.loads((state / 'favorites.json').read_text()) == {'my': 'library'}


def test_missing_config_starts_empty(tmp_path, monkeypatch):
    monkeypatch.setenv('CONFIG_FILE', str(tmp_path / 'absent'))
    state = dev.prepare_state(tmp_path)
    assert json.loads((state / 'config.json').read_text()) == {'version': 1, 'schedules': {}}


@pytest.mark.parametrize('raw', [[], {'schedules': []}, {'R': [None]}])
def test_bad_config_does_not_create_test_config(tmp_path, monkeypatch, raw):
    source = tmp_path / '.wisp-dev.json'
    source.write_text(json.dumps(raw))
    monkeypatch.setenv('CONFIG_FILE', str(source))
    with pytest.raises(ValueError):
        dev.prepare_state(tmp_path)
    assert not (tmp_path / '.wisp-container' / 'config.json').exists()


def test_symlink_state_refused(tmp_path):
    (tmp_path / 'outside').mkdir()
    (tmp_path / '.wisp-container').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError):
        dev.prepare_state(tmp_path)


def test_settings(monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://192.168.1.10:9001/')
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2,192.168.1.3')
    monkeypatch.delenv('TZ', raising=False)
    assert dev.settings() == ('http://192.168.1.10:9001', '192.168.1.2,192.168.1.3', 'America/Toronto')


def test_settings_infers_base_url_when_override_is_absent(monkeypatch):
    monkeypatch.delenv('WISP_BASE_URL', raising=False)
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2')
    monkeypatch.setattr(dev.startup_network, 'resolve_base_url', lambda: 'http://192.168.1.10:9001')
    assert dev.settings()[0] == 'http://192.168.1.10:9001'


@pytest.mark.parametrize('url', ['http://localhost:9001', 'https://192.168.1.10:9001',
                                 'http://192.168.1.10:9002', 'http://192.168.1.10:9001/path',
                                 'http://user:pass@192.168.1.10:9001'])
def test_settings_reject_unusable_base_url(monkeypatch, url):
    monkeypatch.setenv('WISP_BASE_URL', url)
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2')
    with pytest.raises(ValueError):
        dev.settings()


def test_other_container_ownership_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps([{'Config': {'Labels': {dev.LABEL: '/other'}}}]), stderr=''))
    with pytest.raises(ValueError, match='ownership'):
        dev.owned_container(tmp_path, 'name')


def test_inspect_error_is_not_absence(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: SimpleNamespace(
        returncode=1, stdout='', stderr='permission denied'))
    with pytest.raises(ValueError):
        dev.owned_container(tmp_path, 'name')


def test_absent_container(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: SimpleNamespace(
        returncode=1, stdout='', stderr='Error: No such container: name'))
    assert dev.owned_container(tmp_path, 'name') is None


def test_names_unique_per_checkout(tmp_path):
    assert dev.name_for(tmp_path) == dev.name_for(tmp_path)
    assert dev.name_for(tmp_path) != dev.name_for(tmp_path / 'other')


@pytest.mark.parametrize("hls_flag", [None, "0"])
def test_run_command_mounts_only_test_data_and_preserves_peer_guard(tmp_path, monkeypatch, hls_flag):
    if hls_flag is None:
        monkeypatch.delenv("WISP_ENABLE_HLS_RADIO", raising=False)
    else:
        monkeypatch.setenv("WISP_ENABLE_HLS_RADIO", hls_flag)
    monkeypatch.setenv('WISP_BASE_URL', 'http://192.168.1.10:9001')
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2')
    monkeypatch.setenv('CONFIG_FILE', str(tmp_path / 'missing'))
    monkeypatch.setattr(dev, 'owned_container', lambda *a: None)
    class Probe:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def bind(self, address): assert address == ('0.0.0.0', 9001)
    monkeypatch.setattr(dev.socket, 'socket', Probe)
    calls = []
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: calls.append(a))
    dev.up(tmp_path, 'wisp-test')
    run = calls[1]
    assert run[:2] == ('run', '--detach')
    assert '9001:9001' in run
    assert f'type=bind,source={tmp_path}/.wisp-container,target=/workspace/state' in run
    assert any(arg == 'WISP_ENABLE_HLS_RADIO=0' for arg in run) is (hls_flag == '0')
    assert '--network' not in run
    assert not any('PROXY' in arg or 'PRIVILEGED' in arg for arg in run)


def test_taskfile_keeps_native_tasks_and_has_container_tasks():
    text = (Path(__file__).parents[1] / 'Taskfile.yml').read_text()
    for task in ('up', 'down', 'tag', 'container:up', 'container:down', 'container:logs'):
        assert f'  {task}:\n' in text
    resolver = 'WISP_BASE_URL=$(.venv/bin/python scripts/startup_network.py)'
    assert resolver in text
    assert text.index(resolver) < text.index('mkdir .wisp-run')


@pytest.mark.parametrize('host', ['tcp://remote:2375', 'ssh://remote', 'npipe://pipe'])
def test_remote_engine_rejected(monkeypatch, host):
    monkeypatch.delenv('DOCKER_CONTEXT', raising=False)
    monkeypatch.setenv('DOCKER_HOST', host)
    with pytest.raises(ValueError, match='local Docker'):
        dev.check_local_engine()


def test_local_context_accepted(monkeypatch):
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: SimpleNamespace(stdout=json.dumps([
        {'Endpoints': {'docker': {'Host': 'unix:///Users/test/.docker/run/docker.sock'}}}])) )
    dev.check_local_engine()


def test_stop_uses_owned_id_and_never_deletes_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'ROOT', tmp_path)
    monkeypatch.setattr(dev.sys, 'argv', ['container_dev.py', 'down'])
    monkeypatch.setattr(dev.shutil, 'which', lambda name: '/bin/docker')
    monkeypatch.setattr(dev, 'check_local_engine', lambda: None)
    monkeypatch.setattr(dev, 'owned_container', lambda *a: {'Id': 'verified-id'})
    calls = []
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: calls.append(a))
    state = tmp_path / '.wisp-container'
    state.mkdir()
    (state / 'config.json').write_text('{}')
    assert dev.main() == 0
    assert calls == [('info',), ('stop', '--time', '15', 'verified-id'), ('rm', 'verified-id')]
    assert (state / 'config.json').exists()


def test_existing_container_refused_without_build(tmp_path, monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://192.168.1.10:9001')
    monkeypatch.setenv('WISP_SPEAKER_IPS', '192.168.1.2')
    monkeypatch.setattr(dev, 'owned_container', lambda *a: {'Id': 'existing'})
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: pytest.fail('must not build or replace'))
    with pytest.raises(ValueError, match='already exists'):
        dev.up(tmp_path, 'name')


def test_context_override_cannot_hide_remote_endpoint(monkeypatch):
    monkeypatch.setenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
    monkeypatch.setenv('DOCKER_CONTEXT', 'remote')
    monkeypatch.setattr(dev, 'docker', lambda *a, **k: SimpleNamespace(stdout=json.dumps([
        {'Endpoints': {'docker': {'Host': 'ssh://remote'}}}])))
    with pytest.raises(ValueError):
        dev.check_local_engine()
