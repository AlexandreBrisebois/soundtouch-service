import copy
import xml.etree.ElementTree as ET

import pytest
from flask import Flask

from app.api.favorites import favorites_bp
from app.core import favorites, library, playback, radio_relay, status

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
    favorites._save({'version': 1, 'favorites': {}, 'station_seed_version': 1})
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
    before = favorites.path().read_bytes()
    slots[2] = {**ITEM, 'location': 'old-other', 'name': 'Existing NAS'}
    plan = make_plan()
    assert not calls
    assert favorites.path().read_bytes() == before
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


def test_legacy_radio_descriptor_remains_readable_without_fetch(rig):
    value = {
        'id': 'f' * 32, 'name': 'Station', 'kind': 'radio', 'speaker_id': 'ABC',
        'slot': 1, 'state': 'readback_matched', 'radio_url': 'https://radio.example/live.mp3',
        'content': {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl',
                    'location': 'http://old-wisp/api/radio/' + 'f' * 32,
                    'name': 'Station', 'presetable': True},
    }
    favorites._save({'version': 1, 'favorites': {value['id']: value}, 'station_seed_version': 1})
    descriptor = favorites.descriptor(value['id'])
    assert descriptor['audio']['streams'][0]['streamUrl'] == 'https://radio.example/live.mp3'
    assert descriptor['streamType'] == 'liveRadio'
    assert 'sourceAccount' not in value['content']


@pytest.mark.parametrize('payload', [
    {'station_id': 'a' * 32, 'name': 'Station', 'slot': 1},
    {'radio_url': 'https://radio.example/live.mp3', 'name': 'Station', 'slot': 1},
])
def test_new_radio_preset_plan_is_rejected_before_device_or_storage(rig, monkeypatch, payload):
    before = favorites.path().read_bytes()
    monkeypatch.setattr(favorites, 'device', lambda *_a, **_kw: pytest.fail('must not inspect speaker'))
    with pytest.raises(ValueError, match='cannot be assigned'):
        favorites.plan('Bedroom', payload)
    assert favorites.path().read_bytes() == before
    assert not favorites._tokens
    assert not rig[1]


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


def test_station_removal_preserves_legacy_descriptor_and_physical_favorite(rig, monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    saved = favorites.add_station('Radio', 'https://radio.example/live')
    favorite = {
        'id': 'f' * 32, 'name': 'Morning', 'kind': 'radio', 'speaker_id': 'ABC',
        'slot': 1, 'state': 'readback_matched', 'radio_url': saved['url'],
        'content': {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl',
                    'location': 'http://old-wisp/api/radio/' + 'f' * 32,
                    'name': 'Morning', 'presetable': True},
    }
    document = favorites._load()
    document['favorites'][favorite['id']] = favorite
    favorites._save(document)
    rig[0][1] = copy.deepcopy(favorite['content'])
    favorites.remove_station(saved['id'])
    assert not favorites.stations()
    assert not rig[1]
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
    item = favorites.add_station('Radio', 'https://radio.example/live.mp3')
    calls = []
    monkeypatch.setattr(api.jobs, 'queue_station', lambda *args, **kw: calls.append((args, kw)) or {'state': 'accepted'})
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    endpoint = '/api/Bedroom/stations/' + item['id'] + '/play'
    assert client.post(endpoint, json={}).status_code == 400
    assert client.post(endpoint, json={'confirmed': True, 'speaker_id': 'ABC', 'volume': 23}).status_code == 202
    assert calls == [(('Bedroom', 'ABC', item['id'], 23), {'listening': True})]
    assert not rig[1]


def test_normal_station_dispatch_uses_playback_engine_without_diagnostic_timer(rig, monkeypatch):
    from app.scheduler import jobs

    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *args: calls.append(args) or True)
    first = jobs.queue_station('Bedroom', 'ABC', 'station', 23, listening=True)
    second = jobs.queue_station('Bedroom', 'ABC', 'station', 23, listening=True)
    assert first['operation_id'] == second['operation_id']
    assert len(calls) == 1
    assert calls[0][1] is playback.run_on
    assert calls[0][3:] == (None, 23, None, 2, True, None, 'station')
    assert calls[0][2]['device_id'] == 'ABC'


def test_seed_initializes_missing_store_once_without_speakers(rig, monkeypatch):
    favorites.path().unlink()
    def forbidden(*args, **kwargs):
        pytest.fail('Seed must not access speakers or start playback')
    monkeypatch.setattr(favorites.discovery, 'resolve_device', forbidden)
    monkeypatch.setattr(library, 'read_presets', forbidden)
    monkeypatch.setattr(library, 'store_preset', forbidden)
    monkeypatch.setattr(playback, 'manual', forbidden)
    assert len(favorites.stations()) == 5
    before = favorites.path().read_bytes()
    assert len(favorites.stations()) == 5
    assert favorites.path().read_bytes() == before
    assert favorites._load()['station_seed_version'] == 1
    assert all('ready' not in item for item in favorites.stations())
    assert not rig[1]


