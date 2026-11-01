"""Collection schedule contracts; all device reads/writes are fake."""
import copy
import json
import queue
from unittest.mock import Mock

import pytest
from flask import Flask

from app.api import routes
from app.core import playback, collections
from app.scheduler import jobs


@pytest.fixture
def binding():
    return {'version': 1, 'library_id': 'server-id', 'speaker_id': 'ABC',
            'content': {'source': 'STORED_MUSIC', 'sourceAccount': 'server/0',
                        'location': 'folder:1', 'type': 'dir', 'name': 'Album',
                        'playable': True, 'presetable': True}, 'ancestors': []}


@pytest.fixture
def contract(monkeypatch, binding):
    def validate(value, speaker_name=None):
        if not isinstance(value, dict) or value.get('version') != 1 or not value.get('content'):
            raise ValueError('Invalid collection binding.')
        return copy.deepcopy(value)
    monkeypatch.setattr(collections, 'validate_binding', validate)
    monkeypatch.setattr(collections, 'resolve', lambda value, speaker_name: copy.deepcopy(value['content']))
    monkeypatch.setattr(jobs, 'current_config', {'Room': []})
    return binding


def payload(binding):
    return {'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00',
            'volume': 8, 'fade_in_duration': 2, 'fade_out_duration': 3, 'paused': False,
            'source_kind': 'collection', 'speaker_id': 'ABC', 'collection': copy.deepcopy(binding)}


def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(routes.api_bp)
    queued = []
    monkeypatch.setattr(jobs.config_queue, 'put', queued.append)
    return app.test_client(), queued


def test_collection_save_persists_binding_without_playback(monkeypatch, contract):
    http, queued = client(monkeypatch)
    play = Mock(side_effect=AssertionError('Save cannot play'))
    monkeypatch.setattr(jobs, 'queue_on', play)
    response = http.post('/api/Room/schedules', json=payload(contract))
    assert response.status_code == 202
    saved = queued[0]['data']
    assert saved['collection'] == contract
    assert saved['speaker_id'] == 'ABC'
    assert saved['source_kind'] == 'collection'
    assert 'preset' not in saved and 'source' not in saved
    play.assert_not_called()


@pytest.mark.parametrize('extra', [{'preset': 1}, {'source': 'AUX'}, {'station_id': 'a' * 32},
                                  {'favorite_id': 'b' * 32}, {'source_kind': 'future'},
                                  {'source_kind': 'station'}, {'source_kind': 'favorite'},
                                  {'source_kind': 'preset'}, {'source_kind': 'aux'},
                                  {'collection_id': 'ignored'}, {'speaker_id': 'OTHER'}])
def test_collection_source_conflicts_never_become_button_one(monkeypatch, contract, extra):
    http, queued = client(monkeypatch)
    data = payload(contract)
    data.update(extra)
    response = http.post('/api/Room/schedules', json=data)
    assert response.status_code == 400
    assert not queued


@pytest.mark.parametrize('value', [None, {}, {'version': 2}, 'browse-token'])
def test_invalid_explicit_collection_rejected_before_default(monkeypatch, contract, value):
    http, queued = client(monkeypatch)
    data = payload(contract)
    data['collection'] = value
    response = http.post('/api/Room/schedules', json=data)
    assert response.status_code == 400
    assert not queued


def test_old_client_edit_preserves_collection(monkeypatch, contract):
    saved = routes._to_schedule(payload(contract))
    monkeypatch.setattr(jobs, 'current_config', {'Room': [saved]})
    http, queued = client(monkeypatch)
    data = payload(contract)
    del data['collection'], data['source_kind']
    data['volume'] = 11
    assert http.post('/api/Room/schedules', json=data).status_code == 202
    assert queued[0]['data']['collection'] == contract
    assert queued[0]['data']['volume'] == 11
    assert 'preset' not in queued[0]['data']


