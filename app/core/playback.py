"""Cancelable, conservative per-speaker playback operations.

Only fresh device readback establishes speaker-reported Playing, never audibility.
No command is retried. Failed/ambiguous writes leave volume as-is, without rollback.
"""
import threading
import time
import uuid
from typing import Any, Callable, TypedDict

from app.core import control, discovery, status

START_DEADLINE_SECONDS = 30.0
RECOVERY_DEADLINE_SECONDS = 15.0
MAX_FADE_SECONDS = 3600.0
TERMINAL = {'completed', 'playing', 'failed', 'unknown', 'skipped', 'canceled'}


class Operation(TypedDict):
    speaker: str
    outcome: dict[str, Any]
    canceled: threading.Event
    changed: threading.Event
    device_id: str | None
    expected: status.ContentIdentity | dict[str, str] | None
    expected_volume: int | None
    deadline: float
    mode: str
    initial_state: str
    verified: bool
    pending_volume: int | None
    radio_idle: dict[str, Any] | None
    recovery: dict[str, Any] | None


_lock = threading.RLock()
_operations: dict[str, Operation] = {}
_write_locks: dict[str, threading.RLock] = {}
_bindings: dict[str, str] = {}
_device_owners: dict[str, Operation] = {}
_radio_idle: dict[str, dict[str, Any]] = {}


def reset() -> None:
    """Clear volatile state; no pending operation is resumed after restart."""
    from app.core import radio_relay
    radio_relay.reset()
    with _lock:
        for op in _operations.values():
            op['canceled'].set()
            op['changed'].set()
        _operations.clear()
        _write_locks.clear()
        _bindings.clear()
        _device_owners.clear()
        _radio_idle.clear()


def last(speaker: str) -> dict[str, Any] | None:
    with _lock:
        op = _operations.get(speaker)
        return dict(op['outcome']) if op else None


def current(op: Operation) -> bool:
    with _lock:
        return _operations.get(op['speaker']) is op and not op['canceled'].is_set()


def finish(op: Operation, state: str, reason: str, observed_at: float | None = None) -> None:
    with _lock:
        if not current(op):
            return
        if op['outcome']['terminal']:
            return
        if state == 'playing' and op['outcome'].get('radio_mode') == 'relay':
            from app.core import radio_relay
            session = radio_relay.for_device(op['device_id'])
            live = session is not None and radio_relay.active(session, op['outcome']['operation_id'])
            op['outcome']['relay_active'] = live
            if not live:
                state, reason = 'unknown', 'radio_session_ended'
        if state in TERMINAL:
            op['verified'] = False
            if state != 'playing':
                from app.core import radio_relay
                radio_relay.cancel_owner(op['outcome']['operation_id'])
        op['outcome'].update(state=state, reason=reason, updated_at=time.time(),
                             observed_at=observed_at, terminal=state in TERMINAL)


def cancel(speaker: str, reason: str = 'manual_override', *, preserve_radio: bool = False) -> None:
    with _lock:
        op = _operations.get(speaker)
        # Also invalidate another name's operation on this already-bound device.
        owner = _device_owners.get(_bindings.get(speaker, ''))
        for identity in (_bindings.get(speaker), op['device_id'] if op else None):
            if identity:
                _radio_idle.pop(identity, None)
        for target in (op, owner):
            if target is not None:
                if not preserve_radio:
                    from app.core import radio_relay
                    radio_relay.cancel_owner(target['outcome']['operation_id'])
                target['canceled'].set()
                target['changed'].set()
                target['verified'] = False
                if target['outcome']['terminal']:
                    continue
                target['outcome'].update(state='canceled', reason=reason,
                                          updated_at=time.time(), terminal=True)


def begin(speaker: str, schedule_name: str | None = None,
          device_id: str | None = None, *, preserve_radio: bool = False,
          allow_radio_idle: bool = False) -> Operation:
    with _lock:
        from app.core import radio_relay
        identity = device_id or _bindings.get(speaker)
        idle = _radio_idle.pop(identity or '', None) if allow_radio_idle else None
        previous_radio = radio_relay.for_device(device_id or _bindings.get(speaker)) if preserve_radio else None
        cancel(speaker, 'superseded', preserve_radio=preserve_radio)
        now = time.time()
        op: Operation = {
            'speaker': speaker, 'canceled': threading.Event(), 'changed': threading.Event(),
            'device_id': device_id or _bindings.get(speaker),
            'expected': None, 'expected_volume': None,
            'deadline': time.monotonic() + START_DEADLINE_SECONDS,
            'mode': 'on', 'initial_state': '', 'verified': False, 'pending_volume': None,
            'radio_idle': idle, 'recovery': None,
            'outcome': {'operation_id': uuid.uuid4().hex, 'schedule_name': schedule_name,
                        'state': 'accepted', 'reason': 'queued', 'accepted_at': now,
                        'updated_at': now, 'observed_at': None, 'terminal': False,
                        'audible_confirmed': False, 'in_flight': False},
        }
        _operations[speaker] = op
        if previous_radio is not None:
            radio_relay.transfer(previous_radio, op['outcome']['operation_id'])
        return op


