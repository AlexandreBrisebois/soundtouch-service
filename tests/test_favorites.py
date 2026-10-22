import copy
import xml.etree.ElementTree as ET

import pytest
from flask import Flask

from app.api.favorites import favorites_bp
from app.core import favorites, library, playback, status

DEVICE = {'device_id': 'ABC', 'ip': '192.0.2.1', 'name': 'Bedroom'}
ACCOUNT = 'server-uuid/0'
SOURCE = {'id': library.source_id('STORED_MUSIC:' + ACCOUNT), 'source': 'STORED_MUSIC',
          'account': ACCOUNT, 'name': 'Music', 'ready': True}
ITEM = {'source': 'STORED_MUSIC', 'sourceAccount': ACCOUNT, 'location': 'opaque-folder',
        'type': 'dir', 'name': 'Calm', 'presetable': True, 'playable': True, 'is_dir': True}


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    monkeypatch.delenv('WISP_BASE_URL', raising=False)
    monkeypatch.delenv('WISP_RADIO_ALLOWED_HOSTS', raising=False)
    favorites._tokens.clear()
    playback.reset()
    monkeypatch.setattr(favorites.discovery, 'resolve_device', lambda *a: dict(DEVICE))
    monkeypatch.setattr(status, 'get_device_id', lambda *a, **k: 'ABC')
    monkeypatch.setattr(library, 'read_sources', lambda ip: [copy.deepcopy(SOURCE)])
    monkeypatch.setattr(favorites, 'capabilities', lambda ip: {'/storePreset', '/navigate'})
    slots = {i: None for i in range(1, 7)}
    calls = []
    monkeypatch.setattr(library, 'read_presets', lambda ip: copy.deepcopy(slots))

    def store(ip, slot, item):
        calls.append((ip, slot, copy.deepcopy(item)))
        slots[slot] = copy.deepcopy(item)
        return True
    monkeypatch.setattr(library, 'store_preset', store)
    monkeypatch.setattr(playback, 'manual', lambda speaker, callback: callback(DEVICE['ip']))
    return slots, calls


def make_plan(slot=1):
    token = favorites._token('item', 'ABC', ITEM)
    return favorites.plan('Bedroom', {'item_id': token, 'slot': slot, 'name': 'Morning calm'})


def test_preview_does_not_write_and_explicit_confirmation_preserves_other_slots(rig):
    slots, calls = rig
    slots[2] = {**ITEM, 'location': 'old-other', 'name': 'Existing NAS'}
    plan = make_plan()
    assert not calls
    assert not favorites.path().exists()
    result = favorites.confirm('Bedroom', plan['plan_id'])
    assert result['state'] == 'readback_matched'
    assert len(calls) == 1
    assert slots[2]['location'] == 'old-other'
    value = favorites.get(result['favorite']['id'])
    assert value['speaker_id'] == 'ABC' and value['content']['sourceAccount'] == ACCOUNT
    assert 'content' not in result['favorite']
    assert favorites.path().stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match='expired'):
        favorites.confirm('Bedroom', plan['plan_id'])
    assert len(calls) == 1


def test_changed_whole_map_rejects_confirm(rig):
    slots, calls = rig
    plan = make_plan()
    slots[6] = {**ITEM, 'location': 'manual-change'}
    with pytest.raises(ValueError, match='Presets changed'):
        favorites.confirm('Bedroom', plan['plan_id'])
    assert calls == []


def test_duplicate_content_in_other_slot_is_not_moved(rig):
    slots, calls = rig
    slots[2] = copy.deepcopy(ITEM)
    with pytest.raises(ValueError, match='another button'):
        make_plan()
    assert not calls


def test_collateral_slot_change_is_unknown_not_rolled_back(rig, monkeypatch):
    slots, calls = rig
    slots[2] = {**ITEM, 'location': 'other'}
    def store(ip, slot, item):
        calls.append(1)
        slots[slot] = copy.deepcopy(item)
        slots[2] = None
        return True
    monkeypatch.setattr(library, 'store_preset', store)
    result = favorites.confirm('Bedroom', make_plan()['plan_id'])
    assert result['state'] == 'unknown'
    assert 'Another preset changed' in result['message']
    assert len(calls) == 1 and slots[2] is None