def test_explicit_change_music_can_clear_collection(monkeypatch, contract):
    monkeypatch.setattr(jobs, 'current_config', {'Room': [routes._to_schedule(payload(contract))]})
    http, queued = client(monkeypatch)
    data = payload(contract)
    data.update(collection=None, source_kind='preset', preset=3)
    assert http.post('/api/Room/schedules', json=data).status_code == 202
    assert 'collection' not in queued[0]['data']
    assert queued[0]['data']['preset'] == 3


def test_unavailable_collection_edit_keeps_review_pause_and_settings(monkeypatch, contract):
    saved = routes._to_schedule(payload(contract))
    saved.update(paused=True, review_reason='library_removed')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [saved]})
    monkeypatch.setattr(collections, 'resolve', Mock(side_effect=ValueError('Unavailable')))
    http, queued = client(monkeypatch)
    assert http.post('/api/Room/schedules', json=payload(contract)).status_code == 202
    changed = queued[0]['data']
    assert changed['paused'] is True and changed['review_reason'] == 'library_removed'
    assert changed['on_time'] == saved['on_time'] and changed['days'] == saved['days']
    assert changed['volume'] == saved['volume']


def test_review_resume_requires_explicit_review_and_ready_source(monkeypatch, contract):
    saved = routes._to_schedule(payload(contract))
    saved.update(paused=True, review_reason='button_replaced')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [saved]})
    http, queued = client(monkeypatch)
    assert http.patch('/api/Room/schedules/Morning/resume').status_code == 409
    assert not queued
    assert http.patch('/api/Room/schedules/Morning/resume', json={'reviewed': True}).status_code == 202
    assert queued[0]['review_confirmed'] is True
    assert queued[0]['data']['paused'] is False
    assert 'review_reason' not in queued[0]['data']


def test_collection_binding_survives_persist_reload_and_buttons(contract, monkeypatch, tmp_path):
    path = tmp_path / 'schedules.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    schedule = routes._to_schedule(payload(contract))
    jobs._write_config({'Room': [schedule]})
    loaded = jobs.load_config()['Room'][0]
    assert loaded['collection'] == contract
    assert loaded['speaker_id'] == 'ABC'
    assert loaded['preset'] is None
    assert 'source_error' not in loaded
    assert json.loads(path.read_text())['schedules']['Room'][0]['collection'] == contract


def test_invalid_loaded_collection_is_visible_unavailable_never_preset(contract):
    data = payload(contract)
    data['collection']['version'] = 999
    loaded = jobs.sanitize_config({'Room': [data]})['Room'][0]
    assert loaded['preset'] is None and loaded['source'] is None
    assert loaded['source_error']
    assert loaded['collection']['version'] == 999
    assert jobs.queue_on('Room', loaded)['state'] == 'skipped'


def test_unknown_loaded_discriminator_is_not_defaulted(contract):
    data = payload(contract)
    del data['collection']
    data['source_kind'] = 'future'
    loaded = jobs.sanitize_config({'Room': [data]})['Room'][0]
    assert loaded['preset'] is None and loaded['source_error']


@pytest.fixture
def device(monkeypatch):
    playback.reset()
    monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a, **kw: {
        'name': 'Room', 'ip': 'fake', 'device_id': 'ABC'})
    monkeypatch.setattr(playback.status, 'get_device_id', lambda *a, **kw: 'ABC')
    state = {'status': 'Standby', 'source_type': 'STANDBY', 'device_id': 'ABC'}
    calls = []
    volume = [10]
    monkeypatch.setattr(playback.status, 'get_now_playing', lambda *a, **kw: dict(state, observed_at=playback.time.time()))
    monkeypatch.setattr(playback.status, 'get_volume', lambda *a, **kw: volume[0])
    def change_volume(ip, value, **kw):
        calls.append(('volume', value))
        volume[0] = value
        return True
    def select(ip, content, **kw):
        calls.append(('select', content['location']))
        state.update(status='Playing', source_type='STORED_MUSIC', content_identity={
            'source': 'STORED_MUSIC', 'sourceAccount': 'server/0', 'location': 'folder:1', 'type': 'dir'})
        return True
    monkeypatch.setattr(playback.control, 'set_volume', change_volume)
    monkeypatch.setattr(playback.control, 'select_content', select)
    monkeypatch.setattr(playback.control, 'play_preset', Mock(side_effect=AssertionError('No preset fallback')))
    monkeypatch.setattr(playback.control, 'power_action', Mock(side_effect=AssertionError('No power toggle')))
    monkeypatch.setattr(playback, 'wait', lambda op, delay: playback.current(op))
    return state, calls