def begin_radio_off(speaker: str, schedule_name: str | None, device_id: str | None,
                    station_id: str) -> Operation | None:
    """Never let a stale routine's OFF stop a later routine or manual session."""
    from app.core import radio_relay
    with _lock:
        previous = _operations.get(speaker)
        if (previous is not None and current(previous) and previous['recovery'] is not None
                and previous['outcome']['state'] in {'playing', 'recovery_pending', 'recovering'}
                and previous['device_id'] == (device_id or previous['device_id'])
                and previous['outcome'].get('station_id') == station_id
                and previous['outcome'].get('schedule_name') == schedule_name):
            old_id = previous['outcome']['operation_id']
            op = begin(speaker, schedule_name, device_id)
            op['mode'] = 'recovery_cancel'
            op['outcome'].update(
                station_id=station_id, speaker_id=device_id, radio_mode='relay',
                recovery_state='canceled', stops_operation_id=old_id)
            return op
        session = radio_relay.for_device(device_id or _bindings.get(speaker))
        if session is not None:
            if session['station_id'] != station_id or session['schedule_name'] != schedule_name:
                return None
            return begin(speaker, schedule_name, device_id, preserve_radio=True)
        previous = _operations.get(speaker)
        if (previous is not None and current(previous)
                and previous['outcome'].get('radio_mode') == 'native'
                and previous['outcome'].get('station_id') == station_id
                and previous['outcome'].get('schedule_name') == schedule_name
                and (previous['outcome']['state'] == 'playing' or previous['verified'])):
            expected, volume = previous['expected'], previous['expected_volume']
            op = begin(speaker, schedule_name, device_id)
            op['mode'] = 'native_station_off'
            op['expected'], op['expected_volume'] = expected, volume
            return op
        return None


def begin_nonradio_schedule_off(speaker: str, schedule_name: str, device_id: str | None) -> Operation | None:
    with _lock:
        if has_radio(speaker, device_id):
            return None
        return begin(speaker, schedule_name, device_id)


def begin_station_stop(speaker: str, device_id: str, station_id: str,
                       operation_id: str) -> Operation | None:
    """Compare the exact listening owner before transferring any ownership."""
    from app.core import radio_relay
    with _lock:
        previous = _operations.get(speaker)
        if (previous is not None and current(previous) and previous['recovery'] is not None
                and previous['outcome']['state'] in {'playing', 'recovery_pending', 'recovering'}
                and previous['device_id'] == device_id
                and previous['outcome'].get('operation_id') == operation_id
                and previous['outcome'].get('station_id') == station_id
                and previous['outcome'].get('listening_session') is True):
            op = begin(speaker, previous['outcome']['schedule_name'], device_id)
            op['mode'] = 'recovery_cancel'
            op['outcome'].update(
                station_id=station_id, speaker_id=device_id, listening_session=True,
                radio_mode='relay', recovery_state='canceled',
                stops_operation_id=operation_id)
            return op
        if (previous is None or not current(previous) or previous['device_id'] != device_id
                or previous['outcome'].get('operation_id') != operation_id
                or previous['outcome'].get('station_id') != station_id
                or previous['outcome'].get('listening_session') is not True
                or previous['outcome']['state'] != 'playing'):
            return None
        mode = previous['outcome'].get('radio_mode')
        session = radio_relay.for_device(device_id)
        if mode == 'relay':
            if session is None or session['owner'] != operation_id or session['station_id'] != station_id:
                return None
        elif mode != 'native' or session is not None or not previous['expected']:
            return None
        expected = previous['expected']
        op = begin(speaker, previous['outcome']['schedule_name'], device_id, preserve_radio=True)
        op['expected'] = expected
        op['mode'] = 'listening_stop'
        op['outcome'].update(station_id=station_id, speaker_id=device_id,
                             listening_session=True, radio_mode=mode, stops_operation_id=operation_id)
        return op


