"""Isolated operation contracts; never start discovery or real speaker transport."""
from unittest.mock import Mock

import pytest

from app.core import playback

REAL_WAIT = playback.wait


@pytest.fixture
def device(monkeypatch):
    playback.reset()
    monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a, **k: {
        'name': 'Room', 'ip': 'fake', 'device_id': 'ABC'})
    monkeypatch.setattr(playback.status, 'get_device_id', lambda _, **kw: 'ABC')
    monkeypatch.setattr(playback.status, 'get_preset_identity', lambda *a, **kw: {
        'source': 'STORED_MUSIC', 'sourceAccount': 'server', 'location': 'album/1'})
    state = {'status': 'Standby', 'source_type': 'STANDBY', 'device_id': 'ABC'}
    volume = [15]
    calls = []
    def observe(_, **kw):
        return dict(state, observed_at=playback.time.time())
    def set_volume(_, value, **kw):
        calls.append(('volume', value))
        volume[0] = value
        return True
    def select(*_, **kw):
        calls.append(('preset', 1))
        state.update(status='Playing', source_type='STORED_MUSIC',
                     content_identity={'source': 'STORED_MUSIC',
                     'sourceAccount': 'server', 'location': 'album/1'})
        return True
    monkeypatch.setattr(playback.status, 'get_now_playing', observe)
    monkeypatch.setattr(playback.status, 'get_volume', lambda _, **kw: volume[0])
    monkeypatch.setattr(playback.control, 'set_volume', set_volume)
    monkeypatch.setattr(playback.control, 'play_preset', select)
    monkeypatch.setattr(playback.control, 'power_action', lambda _, **kw: calls.append(('power', 1)) or True)
    monkeypatch.setattr(playback, 'wait', lambda op, delay: playback.current(op))
    return state, volume, calls


def test_quiet_before_selection_and_verified_nas_fade(device):
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3, fade_in_duration=0)
    assert device[2][0] == ('volume', 0)
    assert ('preset', 1) in device[2]
    assert device[2][-1] == ('volume', 3)
    assert playback.last('Room')['state'] == 'playing'
    assert playback.last('Room')['audible_confirmed'] is False


@pytest.mark.parametrize('state', ['OFFLINE', 'Unknown'])
def test_unknown_never_blind_power(device, state):
    device[0]['status'] = state
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3)
    assert device[2] == []
    assert playback.last('Room')['state'] == 'unknown'


def test_polite_active_skips(device):
    device[0]['status'] = 'Playing'
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3)
    assert device[2] == []
    assert playback.last('Room')['state'] == 'skipped'


def test_selection_failure_no_fade_or_retry(device, monkeypatch):
    select = Mock(return_value=False)
    monkeypatch.setattr(playback.control, 'play_preset', select)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3)
    assert select.call_count == 1
    assert device[2] == [('volume', 0)]
    assert playback.last('Room')['state'] == 'unknown'


def test_cancel_queued_operation_prevents_all_writes(device):
    op = playback.begin('Room', 'Morning')
    playback.cancel('Room')
    playback.run_on(op, preset=1, volume=3)
    assert not device[2]
    assert playback.last('Room')['state'] == 'canceled'


def test_manual_change_during_fade_cancels(device, monkeypatch):
    def wait(op, delay):
        device[1][0] = 7
        return playback.current(op)
    monkeypatch.setattr(playback, 'wait', wait)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3, fade_in_duration=3)
    assert ('volume', 1) not in device[2]
    assert playback.last('Room')['state'] == 'canceled'


@pytest.mark.parametrize('observed', ['Buffering', 'Playing'])
def test_buffering_or_wrong_content_never_fades(device, monkeypatch, observed):
    clock = [0.0]
    monkeypatch.setattr(playback.time, 'monotonic', lambda: clock[0])
    def select(*_, **kw):
        device[0].update(status=observed, source_type='STORED_MUSIC',
                         content_identity={'source': 'STORED_MUSIC', 'location': 'wrong'})
        return True
    def advance(op, delay):
        clock[0] += 1
        return playback.current(op)
    monkeypatch.setattr(playback.control, 'play_preset', select)
    monkeypatch.setattr(playback, 'wait', advance)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 10)
    assert device[2] == [('volume', 0)]
    assert playback.last('Room')['state'] == 'unknown'
    assert clock[0] <= playback.START_DEADLINE_SECONDS