def test_direct_collection_execution_reuses_quiet_start(contract, device):
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, None, 4, fade_in_duration=0, collection=contract)
    assert device[1] == [('volume', 0), ('select', 'folder:1'), ('volume', 4)]
    assert playback.last('Room')['state'] == 'playing'


def test_missing_collection_skips_without_source_or_volume_write(contract, device, monkeypatch):
    monkeypatch.setattr(collections, 'resolve', Mock(side_effect=ValueError('NAS unavailable')))
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, None, 4, collection=contract)
    assert device[1] == []
    assert playback.last('Room')['state'] == 'skipped'
    assert 'NAS unavailable' in playback.last('Room')['reason']


def test_new_speaker_and_conflicting_source_fail_closed(contract, device):
    contract['speaker_id'] = 'OTHER'
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, None, 4, collection=contract)
    assert device[1] == []
    contract['speaker_id'] = 'ABC'
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, 1, 4, collection=contract)
    assert device[1] == []


def test_automatic_collection_remains_polite_and_cancelable(contract, device):
    device[0]['status'] = 'Playing'
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, None, 4, collection=contract)
    assert playback.last('Room')['reason'] == 'speaker_active' and device[1] == []
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.cancel('Room')
    playback.run_on(op, None, 4, force=True, collection=contract)
    assert device[1] == []


def test_collection_stop_refuses_replacement_and_uses_stop_only(contract, device, monkeypatch):
    op = playback.begin('Room', 'Listen', 'ABC')
    op['outcome']['collection_session'] = True
    playback.run_on(op, None, 4, fade_in_duration=0, force=True, collection=contract)
    assert playback.begin_collection_stop('Room', 'OTHER', op['outcome']['operation_id']) is None
    stop = playback.begin_collection_stop('Room', 'ABC', op['outcome']['operation_id'])
    assert stop is not None
    assert playback.begin_collection_stop('Room', 'ABC', op['outcome']['operation_id']) is None
    def native_stop(ip, **kw):
        device[1].append(('stop',))
        device[0]['status'] = 'Stopped'
        return True
    monkeypatch.setattr(playback.control, 'stop_action', native_stop)
    playback.run_station_stop(stop)
    assert device[1][-1] == ('stop',)
    assert playback.last('Room')['state'] == 'completed'


def test_pause_slot_is_durable_and_excludes_direct_collections(contract, monkeypatch, tmp_path):
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    legacy = routes._to_schedule(dict(payload(contract), collection=None))
    legacy.pop('collection')
    legacy.pop('source_kind')
    legacy['preset'] = 2
    direct = routes._to_schedule(payload(contract))
    direct['name'] = 'Direct'
    jobs._write_config({'Room': [legacy, direct]})
    monkeypatch.setattr(jobs, 'current_config', {'Room': [legacy, direct]})
    monkeypatch.setattr(playback.discovery, 'get_all_cached_devices', lambda: [{'name': 'Room', 'device_id': 'ABC'}])
    impacts = jobs.pause_source_schedules('ABC', slot=2, reason='button_replaced')
    assert [item['name'] for item in impacts] == ['Morning']
    loaded = jobs.load_config()['Room']
    assert loaded[0]['paused'] and loaded[0]['review_reason'] == 'button_replaced'
    assert loaded[1]['paused'] is False