def run_station_stop(op: Operation) -> None:
    """Explicit radio STOP, never the generic power-toggle OFF path."""
    if not current(op):
        return
    if op['mode'] == 'recovery_cancel':
        finish(op, 'completed', 'radio_recovery_canceled_no_speaker_command')
        return
    finish(op, 'starting', 'stopping_radio')
    if _resolve(op) is None:
        return
    from app.core import radio_relay, relay_playback
    session = radio_relay.for_device(op['device_id'])
    if op['outcome'].get('radio_mode') == 'relay':
        if session is None or session['owner'] != op['outcome']['operation_id']:
            finish(op, 'canceled', 'radio_session_no_longer_owned')
            return
        relay_playback.run_off(op, session, 0)
        return
    data = _read(op)
    if data is None:
        return
    if not matches(op['expected'] or {}, data):
        finish(op, 'canceled', 'radio_station_changed')
        return
    ip = _address(op)
    if ip is None:
        return
    volume = status.get_volume(ip, timeout=_budget(op))
    if volume is None:
        finish(op, 'unknown', 'volume_observation_unavailable')
        return
    op['initial_state'] = data.get('status', '').upper()
    op['expected_volume'], op['verified'] = volume, True
    if not _guard(op):
        return
    if not _write(op, lambda address: _guard(op) and control.stop_action(address, timeout=_budget(op, 3))):
        return
    after = _read(op)
    if after is None:
        return
    stopped = after.get('status', '').upper() in {'STOPPED', 'STANDBY'}
    if stopped and (after.get('source_type') == 'STANDBY' or matches(op['expected'] or {}, after)):
        finish(op, 'completed', 'radio_stopped_verified', after.get('observed_at'))
    else:
        finish(op, 'unknown', 'radio_stop_readback_unknown')


def has_radio(speaker: str, device_id: str | None = None) -> bool:
    from app.core import radio_relay
    with _lock:
        identity = device_id or _bindings.get(speaker)
        owner = _device_owners.get(identity or '') or _operations.get(speaker)
        native = (owner is not None and current(owner)
                  and owner['outcome'].get('radio_mode') == 'native'
                  and (owner['outcome']['state'] == 'playing' or owner['verified']))
        return radio_relay.for_device(identity) is not None or native


def begin_relay_recovery(owner: str, ended: dict[str, Any]) -> tuple[Operation, str] | None:
    """Create one volatile grant only after a recovery worker is reserved."""
    with _lock:
        op = next((candidate for candidate in _operations.values()
                   if candidate['outcome']['operation_id'] == owner and current(candidate)), None)
        candidate = op['recovery'] if op is not None else None
        if (op is not None and candidate is not None and candidate.get('phase') == 'candidate'
                and time.monotonic() >= candidate.get('expires_at', 0)):
            op['recovery'] = None
            op['outcome'].update(
                state='unknown', reason='radio_recovery_expired', terminal=True,
                relay_active=False, recovery_state='declined',
                recovery_reason='radio_recovery_expired', recovery_attempts=0,
                updated_at=time.time())
            op['changed'].set()
            return None
        if (op is None or op['outcome']['state'] != 'playing'
                or op['outcome'].get('radio_mode') != 'relay'
                or op['outcome'].get('recovery_attempts', 0) != 0
                or candidate is None or candidate.get('phase') != 'candidate'
                or op['device_id'] != ended.get('device_id')
                or op['outcome'].get('station_id') != ended.get('station_id')
                or op['outcome'].get('schedule_name') != ended.get('schedule_name')
                or not isinstance(ended.get('saved_url'), str)
                or not isinstance(ended.get('url'), str)):
            return None
        target = op['outcome'].get('target_volume', op['expected_volume'])
        if not isinstance(target, int) or not 0 <= target <= 100:
            return None
        generation = uuid.uuid4().hex
        op['recovery'] = {
            'phase': 'granted',
            'generation': generation, 'operation_id': owner,
            'device_id': ended['device_id'], 'speaker_ip': ended.get('speaker_ip'),
            'station_id': ended['station_id'], 'schedule_name': ended.get('schedule_name'),
            'saved_url': ended['saved_url'], 'prior_url': ended['url'],
            'target_volume': target,
            'fade_duration': op['outcome'].get('fade_in_duration', 0),
            'expires_at': time.monotonic() + RECOVERY_DEADLINE_SECONDS,
        }
        op['verified'] = False
        op['outcome'].update(
            state='recovery_pending', reason='radio_client_disconnected', terminal=False,
            relay_active=False, recovery_state='pending', recovery_reason='radio_client_disconnected',
            recovery_attempts=1, updated_at=time.time(), audible_confirmed=False)
        op['changed'].set()
        return op, generation


