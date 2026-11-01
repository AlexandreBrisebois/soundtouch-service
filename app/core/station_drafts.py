"""Transient station tests using the existing guarded radio operation lifecycle.

No station is persisted before a matched PLAYING observation and verified Stop.
Drafts are bounded, process-local and never evicted while a speaker may refetch
its descriptor. A restart clears draft evidence; it does not certify a test.
"""
import copy
import threading
import time
import uuid
from typing import Any

from app.core import favorites, playback, radio_relay, status as speaker_status
from app.scheduler import jobs

_lock = threading.RLock()
_drafts: dict[str, dict[str, Any]] = {}
MAX_DRAFTS = 100
_STOP_REASONS = {'radio_stopped_verified', 'radio_stop_acknowledged_source_inactive'}


def _find(draft_id: str) -> dict[str, Any]:
    value = _drafts.get(draft_id)
    if value is None:
        raise favorites.FavoriteError('Station draft is unavailable. Keep the form and test again.')
    return value


def _public_operation(operation: dict[str, Any] | None) -> dict[str, Any] | None:
    if operation is None:
        return None
    allowed = {'operation_id', 'speaker_id', 'station_id', 'state', 'reason',
               'terminal', 'accepted_at', 'updated_at', 'observed_at',
               'stops_operation_id', 'radio_mode', 'target_volume',
               'physical_stop_may_be_needed', 'relay_active', 'listening_session',
               'recovery_state'}
    return {key: copy.deepcopy(value) for key, value in operation.items() if key in allowed}

def station(draft_id: str) -> dict[str, Any]:
    """Private descriptor lookup; drafts never appear in the saved library."""
    with _lock:
        value = _find(draft_id)
        return {**{key: value[key] for key in ('id', 'name', 'url')}, 'draft': True}


def create(name: Any, url: Any) -> dict[str, Any]:
    value: dict[str, Any] = {'id': uuid.uuid4().hex, 'name': favorites._name(name),
                             'url': favorites._safe_url(url), 'state': 'untested',
                             'observed_playing': False, 'stopped_verified': False}
    with _lock:
        if len(_drafts) >= MAX_DRAFTS:
            raise favorites.FavoriteError('Too many station drafts. Existing test sessions were retained; no station was saved.')
        _drafts[value['id']] = value
        return copy.deepcopy(value)


def _observe(value: dict[str, Any]) -> dict[str, Any] | None:
    speaker = value.get('speaker')
    latest = playback.last(speaker) if speaker else None
    if not latest:
        return None
    if (latest.get('station_id') != value['id']
            or latest.get('speaker_id') != value.get('speaker_id')):
        return None
    original = value.get('operation_id')
    if latest.get('operation_id') == original:
        if latest.get('state') == 'playing':
            value['observed_playing'] = True
        value['state'] = latest.get('state', 'unknown')
        return latest
    if (latest.get('operation_id') == value.get('stop_operation_id')
            and latest.get('stops_operation_id') == original):
        if (value['observed_playing'] and latest.get('state') == 'completed'
                and latest.get('reason') in _STOP_REASONS):
            value['stopped_verified'] = True
            value['state'] = 'stopped'
        else:
            value['state'] = latest.get('state', 'unknown')
        return latest
    return None


def _check_unknown_stop(value: dict[str, Any], operation: dict[str, Any] | None) -> None:
    """Read back an ambiguous STOP without issuing another speaker command."""
    if (not operation or operation.get('state') != 'unknown'
            or operation.get('operation_id') != value.get('stop_operation_id')
            or operation.get('stops_operation_id') != value.get('operation_id')
            or not value['observed_playing']):
        return
    try:
        found = favorites.device(value['speaker'], value['speaker_id'])
        started = time.time()
        observed = speaker_status.get_now_playing(found['ip'], timeout=3)
    except ValueError:
        return
    # Standby is independently conclusive even if the old source disappeared.
    # STOPPED on a different/unknown source is not evidence about this test.
    if (observed.get('device_id') != value['speaker_id']
            or observed.get('source_type') != 'STANDBY'
            or observed.get('status', '').upper() != 'STANDBY'
            or isinstance(observed.get('observed_at'), bool)
            or not isinstance(observed.get('observed_at'), (int, float))
            or not started <= observed['observed_at'] <= time.time()):
        return
    latest = playback.last(value['speaker'])
    if (latest and latest.get('operation_id') == value['stop_operation_id']
            and latest.get('stops_operation_id') == value['operation_id']
            and latest.get('speaker_id') == value['speaker_id']
            and latest.get('station_id') == value['id']):
        value.update(stopped_verified=True, state='stopped')

