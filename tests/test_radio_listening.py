"""Everyday listening contracts. All transport and storage use isolated fixtures."""
import pytest
from flask import Flask

from app.api import favorites as api
from app.core import playback, favorites
from app.scheduler import jobs
from tests.test_direct_radio import device as device  # noqa: F401
from tests.test_radio_relay import radio as radio, start  # noqa: F401

QUEUE_STATION = jobs.queue_station


@pytest.mark.parametrize(('first_volume', 'first_listening', 'identity', 'station', 'volume', 'intent'), [
    (5, False, 'ABC', 'station', 23, True),
    (5, False, 'ABC', 'station', 5, True),
    (23, True, 'ABC', 'station', 23, False),
    (23, True, 'ABC', 'station', 24, True),
    (23, True, 'OTHER', 'station', 23, True),
    (23, True, 'ABC', 'different', 23, True),
])
def test_conflicting_pending_station_request_preserves_original(
        monkeypatch, first_volume, first_listening, identity, station, volume, intent):
    playback.reset()
    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: calls.append(a) or True)
    original = jobs.queue_station('Room', 'ABC', 'station', first_volume, listening=first_listening)
    with pytest.raises(jobs.StationRequestConflict, match='still starting or stopping'):
        jobs.queue_station('Room', identity, station, volume, listening=intent)
    assert len(calls) == 1
    assert playback.current(calls[0][2])
    assert playback.last('Room') == original
    playback.reset()


def test_equivalent_pending_station_request_is_reused(monkeypatch):
    playback.reset()
    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: calls.append(a) or True)
    first = jobs.queue_station('Room', 'ABC', 'station', 23, listening=True)
    second = jobs.queue_station('Room', 'ABC', 'station', 23, listening=True)
    assert first == second and len(calls) == 1
    playback.reset()


@pytest.mark.parametrize('direct_first', [False, True])
def test_direct_diagnostic_conflicts_with_other_pending_radio_intent(monkeypatch, direct_first):
    playback.reset()
    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: calls.append(a) or True)
    if direct_first:
        original = jobs.queue_direct_radio_test(
            'Room', 'ABC', 'station', 'https://example.com/live.mp3')
        def conflicting():
            return jobs.queue_station('Room', 'ABC', 'station', 5, listening=False)
    else:
        original = jobs.queue_station('Room', 'ABC', 'station', 23, listening=True)
        def conflicting():
            return jobs.queue_direct_radio_test(
                'Room', 'ABC', 'station', 'https://example.com/live.mp3')
    with pytest.raises(jobs.StationRequestConflict, match='still starting or stopping'):
        conflicting()
    assert len(calls) == 1
    assert playback.last('Room') == original
    playback.reset()


def test_stop_submission_failure_preserves_current_listening_owner(monkeypatch):
    playback.reset()
    old = playback.begin('Room', 'Station station', 'ABC')
    old['expected'] = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'station-url'}
    old['outcome'].update(state='playing', terminal=True, radio_mode='native',
                           listening_session=True, station_id='station', speaker_id='ABC')
    before = playback.last('Room')
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: False)
    with pytest.raises(jobs.StationWorkerUnavailable):
        jobs.queue_station_stop('Room', 'ABC', 'station', old['outcome']['operation_id'])
    assert playback.current(old)
    assert playback.last('Room') == before
    playback.reset()


def test_stop_worker_is_reserved_before_ownership_transfer(monkeypatch):
    playback.reset()
    old = playback.begin('Room', 'Station station', 'ABC')
    old['expected'] = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'station-url'}
    old['outcome'].update(state='playing', terminal=True, radio_mode='native',
                           listening_session=True, station_id='station', speaker_id='ABC')
    submitted = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: submitted.append(a) or True)
    result = jobs.queue_station_stop(
        'Room', 'ABC', 'station', old['outcome']['operation_id'])
    assert result is not None and result['stops_operation_id'] == old['outcome']['operation_id']
    assert submitted[0][0] is jobs._run_reserved_station_stop
    ready, holder = submitted[0][1:]
    assert ready.is_set() and holder['operation']['outcome']['operation_id'] == result['operation_id']
    playback.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(favorites, 'station', lambda *_: {'url': 'https://example.com/live.mp3'})
    monkeypatch.setattr(favorites, 'device', lambda *_: {'ip': 'fake', 'device_id': 'ABC'})
    monkeypatch.setattr(api.jobs, 'queue_station', lambda *a, **kw: {'state': 'accepted', 'volume': a[3]})
    from app.core import radio_relay, status
    monkeypatch.setattr(radio_relay, 'readiness', lambda *_: {'available': True, 'mode': 'relay'})
    monkeypatch.setattr(status, 'get_volume', lambda *_: 19)
    app = Flask(__name__)
    app.register_blueprint(api.favorites_bp)
    return app.test_client()


