"""Offline recovery coverage for a lost, still-current Wisp relay lease."""
import threading

import pytest

from app.core import direct_radio, favorites, playback, radio_relay as relay
from app.scheduler import jobs
from tests.test_direct_radio import SAVED
from tests.test_direct_radio import device as device  # noqa: F401
from tests.test_radio_relay import radio as radio  # noqa: F401
from tests.test_radio_relay import start


class ReservedWorkers:
    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
        monkeypatch.setattr(jobs, 'submit_background_task', self.submit)

    def submit(self, callback, *args):
        self.calls.append((callback, args))
        return True

    def run(self, index=0):
        callback, args = self.calls[index]
        callback(*args)


def disconnect_playing(device, radio, monkeypatch, *, listening=False):
    workers = ReservedWorkers(monkeypatch)
    op = start()
    if listening:
        op['outcome'].update(listening_session=True, speaker_id='A')
    session = relay.for_device('A')
    old_url = session['url']
    relay.close(session, 'radio_client_disconnected')
    return op, old_url, workers


def test_current_reported_playing_disconnect_reserves_one_recovery(device, radio, monkeypatch):
    op, old_url, workers = disconnect_playing(device, radio, monkeypatch)
    outcome = playback.last('A')
    assert outcome['operation_id'] == op['outcome']['operation_id']
    assert outcome['state'] == 'recovery_pending'
    assert outcome['reason'] == 'radio_client_disconnected'
    assert outcome['recovery_state'] == 'pending'
    assert outcome['recovery_attempts'] == 1
    assert outcome['terminal'] is False
    assert len(workers.calls) == 1
    assert old_url not in repr(outcome)


@pytest.mark.parametrize('reason', [
    'radio_gate_not_released', 'radio_upstream_ended',
    'radio_upstream_unavailable', 'canceled', 'completed', 'shutdown',
])
def test_non_client_or_non_live_endings_never_recover(device, radio, monkeypatch, reason):
    workers = ReservedWorkers(monkeypatch)
    op = start()
    relay.close(relay.for_device('A'), reason)
    assert not workers.calls
    outcome = playback.last('A')
    if reason in {'canceled', 'completed', 'shutdown'}:
        assert outcome['state'] == 'playing'
    else:
        assert outcome['state'] == 'unknown'
        assert outcome['reason'] == reason
    assert outcome.get('recovery_attempts', 0) == 0
    assert op['outcome']['operation_id'] == outcome['operation_id']


def test_disconnect_before_reported_playing_never_recovers(device, radio, monkeypatch):
    workers = ReservedWorkers(monkeypatch)
    op = playback.begin('A', 'Morning', 'A')
    op['outcome'].update(radio_mode='relay', station_id='station', target_volume=5)
    session = relay.prepare('A', 'A', op['outcome']['operation_id'], 'station',
                            'Morning', 'https://example.com/radio.mp3',
                            'http://192.0.2.10:9001')
    relay.close(session, 'radio_client_disconnected')
    assert not workers.calls
    assert playback.last('A')['state'] == 'unknown'


def test_recovery_worker_unavailable_is_terminal_and_not_accepted(device, radio, monkeypatch):
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', None)
    op = start()
    relay.close(relay.for_device('A'), 'radio_client_disconnected')
    outcome = playback.last('A')
    assert outcome['operation_id'] == op['outcome']['operation_id']
    assert outcome['state'] == 'unknown'
    assert outcome['reason'] == 'radio_recovery_worker_unavailable'
    assert outcome['recovery_state'] == 'failed'
    assert outcome['recovery_attempts'] == 0
    assert outcome['terminal'] is True