def test_run_now_can_replace_active_audio(device):
    device[0]['status'] = 'Playing'
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 2, fade_in_duration=0, force=True)
    assert playback.last('Room')['state'] == 'playing'
    assert device[2] == [('volume', 0), ('preset', 1), ('volume', 2)]


def test_unknown_preset_keeps_existing_volume(device, monkeypatch):
    monkeypatch.setattr(playback.status, 'get_preset_identity', lambda *_, **kw: None)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 10)
    assert not device[2]
    assert playback.last('Room')['reason'] == 'preset_identity_unavailable'


def test_volume_write_failure_never_reports_playing(device, monkeypatch):
    monkeypatch.setattr(playback.control, 'set_volume', lambda *_, **kw: False)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 10)
    assert not device[2]
    assert playback.last('Room')['state'] == 'unknown'


def test_identity_changed_no_commands(device, monkeypatch):
    monkeypatch.setattr(playback.status, 'get_device_id', lambda _, **kw: 'OTHER')
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 10)
    assert not device[2]
    assert playback.last('Room')['state'] == 'unknown'


def test_queued_supersession_never_replays(device):
    old = playback.begin('Room', 'Old')
    new = playback.begin('Room', 'New')
    playback.run_on(old, 1, 10)
    assert not device[2]
    assert playback.last('Room')['operation_id'] == new['outcome']['operation_id']


def test_off_stops_manually_started_audio_without_prior_wisp_session(device, monkeypatch):
    device[0].update(status='Playing', source_type='AUX', content_identity={'source': 'AUX'})
    def power(_, **kw):
        device[2].append(('power', 1))
        device[0].update(status='Standby', source_type='STANDBY')
        return True
    monkeypatch.setattr(playback.control, 'power_action', power)
    op = playback.begin('Room', 'Evening')
    playback.run_off(op, fade_out_duration=0)
    assert device[2] == [('power', 1)]
    assert playback.last('Room')['reason'] == 'speaker_reported_standby'


def test_off_fade_stops_after_physical_override(device, monkeypatch):
    device[0].update(status='Playing', source_type='AUX', content_identity={'source': 'AUX'})
    def change_source(op, delay):
        device[0].update(source_type='BLUETOOTH', content_identity={'source': 'BLUETOOTH'})
        return playback.current(op)
    monkeypatch.setattr(playback, 'wait', change_source)
    op = playback.begin('Room', 'Evening')
    playback.run_off(op, fade_out_duration=1)
    assert not device[2]
    assert playback.last('Room')['state'] == 'canceled'


def test_websocket_event_wakes_reconciliation_without_trusting_old_echo(device):
    op = playback.begin('Room', 'Morning')
    op['expected'] = {'source': 'AUX'}
    op['verified'] = True
    op['expected_volume'] = 0
    playback.observe_external('Room', {'volume': 9})
    assert op['changed'].is_set()
    assert not op['canceled'].is_set()


class ClockEvent:
    def __init__(self, clock, action=None):
        self.clock = clock
        self.action = action
        self.flag = False
        self.waits = []

    def wait(self, duration):
        self.waits.append(duration)
        if not self.flag:
            self.clock[0] += duration
        if self.action:
            self.action()
        return self.flag

    def set(self):
        self.flag = True

    def clear(self):
        self.flag = False

    def is_set(self):
        return self.flag