def recovery_grant(op: Operation, generation: str, *, claim: bool = False) -> dict[str, Any] | None:
    """Return a copy only while this exact volatile generation remains current."""
    with _lock:
        grant = op['recovery']
        if (not current(op) or grant is None or grant.get('generation') != generation):
            return None
        if time.monotonic() >= grant['expires_at']:
            op['recovery'] = None
            op['outcome'].update(state='unknown', reason='radio_recovery_expired', terminal=True,
                                 recovery_state='declined', recovery_reason='radio_recovery_expired',
                                 updated_at=time.time())
            op['changed'].set()
            return None
        if claim:
            if not grant.get('claimed'):
                grant['claimed'] = True
                grant['expires_at'] = (time.monotonic()
                                       + min(MAX_FADE_SECONDS, max(0, grant['fade_duration']))
                                       + 60.0)
            op['outcome'].update(state='recovering', reason='radio_recovery_started',
                                 recovery_state='recovering', recovery_reason='radio_recovery_started',
                                 updated_at=time.time())
            op['changed'].set()
        return dict(grant)


def end_recovery(op: Operation, generation: str, reason: str,
                 *, recovery_state: str = 'failed') -> None:
    with _lock:
        grant = op['recovery']
        if not current(op) or grant is None or grant.get('generation') != generation:
            return
        op['recovery'] = None
        op['outcome'].update(state='unknown', reason=reason, terminal=True,
                             recovery_state=recovery_state, recovery_reason=reason,
                             relay_active=False, updated_at=time.time())
        op['changed'].set()


def complete_recovery(op: Operation, generation: str) -> None:
    with _lock:
        grant = op['recovery']
        if (not current(op) or grant is None or grant.get('generation') != generation):
            return
        from app.core import radio_relay
        session = radio_relay.for_device(op['device_id'])
        if (session is None or session['owner'] != op['outcome']['operation_id']
                or session['station_id'] != grant['station_id']):
            op['recovery'] = None
            op['outcome'].update(
                state='unknown', reason='radio_recovery_session_ended_before_commit',
                terminal=True, relay_active=False, recovery_state='failed',
                recovery_reason='radio_recovery_session_ended_before_commit',
                updated_at=time.time())
            op['changed'].set()
            return
        op['recovery'] = None
        op['verified'] = False
        op['expected_volume'] = grant['target_volume']
        op['outcome'].update(
            state='playing', reason='radio_relay_recovered', terminal=True,
            relay_active=True, physical_stop_may_be_needed=True,
            recovery_state='recovered', recovery_reason='radio_relay_recovered',
            recovered_at=time.time(), updated_at=time.time(), audible_confirmed=False)
        op['changed'].set()


def release_recovery_gate(op: Operation, generation: str, session: Any) -> bool:
    """Linearize grant validation and gate release against Stop/replacement."""
    from app.core import radio_relay
    with _lock:
        grant = op['recovery']
        if (not current(op) or grant is None or grant.get('generation') != generation
                or time.monotonic() >= grant['expires_at']
                or session['owner'] != op['outcome']['operation_id']):
            return False
        return radio_relay.release(session, op['outcome']['operation_id'])


def relay_recovery_unavailable(owner: str) -> None:
    with _lock:
        op = next((candidate for candidate in _operations.values()
                   if candidate['outcome']['operation_id'] == owner and current(candidate)), None)
        if op is None or op['outcome']['state'] != 'playing':
            return
        op['recovery'] = None
        op['outcome'].update(state='unknown', reason='radio_recovery_worker_unavailable',
                             terminal=True, relay_active=False, recovery_state='failed',
                             recovery_reason='radio_recovery_worker_unavailable',
                             recovery_attempts=0, updated_at=time.time())
        op['changed'].set()


