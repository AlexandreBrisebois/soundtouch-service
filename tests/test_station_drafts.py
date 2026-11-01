"""Draft radio evidence tests; all operations and devices are isolated fixtures."""
import copy
import time

import pytest
from flask import Flask

from app.api.favorites import favorites_bp
from app.api.station_drafts import station_drafts_bp
from app.core import favorites, playback, station_drafts
from app.scheduler import jobs

REAL_RECONCILE = playback.reconcile_station_session
URL = 'https://radio.example/live.mp3'
DEVICE = {'device_id': 'ABC', 'ip': '192.0.2.1', 'name': 'Bedroom'}


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    favorites._save({'version': 1, 'favorites': {}, 'station_seed_version': 1})
    station_drafts._drafts.clear()
    monkeypatch.setattr(station_drafts.playback, 'reconcile_station_session', lambda *a: False)
    current, calls = {}, []
    monkeypatch.setattr(favorites, 'device', lambda *a: dict(DEVICE))
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing', lambda *a, **k: {})
    monkeypatch.setattr(station_drafts.radio_relay, 'readiness',
                        lambda *a: {'available': True, 'mode': 'native'})
    monkeypatch.setattr(station_drafts.playback, 'last', lambda speaker: copy.deepcopy(current.get(speaker)))

    def queue(speaker, device_id, draft_id, volume, *, listening):
        calls.append(('play', speaker, draft_id, volume, listening))
        current[speaker] = {'operation_id': 'play-' + str(len(calls)), 'station_id': draft_id,
                            'speaker_id': device_id, 'state': 'accepted', 'terminal': False}
        return copy.deepcopy(current[speaker])

    def stop(speaker, device_id, draft_id, operation_id):
        old = current.get(speaker, {})
        if old.get('operation_id') != operation_id or old.get('state') != 'playing':
            return None
        calls.append(('stop', speaker, draft_id, operation_id))
        current[speaker] = {'operation_id': 'stop-' + str(len(calls)), 'station_id': draft_id,
                            'speaker_id': device_id, 'stops_operation_id': operation_id,
                            'state': 'accepted', 'terminal': False}
        return copy.deepcopy(current[speaker])

    monkeypatch.setattr(jobs, 'queue_station', queue)
    monkeypatch.setattr(jobs, 'queue_station_stop', stop)
    return current, calls


def started():
    draft = station_drafts.create('Test station', URL)
    result = station_drafts.test(draft['id'], {'speaker': 'Bedroom', 'speaker_id': 'ABC',
                                               'confirmed': True})
    return draft['id'], result['operation']['operation_id']


def completed(rig, reason='radio_stopped_verified'):
    current, _ = rig
    draft_id, operation_id = started()
    current['Bedroom'].update(state='playing', terminal=True)
    station_drafts.stop(draft_id, {'speaker_id': 'ABC', 'operation_id': operation_id})
    current['Bedroom'].update(state='completed', reason=reason, terminal=True)
    return draft_id, operation_id


def save_data(operation_id, **changes):
    return {'name': 'Saved name', 'url': URL, 'audible_confirmed': True,
            'operation_id': operation_id, **changes}


def test_draft_creation_is_transient_and_preserves_store(rig):
    before = favorites.path().read_bytes()
    draft = station_drafts.create('Draft', URL)
    assert draft['state'] == 'untested'
    assert favorites.path().read_bytes() == before
    assert favorites.stations() == []
    assert station_drafts.station(draft['id'])['draft'] is True


def test_untested_and_unheard_drafts_cannot_save(rig):
    draft = station_drafts.create('Draft', URL)
    with pytest.raises(ValueError, match='verified Stop'):
        station_drafts.save(draft['id'], save_data(None))
    with pytest.raises(ValueError, match='heard'):
        station_drafts.save(draft['id'], save_data(None, audible_confirmed=False))
    assert favorites.stations() == []


def test_test_reuses_quiet_volume_and_existing_session_stop(rig):
    _, calls = rig
    draft_id, _ = started()
    assert calls == [('play', 'Bedroom', draft_id, 5, True)]
    assert station_drafts.status(draft_id)['can_save'] is False