def test_real_wait_polls_at_bounded_cadence_and_cancels(device, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(playback.time, 'monotonic', lambda: clock[0])
    op = playback.begin('Room', 'Morning')
    playback._resolve(op)
    op['verified'] = True
    op['expected'] = {'source': 'AUX'}
    op['expected_volume'] = 15
    device[0].update(status='Playing', source_type='AUX')
    op['changed'] = ClockEvent(clock)
    assert REAL_WAIT(op, 5)
    assert op['changed'].waits == [5]
    op['changed'].action = lambda: device[1].__setitem__(0, 8)
    assert not REAL_WAIT(op, 20)
    assert clock[0] == 10
    assert playback.last('Room')['state'] == 'canceled'
    assert not device[2]


def test_stale_volume_notification_reconciles_current_volume(device, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(playback.time, 'monotonic', lambda: clock[0])
    op = playback.begin('Room', 'Morning')
    playback._resolve(op)
    op['verified'] = True
    op['expected'] = {'source': 'AUX'}
    op['expected_volume'] = 15
    device[0].update(status='Playing', source_type='AUX')
    op['changed'] = ClockEvent(clock)
    playback.observe_external('Room', {'volume': 2})
    assert REAL_WAIT(op, 1)
    assert playback.current(op)
    assert playback.last('Room')['state'] == 'accepted'


def test_cancel_before_dispatch_reservation_prevents_write(device, monkeypatch):
    op = playback.begin('Room')
    playback._resolve(op)
    def address(*args, **kwargs):
        playback.cancel('Room')
        return 'fake'
    monkeypatch.setattr(playback, '_address', address)
    called = []
    assert not playback._write(op, lambda ip: called.append(ip) or True)
    assert called == []


def test_cancel_after_reservation_allows_only_inflight_command(device):
    op = playback.begin('Room')
    playback._resolve(op)
    called = []
    def command(ip):
        assert playback.last('Room')['in_flight']
        playback.cancel('Room')
        called.append(ip)
        return True
    assert not playback._write(op, command)
    assert not playback._write(op, command)
    assert called == ['fake']
    assert not playback.last('Room')['in_flight']
    assert playback.last('Room')['state'] == 'canceled'


def test_off_own_standby_event_is_completion_not_override(device, monkeypatch):
    device[0].update(status='Playing', source_type='AUX', content_identity={'source': 'AUX'})
    def power(ip, **kwargs):
        device[0].update(status='Standby', source_type='STANDBY')
        playback.observe_external('Room', dict(device[0]))
        return True
    monkeypatch.setattr(playback.control, 'power_action', power)
    op = playback.begin('Room')
    playback.run_off(op, 0)
    assert playback.last('Room')['state'] == 'completed'
    assert not op['canceled'].is_set()


def test_terminal_history_not_changed_by_later_manual_activity(device):
    op = playback.begin('Room')
    playback.run_on(op, 1, 2, fade_in_duration=0)
    original = playback.last('Room')
    playback.observe_external('Room', {'volume': 88})
    playback.cancel('Room')
    assert playback.last('Room') == original


def test_identity_read_exhausting_deadline_prevents_command(device, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(playback.time, 'monotonic', lambda: clock[0])
    op = playback.begin('Room')
    playback._resolve(op)
    def slow_identity(ip, **kwargs):
        clock[0] = playback.START_DEADLINE_SECONDS + 1
        return 'ABC'
    monkeypatch.setattr(playback.status, 'get_device_id', slow_identity)
    called = []
    assert not playback._write(op, lambda ip: called.append(ip) or True)
    assert not called
    assert playback.last('Room')['reason'] == 'operation_deadline'


def test_manual_resolves_again_inside_lock(device, monkeypatch):
    addresses = iter(['old', 'new'])
    monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a, **kw: {
        'name': 'Room', 'ip': next(addresses), 'device_id': 'ABC'})
    called = []
    assert playback.manual('Room', lambda ip: called.append(ip) or True)
    assert called == ['new']


@pytest.mark.parametrize('state', ['Error', 'Invalid', 'Idle', 'garbage'])
@pytest.mark.parametrize('mode', ['on', 'off'])
def test_unrecognized_transport_state_never_authorizes_write(device, state, mode):
    device[0]['status'] = state
    op = playback.begin('Room')
    if mode == 'on':
        playback.run_on(op, 1, 10, force=True)
    else:
        playback.run_off(op, 0)
    assert not device[2]
    assert playback.last('Room')['state'] == 'unknown'


def test_scheduled_on_stays_polite_if_manual_audio_starts_during_preset_read(device, monkeypatch):
    def preset(ip, number, **kwargs):
        device[0]['status'] = 'Playing'
        return {'source': 'STORED_MUSIC', 'location': 'album/1'}
    monkeypatch.setattr(playback.status, 'get_preset_identity', preset)
    op = playback.begin('Room')
    playback.run_on(op, 1, 10)
    assert not device[2]
    assert playback.last('Room')['state'] == 'skipped'

@pytest.mark.parametrize('change', ['slot', 'speaker_id', 'state', 'content'])
def test_favorite_drift_never_changes_volume_or_plays(device, monkeypatch, change):
    from app.core import favorites, library
    saved = {'kind': 'nas', 'state': 'readback_matched', 'speaker_id': 'ABC', 'slot': 1,
             'content': {'source': 'STORED_MUSIC', 'sourceAccount': 'server', 'location': 'album/1'}}
    saved[change] = {'source': 'STORED_MUSIC', 'sourceAccount': 'server', 'location': 'other'} if change == 'content' else 'changed'
    monkeypatch.setattr(favorites, 'get', lambda _: saved)
    monkeypatch.setattr(library, 'read_sources', lambda _: [])
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3, favorite_id='favorite')
    assert not device[2]
    assert playback.last('Room')['reason'] == 'favorite_preset_changed'


def test_ready_native_favorite_uses_existing_quiet_playback(device, monkeypatch):
    from app.core import favorites, library
    monkeypatch.setattr(favorites, 'get', lambda _: {
        'kind': 'nas', 'state': 'readback_matched', 'speaker_id': 'ABC', 'slot': 1,
        'content': {'source': 'STORED_MUSIC', 'type': 'dir', 'sourceAccount': 'server', 'location': 'album/1'}})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'STORED_MUSIC', 'account': 'server', 'ready': True}])
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3, fade_in_duration=0, favorite_id='favorite')
    assert playback.last('Room')['state'] == 'playing'
    assert device[2][0] == ('volume', 0)