def relay_ended(owner: str, reason: str, ended: dict[str, Any] | None = None) -> None:
    """A live audio feed ending invalidates a previous terminal Playing outcome."""
    eligible = False
    with _lock:
        for op in _operations.values():
            if op['outcome']['operation_id'] == owner and current(op):
                if op['mode'] == 'relay_stop':
                    op['changed'].set()
                    return
                eligible = (reason == 'radio_client_disconnected' and ended is not None
                            and op['outcome']['state'] == 'playing'
                            and op['outcome'].get('radio_mode') == 'relay'
                            and op['outcome'].get('recovery_attempts', 0) == 0)
                if eligible and ended is not None:
                    op['recovery'] = {
                        'phase': 'candidate', 'expires_at': time.monotonic() + RECOVERY_DEADLINE_SECONDS,
                        **ended,
                    }
                    break
                recovering = op['outcome']['state'] in {'recovery_pending', 'recovering'}
                if recovering or op['recovery'] is not None:
                    op['recovery'] = None
                op['outcome'].update(state='unknown', reason=reason, terminal=True,
                                     updated_at=time.time(), relay_active=False,
                                     **({'recovery_state': 'failed', 'recovery_reason': reason}
                                        if recovering else {}))
                op['changed'].set()
                return
        else:
            return
    if eligible:
        from app.scheduler import jobs
        jobs.queue_relay_recovery(owner, ended or {})


def record_radio_idle(op: Operation, observed: dict[str, Any]) -> None:
    with _lock:
        if (current(op) and op['device_id'] and op['outcome']['state'] == 'completed'
                and observed['source'] == 'INVALID_SOURCE' and observed['bose_state'] == ''
                and observed['state'] == 'PAUSED_PLAYBACK' and observed['transport_status'] == 'OK'):
            _radio_idle[op['device_id']] = {'volume': observed['volume']}


def wait(op: Operation, delay: float) -> bool:
    """Interruptible wait, including long configured fades."""
    until = time.monotonic() + max(0.0, delay)
    while current(op):
        remaining = until - time.monotonic()
        if remaining <= 0:
            return True
        op['changed'].wait(min(5.0, remaining))
        op['changed'].clear()
        if not current(op):
            return False
        if op['verified'] and not _guard(op):
            return False
    return False


def _resolve(op: Operation) -> dict[str, str] | None:
    if not current(op):
        return None
    device = discovery.resolve_device(op['speaker'], op['device_id'])
    if not device or not device.get('device_id'):
        finish(op, 'unknown', 'speaker_identity_unavailable')
        return None
    identity = device['device_id']
    if op['device_id'] is not None and identity != op['device_id']:
        finish(op, 'unknown', 'speaker_identity_changed')
        return None
    with _lock:
        if not current(op):
            return None
        previous = _device_owners.get(identity)
        if previous is not None and previous is not op and current(previous):
            cancel(previous['speaker'], 'superseded')
        _bindings[op['speaker']] = identity
        op['device_id'] = identity
        _device_owners[identity] = op
        _write_locks.setdefault(identity, threading.RLock())
    return device


def _budget(op: Operation, maximum: float = 5.0) -> float:
    return max(0.0, min(maximum, op['deadline'] - time.monotonic()))


def _address(op: Operation, verify: bool = True) -> str | None:
    """Resolve current address; writes independently verify stable device identity."""
    if not current(op):
        return None
    if time.monotonic() >= op['deadline']:
        finish(op, 'unknown', 'operation_deadline')
        return None
    device = discovery.resolve_device(op['speaker'], op['device_id'])
    if not device or (verify and status.get_device_id(
            device['ip'], timeout=_budget(op)) != op['device_id']):
        finish(op, 'unknown', 'speaker_identity_unavailable')
        return None
    if time.monotonic() >= op['deadline']:
        finish(op, 'unknown', 'operation_deadline')
        return None
    return device['ip'] if current(op) else None


def _write(op: Operation, callback: Callable[[str], bool]) -> bool:
    if not current(op):
        return False
    key = op['device_id'] or op['speaker']
    with _lock:
        mutex = _write_locks.setdefault(key, threading.RLock())
    with mutex:
        if op['verified'] and op['changed'].is_set():
            op['changed'].clear()
            if not _guard(op):
                return False
        ip = _address(op)
        if ip is None or not current(op):
            return False
        # Dispatch reservation is atomic with cancellation. The reserved bounded
        # command may finish; no later command can reserve after cancellation.
        with _lock:
            if not current(op):
                return False
            op['outcome']['in_flight'] = True
        try:
            confirmed = callback(ip)
        finally:
            with _lock:
                op['outcome']['in_flight'] = False
        if not confirmed:
            # A timeout or a failed key release may have executed at the device.
            finish(op, 'unknown', 'command_not_confirmed')
            return False
        return current(op)