@pytest.mark.parametrize('volume', [None, True, -1, 101, 1.5, '25'])
def test_bad_listening_volume_cannot_queue_or_cancel(client, monkeypatch, volume):
    monkeypatch.setattr(jobs, 'queue_station', lambda *a, **kw: pytest.fail('must not queue'))
    response = client.post('/api/Room/stations/id/play', json={
        'confirmed': True, 'speaker_id': 'ABC', 'volume': volume})
    assert response.status_code == 400
    assert 'listening volume' in response.json['error']


@pytest.mark.parametrize('volume', [0, 18, 100])
def test_explicit_volume_reaches_production_queue(client, volume):
    response = client.post('/api/Room/stations/id/play', json={
        'confirmed': True, 'speaker_id': 'ABC', 'volume': volume})
    assert response.status_code == 202
    assert response.json['operation']['volume'] == volume


def test_changed_selected_identity_cannot_start(client, monkeypatch):
    monkeypatch.setattr(jobs, 'queue_station', lambda *a, **kw: pytest.fail('must not queue'))
    assert client.post('/api/Room/stations/id/play', json={
        'confirmed': True, 'speaker_id': 'OTHER', 'volume': 20}).status_code == 400


def test_fresh_volume_options_and_unavailable_volume(client, monkeypatch):
    from app.core import status
    response = client.get('/api/Room/stations/id/listening-options')
    assert response.json['volume'] == 19
    assert response.json['speaker_id'] == 'ABC'
    assert response.headers['Cache-Control'] == 'no-store'
    monkeypatch.setattr(status, 'get_volume', lambda *_: None)
    assert client.get('/api/Room/stations/id/listening-options').json['volume'] is None


def test_quiet_test_remains_fixed_volume_without_listening_intent(client, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, 'queue_station', lambda *a, **kw: calls.append((a, kw)) or {})
    assert client.post('/api/Room/stations/id/test', json={'confirmed': True, 'volume': 90}).status_code == 202
    assert calls == [(('Room', 'ABC', 'id', 5), {'listening': False})]


def test_pending_quiet_test_then_normal_play_returns_conflict(client, monkeypatch):
    playback.reset()
    monkeypatch.setattr(jobs, 'queue_station', QUEUE_STATION)
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    calls = []
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: calls.append(a) or True)
    test = client.post('/api/Room/stations/id/test', json={'confirmed': True})
    assert test.status_code == 202
    normal = client.post('/api/Room/stations/id/play', json={
        'confirmed': True, 'speaker_id': 'ABC', 'volume': 23})
    assert normal.status_code == 409
    assert 'still starting or stopping' in normal.json['error']
    assert len(calls) == 1 and playback.current(calls[0][2])
    playback.reset()


def test_direct_diagnostic_conflict_is_reported_as_http_409(client, monkeypatch):
    from app.core import radio_stream
    monkeypatch.setattr(radio_stream, 'candidate', lambda value: value)
    monkeypatch.setattr(
        jobs, 'queue_direct_radio_test',
        lambda *a: (_ for _ in ()).throw(jobs.StationRequestConflict('radio request pending')))
    response = client.post('/api/Room/stations/id/direct-test', json={
        'confirmed': True, 'accept_startup_volume_risk': True})
    assert response.status_code == 409
    assert response.json == {'error': 'radio request pending'}


def test_stop_api_passes_exact_session_and_reports_stale(client, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, 'queue_station_stop', lambda *a: calls.append(a))
    result = client.post('/api/Room/stations/id/stop', json={'speaker_id': 'ABC', 'operation_id': 'old'})
    assert result.status_code == 409
    assert calls == [('Room', 'ABC', 'id', 'old')]


def test_stop_api_reports_worker_unavailable_without_claiming_stale(client, monkeypatch):
    monkeypatch.setattr(
        jobs, 'queue_station_stop',
        lambda *a: (_ for _ in ()).throw(jobs.StationWorkerUnavailable()))
    result = client.post(
        '/api/Room/stations/id/stop', json={'speaker_id': 'ABC', 'operation_id': 'current'})
    assert result.status_code == 503
    assert result.json == {'error': 'Playback worker unavailable. No stop request was accepted.'}


def listening(name='A', station='station', volume=23):
    op = start(name, 'Station ' + station, station, volume)
    op['outcome'].update(listening_session=True, speaker_id=name)
    return op


def test_listening_relay_stays_live_and_stop_is_scoped(device, radio):
    from app.core import radio_relay
    a = listening('A', 'one')
    b = listening('B', 'two', 17)
    assert a['outcome']['state'] == b['outcome']['state'] == 'playing'
    assert device[0]('A')['volume'] == 23
    old = radio_relay.for_device('A')
    other = radio_relay.for_device('B')
    assert next(radio[1][0][0]) == b'MP3 audio'
    stop = playback.begin_station_stop('A', 'A', 'one', a['outcome']['operation_id'])
    assert stop is not None
    playback.run_station_stop(stop)
    assert stop['outcome']['state'] == 'completed'
    assert old['closed'].is_set() and not other['closed'].is_set()
    assert device[0]('B')['volume'] == 17
    assert ('A', 'Stop') in device[1]
    assert not any('power' in str(call).lower() for call in device[1])