def test_pause_persistence_failure_does_not_publish_pause(contract, monkeypatch, tmp_path):
    schedule = routes._to_schedule(payload(contract))
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    jobs._write_config({'Room': [schedule]})
    monkeypatch.setattr(jobs, 'current_config', {'Room': [schedule]})
    monkeypatch.setattr(jobs, '_write_config', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        jobs.pause_source_schedules('ABC', source_account='server/0')
    assert jobs.current_config['Room'][0]['paused'] is False


def test_queued_old_edit_cannot_clear_new_review_pause(contract, monkeypatch, tmp_path):
    schedule = routes._to_schedule(payload(contract))
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    saved = dict(schedule, paused=True, review_reason='button_replaced')
    jobs._write_config({'Room': [saved]})
    work = queue.Queue()
    work.put({'action': 'add_update', 'speaker': 'Room', 'schedule_name': 'Morning', 'data': schedule})
    work.put(None)
    monkeypatch.setattr(jobs, 'config_queue', work)
    monkeypatch.setattr(jobs, '_stop_event', __import__('threading').Event())
    jobs.config_io_worker()
    reloaded = jobs.load_config()['Room'][0]
    assert reloaded['paused'] and reloaded['review_reason'] == 'button_replaced'


def test_pending_collection_coalesces_only_equivalent_request(contract, monkeypatch):
    playback.reset()
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a, **kw: True)
    monkeypatch.setattr(playback, 'has_radio', lambda *a: False)
    schedule = routes._to_schedule(payload(contract))
    first = jobs.queue_on('Room', schedule, force=True)
    assert jobs.queue_on('Room', copy.deepcopy(schedule), force=True)['operation_id'] == first['operation_id']
    changed = copy.deepcopy(schedule)
    changed['collection']['content']['location'] = 'another-folder'
    with pytest.raises(jobs.StationRequestConflict):
        jobs.queue_on('Room', changed, force=True)
    changed = copy.deepcopy(schedule)
    changed['volume'] += 1
    with pytest.raises(jobs.StationRequestConflict):
        jobs.queue_on('Room', changed, force=True)
    assert playback.last('Room')['operation_id'] == first['operation_id']


def test_station_draft_cannot_be_scheduled(contract, monkeypatch):
    http, queued = client(monkeypatch)
    data = payload(contract)
    del data['collection'], data['source_kind']
    data['station_id'] = 'a' * 32
    monkeypatch.setattr(routes.favorites, 'station', lambda *a, **kw: {'draft': True, 'url': 'https://example.invalid/radio'})
    response = http.post('/api/Room/schedules', json=data)
    assert response.status_code == 400 and not queued
    assert 'save' in response.get_json()['errors']['station_id']


def test_read_only_collection_check_recovers_only_exact_unknown_session(contract, device):
    op = playback.begin('Room', 'Listen', 'ABC')
    op['outcome']['collection_session'] = True
    playback.run_on(op, None, 4, fade_in_duration=0, force=True, collection=contract)
    op['outcome'].update(state='unknown', reason='readback_timeout', terminal=True)
    writes = list(device[1])
    assert playback.reconcile_collection_session('Room', 'ABC', 'old-operation') is False
    assert playback.reconcile_collection_session('Room', 'OTHER', op['outcome']['operation_id']) is False
    assert playback.reconcile_collection_session('Room', 'ABC', op['outcome']['operation_id']) is True
    assert playback.last('Room')['state'] == 'playing'
    assert playback.last('Room')['audible_confirmed'] is False
    assert device[1] == writes
    assert playback.begin_collection_stop('Room', 'ABC', op['outcome']['operation_id']) is not None