def manual(speaker: str, callback: Callable[[str], bool]) -> bool:
    """Cancel first, resolve and verify the current address inside the write lock."""
    cancel(speaker)
    with _lock:
        bound = _bindings.get(speaker)
    device = discovery.resolve_device(speaker, bound)
    if not device or not device.get('device_id'):
        return False
    identity = device['device_id']
    with _lock:
        owner = _device_owners.get(identity)
        if owner:
            cancel(owner['speaker'])
        _bindings[speaker] = identity
        mutex = _write_locks.setdefault(identity, threading.RLock())
    with mutex:
        device = discovery.resolve_device(speaker, identity)
        if not device or status.get_device_id(device['ip']) != identity:
            return False
        return bool(callback(device['ip']))


def _read(op: Operation, *, allow_unselected: bool = False) -> status.PlaybackState | None:
    ip = _address(op, verify=False)
    if ip is None:
        return None
    read_started = time.time()
    data = status.get_now_playing(ip, timeout=_budget(op))
    if not current(op):
        return None
    if data.get('device_id') != op['device_id']:
        finish(op, 'unknown', 'playback_identity_unavailable')
        return None
    if not isinstance(data.get('observed_at'), (int, float)):
        finish(op, 'unknown', 'playback_observation_unavailable')
        return None
    # Some speakers report this exact state when on without selected content.
    # Explicit starts or a provenance-checked radio cycle may request this read.
    # It never establishes playback or by itself authorizes any fade/selection.
    observed_at = data['observed_at']
    if (allow_unselected and data.get('source_type') == 'INVALID_SOURCE'
            and data.get('status') == 'Unknown' and data.get('raw_state') == 'UNKNOWN'
            and not isinstance(observed_at, bool)
            and read_started <= observed_at <= time.time()):
        return data
    if (data.get('status', '').upper() not in
            {'STANDBY', 'PLAYING', 'PAUSED', 'BUFFERING', 'STOPPED'}
            or data.get('source_type') in {None, '', 'UNKNOWN'}):
        finish(op, 'unknown', 'playback_observation_unavailable')
        return None
    return data


def matches(expected: status.ContentIdentity | dict[str, str], data: status.PlaybackState) -> bool:
    if expected.get('source') == 'AUX':
        return data.get('source_type') == 'AUX'
    actual = data.get('content_identity') or {}
    # A source alone cannot distinguish two presets. Location is opaque and not logged.
    return bool(expected.get('source') and expected.get('location')) and all(
        actual.get(key) == value for key, value in expected.items() if value
        and not (key == 'type' and expected.get('source') == 'STORED_MUSIC' and not actual.get('type'))
    )


def _same_session(op: Operation, data: status.PlaybackState) -> bool:
    expected = op['expected'] or {}
    if op['mode'] == 'off':
        actual = data.get('content_identity') or {'source': data.get('source_type', '')}
        return (bool(expected.get('source')) and actual == expected
                and data.get('status', '').upper() == op['initial_state'])
    return matches(expected, data) and data.get('status', '').upper() == 'PLAYING'


def _radio_idle_event_conflicts(evidence: dict[str, Any], data: dict[str, Any]) -> bool:
    return (('status' in data and not (data.get('source_type') == 'INVALID_SOURCE'
                                     and data.get('status') == 'Unknown'
                                     and data.get('raw_state') == 'UNKNOWN'))
            or ('volume' in data and data['volume'] != evidence['volume']))


def observe_external(speaker: str, data: dict[str, Any]) -> None:
    """Wake the owner to reconcile fresh reads, never trust delayed event echoes.

    WebSocket events can arrive out of order, including Wisp's own old volume or
    source notifications. They prompt a fresh guard before the next write rather
    than themselves establishing either success or a manual override.
    """
    with _lock:
        identity = _bindings.get(speaker)
        evidence = _radio_idle.get(identity or '')
        if evidence is not None and _radio_idle_event_conflicts(evidence, data):
            _radio_idle.pop(identity or '', None)
        op = _operations.get(speaker)
        for candidate in (op, _device_owners.get(identity or '')):
            if (candidate is not None and current(candidate) and candidate['radio_idle'] is not None
                    and _radio_idle_event_conflicts(candidate['radio_idle'], data)):
                candidate['radio_idle'] = None
        if op and current(op) and op['verified']:
            op['changed'].set()