def test_favorite_unready_source_never_selects(device, monkeypatch):
    from app.core import favorites, library
    monkeypatch.setattr(favorites, 'get', lambda _: {
        'kind': 'nas', 'state': 'readback_matched', 'speaker_id': 'ABC', 'slot': 1,
        'content': {'source': 'STORED_MUSIC', 'sourceAccount': 'server', 'location': 'album/1'}})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'STORED_MUSIC', 'account': 'server', 'ready': False}])
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, preset=1, volume=3, favorite_id='favorite')
    assert not device[2]
    assert playback.last('Room')['reason'] == 'favorite_source_unavailable'


@pytest.mark.parametrize('scheduled', [False, True])
def test_direct_station_quiets_then_selects_without_preset_write(device, monkeypatch, scheduled):
    from app.core import favorites, library
    content = {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl', 'location': 'http://wisp/api/stations/id/stream', 'name': 'Radio', 'presetable': True}
    archive_access = []
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp:9001')
    monkeypatch.setattr(favorites, 'station', lambda *a, **kw: {'url': 'https://radio.example/live.mp3'})
    monkeypatch.setattr(favorites, 'station_content', lambda _, **kwargs: archive_access.append(kwargs['allow_removed']) or content)
    monkeypatch.setattr(favorites, 'capabilities', lambda _: {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    def select(ip, selected, **kwargs):
        device[2].append(('select', selected))
        device[0].update(status='Playing', source_type='LOCAL_INTERNET_RADIO', content_identity={key: content[key] for key in ('source', 'type', 'location')})
        return True
    monkeypatch.setattr(playback.control, 'select_content', select)
    op = playback.begin('Room', 'Station test', 'ABC')
    playback.run_on(op, None, 5, fade_in_duration=0, force=not scheduled, station_id='id', allow_archived_station=scheduled)
    assert archive_access == [scheduled]
    assert playback.last('Room')['state'] == 'playing'
    assert device[2][0] == ('volume', 0)
    assert device[2][1] == ('select', content)
    assert not any(call[0] == 'preset' for call in device[2])


@pytest.mark.parametrize('reason', ['removed', 'source', 'capability'])
def test_direct_station_unready_never_changes_audio(device, monkeypatch, reason):
    from app.core import favorites, library
    def get(_, **kwargs):
        if reason == 'removed':
            raise ValueError('removed')
        return {'source': 'LOCAL_INTERNET_RADIO', 'location': 'http://wisp/station'}
    monkeypatch.setattr(favorites, 'station_content', get)
    monkeypatch.setattr(favorites, 'capabilities', lambda _: set() if reason == 'capability' else {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': reason != 'source'}])
    op = playback.begin('Room', 'Station test', 'ABC')
    playback.run_on(op, None, 5, force=True, station_id='id')
    assert playback.last('Room')['state'] == 'unknown'
    assert not device[2]


def test_seventh_station_schedule_roundtrip_plays_without_any_preset(device, monkeypatch, tmp_path):
    import json
    from flask import Flask
    from app.api.routes import api_bp
    from app.core import favorites, library
    from app.scheduler import jobs
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    initial_count = len(favorites.stations())
    saved = [favorites.add_station(f'Radio {index}', f'https://radio.example/{index}') for index in range(7)]
    chosen = saved[-1]
    mutations = []
    monkeypatch.setattr(jobs, 'get_current_config', lambda: {})
    monkeypatch.setattr(jobs.config_queue, 'put', mutations.append)
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    monkeypatch.setattr(favorites, 'capabilities', lambda _: {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    response = app.test_client().post('/api/Room/schedules', json={
        'name': 'Seventh radio', 'station_id': chosen['id'], 'preset': None, 'source': None,
        'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'volume': 9, 'fade_in_duration': 0})
    assert response.status_code == 202
    config = tmp_path / 'saved-config.json'
    config.write_text(json.dumps(mutations[0]['data']))
    schedule = jobs._normalize_schedule(json.loads(config.read_text()), 'Room', 0)
    favorites.remove_station(chosen['id'])
    assert len(favorites.stations()) == initial_count + 6
    monkeypatch.setattr(favorites, 'capabilities', lambda _: {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    def select(ip, content, **kwargs):
        device[2].append(('select', content['location']))
        device[0].update(status='Playing', source_type='LOCAL_INTERNET_RADIO',
                         content_identity={key: content[key] for key in ('source', 'type', 'location')})
        return True
    monkeypatch.setattr(playback.control, 'select_content', select)
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda fn, *args: fn(*args) or True)
    jobs.queue_on('Room', schedule)
    assert playback.last('Room')['state'] == 'playing'
    assert device[2][0] == ('volume', 0)
    assert device[2][-1] == ('volume', 9)
    assert ('select', f"http://wisp.local:9001/api/stations/{chosen['id']}/stream") in device[2]
    assert not any(call[0] == 'preset' for call in device[2])


def unselected(device):
    device[0].update(status='Unknown', source_type='INVALID_SOURCE', raw_state='UNKNOWN')


def test_manual_start_from_unselected_idle_is_quiet_and_verified(device):
    unselected(device)
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=0, force=True)
    assert device[2] == [('volume', 0), ('preset', 1), ('volume', 5)]
    assert playback.last('Room')['state'] == 'playing'


def test_automatic_start_from_unselected_idle_still_refuses(device):
    unselected(device)
    op = playback.begin('Room', 'Morning')
    playback.run_on(op, 1, 5, fade_in_duration=0)
    assert device[2] == []
    assert playback.last('Room')['reason'] == 'playback_observation_unavailable'


@pytest.mark.parametrize('field,value', [
    ('source_type', 'UNKNOWN'), ('source_type', 'STORED_MUSIC'),
    ('status', 'OFFLINE'), ('raw_state', 'PLAY_STATE'), ('raw_state', None),
    ('device_id', None), ('device_id', 'OTHER'),
])
def test_manual_idle_exception_requires_exact_state_and_identity(device, field, value):
    unselected(device)
    device[0][field] = value
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=0, force=True)
    assert device[2] == []
    assert playback.last('Room')['state'] == 'unknown'


@pytest.mark.parametrize('observed_at', [None, 'now', True, 0, float('nan'), float('inf')])
def test_manual_idle_exception_requires_fresh_observation(device, monkeypatch, observed_at):
    unselected(device)
    monkeypatch.setattr(playback.status, 'get_now_playing',
                        lambda *_, **kw: dict(device[0], observed_at=observed_at))
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=0, force=True)
    assert device[2] == []
    assert playback.last('Room')['reason'] == 'playback_observation_unavailable'


def test_unselected_after_preset_never_fades_up(device, monkeypatch):
    unselected(device)
    def select(*_, **kw):
        device[2].append(('preset', 1))
        return True
    monkeypatch.setattr(playback.control, 'play_preset', select)
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=0, force=True)
    assert device[2] == [('volume', 0), ('preset', 1)]
    assert playback.last('Room')['reason'] == 'playback_observation_unavailable'


def test_unselected_during_manual_fade_never_increases_volume(device, monkeypatch):
    unselected(device)
    def wait(op, delay):
        unselected(device)
        return playback.current(op)
    monkeypatch.setattr(playback, 'wait', wait)
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=5, force=True)
    assert device[2] == [('volume', 0), ('preset', 1)]
    assert playback.last('Room')['reason'] == 'playback_observation_unavailable'


def test_manual_idle_does_not_select_without_confirmed_zero_volume(device, monkeypatch):
    unselected(device)
    monkeypatch.setattr(playback.status, 'get_volume', lambda *_, **kw: None)
    op = playback.begin('Room', 'Test favorite')
    playback.run_on(op, 1, 5, fade_in_duration=0, force=True)
    assert device[2] == [('volume', 0)]
    assert playback.last('Room')['reason'] == 'volume_not_confirmed'


@pytest.mark.parametrize('change', ['source', 'volume'])
def test_native_station_off_does_not_adopt_external_takeover(device, monkeypatch, change):
    from app.core import favorites, library
    monkeypatch.setenv('WISP_BASE_URL', 'http://wisp.local:9001')
    monkeypatch.setattr(favorites, 'station', lambda *a, **k: {'url': 'https://radio.example/live.mp3'})
    content = {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl', 'location': 'http://wisp/api/stations/id/stream'}
    monkeypatch.setattr(favorites, 'station_content', lambda *a, **kw: content)
    monkeypatch.setattr(favorites, 'capabilities', lambda _: {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    def select(ip, value, **kwargs):
        device[0].update(status='Playing', source_type='LOCAL_INTERNET_RADIO', content_identity=dict(content))
        return True
    monkeypatch.setattr(playback.control, 'select_content', select)
    op = playback.begin('Room', 'Morning', 'ABC')
    playback.run_on(op, None, 5, fade_in_duration=0, station_id='id')
    assert op['outcome']['state'] == 'playing'
    before = list(device[2])
    if change == 'source':
        device[0].update(source_type='AUX', content_identity={'source': 'AUX'})
    else:
        device[1][0] = 8
    off = playback.begin_radio_off('Room', 'Morning', 'ABC', 'id')
    assert off is not None
    playback.run_off(off, 0)
    assert device[2] == before
    assert off['outcome']['state'] == 'canceled'


def test_older_nonradio_schedule_off_cannot_steal_native_radio_operation(device, monkeypatch):
    from app.scheduler import jobs
    op = playback.begin('Room', 'New radio', 'ABC')
    playback._resolve(op)
    op['outcome'].update(radio_mode='native', station_id='id', state='playing', terminal=True)
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    result = jobs.queue_off('Room', {'name': 'Old NAS', 'speaker_id': 'ABC', 'fade_out_duration': 0})
    assert result['state'] == 'skipped'
    assert playback.current(op)
    assert not device[2]
    # A polite later automatic ON must not discard the original OFF ownership.
    assert jobs.queue_on('Room', {'name': 'Later preset', 'speaker_id': 'ABC'})['operation_id'] == op['outcome']['operation_id']
    assert playback.current(op)