def test_read_only_check_refuses_source_or_owner_change(contract, device, monkeypatch):
    op = playback.begin('Room', 'Listen', 'ABC')
    op['outcome']['collection_session'] = True
    playback.run_on(op, None, 4, fade_in_duration=0, force=True, collection=contract)
    op['outcome'].update(state='unknown', reason='readback_timeout', terminal=True)
    device[0]['content_identity']['location'] = 'replacement'
    assert playback.reconcile_collection_session('Room', 'ABC', op['outcome']['operation_id']) is False
    device[0]['content_identity']['location'] = 'folder:1'
    original_read = playback.status.get_now_playing
    def supersede(*args, **kwargs):
        observed = original_read(*args, **kwargs)
        playback.begin('Room', 'Replacement', 'ABC')
        return observed
    monkeypatch.setattr(playback.status, 'get_now_playing', supersede)
    assert playback.reconcile_collection_session('Room', 'ABC', op['outcome']['operation_id']) is False
    assert playback.last('Room')['schedule_name'] == 'Replacement'


def test_old_reviewed_edit_cannot_clear_new_pause_with_same_reason(contract, monkeypatch, tmp_path):
    schedule = routes._to_schedule(payload(contract))
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    saved = dict(schedule, paused=True, review_reason='library_removed', review_token='new-revision')
    jobs._write_config({'Room': [saved]})
    work = queue.Queue()
    work.put({'action': 'add_update', 'speaker': 'Room', 'schedule_name': 'Morning',
              'data': schedule, 'review_confirmed': True, 'expected_review_token': 'old-revision'})
    work.put(None)
    monkeypatch.setattr(jobs, 'config_queue', work)
    monkeypatch.setattr(jobs, '_stop_event', __import__('threading').Event())
    jobs.config_io_worker()
    reloaded = jobs.load_config()['Room'][0]
    assert reloaded['paused'] and reloaded['review_token'] == 'new-revision'


def test_explicit_resume_rejects_stale_pause_revision(contract, monkeypatch):
    saved = routes._to_schedule(payload(contract))
    saved.update(paused=True, review_reason='library_removed', review_token='current-revision')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [saved]})
    http, queued = client(monkeypatch)
    assert http.patch('/api/Room/schedules/Morning/resume', json={
        'reviewed': True, 'review_token': 'old-revision'}).status_code == 409
    assert not queued
    assert http.patch('/api/Room/schedules/Morning/resume', json={
        'reviewed': True, 'review_token': 'current-revision'}).status_code == 202
    assert queued[0]['expected_review_token'] == 'current-revision'


def test_missing_favorite_does_not_hide_known_removal_impacts(contract, monkeypatch, tmp_path):
    direct = routes._to_schedule(payload(contract))
    stale = dict(direct, name='Missing favorite', favorite_id='f' * 32, preset=2)
    stale.pop('collection')
    stale.pop('source_kind')
    legacy = dict(stale, name='Legacy', preset=3)
    legacy.pop('favorite_id')
    unrelated = dict(legacy, name='Unrelated', preset=4)
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    jobs._write_config({'Room': [stale, direct, legacy, unrelated]})
    monkeypatch.setattr(jobs, 'current_config', {'Room': [stale, direct, legacy, unrelated]})
    monkeypatch.setattr(routes.favorites, 'get', Mock(side_effect=ValueError('Favorite missing')))
    monkeypatch.setattr(routes.favorites, 'device', lambda *a, **kw: {'device_id': 'ABC', 'ip': 'fake'})
    from app.core import library
    slots = {slot: None for slot in range(1, 7)}
    slots[3] = contract['content']
    slots[4] = dict(contract['content'], sourceAccount='other/0')
    monkeypatch.setattr(library, 'read_presets', lambda *a: slots)
    impacts = jobs.source_schedule_impacts('ABC', source_account='server/0')
    assert {item['name'] for item in impacts} == {'Missing favorite', 'Morning', 'Legacy'}
    assert next(item for item in impacts if item['name'] == 'Missing favorite')['impact_unknown'] is True
    jobs.pause_source_schedules('ABC', source_account='server/0')
    loaded = {item['name']: item for item in jobs.load_config()['Room']}
    assert loaded['Missing favorite']['paused'] and loaded['Morning']['paused'] and loaded['Legacy']['paused']
    assert loaded['Unrelated']['paused'] is False