def test_seed_manifest_keeps_five_defaults_without_buzz():
    import json
    seed = json.loads((favorites.Path(favorites.__file__).resolve().parents[1] / 'data/stations.seed.json').read_text())
    assert seed == {
        'version': 1,
        'stations': [
            {'name': 'CHOM 97.7', 'url': radio_relay.CHOM_MP3_URL},
            {'name': 'Énergie Montréal 94.3', 'url':
             'https://playerservices.streamtheworld.com/api/livestream-redirect/CKMFFMAAC.aac'},
            {'name': 'CBC Radio One Montréal', 'url':
             'https://cbcradiolive.akamaized.net/hls/live/2041030/ES_R1EMT/master.m3u8'},
            {'name': 'ICI Première Montréal 95.1', 'url':
             'https://rcavliveaudio.akamaized.net/hls/live/2006635/P-2QMTL0_MTL/master.m3u8'},
            {'name': 'Star 92.9', 'url':
             'https://live.amperwave.net/direct/vox-wezffmmp3-imc'},
        ],
    }


def test_seed_upgrades_empty_store_once_and_never_reseeds_removals(rig):
    favorites._save({'version': 1, 'favorites': {}})
    for item in favorites.stations():
        favorites.remove_station(item['id'])
    assert favorites.stations() == []
    before = favorites.path().read_bytes()
    assert favorites._load()['station_seed_version'] == 1
    assert favorites.path().read_bytes() == before


def test_seed_preserves_custom_names_urls_favorites_schedules_and_archived_links(
        rig, monkeypatch, tmp_path):
    import json
    seed = json.loads((favorites.Path(favorites.__file__).resolve().parents[1] / 'data/stations.seed.json').read_text())['stations']
    renamed = favorites.add_station('My radio', seed[0]['url'])
    custom = favorites.add_station('  ' + seed[1]['name'].upper() + '  ', 'https://radio.example/custom')
    legacy = favorites.add_station('Legacy CHOM', radio_relay.CHOM_LEGACY_AAC_URL)
    removed = favorites.add_station(seed[2]['name'], seed[2]['url'])
    favorites.remove_station(removed['id'])
    document = favorites._load()
    document.pop('station_seed_version')
    document['favorites']['existing'] = {'name': 'Keep unchanged'}
    document['custom_metadata'] = {'untouched': True}
    existing_ids = set(document['stations'])
    favorites._save(document)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'version': 1, 'schedules': {
        'Bedroom': [{'name': 'Legacy CHOM schedule', 'station_id': legacy['id'], 'paused': False}]
    }}))
    monkeypatch.setenv('CONFIG_FILE', str(config))
    config_before = config.read_bytes()
    assert len(favorites.stations()) == 5
    for item in (renamed, custom, legacy):
        assert favorites.station(item['id']) == item
    loaded = favorites._load()
    assert existing_ids <= set(loaded['stations'])
    assert loaded['favorites'] == document['favorites']
    assert loaded['custom_metadata'] == document['custom_metadata']
    assert favorites.station(removed['id'], allow_removed=True) == {**removed, 'removed': True}
    assert config.read_bytes() == config_before


def test_concurrent_initial_reads_seed_once(rig):
    from concurrent.futures import ThreadPoolExecutor
    favorites.path().unlink()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: favorites.stations(), range(4)))
    assert all(result == results[0] for result in results)
    assert len(results[0]) == 5


def test_seed_capacity_and_failed_write_are_atomic(rig, monkeypatch):
    document = {'version': 1, 'favorites': {}, 'stations': {
        str(i): {'id': str(i), 'name': str(i), 'url': f'https://radio.example/{i}'}
        for i in range(496)}}
    favorites._save(document)
    before = favorites.path().read_bytes()
    warnings = []
    assert len(favorites.stations(seed_warnings=warnings)) == 496
    assert 'storage is full' in warnings[0]
    assert favorites.path().read_bytes() == before
    document['stations'] = {}
    favorites._save(document)
    before = favorites.path().read_bytes()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(favorites.os, 'replace', fail)
    warnings = []
    assert favorites.stations(seed_warnings=warnings) == []
    assert 'could not be saved' in warnings[0]
    assert favorites.path().read_bytes() == before