def test_relay_disconnect_during_stop_defers_to_fresh_stop_readback(
        device, radio, monkeypatch):
    from app.core import direct_radio, radio_relay
    old = listening()
    session = radio_relay.for_device('A')
    stop = playback.begin_station_stop('A', 'A', 'station', old['outcome']['operation_id'])
    original = direct_radio._soap

    def soap(ip, action, timeout, **kwargs):
        result = original(ip, action, timeout, **kwargs)
        if action == 'Stop':
            radio_relay.close(session, 'radio_client_disconnected')
        return result

    monkeypatch.setattr(direct_radio, '_soap', soap)
    playback.run_station_stop(stop)
    assert stop['outcome']['state'] == 'completed'
    assert stop['outcome']['reason'] == 'radio_stop_acknowledged_source_inactive'
    assert stop['outcome']['relay_active'] is False


def test_stale_stop_does_not_cancel_new_owner(device, radio):
    old = listening()
    newer = playback.begin('A', 'newer', 'A')
    calls = list(device[1])
    assert playback.begin_station_stop('A', 'A', 'station', old['outcome']['operation_id']) is None
    assert playback.current(newer)
    assert calls == device[1]


def test_queued_stop_cannot_touch_replacement(device, radio):
    old = listening()
    stop = playback.begin_station_stop('A', 'A', 'station', old['outcome']['operation_id'])
    newer = playback.begin('A', 'newer', 'A')
    calls = list(device[1])
    playback.run_station_stop(stop)
    assert playback.current(newer) and device[1] == calls


def test_wrong_station_or_device_cannot_cancel_session(device, radio):
    old = listening()
    for identity, station in [('B', 'station'), ('A', 'other')]:
        assert playback.begin_station_stop('A', identity, station, old['outcome']['operation_id']) is None
    assert playback.current(old)


def test_relay_takeover_prevents_stop_command(device, radio):
    old = listening()
    stop = playback.begin_station_stop('A', 'A', 'station', old['outcome']['operation_id'])
    device[0]('A')['uri'] = 'https://replacement.example/stream'
    calls = list(device[1])
    playback.run_station_stop(stop)
    assert device[1] == calls
    assert stop['outcome']['state'] != 'completed'


@pytest.mark.parametrize('takeover', [False, True])
def test_native_stop_uses_stop_not_power_and_refuses_other_content(monkeypatch, takeover):
    import time
    playback.reset()
    content = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'station-url'}
    state = {'device_id': 'ABC', 'status': 'Playing', 'source_type': 'LOCAL_INTERNET_RADIO',
             'content_identity': dict(content)}
    monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a: {'ip': 'fake', 'device_id': 'ABC'})
    monkeypatch.setattr(playback.status, 'get_device_id', lambda *a, **kw: 'ABC')
    monkeypatch.setattr(playback.status, 'get_now_playing', lambda *a, **kw: dict(state, observed_at=time.time()))
    monkeypatch.setattr(playback.status, 'get_volume', lambda *a, **kw: 29)
    monkeypatch.setattr(playback.control, 'power_action', lambda *a, **kw: pytest.fail('must never toggle power'))
    calls = []
    def stop(*a, **kw):
        calls.append('STOP')
        state['status'] = 'Stopped'
        return True
    monkeypatch.setattr(playback.control, 'stop_action', stop)
    old = playback.begin('Room', 'Station station', 'ABC')
    old['expected'] = content
    old['outcome'].update(state='playing', terminal=True, radio_mode='native',
                           listening_session=True, station_id='station')
    chosen = playback.begin_station_stop('Room', 'ABC', 'station', old['outcome']['operation_id'])
    if takeover:
        state['content_identity'] = {'source': 'LOCAL_INTERNET_RADIO', 'location': 'other'}
    playback.run_station_stop(chosen)
    assert calls == ([] if takeover else ['STOP'])
    assert chosen['outcome']['state'] == ('canceled' if takeover else 'completed')
    playback.reset()


@pytest.mark.parametrize(('resolved', 'live', 'message'), [
    ({'ip': 'fake', 'device_id': ''}, 'ABC', 'Refresh the speaker list'),
    ({'ip': 'fake', 'device_id': 'ABC'}, None, 'did not answer identity verification'),
    ({'ip': 'fake', 'device_id': 'ABC'}, 'OTHER', 'identity changed'),
])
def test_identity_failures_are_distinct(monkeypatch, resolved, live, message):
    monkeypatch.setattr(favorites.discovery, 'resolve_device', lambda *a: resolved)
    monkeypatch.setattr(favorites.status, 'get_device_id', lambda *a: live)
    with pytest.raises(ValueError, match=message):
        favorites.device('Room')