def test_restart_discards_pending_recovery_grant(device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    before = list(device[1])
    playback.reset()
    workers.run()
    assert device[1] == before
    assert relay.for_device('A') is None


def test_expired_recovery_performs_no_speaker_write(device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    before = list(device[1])
    monkeypatch.setattr(playback.time, 'monotonic', lambda: 10_000.0)
    workers.run()
    assert device[1] == before
    outcome = playback.last('A')
    assert outcome['state'] == 'unknown'
    assert outcome['reason'] == 'radio_recovery_expired'
    assert outcome['recovery_state'] == 'declined'


def test_candidate_expiry_starts_at_disconnect_before_worker_reservation(
        device, radio, monkeypatch):
    workers = ReservedWorkers(monkeypatch)
    op = start()
    original = jobs.queue_relay_recovery
    def delayed(owner, ended):
        device[2][0] += playback.RECOVERY_DEADLINE_SECONDS + 1
        return original(owner, ended)
    monkeypatch.setattr(jobs, 'queue_relay_recovery', delayed)
    before = list(device[1])
    relay.close(relay.for_device('A'), 'radio_client_disconnected')
    assert device[1] == before
    assert len(workers.calls) == 1
    workers.run()
    outcome = playback.last('A')
    assert outcome['operation_id'] == op['outcome']['operation_id']
    assert outcome['reason'] == 'radio_recovery_expired'
    assert outcome['recovery_state'] == 'declined'
    assert outcome['recovery_attempts'] == 0


@pytest.mark.parametrize('change', [
    'identity', 'station_url', 'group', 'uri', 'source', 'volume', 'target',
])
def test_fresh_exact_mismatch_declines_before_volume_or_uri_write(
        device, radio, monkeypatch, change):
    _, old_url, workers = disconnect_playing(device, radio, monkeypatch)
    room = device[0]('A')
    if change == 'identity':
        monkeypatch.setattr(playback.status, 'get_device_id', lambda *a, **kw: 'OTHER')
    elif change == 'station_url':
        monkeypatch.setattr(favorites, 'station', lambda *a, **kw: {
            'url': 'https://example.com/changed.mp3'})
    elif change == 'group':
        room['group'] = True
    elif change == 'uri':
        room['uri'] = old_url + '-changed'
    elif change == 'source':
        room['source'] = 'STORED_MUSIC'
    elif change == 'volume':
        room['volume'] = 6
    elif change == 'target':
        room['target'] = 6
    before = list(device[1])
    workers.run()
    assert device[1] == before
    outcome = playback.last('A')
    assert outcome['state'] == 'unknown'
    assert outcome['recovery_state'] == 'declined'


def test_recovery_uses_new_gated_token_and_zero_before_uri(device, radio, monkeypatch):
    op, old_url, workers = disconnect_playing(device, radio, monkeypatch)
    released = []
    original_release = relay.release
    def release_at_zero(session, owner):
        room = device[0]('A')
        assert room['volume'] == room['target'] == 0
        assert radio[0][-1].reads == 0
        released.append(session['url'])
        return original_release(session, owner)
    monkeypatch.setattr(relay, 'release', release_at_zero)
    before = len(device[1])
    workers.run()
    replacement = relay.for_device('A')
    assert replacement is not None and replacement['url'] != old_url
    assert replacement['owner'] == op['outcome']['operation_id']
    assert [call[1:] for call in device[1][before:]] == [
        ('volume', 0), ('SetAVTransportURI', replacement['url']),
        ('volume', 0), ('volume', 5),
    ]
    assert released == [replacement['url']]
    assert next(radio[1][-1][0]) == b'MP3 audio'
    outcome = playback.last('A')
    assert outcome['state'] == 'playing'
    assert outcome['reason'] == 'radio_relay_recovered'
    assert outcome['recovery_state'] == 'recovered'
    assert outcome['recovery_attempts'] == 1
    assert outcome['audible_confirmed'] is False


def test_claimed_recovery_has_time_for_the_original_bounded_fade(
        device, radio, monkeypatch):
    workers = ReservedWorkers(monkeypatch)
    op = playback.begin('A', 'Morning', 'A', allow_radio_idle=True)
    playback.run_on(op, None, 5, fade_in_duration=20, station_id='station')
    relay.close(relay.for_device('A'), 'radio_client_disconnected')
    workers.run()
    assert playback.last('A')['recovery_state'] == 'recovered'
    assert device[0]('A')['volume'] == device[0]('A')['target'] == 5


def test_unconfirmed_zero_never_selects_replacement_or_releases_audio(
        device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    original = direct_radio.control.set_volume
    def unstable(ip, target, **kwargs):
        result = original(ip, target, **kwargs)
        if target == 0:
            device[0](ip)['target'] = 1
        return result
    monkeypatch.setattr(direct_radio.control, 'set_volume', unstable)
    before = len(device[1])
    workers.run()
    later = device[1][before:]
    assert later == [('A', 'volume', 0)]
    assert all(call[1] != 'SetAVTransportURI' for call in later)
    assert radio[0][-1].reads == 0
    assert radio[0][-1].closed
    assert playback.last('A')['recovery_state'] == 'failed'


@pytest.mark.parametrize('moment', ['before_select', 'before_release'])
def test_station_change_after_preflight_prevents_later_selection_or_gate(
        device, radio, monkeypatch, moment):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    calls = [0]
    def station(*args, **kwargs):
        calls[0] += 1
        changed_at = 2 if moment == 'before_select' else 3
        return {'url': ('https://example.com/changed.mp3'
                        if calls[0] >= changed_at else SAVED)}
    monkeypatch.setattr(favorites, 'station', station)
    before = len(device[1])
    workers.run()
    later = device[1][before:]
    if moment == 'before_select':
        assert later == [('A', 'volume', 0)]
    else:
        assert [call[1] for call in later] == ['volume', 'SetAVTransportURI', 'volume']
    assert radio[0][-1].reads == 0
    assert radio[0][-1].closed
    assert relay.for_device('A') is None
    assert playback.last('A')['recovery_state'] == 'failed'


def test_recovery_never_touches_another_speaker(device, radio, monkeypatch):
    start('B', 'Other', 'other', 7)
    b_before = dict(device[0]('B'))
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    workers.run()
    assert device[0]('B') == b_before
    assert all(call[0] == 'A' for call in device[1][-4:])


def test_recovered_relay_disconnects_only_once(device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    workers.run()
    recovered = relay.for_device('A')
    relay.close(recovered, 'radio_client_disconnected')
    assert len(workers.calls) == 1
    outcome = playback.last('A')
    assert outcome['state'] == 'unknown'
    assert outcome['recovery_attempts'] == 1


def test_disconnect_after_final_guard_cannot_publish_false_recovery(
        device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    original = playback.complete_recovery
    def disconnect_then_complete(op, generation):
        relay.close(relay.for_device('A'), 'radio_client_disconnected')
        original(op, generation)
    monkeypatch.setattr(playback, 'complete_recovery', disconnect_then_complete)
    workers.run()
    outcome = playback.last('A')
    assert outcome['state'] == 'unknown'
    assert outcome['reason'] == 'radio_client_disconnected'
    assert outcome['recovery_state'] == 'failed'
    assert relay.for_device('A') is None


def test_exact_listening_stop_cancels_pending_recovery_without_speaker_command(
        device, radio, monkeypatch):
    op, _, workers = disconnect_playing(device, radio, monkeypatch, listening=True)
    before = list(device[1])
    accepted = jobs.queue_station_stop(
        'A', 'A', 'station', op['outcome']['operation_id'])
    assert accepted is not None
    workers.run(1)
    assert device[1] == before
    outcome = playback.last('A')
    assert outcome['state'] == 'completed'
    assert outcome['reason'] == 'radio_recovery_canceled_no_speaker_command'
    assert outcome['recovery_state'] == 'canceled'
    workers.run(0)
    assert device[1] == before


def test_exact_stop_in_disconnect_to_worker_reservation_gap_wins(
        device, radio, monkeypatch):
    workers = ReservedWorkers(monkeypatch)
    op = start()
    op['outcome'].update(listening_session=True, speaker_id='A')
    original = jobs.queue_relay_recovery
    stopped = []
    def stop_before_reservation(owner, ended):
        stopped.append(jobs.queue_station_stop('A', 'A', 'station', owner))
        return original(owner, ended)
    monkeypatch.setattr(jobs, 'queue_relay_recovery', stop_before_reservation)
    before = list(device[1])
    relay.close(relay.for_device('A'), 'radio_client_disconnected')
    assert stopped[0] is not None
    workers.run(0)
    workers.run(1)
    assert device[1] == before
    assert playback.last('A')['reason'] == 'radio_recovery_canceled_no_speaker_command'


def test_gate_release_holds_generation_boundary_against_cancel(
        device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    original = relay.release
    cancel_done = threading.Event()
    cancel_thread = []
    def release_while_cancel_waits(session, owner):
        thread = threading.Thread(
            target=lambda: (playback.cancel('A'), cancel_done.set()))
        cancel_thread.append(thread)
        thread.start()
        assert not cancel_done.wait(.02)
        return original(session, owner)
    monkeypatch.setattr(relay, 'release', release_while_cancel_waits)
    workers.run()
    assert cancel_done.wait(1)
    cancel_thread[0].join(1)
    assert playback.last('A')['state'] == 'canceled'
    assert relay.for_device('A') is None


def test_matching_schedule_off_cancels_pending_recovery_without_speaker_command(
        device, radio, monkeypatch):
    disconnect_playing(device, radio, monkeypatch)
    before = list(device[1])
    off = playback.begin_radio_off('A', 'Morning', 'A', 'station')
    assert off is not None
    playback.run_off(off, 60)
    assert device[1] == before
    assert off['outcome']['reason'] == 'radio_recovery_canceled_no_speaker_command'


@pytest.mark.parametrize('invalidate', ['replacement', 'cancel', 'shutdown'])
def test_invalidation_prevents_pending_recovery_writes(
        device, radio, monkeypatch, invalidate):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    before = list(device[1])
    if invalidate == 'replacement':
        playback.begin('A', 'Replacement', 'A')
    elif invalidate == 'cancel':
        playback.cancel('A')
    else:
        playback.reset()
    workers.run()
    assert device[1] == before


def test_invalidation_after_reserved_zero_prevents_uri_and_later_writes(
        device, radio, monkeypatch):
    _, _, workers = disconnect_playing(device, radio, monkeypatch)
    original = direct_radio.control.set_volume
    def replace_after_zero(ip, target, **kwargs):
        result = original(ip, target, **kwargs)
        if target == 0:
            playback.begin('A', 'Replacement', 'A')
        return result
    monkeypatch.setattr(direct_radio.control, 'set_volume', replace_after_zero)
    before = len(device[1])
    workers.run()
    assert device[1][before:] == [('A', 'volume', 0)]
    assert relay.for_device('A') is None


def test_recovery_failure_on_a_does_not_change_live_b(device, radio, monkeypatch):
    start('B', 'Other', 'other', 7)
    b_session = relay.for_device('B')
    b_before = dict(device[0]('B'))
    _, old_url, workers = disconnect_playing(device, radio, monkeypatch)
    device[0]('A')['uri'] = old_url + '-takeover'
    workers.run()
    assert relay.for_device('B') is b_session
    assert device[0]('B') == b_before

