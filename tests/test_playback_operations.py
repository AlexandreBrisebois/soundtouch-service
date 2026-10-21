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
