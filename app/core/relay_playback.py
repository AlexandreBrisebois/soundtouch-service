"""Scheduled radio through Wisp's volume-gated per-speaker MP3 relay."""
import time
from typing import Any

from app.core import control, direct_radio, favorites, playback, radio_relay, radio_upstream


def _owner(op: playback.Operation, session: radio_relay.Session) -> None:
    if not playback.current(op) or not radio_relay.active(session, op['outcome']['operation_id']):
        raise direct_radio.TestError('radio_session_no_longer_owned')


def _guard(op: playback.Operation, session: radio_relay.Session,
           volume: int | None = None) -> dict[str, Any]:
    _owner(op, session)
    value = direct_radio._guard(op, session['url'], volume)
    _owner(op, session)
    return value


def _volume(op: playback.Operation, session: radio_relay.Session, before: int, target: int) -> None:
    def write(_ip: str) -> bool:
        _guard(op, session, before)
        return playback.current(op) and control.set_volume(
            direct_radio._address(op), target, timeout=playback._budget(op, 2))
    direct_radio._write(op, write)
    _guard(op, session, target)


def _automatic_idle(op: playback.Operation) -> None:
    data = playback._read(op, allow_unselected=op['radio_idle'] is not None)
    if data is not None and data.get('status', '').upper() == 'STANDBY':
        return
    evidence = op['radio_idle']
    if data is None or evidence is None or data.get('source_type') != 'INVALID_SOURCE':
        raise direct_radio.TestError('radio_speaker_no_longer_standby')
    observed = direct_radio._snapshot(op)
    if not (observed['source'] == 'INVALID_SOURCE' and observed['bose_state'] == ''
            and observed['state'] == 'PAUSED_PLAYBACK' and observed['transport_status'] == 'OK'
            and op['radio_idle'] is evidence and observed['volume'] == evidence['volume']):
        raise direct_radio.TestError('radio_owned_idle_changed')


def run_on(op: playback.Operation, station_id: str, saved_url: str,
           volume: int, fade_duration: float, force: bool) -> None:
    session = None
    succeeded = False
    try:
        op['deadline'] = time.monotonic() + 60
        op['outcome']['physical_stop_may_be_needed'] = False
        base = radio_relay.base_url(favorites.radio_base())
        # The normal automatic preflight already requires Standby. Repeat after
        # upstream preparation, immediately before the source-changing command.
        if not force:
            _automatic_idle(op)
        initial = direct_radio._idle(op)
        initial_volume = direct_radio._volume(op)
        direct_radio._ungrouped(op)
        direct_radio._capabilities(op)
        session = radio_relay.prepare(op['device_id'] or '', direct_radio._address(op),
                                      op['outcome']['operation_id'], station_id,
                                      op['outcome']['schedule_name'], saved_url, base)
        _owner(op, session)
        def select(_ip: str) -> bool:
            direct_radio._ungrouped(op)
            if direct_radio._idle(op) != initial or direct_radio._volume(op) != initial_volume:
                raise direct_radio.TestError('radio_preflight_changed')
            if not force:
                _automatic_idle(op)
            _owner(op, session)
            direct_radio._soap(direct_radio._address(op), 'SetAVTransportURI', playback._budget(op, 2),
                               CurrentURI=session['url'], CurrentURIMetaData='')
            return True
        direct_radio._write(op, select)
        after = _guard(op, session)
        # No audio bytes have left Wisp, even if SetURI reset actual/target to 10.
        _volume(op, session, after['volume'], 0)
        while not session['connected'].is_set():
            _guard(op, session, 0)
            if not playback.wait(op, .1):
                return
        _guard(op, session, 0)
        if not radio_relay.release(session, op['outcome']['operation_id']):
            raise direct_radio.TestError('radio_gate_not_released')
        op['outcome']['physical_stop_may_be_needed'] = True
        while True:
            observed = _guard(op, session, 0)
            if observed['bose_state'] == 'PLAY_STATE':
                break
            if not playback.wait(op, .25):
                return
        duration = min(playback.MAX_FADE_SECONDS, max(0, fade_duration))
        op['deadline'] = time.monotonic() + duration + 120
        started = time.monotonic()
        current_volume = 0
        for target in range(1, volume + 1) if duration else [volume]:
            due = started + duration * target / max(volume, 1)
            if not playback.wait(op, max(0, due - time.monotonic())):
                return
            _volume(op, session, current_volume, target)
            current_volume = target
        _guard(op, session, volume)
        playback.finish(op, 'playing', 'radio_relay_speaker_reported_playing')
        succeeded = True
    except Exception as error:
        reason = ('radio_upstream_' + error.reason if isinstance(error, radio_upstream.UpstreamError)
                  else str(error) if isinstance(error, (direct_radio.TestError, radio_relay.RelayError))
                  else 'radio_relay_start_unavailable')
        playback.finish(op, 'unknown', reason)
    finally:
        if session is not None and not succeeded and radio_relay.active(session, op['outcome']['operation_id']):
            radio_relay.close(session)


def run_off(op: playback.Operation, session: radio_relay.Session, fade_duration: float) -> None:
    try:
        observed = _guard(op, session)
        volume = observed['volume']
        duration = min(playback.MAX_FADE_SECONDS, max(0, fade_duration))
        op['deadline'] = time.monotonic() + duration + 120
        started = time.monotonic()
        current_volume = volume
        for target in range(volume - 1, -1, -1) if duration else [0]:
            due = started + duration * (volume - target) / max(volume, 1)
            if not playback.wait(op, max(0, due - time.monotonic())):
                return
            _volume(op, session, current_volume, target)
            current_volume = target
        def stop(_ip: str) -> bool:
            _guard(op, session, 0)
            direct_radio._soap(direct_radio._address(op), 'Stop', playback._budget(op, 2))
            return True
        direct_radio._write(op, stop)
        after = direct_radio._snapshot(op)
        inactive = (after['source'] == 'INVALID_SOURCE' and after['bose_state'] == ''
                    and after['state'] == 'PAUSED_PLAYBACK')
        stopped = (after['uri'] == session['url'] and after['source'] == 'UPNP'
                   and after['state'] == 'STOPPED' and after['bose_state'] == 'STOP_STATE')
        if after['volume'] != 0 or after['transport_status'] != 'OK' or not (inactive or stopped):
            raise direct_radio.TestError('radio_stop_readback_unknown')
        op['outcome']['relay_active'] = False
        op['outcome']['physical_stop_may_be_needed'] = False
        radio_relay.close(session, 'completed')
        playback.finish(op, 'completed', 'radio_stop_acknowledged_source_inactive' if inactive
                        else 'radio_stopped_verified')
        playback.record_radio_idle(op, after)
    except Exception as error:
        reason = str(error) if isinstance(error, direct_radio.TestError) else 'radio_relay_stop_unavailable'
        playback.finish(op, 'unknown', reason)
    finally:
        if radio_relay.active(session, op['outcome']['operation_id']):
            radio_relay.close(session)