def test_duplicate_speaker_names_do_not_choose_arbitrary_legacy_owner(contract, monkeypatch, tmp_path):
    direct = routes._to_schedule(payload(contract))
    legacy = dict(direct, name='Legacy', preset=2)
    legacy.pop('collection')
    legacy.pop('source_kind')
    legacy.pop('speaker_id')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [legacy, direct]})
    monkeypatch.setattr(playback.discovery, 'get_all_cached_devices', lambda: [
        {'name': 'Room', 'device_id': 'ABC'}, {'name': 'Room', 'device_id': 'OTHER'}])
    abc = jobs.source_schedule_impacts('ABC', slot=2)
    other = jobs.source_schedule_impacts('OTHER', slot=2)
    assert [item['name'] for item in abc] == ['Legacy']
    assert [item['name'] for item in other] == ['Legacy']
    assert abc[0]['impact_unknown'] and other[0]['impact_unknown']


def move_payload(binding):
    data = payload(binding)
    data.update(previous_speaker='Room', previous_name='Morning', previous_speaker_id='ABC',
                previous_collection=copy.deepcopy(binding))
    data['collection']['speaker_id'] = 'XYZ'
    data['speaker_id'] = 'XYZ'
    return data


def run_mutations(monkeypatch, mutations):
    work = queue.Queue()
    for mutation in mutations:
        work.put(mutation)
    work.put(None)
    monkeypatch.setattr(jobs, 'config_queue', work)
    monkeypatch.setattr(jobs, '_stop_event', __import__('threading').Event())
    jobs.config_io_worker()


def test_collection_target_edit_moves_one_routine_in_single_mutation(contract, monkeypatch, tmp_path):
    original = routes._to_schedule(payload(contract))
    original.update(paused=True, review_reason='library_removed', review_token='current-pause')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', tmp_path / 'config.json')
    jobs._write_config({'Room': [original]})
    resolve = Mock(return_value=contract['content'])
    monkeypatch.setattr(collections, 'resolve', resolve)
    http, queued = client(monkeypatch)
    assert http.post('/api/Bedroom/schedules', json=move_payload(contract)).status_code == 202
    assert len(queued) == 1 and queued[0]['action'] == 'move_collection'
    assert queued[0]['previous_speaker'] == 'Room'
    resolve.assert_called_once()
    run_mutations(monkeypatch, queued)
    loaded = jobs.load_config()
    assert 'Room' not in loaded
    assert len(loaded['Bedroom']) == 1
    moved = loaded['Bedroom'][0]
    assert moved['speaker_id'] == 'XYZ' and moved['collection']['speaker_id'] == 'XYZ'
    assert moved['paused'] and moved['review_token'] == 'current-pause'
    for field in ('name', 'days', 'on_time', 'off_time', 'volume', 'fade_in_duration', 'fade_out_duration'):
        assert moved[field] == original[field]


@pytest.mark.parametrize('change', [
    {'previous_name': None}, {'previous_speaker_id': 'WRONG'},
    {'previous_collection': {}},
])
def test_collection_move_rejects_unverified_original_or_noncollection_target(contract, monkeypatch, change):
    original = routes._to_schedule(payload(contract))
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    http, queued = client(monkeypatch)
    data = move_payload(contract)
    data.update(change)
    assert http.post('/api/Bedroom/schedules', json=data).status_code == 409
    assert not queued
    assert jobs.current_config['Room'][0] == original


def test_collection_move_rejects_target_name_collision(contract, monkeypatch):
    original = routes._to_schedule(payload(contract))
    other = dict(original, volume=22)
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original], 'Bedroom': [other]})
    http, queued = client(monkeypatch)
    assert http.post('/api/Bedroom/schedules', json=move_payload(contract)).status_code == 409
    assert not queued and jobs.current_config['Bedroom'][0]['volume'] == 22