def _guard(op: Operation) -> bool:
    """Fresh content/transport/volume read before each fade write; manual changes win."""
    data = _read(op)
    if data is None:
        return False
    if not _same_session(op, data):
        finish(op, 'canceled', 'playback_changed', data.get('observed_at'))
        return False
    ip = _address(op, verify=False)
    if ip is None:
        return False
    volume = status.get_volume(ip, timeout=_budget(op))
    if volume is None:
        finish(op, 'unknown', 'volume_observation_unavailable')
        return False
    if volume != op['expected_volume']:
        finish(op, 'canceled', 'volume_changed')
        return False
    return current(op)


def _volume(op: Operation, value: int) -> bool:
    op['pending_volume'] = value
    if not _write(op, lambda ip: control.set_volume(ip, value, timeout=_budget(op, 3.0))):
        op['pending_volume'] = None
        return False
    ip = _address(op)
    if ip is None:
        return False
    observed = status.get_volume(ip, timeout=_budget(op))
    if observed != value:
        finish(op, 'unknown', 'volume_not_confirmed')
        return False
    op['expected_volume'] = value
    op['pending_volume'] = None
    return current(op)


def run_on(op: Operation, preset: int | None, volume: int, source: str | None = None,
           fade_in_duration: float = 300, force: bool = False, favorite_id: str | None = None, station_id: str | None = None, allow_archived_station: bool = False) -> None:
    if not current(op):
        return
    finish(op, 'starting', 'checking_speaker')
    if _resolve(op) is None:
        return
    owned_idle = bool(station_id and op['radio_idle'] is not None)
    data = _read(op, allow_unselected=force or owned_idle)
    if data is None:
        return
    if data.get('status', '').upper() != 'STANDBY' and not force and not (
            owned_idle and data.get('source_type') == 'INVALID_SOURCE'):
        finish(op, 'skipped', 'speaker_active', data.get('observed_at'))
        return
    ip = _address(op)
    if ip is None:
        return
    expected: status.ContentIdentity | dict[str, str] | None
    if station_id:
        from app.core import favorites, library, radio_relay, relay_playback
        try:
            saved = favorites.station(station_id, allow_removed=allow_archived_station)
            op['outcome']['station_id'] = station_id
            ready = radio_relay.readiness(saved['url'], ip)
            if not ready['available']:
                finish(op, 'failed', ready['reason'])
                return
            op['outcome']['radio_mode'] = ready['mode']
            if ready['mode'] == 'relay':
                relay_playback.run_on(op, station_id, saved['url'], volume, fade_in_duration, force)
                return
            if not force and data.get('status', '').upper() != 'STANDBY':
                finish(op, 'skipped', 'native_station_requires_standby')
                return
            station_content = favorites.station_content(station_id, allow_removed=allow_archived_station)
            expected = {key: station_content[key] for key in ('source', 'sourceAccount', 'location', 'type') if station_content.get(key)}
            source_ready = any(item['source'] == 'LOCAL_INTERNET_RADIO' and item['ready'] for item in library.read_sources(ip))
            if not source_ready or '/select' not in favorites.capabilities(ip):
                finish(op, 'unknown', 'station_source_unavailable')
                return
        except (ValueError, KeyError, TypeError):
            finish(op, 'unknown', 'station_unavailable')
            return
    else:
        expected = {'source': 'AUX'} if source == 'AUX' else status.get_preset_identity(ip, preset or 1, timeout=_budget(op))
    if not expected or (source != 'AUX' and not expected.get('location')):
        finish(op, 'unknown', 'preset_identity_unavailable')
        return
    if favorite_id:
        from app.core import favorites, library
        try:
            favorite = favorites.get(favorite_id)
            if (favorite.get('state') != 'readback_matched'
                    or favorite.get('speaker_id') != op['device_id']
                    or favorite.get('slot') != preset
                    or not library.same_content(favorite['content'], dict(expected))):
                finish(op, 'unknown', 'favorite_preset_changed')
                return
            sources = library.read_sources(ip)
            if not any(s['source'] == expected['source'] and s['ready'] and
                       (s['source'] != 'STORED_MUSIC' or s['account'] == expected.get('sourceAccount')) for s in sources):
                finish(op, 'unknown', 'favorite_source_unavailable')
                return
            if favorite['kind'] == 'radio' and expected['location'] != f"{favorites.radio_base()}/api/radio/{favorite_id}":
                finish(op, 'unknown', 'radio_base_changed')
                return
        except (ValueError, KeyError, TypeError):
            finish(op, 'unknown', 'favorite_unavailable')
            return
    op['expected'] = expected
    # Preset/identity reads may have taken seconds. An automatic ON must remain
    # polite if someone started audio while those reads were in flight.
    if not force:
        latest = _read(op)
        if latest is None:
            return
        if latest.get('status', '').upper() != 'STANDBY':
            finish(op, 'skipped', 'speaker_active', latest.get('observed_at'))
            return
    # Quiet the existing source BEFORE anything that might start playback. Do not
    # restore volume on failure: that could blast the old or externally selected source.
    if not _volume(op, 0):
        return
    # PRESET and AUX keys request the intended source directly, avoiding a POWER
    # toggle that could resume the wrong source. Firmware behavior is qualified separately.
    selected = _write(op, lambda ip: control.select_content(ip, station_content, timeout=_budget(op, 3.0)) if station_id else control.send_key(ip, 'AUX_INPUT', timeout=_budget(op, 3.0)) if source == 'AUX'
                      else control.play_preset(ip, preset or 1, timeout=_budget(op, 3.0)))
    if not selected:
        return
    while current(op) and time.monotonic() < op['deadline']:
        data = _read(op)
        if data is None:
            return
        if matches(expected, data) and data.get('status', '').upper() == 'PLAYING':
            break
        if not wait(op, 0.25):
            return
    else:
        finish(op, 'unknown', 'playback_not_verified')
        return
    op['verified'] = True
    duration = min(MAX_FADE_SECONDS, max(0.0, fade_in_duration))
    op['deadline'] = time.monotonic() + duration + 120.0
    steps = range(1, volume + 1) if duration > 0 else [volume]
    fade_started = time.monotonic()
    for value in steps:
        due = fade_started + duration * value / max(volume, 1)
        if not wait(op, max(0.0, due - time.monotonic())) or not _guard(op):
            return
        if not _volume(op, value):
            return
    if not _guard(op):
        return
    finish(op, 'playing', 'speaker_reported_playing', data.get('observed_at'))