def _check_unknown_test(value: dict[str, Any], operation: dict[str, Any] | None) -> None:
    """Recover exact native playback or read back standby before explicit Retry."""
    if (not operation or operation.get('state') != 'unknown'
            or operation.get('operation_id') != value.get('operation_id')):
        return
    if playback.reconcile_station_session(value['speaker'], value['speaker_id'],
                                           value['id'], value['operation_id']):
        _observe(value)
        return
    try:
        found = favorites.device(value['speaker'], value['speaker_id'])
        started = time.time()
        observed = speaker_status.get_now_playing(found['ip'], timeout=3)
    except ValueError:
        return
    latest = playback.last(value['speaker'])
    if (observed.get('device_id') == value['speaker_id']
            and observed.get('source_type') == 'STANDBY'
            and observed.get('status', '').upper() == 'STANDBY'
            and not isinstance(observed.get('observed_at'), bool)
            and isinstance(observed.get('observed_at'), (int, float))
            and started <= observed['observed_at'] <= time.time() and latest
            and latest.get('operation_id') == value['operation_id']
            and latest.get('speaker_id') == value['speaker_id']
            and latest.get('station_id') == value['id']):
        value.update(retry_ready=True, state='test_unavailable')

def status(draft_id: str) -> dict[str, Any]:
    with _lock:
        value = _find(draft_id)
        operation = _observe(value)
        _check_unknown_test(value, operation)
        if value.get('state') == 'playing':
            operation = _observe(value)
        _check_unknown_stop(value, operation)
        return {'draft': copy.deepcopy(value), 'operation': _public_operation(operation),
                'can_save': bool(value['observed_playing'] and value['stopped_verified']
                                 and not value.get('saved_station_id'))}


def test(draft_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if data.get('confirmed') is not True:
        raise favorites.FavoriteError('Confirm that Test replaces current playback on the chosen speaker.')
    speaker, speaker_id = data.get('speaker'), data.get('speaker_id')
    if not isinstance(speaker, str) or not speaker.strip() or not isinstance(speaker_id, str) or not speaker_id:
        raise favorites.FavoriteError('Choose and refresh the speaker before Test.')
    found = favorites.device(speaker, speaker_id)
    if found['device_id'] != speaker_id:
        raise favorites.FavoriteError('Speaker identity changed. Select the speaker again.')
    with _lock:
        value = _find(draft_id)
        _observe(value)
        if value.get('saved_station_id'):
            raise favorites.FavoriteError('This draft was saved. Play the station from Radio.')
        if value.get('operation_id') and not value['stopped_verified'] and not value.get('retry_ready'):
            latest = playback.last(value['speaker'])
            if latest and latest.get('operation_id') in {value['operation_id'], value.get('stop_operation_id')}:
                if latest.get('state') not in {'failed', 'canceled', 'skipped'}:
                    raise favorites.FavoriteError('Check or stop the current test before retrying or choosing another speaker.')
        ready = radio_relay.readiness(value['url'], found['ip'])
        if not ready['available']:
            raise favorites.FavoriteError(ready['reason'])
        # Quiet volume is explicit here; listening=True reuses exact-session STOP
        # rather than introducing a second transport or generic power toggle.
        operation = jobs.queue_station(speaker, speaker_id, draft_id, 5, listening=True)
        if operation is None:
            raise jobs.StationWorkerUnavailable('Playback worker unavailable. No test was started.')
        value.update(speaker=speaker, speaker_id=speaker_id,
                     operation_id=operation['operation_id'], stop_operation_id=None,
                     observed_playing=False, stopped_verified=False, retry_ready=False, state='accepted')
        return {'draft': copy.deepcopy(value), 'operation': _public_operation(operation), 'state': 'accepted'}


def stop(draft_id: str, data: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        value = _find(draft_id)
        _observe(value)
        if (data.get('operation_id') != value.get('operation_id')
                or data.get('speaker_id') != value.get('speaker_id')
                or not value.get('observed_playing')):
            raise favorites.FavoriteError('Choose the current reported-playing test session before Stop.')
        operation = jobs.queue_station_stop(value['speaker'], value['speaker_id'],
                                             draft_id, value['operation_id'])
        if operation is None:
            raise favorites.FavoriteError('This test session is no longer current. Refresh its status.')
        value['stop_operation_id'] = operation['operation_id']
        value['state'] = 'stopping'
        return {'draft': copy.deepcopy(value), 'operation': _public_operation(operation), 'state': 'accepted'}


def save(draft_id: str, data: dict[str, Any]) -> dict[str, Any]:
    # Audible sound remains an explicit human observation, never inferred.
    if data.get('audible_confirmed') is not True:
        raise favorites.FavoriteError('Confirm you heard the intended station, then Stop before Save.')
    name, url = favorites._name(data.get('name')), favorites._safe_url(data.get('url'))
    with _lock:
        value = _find(draft_id)
        _observe(value)
        if url != value['url']:
            raise favorites.FavoriteError('The URL changed. Test the new stream before saving; your form is retained.')
        if (data.get('operation_id') != value.get('operation_id')
                or not value['observed_playing'] or not value['stopped_verified']):
            raise favorites.FavoriteError('Complete this stream test and verified Stop before Save.')
        if value.get('saved_station_id'):
            return favorites.station(value['saved_station_id'])
        saved = favorites.add_station(name, url)
        value.update(name=name, saved_station_id=saved['id'], state='saved')
        return saved