def test_confirmed_stop_and_audible_assertion_save_without_new_playback(rig):
    _, calls = rig
    draft_id, operation_id = completed(rig)
    assert station_drafts.status(draft_id)['can_save'] is True
    before_calls = copy.deepcopy(calls)
    saved = station_drafts.save(draft_id, save_data(operation_id))
    assert saved['name'] == 'Saved name' and saved['url'] == URL
    assert favorites.stations() == [saved]
    assert calls == before_calls
    assert station_drafts.status(draft_id)['can_save'] is False
    # A lost Save response is safe to repeat without duplicating station records.
    assert station_drafts.save(draft_id, save_data(operation_id)) == saved


def test_changed_url_requires_new_test_and_keeps_original_form(rig):
    draft_id, operation_id = completed(rig)
    with pytest.raises(ValueError, match='URL changed'):
        station_drafts.save(draft_id, save_data(operation_id, url='https://other.example/live'))
    assert station_drafts.status(draft_id)['draft']['url'] == URL
    assert favorites.stations() == []


@pytest.mark.parametrize('reason', ['radio_recovery_canceled_no_speaker_command',
                                   'radio_stop_readback_unknown', 'arbitrary'])
def test_unverified_stop_reason_cannot_enable_save(rig, reason):
    draft_id, operation_id = completed(rig, reason)
    assert station_drafts.status(draft_id)['can_save'] is False
    with pytest.raises(ValueError, match='verified Stop'):
        station_drafts.save(draft_id, save_data(operation_id))


def test_unknown_stop_retains_draft_and_blocks_save(rig):
    current, _ = rig
    draft_id, operation_id = completed(rig)
    current['Bedroom'].update(state='unknown', reason='radio_stop_readback_unknown')
    assert station_drafts.status(draft_id)['can_save'] is False
    with pytest.raises(ValueError, match='verified Stop'):
        station_drafts.save(draft_id, save_data(operation_id))
    assert station_drafts.status(draft_id)['draft']['name'] == 'Test station'


def test_stale_stop_never_dispatches_to_replacement_session(rig):
    current, calls = rig
    draft_id, operation_id = started()
    current['Bedroom'].update(state='playing', terminal=True)
    station_drafts.status(draft_id)
    current['Bedroom'].update(operation_id='new-owner')
    with pytest.raises(ValueError, match='no longer current'):
        station_drafts.stop(draft_id, {'speaker_id': 'ABC', 'operation_id': operation_id})
    assert len(calls) == 1
    assert station_drafts.status(draft_id)['can_save'] is False


def test_wrong_operation_and_speaker_never_save(rig):
    draft_id, operation_id = completed(rig)
    with pytest.raises(ValueError, match='verified Stop'):
        station_drafts.save(draft_id, save_data('another-test'))
    with pytest.raises(ValueError, match='current reported-playing'):
        station_drafts.stop(draft_id, {'speaker_id': 'OTHER', 'operation_id': operation_id})


def test_unavailable_readiness_preserves_draft_without_operation(rig, monkeypatch):
    _, calls = rig
    draft = station_drafts.create('Draft', URL)
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing', lambda *a, **k: {})
    monkeypatch.setattr(station_drafts.radio_relay, 'readiness',
                        lambda *a: {'available': False, 'reason': 'Native source unavailable'})
    with pytest.raises(ValueError, match='Native source unavailable'):
        station_drafts.test(draft['id'], {'speaker': 'Bedroom', 'speaker_id': 'ABC', 'confirmed': True})
    assert not calls
    assert station_drafts.station(draft['id'])['url'] == URL


def test_worker_unavailable_does_not_claim_accepted_test(rig, monkeypatch):
    draft = station_drafts.create('Draft', URL)
    monkeypatch.setattr(jobs, 'queue_station', lambda *a, **kw: None)
    with pytest.raises(jobs.StationWorkerUnavailable):
        station_drafts.test(draft['id'], {'speaker': 'Bedroom', 'speaker_id': 'ABC', 'confirmed': True})
    assert station_drafts.status(draft['id'])['draft']['state'] == 'untested'


def test_active_or_unknown_test_cannot_switch_target_or_retry_blindly(rig):
    current, calls = rig
    draft_id, _ = started()
    current['Bedroom'].update(state='unknown', terminal=True)
    with pytest.raises(ValueError, match='Check or stop'):
        station_drafts.test(draft_id, {'speaker': 'Other', 'speaker_id': 'ABC', 'confirmed': True})
    assert len(calls) == 1