def run_off(op: Operation, fade_out_duration: float = 60) -> None:
    """Preserve existing OFF semantics, but never act after detected takeover."""
    if not current(op):
        return
    if op['mode'] == 'recovery_cancel':
        finish(op, 'completed', 'radio_recovery_canceled_no_speaker_command')
        return
    protected_station = op['mode'] == 'native_station_off'
    op['mode'] = 'off'
    finish(op, 'starting', 'checking_speaker')
    if _resolve(op) is None:
        return
    from app.core import radio_relay, relay_playback
    session = radio_relay.for_device(op['device_id'])
    if session is not None and session['owner'] == op['outcome']['operation_id']:
        relay_playback.run_off(op, session, fade_out_duration)
        return
    data = _read(op)
    if data is None:
        return
    if data.get('status', '').upper() == 'STANDBY':
        finish(op, 'skipped', 'already_standby', data.get('observed_at'))
        return
    if protected_station and not matches(op['expected'] or {}, data):
        finish(op, 'canceled', 'radio_station_changed')
        return
    previous_volume = op['expected_volume']
    op['initial_state'] = data.get('status', '').upper()
    op['expected'] = data.get('content_identity') or {'source': data.get('source_type', '')}
    ip = _address(op)
    if ip is None:
        return
    volume = status.get_volume(ip, timeout=_budget(op))
    if volume is None:
        finish(op, 'unknown', 'volume_observation_unavailable')
        return
    if protected_station and volume != previous_volume:
        finish(op, 'canceled', 'volume_changed')
        return
    op['expected_volume'] = volume
    op['verified'] = True
    duration = min(MAX_FADE_SECONDS, max(0.0, fade_out_duration))
    op['deadline'] = time.monotonic() + duration + 120.0
    fade_started = time.monotonic()
    for value in range(volume - 1, -1, -1) if duration > 0 else []:
        due = fade_started + duration * (volume - value) / max(volume, 1)
        if not wait(op, max(0.0, due - time.monotonic())) or not _guard(op):
            return
        if not _volume(op, value):
            return
    if not _guard(op):
        return
    if not _write(op, lambda ip: control.power_action(ip, timeout=_budget(op, 3.0))):
        return
    data = _read(op)
    if data and data.get('status', '').upper() == 'STANDBY':
        finish(op, 'completed', 'speaker_reported_standby', data.get('observed_at'))
    elif data:
        finish(op, 'unknown', 'standby_not_verified', data.get('observed_at'))