def test_collection_move_rejects_unavailable_target_even_while_paused(contract, monkeypatch):
    original = routes._to_schedule(payload(contract))
    original['paused'] = True
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    monkeypatch.setattr(collections, 'resolve', Mock(side_effect=ValueError('Target unavailable')))
    http, queued = client(monkeypatch)
    data = dict(move_payload(contract), paused=True)
    assert http.post('/api/Bedroom/schedules', json=data).status_code == 400
    assert not queued


@pytest.mark.parametrize('race', ['new_origin_pause', 'target_collision'])
def test_queued_collection_move_rechecks_original_revision_and_target(contract, monkeypatch, tmp_path, race):
    original = routes._to_schedule(payload(contract))
    path = tmp_path / 'config.json'
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', path)
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    jobs._write_config({'Room': [original]})
    http, queued = client(monkeypatch)
    assert http.post('/api/Bedroom/schedules', json=move_payload(contract)).status_code == 202
    latest = {'Room': [copy.deepcopy(original)]}
    if race == 'new_origin_pause':
        latest['Room'][0].update(paused=True, review_reason='library_removed', review_token='new-pause')
    else:
        latest['Bedroom'] = [dict(original, volume=33)]
    jobs._write_config(latest)
    run_mutations(monkeypatch, queued)
    loaded = jobs.load_config()
    assert len(loaded['Room']) == 1
    if race == 'new_origin_pause':
        assert loaded['Room'][0]['review_token'] == 'new-pause' and 'Bedroom' not in loaded
    else:
        assert len(loaded['Bedroom']) == 1 and loaded['Bedroom'][0]['volume'] == 33


def test_same_speaker_previous_speaker_metadata_keeps_ordinary_edit(contract, monkeypatch):
    original = routes._to_schedule(payload(contract))
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    http, queued = client(monkeypatch)
    data = dict(payload(contract), previous_speaker='Room', previous_name='Morning', volume=9)
    assert http.post('/api/Room/schedules', json=data).status_code == 202
    assert queued[0]['action'] == 'add_update' and queued[0]['data']['volume'] == 9


def test_stoppable_quiet_test_retains_intent_and_does_not_coalesce_with_unstoppable(contract, monkeypatch):
    playback.reset()
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a, **kw: True)
    first = jobs.queue_station('Room', 'ABC', 'station', listening=False)
    assert first['radio_request_intent'] == 'quiet_test' and first['listening_session'] is False
    with pytest.raises(jobs.StationRequestConflict):
        jobs.queue_station('Room', 'ABC', 'station', listening=False, stoppable=True)
    assert playback.last('Room')['operation_id'] == first['operation_id']
    playback.reset()
    accepted = jobs.queue_station('Room', 'ABC', 'station', listening=False, stoppable=True)
    assert accepted['radio_request_intent'] == 'quiet_test' and accepted['listening_session'] is True
    assert accepted['target_volume'] == 5
    repeated = jobs.queue_station('Room', 'ABC', 'station', listening=False, stoppable=True)
    assert repeated['operation_id'] == accepted['operation_id']
    with pytest.raises(jobs.StationRequestConflict):
        jobs.queue_station('Room', 'ABC', 'station', listening=True)


def test_stale_queued_edit_cannot_recreate_original_after_move(contract, monkeypatch, tmp_path):
    original = routes._to_schedule(payload(contract))
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', tmp_path / 'config.json')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    jobs._write_config({'Room': [original]})
    http, queued = client(monkeypatch)
    assert http.post('/api/Bedroom/schedules', json=move_payload(contract)).status_code == 202
    assert http.post('/api/Room/schedules', json=dict(payload(contract), previous_name='Morning', volume=29)).status_code == 202
    assert len(queued) == 2
    run_mutations(monkeypatch, queued)
    loaded = jobs.load_config()
    assert 'Room' not in loaded and len(loaded['Bedroom']) == 1
    assert loaded['Bedroom'][0]['volume'] == original['volume']