def test_timeout_even_with_matching_readback_is_unknown(rig, monkeypatch):
    slots, calls = rig
    def ambiguous(ip, slot, item):
        calls.append(1)
        slots[slot] = copy.deepcopy(item)
        return False
    monkeypatch.setattr(library, 'store_preset', ambiguous)
    result = favorites.confirm('Bedroom', make_plan()['plan_id'])
    assert result['state'] == 'unknown' and len(calls) == 1
    with pytest.raises(ValueError, match='Only readback'):
        favorites.schedule_binding(result['favorite']['id'], 'Bedroom')


def test_write_ahead_failure_prevents_hardware_write(rig, monkeypatch):
    _, calls = rig
    plan = make_plan()
    monkeypatch.setattr(favorites, '_save', lambda doc: (_ for _ in ()).throw(favorites.FavoriteError('disk full')))
    with pytest.raises(ValueError, match='disk full'):
        favorites.confirm('Bedroom', plan['plan_id'])
    assert calls == []


def test_corrupt_persistence_is_not_overwritten(rig):
    favorites.path().write_text('{broken')
    with pytest.raises(ValueError, match='Restore'):
        favorites.overview('Bedroom')
    assert favorites.path().read_text() == '{broken'


def test_token_is_bound_to_device_and_expires(rig, monkeypatch):
    token = favorites._token('item', 'ABC', ITEM)
    with pytest.raises(ValueError):
        favorites._lookup(token, 'item', 'OTHER')
    monkeypatch.setattr(favorites.time, 'monotonic', lambda: 10**20)
    with pytest.raises(ValueError):
        favorites._lookup(token, 'item', 'ABC')


def test_source_stale_at_confirm_does_not_write(rig, monkeypatch):
    _, calls = rig
    plan = make_plan()
    monkeypatch.setattr(library, 'read_sources', lambda ip: [{**SOURCE, 'ready': False}])
    with pytest.raises(ValueError, match='no longer ready'):
        favorites.confirm('Bedroom', plan['plan_id'])
    assert not calls


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'ftp://radio.example/a', 'http://u:p@radio.example/a',
                                 'https://radio.example/a?token=secret', 'https://radio.example/a#x',
                                 'http://localhost/a', 'http://127.0.0.1/a', 'http://169.254.169.254/a',
                                 'http://nas.local/a', 'http://radio.example:8090/a', 'http://radio.example/a\n'])
def test_radio_url_limits(url, rig):
    with pytest.raises(ValueError):
        favorites._safe_url(url)


def test_explicit_lan_stream_allowlist(rig, monkeypatch):
    monkeypatch.setenv('WISP_RADIO_ALLOWED_HOSTS', 'nas.local')
    assert favorites._safe_url('http://nas.local:8000/radio') == 'http://nas.local:8000/radio'