def test_draft_capacity_never_evicts_live_descriptors(rig, monkeypatch):
    monkeypatch.setattr(station_drafts, 'MAX_DRAFTS', 1)
    first = station_drafts.create('First', URL)
    with pytest.raises(ValueError, match='retained'):
        station_drafts.create('Second', 'https://other.example/live')
    assert station_drafts.station(first['id'])['name'] == 'First'


def test_api_new_draft_test_stop_save_contract(rig):
    current, _ = rig
    app = Flask(__name__)
    app.register_blueprint(station_drafts_bp)
    client = app.test_client()
    draft = client.post('/api/station-drafts', json={'name': 'UI draft', 'url': URL}).json['draft']
    prefix = '/api/station-drafts/' + draft['id']
    assert client.post(prefix + '/save', json=save_data(None)).status_code == 400
    result = client.post(prefix + '/test', json={'speaker': 'Bedroom', 'speaker_id': 'ABC', 'confirmed': True})
    assert result.status_code == 202
    operation_id = result.json['operation']['operation_id']
    current['Bedroom'].update(state='playing', terminal=True)
    assert client.post(prefix + '/stop', json={'speaker_id': 'ABC', 'operation_id': operation_id}).status_code == 202
    current['Bedroom'].update(state='completed', reason='radio_stopped_verified', terminal=True)
    assert client.get(prefix).json['can_save'] is True
    assert client.post(prefix + '/save', json=save_data(operation_id)).status_code == 201


def test_api_rejects_cross_site_draft_writes(rig):
    app = Flask(__name__)
    app.register_blueprint(station_drafts_bp)
    response = app.test_client().post('/api/station-drafts', json={'name': 'Draft', 'url': URL},
                                      headers={'Sec-Fetch-Site': 'cross-site'})
    assert response.status_code == 400
    assert station_drafts._drafts == {}


def test_unknown_stop_check_can_confirm_standby_without_new_write(rig, monkeypatch):
    current, calls = rig
    draft_id, operation_id = completed(rig)
    current['Bedroom'].update(state='unknown', reason='command_not_confirmed')
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing',
                        lambda *a, **k: {'device_id': 'ABC', 'source_type': 'STANDBY',
                                         'status': 'Standby', 'observed_at': time.time()})
    count = len(calls)
    assert station_drafts.status(draft_id)['can_save'] is True
    assert len(calls) == count
    assert station_drafts.save(draft_id, save_data(operation_id))['url'] == URL


def test_unknown_stop_check_rejects_replacement_during_read(rig, monkeypatch):
    current, _ = rig
    draft_id, _ = completed(rig)
    current['Bedroom'].update(state='unknown', reason='command_not_confirmed')
    def read(*a, **k):
        current['Bedroom']['operation_id'] = 'replacement'
        return {'device_id': 'ABC', 'source_type': 'STANDBY', 'status': 'Standby', 'observed_at': time.time()}
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing', read)
    assert station_drafts.status(draft_id)['can_save'] is False


def test_unknown_test_checked_standby_allows_explicit_retry_without_save_evidence(rig, monkeypatch):
    current, calls = rig
    draft_id, _ = started()
    current['Bedroom'].update(state='unknown', terminal=True)
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing',
                        lambda *a, **k: {'device_id': 'ABC', 'source_type': 'STANDBY',
                                         'status': 'Standby', 'observed_at': time.time()})
    count = len(calls)
    checked = station_drafts.status(draft_id)
    assert checked['draft']['retry_ready'] is True
    assert checked['can_save'] is False
    assert len(calls) == count
    result = station_drafts.test(draft_id, {'speaker': 'Bedroom', 'speaker_id': 'ABC', 'confirmed': True})
    assert result['state'] == 'accepted'
    assert len(calls) == count + 1
    assert result['draft']['retry_ready'] is False


def test_stale_standby_does_not_confirm_unknown_stop(rig, monkeypatch):
    current, _ = rig
    draft_id, _ = completed(rig)
    current['Bedroom'].update(state='unknown', reason='command_not_confirmed')
    monkeypatch.setattr(station_drafts.speaker_status, 'get_now_playing',
                        lambda *a, **k: {'device_id': 'ABC', 'source_type': 'STANDBY',
                                         'status': 'Standby', 'observed_at': time.time() - 30})
    assert station_drafts.status(draft_id)['can_save'] is False