def test_seed_marks_already_populated_store_and_does_not_overwrite_future_marker(rig):
    favorites.path().unlink()
    favorites.stations()
    document = favorites._load()
    document.pop('station_seed_version')
    favorites._save(document)
    assert len(favorites.stations()) == 5
    assert favorites._load()['station_seed_version'] == 1
    document['station_seed_version'] = 2
    favorites._save(document)
    before = favorites.path().read_bytes()
    favorites.stations()
    assert favorites.path().read_bytes() == before


def test_starter_import_api_is_removed(rig):
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    assert client.post('/api/stations/starter', json={}).status_code == 405


def test_seed_failure_does_not_block_existing_playback_or_removal(rig, monkeypatch):
    saved = favorites.add_station('Existing', 'https://radio.example/live')
    document = favorites._load()
    document.pop('station_seed_version')
    document['favorites']['existing'] = {'name': 'Existing favorite'}
    favorites._save(document)
    def fail(*args):
        raise favorites.FavoriteError('Seed unavailable')
    monkeypatch.setattr(favorites, '_seed_stations', fail)
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    result = app.test_client().get('/api/stations')
    assert result.status_code == 200
    assert result.json['seed_warning'] == 'Seed unavailable'
    assert result.json['stations'] == [saved]
    assert favorites.get('existing') == {'name': 'Existing favorite'}
    assert favorites.station_descriptor(saved['id'])['audio']['streamUrl'] == saved['url']
    favorites.remove_station(saved['id'])
    assert favorites.stations() == []


def test_radio_readiness_distinguishes_native_and_direct_diagnostic(rig):
    radio = favorites.overview('Bedroom')['radio']
    assert radio['available'] is False
    assert radio['native_preset'] == {
        'available': False, 'blockers': ['radio_preset_assignment_unsupported']}
    assert radio['station_playback']['available'] is False
    assert radio['direct_test']['experimental'] is True
    assert radio['direct_test']['automatic_schedules'] is False
    assert radio['direct_test']['physical_presets'] is False
    assert not rig[1]


def test_native_readiness_does_not_require_direct_diagnostic(rig, monkeypatch):
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    radio = favorites.overview('Bedroom')['radio']
    assert radio['available'] is False
    assert radio['native_preset'] == {
        'available': False, 'blockers': ['radio_preset_assignment_unsupported']}
    assert radio['station_playback']['available'] is False  # /select not advertised


def test_overview_allows_spotify_connect_and_preserves_supported_workflows(rig, monkeypatch):
    slots, calls = rig
    slots[2] = {**ITEM, 'name': 'Existing speaker playlist'}
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    monkeypatch.setattr(favorites, 'capabilities', lambda ip: {'/storePreset', '/navigate', '/select'})
    monkeypatch.setattr(library, 'read_sources', lambda ip: [copy.deepcopy(SOURCE),
        {'source': 'SPOTIFY', 'account': 'secret', 'name': 'private@example.test', 'ready': True},
        {'source': 'ALEXA', 'account': 'alexa-secret', 'name': 'Alexa', 'ready': True},
        {'source': 'AMAZON', 'account': 'amazon-secret', 'name': 'Amazon Music', 'ready': True},
        {'source': 'LOCAL_INTERNET_RADIO', 'account': '', 'name': 'Internet radio', 'ready': True}])
    value = favorites.overview('Bedroom')
    assert value['favorites'] == []
    assert value['presets'][1] == {'slot': 2, 'name': 'Existing speaker playlist'}
    assert value['sources'] == [{k: SOURCE[k] for k in ('id', 'name', 'ready')}]
    assert 'services' not in value
    assert value['external_playback'] == [{
        'name': 'Spotify Connect',
        'ready': True,
        'guidance': 'Start playback from the Spotify app.',
    }]
    assert value['radio']['station_playback'] == {
        'available': True, 'requires_source': 'LOCAL_INTERNET_RADIO'}
    assert 'Alexa' not in str(value) and 'Amazon Music' not in str(value)
    assert 'secret' not in str(value) and 'private@example.test' not in str(value)
    assert calls == []


def test_seed_preserves_existing_buzz_entry_and_legacy_candidate(rig):
    from app.core import radio_stream
    url = 'https://playerservices.streamtheworld.com/api/livestream-redirect/WBTZFM.mp3'
    buzz = favorites.add_station('The Buzz 99.9', url)
    document = favorites._load()
    document.pop('station_seed_version')
    favorites._save(document)
    listed = favorites.stations()
    assert buzz in listed
    assert len(listed) == 6
    assert favorites.station(buzz['id']) == buzz
    assert radio_stream.candidate(url) == url.replace('https:', 'http:', 1)
    assert not rig[1]