def test_radio_descriptor_is_data_not_fetch_and_source_must_be_ready(rig, monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    with pytest.raises(ValueError, match='not ready'):
        favorites.plan('Bedroom', {'radio_url': 'https://radio.example/live.mp3', 'name': 'Station', 'slot': 1})
    monkeypatch.setattr(library, 'read_sources', lambda ip: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    plan = favorites.plan('Bedroom', {'radio_url': 'https://radio.example/live.mp3', 'name': 'Station', 'slot': 1})
    result = favorites.confirm('Bedroom', plan['plan_id'])
    value = favorites.get(result['favorite']['id'])
    assert value['content']['location'] == f"http://wisp.local:9001/api/radio/{value['id']}"
    descriptor = favorites.descriptor(value['id'])
    assert descriptor['audio']['streams'][0]['streamUrl'] == 'https://radio.example/live.mp3'
    assert descriptor['streamType'] == 'liveRadio'
    assert 'sourceAccount' not in value['content']


def test_api_requires_explicit_confirmation_and_same_origin(rig):
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    assert client.post('/api/Bedroom/preset-plans/abc/confirm', json={}).status_code == 400
    assert client.post('/api/Bedroom/preset-plans', json={}, headers={'Origin': 'https://evil.example'}).status_code == 400
    assert client.post('/api/Bedroom/preset-plans', data='{}', content_type='text/plain').status_code == 400
    assert rig[1] == []


def test_native_folder_matching_allows_omitted_type_only():
    expected = library.identity(ITEM) | {'type': 'dir'}
    data = {'content_identity': library.identity(ITEM)}
    assert playback.matches(expected, data)
    assert not playback.matches(expected, {'content_identity': {**library.identity(ITEM), 'location': 'different'}})
    assert not playback.matches(expected, {'content_identity': {**library.identity(ITEM), 'sourceAccount': 'other'}})
    assert not playback.matches(expected, {'content_identity': {**library.identity(ITEM), 'type': 'track'}})


def test_read_presets_rejects_duplicate_and_preserves_empty_slots(monkeypatch):
    monkeypatch.setattr(status, '_get_xml', lambda *a, **kw: ET.fromstring('<presets><preset id="0"/><preset id="1"/><preset id="1"/></presets>'))
    with pytest.raises(ValueError, match='ambiguous'):
        library.read_presets('192.0.2.1')
    monkeypatch.setattr(status, '_get_xml', lambda *a, **kw: ET.fromstring('<presets><preset id="0"/></presets>'))
    assert library.read_presets('192.0.2.1') == {i: None for i in range(1, 7)}


def test_schedule_favorite_survives_normalization():
    from app.scheduler.jobs import _normalize_schedule
    value = _normalize_schedule({'name': 'Morning', 'on_time': '07:00', 'favorite_id': 'a'*32, 'speaker_id': 'ABC'}, 'Bedroom', 0)
    assert value['favorite_id'] == 'a'*32


def test_readback_requires_actual_identity_not_display_name(rig, monkeypatch):
    slots, _ = rig
    def wrong(ip, slot, item):
        slots[slot] = {**item, 'location': 'wrong'}
        return True
    monkeypatch.setattr(library, 'store_preset', wrong)
    assert favorites.confirm('Bedroom', make_plan()['plan_id'])['state'] == 'unknown'


def test_final_storage_failure_remains_durable_unknown(rig, monkeypatch):
    save = favorites._save
    count = []
    def fail_second(value):
        count.append(1)
        if len(count) == 2:
            raise favorites.FavoriteError('disk full')
        save(value)
    monkeypatch.setattr(favorites, '_save', fail_second)
    plan = make_plan()
    result = favorites.confirm('Bedroom', plan['plan_id'])
    assert result['state'] == 'unknown'
    assert favorites.get(result['favorite']['id'])['state'] == 'unknown'
    assert len(rig[1]) == 1


def test_new_assignment_supersedes_old_without_rebinding_schedules(rig):
    old = favorites.confirm('Bedroom', make_plan()['plan_id'])['favorite']['id']
    token = favorites._token('item', 'ABC', {**ITEM, 'location': 'new-folder'})
    plan = favorites.plan('Bedroom', {'item_id': token, 'slot': 1, 'name': 'New'})
    new = favorites.confirm('Bedroom', plan['plan_id'])['favorite']['id']
    assert favorites.get(old)['state'] == 'superseded'
    assert favorites.get(new)['state'] == 'readback_matched'
    with pytest.raises(ValueError):
        favorites.schedule_binding(old, 'Bedroom')


def test_overview_and_scheduling_recheck_current_assignment(rig):
    saved = favorites.confirm('Bedroom', make_plan()['plan_id'])['favorite']
    rig[0][1]['location'] = 'changed-outside-wisp'
    view = favorites.overview('Bedroom')
    assert view['favorites'][0]['state'] == 'mismatch'
    with pytest.raises(ValueError, match='button has changed'):
        favorites.schedule_binding(saved['id'], 'Bedroom')


def test_storage_size_checked_in_utf8_before_replacing_or_programming(rig, monkeypatch):
    favorites._save({'version': 1, 'favorites': {}})
    before = favorites.path().read_bytes()
    monkeypatch.setattr(favorites, 'MAX_STORAGE_BYTES', 300)
    with pytest.raises(ValueError, match='storage is full'):
        favorites._save({'version': 1, 'favorites': {'name': 'é' * 200}})
    assert favorites.path().read_bytes() == before
    plan = make_plan()
    with pytest.raises(ValueError, match='storage is full'):
        favorites.confirm('Bedroom', plan['plan_id'])
    assert not rig[1]


def test_explicit_conflicting_type_never_confirms_or_binds(rig, monkeypatch):
    original = library.store_preset
    def wrong_type(ip, slot, item):
        original(ip, slot, item)
        rig[0][slot]['type'] = 'track'
        return True
    monkeypatch.setattr(library, 'store_preset', wrong_type)
    result = favorites.confirm('Bedroom', make_plan()['plan_id'])
    assert result['state'] == 'unknown'
    assert library.same_content(ITEM, {key: value for key, value in ITEM.items() if key != 'type'})
    assert not library.same_content(ITEM, {**ITEM, 'type': 'track'})


def test_station_library_exceeds_six_without_speaker_commands(rig):
    saved = [favorites.add_station(f'Station {i}', f'https://radio.example/{i}') for i in range(7)]
    assert len(favorites.stations()) == 7
    assert len({item['id'] for item in saved}) == 7
    assert not rig[1]
    assert all('slot' not in item and 'speaker_id' not in item for item in saved)


def test_station_duplicate_does_not_create_second_record(rig):
    favorites.add_station('One', 'https://radio.example/live')
    with pytest.raises(ValueError, match='already'):
        favorites.add_station('Other name', 'https://radio.example/live')
    assert len(favorites.stations()) == 1


def test_station_removal_preserves_descriptor_and_physical_favorite(rig, monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    saved = favorites.add_station('Radio', 'https://radio.example/live')
    plan = favorites.plan('Bedroom', {'station_id': saved['id'], 'name': 'Morning', 'slot': 1})
    favorite = favorites.confirm('Bedroom', plan['plan_id'])['favorite']
    assert favorites.get(favorite['id'])['content']['location'].endswith('/api/radio/' + favorite['id'])
    favorites.remove_station(saved['id'])
    assert not favorites.stations()
    assert len(rig[1]) == 1
    assert favorites.station_descriptor(saved['id'])['audio']['streamUrl'] == 'https://radio.example/live'
    assert favorites.descriptor(favorite['id'])['audio']['streamUrl'] == 'https://radio.example/live'
    assert favorites.schedule_binding(favorite['id'], 'Bedroom')['id'] == favorite['id']
    assert favorites.station_content(saved['id'], allow_removed=True)['location'].endswith('/api/stations/' + saved['id'] + '/stream')
    with pytest.raises(ValueError, match='not found'):
        favorites.station_content(saved['id'])


def test_station_add_and_remove_require_json_and_confirmation(rig):
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    result = client.post('/api/stations', json={'name': 'Radio', 'url': 'https://radio.example/live'})
    assert result.status_code == 201
    id = result.json['station']['id']
    assert client.delete('/api/stations/' + id, json={}).status_code == 400
    assert len(client.get('/api/stations').json['stations']) == 1
    assert client.delete('/api/stations/' + id, json={'confirmed': True}).status_code == 200
    assert client.get('/api/stations/' + id + '/stream').status_code == 200
    assert client.get('/api/stations').json['stations'] == []


def test_station_direct_play_pins_device_without_preset_mutation(rig, monkeypatch):
    from app.api import favorites as api
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    item = favorites.add_station('Radio', 'https://radio.example/live')
    calls = []
    monkeypatch.setattr(api.jobs, 'queue_station', lambda *args: calls.append(args) or {'state': 'accepted'})
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    endpoint = '/api/Bedroom/stations/' + item['id'] + '/play'
    assert client.post(endpoint, json={}).status_code == 400
    assert client.post(endpoint, json={'confirmed': True}).status_code == 202
    assert calls == [('Bedroom', 'ABC', item['id'])]
    assert not rig[1]


def test_starters_are_explicit_idempotent_and_library_only(rig, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Starter import must not access speakers or start playback')
    monkeypatch.setattr(favorites.discovery, 'resolve_device', forbidden)
    monkeypatch.setattr(library, 'read_presets', forbidden)
    monkeypatch.setattr(library, 'store_preset', forbidden)
    monkeypatch.setattr(playback, 'manual', forbidden)
    assert favorites.stations() == []
    assert not favorites.path().exists()
    assert favorites.add_starter_stations() == {'added': 6, 'skipped': 0}
    saved = favorites.path().read_bytes()
    assert favorites.add_starter_stations() == {'added': 0, 'skipped': 6}
    assert favorites.path().read_bytes() == saved
    assert len(favorites.stations()) == 6
    assert all('ready' not in item for item in favorites.stations())
    assert not rig[1]


def test_starters_preserve_custom_names_urls_favorites_and_removed_links(rig):
    name, url = favorites.STARTER_STATIONS[0]
    renamed = favorites.add_station('My radio', url)
    custom = favorites.add_station('  ' + favorites.STARTER_STATIONS[1][0].upper() + '  ', 'https://radio.example/custom')
    other = favorites.add_station('Custom', 'https://radio.example/other')
    document = favorites._load()
    document['favorites']['existing'] = {'name': 'Keep unchanged'}
    favorites._save(document)
    assert favorites.add_starter_stations() == {'added': 4, 'skipped': 2}
    for item in (renamed, custom, other):
        assert favorites.station(item['id']) == item
    assert favorites._load()['favorites'] == document['favorites']
    favorites.remove_station(renamed['id'])
    assert len(favorites.stations()) == 6  # Reads never restore removed starters.
    assert favorites.add_starter_stations() == {'added': 1, 'skipped': 5}
    assert favorites.station(renamed['id'], allow_removed=True) == {**renamed, 'removed': True}
    assert any(item['name'] == name and item['id'] != renamed['id'] for item in favorites.stations())


def test_concurrent_starter_imports_do_not_duplicate(rig):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: favorites.add_starter_stations(), range(4)))
    assert sum(result['added'] for result in results) == 6
    assert len(favorites.stations()) == 6


def test_starters_capacity_and_failed_write_are_atomic(rig, monkeypatch):
    document = {'version': 1, 'favorites': {}, 'stations': {
        str(i): {'id': str(i), 'name': str(i), 'url': f'https://radio.example/{i}'}
        for i in range(495)}}
    favorites._save(document)
    before = favorites.path().read_bytes()
    with pytest.raises(ValueError, match='storage is full'):
        favorites.add_starter_stations()
    assert favorites.path().read_bytes() == before
    document['stations'] = {}
    favorites._save(document)
    before = favorites.path().read_bytes()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(favorites.os, 'replace', fail)
    with pytest.raises(ValueError, match='could not be saved'):
        favorites.add_starter_stations()
    assert favorites.path().read_bytes() == before


def test_starter_api_requires_json_same_origin_and_no_get_mutation(rig):
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    endpoint = '/api/stations/starter'
    assert client.get(endpoint).status_code == 405
    assert client.post(endpoint).status_code == 400
    assert client.post(endpoint, json={}, headers={'Origin': 'https://elsewhere.example'}).status_code == 400
    assert client.post(endpoint, json={}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 400
    assert not favorites.path().exists()
    assert client.post(endpoint, json={}).json == {'added': 6, 'skipped': 0}
    assert client.post(endpoint, json={}).json == {'added': 0, 'skipped': 6}