def test_real_native_unknown_reconciliation_enables_exact_stop_then_save(rig, monkeypatch):
    playback.reset()
    try:
        draft = station_drafts.create('Recovered native', URL)
        op = playback.begin('Bedroom', device_id='ABC')
        expected = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'http://wisp.example/draft'}
        op['expected'] = expected
        op['outcome'].update(state='unknown', terminal=True, speaker_id='ABC',
                             station_id=draft['id'], listening_session=True, radio_mode='native')
        playback._device_owners['ABC'] = op
        station_drafts._drafts[draft['id']].update(speaker='Bedroom', speaker_id='ABC',
                                                 operation_id=op['outcome']['operation_id'])
        monkeypatch.setattr(playback, 'last', lambda speaker: copy.deepcopy(playback._operations[speaker]['outcome']))
        monkeypatch.setattr(playback, 'reconcile_station_session', REAL_RECONCILE)
        monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a: dict(DEVICE))
        monkeypatch.setattr(playback.status, 'get_device_id', lambda *a, **k: 'ABC')
        monkeypatch.setattr(playback.status, 'get_now_playing',
                            lambda *a, **k: {'device_id': 'ABC', 'status': 'Playing',
                                             'source_type': 'LOCAL_INTERNET_RADIO',
                                             'content_identity': expected, 'observed_at': time.time()})
        checked = station_drafts.status(draft['id'])
        assert checked['draft']['observed_playing'] is True
        assert checked['operation']['state'] == 'playing'
        assert checked['can_save'] is False
        def queue_stop(speaker, speaker_id, station_id, operation_id):
            stopped = playback.begin_station_stop(speaker, speaker_id, station_id, operation_id)
            return copy.deepcopy(stopped['outcome']) if stopped else None
        monkeypatch.setattr(jobs, 'queue_station_stop', queue_stop)
        station_drafts.stop(draft['id'], {'speaker_id': 'ABC', 'operation_id': op['outcome']['operation_id']})
        stop_op = playback._operations['Bedroom']
        stop_op['outcome'].update(state='completed', reason='radio_stopped_verified', terminal=True)
        assert station_drafts.status(draft['id'])['can_save'] is True
        saved = station_drafts.save(draft['id'], save_data(op['outcome']['operation_id']))
        assert saved['url'] == URL
    finally:
        playback.reset()


def test_draft_operation_status_excludes_private_engine_evidence(rig):
    current, _ = rig
    draft_id, _ = started()
    current['Bedroom'].update(location='opaque-private', relay_token='secret',
                              content_identity={'sourceAccount': 'account'})
    operation = station_drafts.status(draft_id)['operation']
    assert operation['operation_id']
    assert 'location' not in operation and 'relay_token' not in operation
    assert 'content_identity' not in operation


def test_saved_quiet_test_keeps_diagnostic_volume_and_supports_exact_stop(monkeypatch, tmp_path):
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    favorites._save({'version': 1, 'favorites': {}, 'station_seed_version': 1})
    saved = favorites.add_station('Saved radio', URL)
    monkeypatch.setattr(favorites, 'device', lambda *a: dict(DEVICE))
    monkeypatch.setattr(station_drafts.radio_relay, 'readiness',
                        lambda *a: {'available': True, 'mode': 'native'})
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    submitted = []
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: submitted.append(a) or True)
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    client = app.test_client()
    prefix = '/api/Bedroom/stations/' + saved['id']
    playback.reset()
    try:
        result = client.post(prefix + '/test', json={'confirmed': True})
        assert result.status_code == 202
        original = result.json['operation']
        assert original['target_volume'] == 5
        assert original['radio_request_intent'] == 'quiet_test'
        assert original['listening_session'] is True
        assert submitted[0][1] is playback.run_on
        assert submitted[0][4] == 5
        # No worker or device request runs in this fixture. Supply native evidence
        # to exercise the real exact-session ownership transfer used by the API.
        op = playback._operations['Bedroom']
        op['expected'] = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'native-location'}
        op['outcome'].update(state='playing', terminal=True, radio_mode='native')
        stopped = client.post(prefix + '/stop', json={'speaker_id': 'ABC',
                                                       'operation_id': original['operation_id']})
        assert stopped.status_code == 202
        assert stopped.json['operation']['stops_operation_id'] == original['operation_id']
        assert len(submitted) == 2
        # The previous quiet-test Stop cannot transfer or stop a replacement owner.
        assert client.post(prefix + '/stop', json={'speaker_id': 'ABC',
                                                     'operation_id': original['operation_id']}).status_code == 409
    finally:
        playback.reset()