@pytest.mark.parametrize('new_speaker', ['Room', 'Bedroom'])
def test_replace_collection_with_radio_retains_one_routine_and_settings(contract, monkeypatch, tmp_path, new_speaker):
    original = routes._to_schedule(payload(contract))
    original.update(paused=True, review_reason='library_removed', review_token='pause-revision')
    monkeypatch.setattr(jobs, 'CONFIG_FILE_PATH', tmp_path / 'config.json')
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    jobs._write_config({'Room': [original]})
    monkeypatch.setattr(routes.favorites, 'station', lambda *a, **kw: {'url': 'https://example.invalid/radio'})
    def target_device(speaker, pinned=None):
        identity = 'XYZ' if speaker == 'Bedroom' else 'ABC'
        if pinned not in (None, identity):
            raise ValueError('Old identity cannot pin the new target')
        return {'device_id': identity, 'ip': 'fake'}
    monkeypatch.setattr(routes.favorites, 'device', target_device)
    from app.core import radio_relay
    ready = Mock(return_value={'available': True})
    monkeypatch.setattr(radio_relay, 'readiness', ready)
    http, queued = client(monkeypatch)
    data = move_payload(contract)
    data.update(collection=None, source_kind='station', station_id='b' * 32)
    data.pop('speaker_id')
    assert http.post(f'/api/{new_speaker}/schedules', json=data).status_code == 202
    assert queued[0]['data']['speaker_id'] == ('XYZ' if new_speaker == 'Bedroom' else 'ABC')
    if new_speaker != 'Room':
        ready.assert_called_once()
    run_mutations(monkeypatch, queued)
    loaded = jobs.load_config()
    assert sum(len(items) for items in loaded.values()) == 1
    saved = loaded[new_speaker][0]
    assert saved['station_id'] == 'b' * 32 and 'collection' not in saved
    assert saved['paused'] and saved['review_token'] == 'pause-revision'
    for field in ('name', 'days', 'on_time', 'off_time', 'volume', 'fade_in_duration', 'fade_out_duration'):
        assert saved[field] == original[field]


def test_move_without_explicit_target_music_never_defaults_to_button_one(contract, monkeypatch):
    original = routes._to_schedule(payload(contract))
    monkeypatch.setattr(jobs, 'current_config', {'Room': [original]})
    http, queued = client(monkeypatch)
    data = move_payload(contract)
    data.pop('collection')
    data.pop('source_kind')
    assert http.post('/api/Bedroom/schedules', json=data).status_code == 400
    assert not queued


def test_operations_check_reconciles_only_unknown_saved_station_session(monkeypatch):
    http, _ = client(monkeypatch)
    unknown = {'state': 'unknown', 'listening_session': True, 'speaker_id': 'ABC',
               'station_id': 'saved', 'operation_id': 'op'}
    refreshed = dict(unknown, state='playing', audible_confirmed=False)
    observations = iter([unknown, refreshed])
    monkeypatch.setattr(jobs, 'get_last_outcome', lambda speaker: next(observations))
    check = Mock(return_value=True)
    monkeypatch.setattr(playback, 'reconcile_station_session', check)
    response = http.get('/api/Room/operations')
    check.assert_called_once_with('Room', 'ABC', 'saved', 'op')
    assert response.get_json()['last_outcome']['state'] == 'playing'
    assert response.get_json()['last_outcome']['audible_confirmed'] is False


def test_operations_does_not_reconcile_unowned_or_nonstation_outcomes(monkeypatch):
    http, _ = client(monkeypatch)
    monkeypatch.setattr(jobs, 'get_last_outcome', lambda speaker: {
        'state': 'unknown', 'operation_id': 'op', 'collection_session': True})
    check = Mock()
    monkeypatch.setattr(playback, 'reconcile_station_session', check)
    assert http.get('/api/Room/operations').status_code == 200
    check.assert_not_called()
