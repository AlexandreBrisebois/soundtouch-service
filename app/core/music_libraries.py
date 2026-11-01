"""Speaker-native NAS discovery and explicit, reconciled registration changes.

All observation is read-only. Writes require a reviewed user action and never
retry themselves. State shares the existing atomic favorites store.
"""
import copy
import hashlib
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any

from requests.exceptions import RequestException

from app.core import discovery, favorites, library
from app.core.constants import SOUNDTOUCH_HTTP_PORT
from app.core.http_client import command_session, parse_speaker_xml, read_response_body

_operations = threading.RLock()
_candidates: dict[str, dict[str, Any]] = {}
_MAX_LIBRARIES = 500
_MAX_SPEAKERS = 64
WARNING = ('Remove this library registration from the selected speaker? Firmware may propagate '
           'this change to other speakers. Affected schedules will pause for review. '
           'Music files and physical buttons are not deleted or overwritten.')
GUIDANCE = ('Search Again after checking that the NAS music/DLNA service is enabled and '
            'allows the speaker on the same network. Discovery does not add a library.')


class LibraryError(ValueError):
    pass


def server_identity(value: str) -> str:
    """UDN/account equivalence only; display names and network addresses are not IDs."""
    if not isinstance(value, str) or not value or len(value) > 200:
        raise LibraryError('Library identity is missing or invalid. Search Again.')
    normalized = value.removeprefix('uuid:').removesuffix('/0')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', normalized):
        raise LibraryError('Library identity is missing or invalid. Search Again.')
    return normalized.lower()


def library_id(server_id: str) -> str:
    return hashlib.sha256(('nas:' + server_identity(server_id)).encode()).hexdigest()[:32]


def _records(document: dict[str, Any]) -> dict[str, Any]:
    records = document.get('music_libraries', {})
    if not isinstance(records, dict) or len(records) > _MAX_LIBRARIES:
        raise LibraryError('Music library data could not be read. Restore the store before changing it.')
    for key, item in records.items():
        if not isinstance(item, dict) or not isinstance(item.get('observations'), dict):
            raise LibraryError('Music library data could not be read. Restore the store before changing it.')
        if key != library_id(item.get('server_id', '')):
            raise LibraryError('Music library identity is invalid. Restore the store before changing it.')
    return records


def _new(server: str, name: str) -> dict[str, Any]:
    return {'id': library_id(server), 'server_id': server_identity(server),
            'name': favorites._name(name), 'added': False, 'observations': {}}


def _get(key: str) -> dict[str, Any]:
    with favorites._lock:
        stored = _records(favorites._load()).get(key)
        value = stored if stored is not None else _candidates.get(key)
        if value is None:
            raise LibraryError('This library is no longer selected. Search Again or Check Again.')
        return copy.deepcopy(value)


def get(key: str) -> dict[str, Any]:
    """Return a catalog record; no network request or mutation."""
    return _get(key)


def _save_record(value: dict[str, Any]) -> None:
    with favorites._lock:
        document = favorites._load()
        records = _records(document)
        if value['id'] not in records and len(records) >= _MAX_LIBRARIES:
            raise LibraryError('Music library storage is full. Existing records were retained.')
        records[value['id']] = copy.deepcopy(value)
        document['music_libraries'] = records
        favorites._save(document)


def _known_speakers() -> list[dict[str, str]]:
    speakers: dict[str, dict[str, str]] = {}
    for item in discovery.get_all_cached_devices():
        if item.get('device_id'):
            speakers[item['device_id']] = {'name': item['name'], 'device_id': item['device_id']}
    with favorites._lock:
        for record in _records(favorites._load()).values():
            for device_id, observation in record['observations'].items():
                speakers.setdefault(device_id, {'name': observation['speaker'], 'device_id': device_id})
    return list(speakers.values())


def listing() -> dict[str, Any]:
    with favorites._lock:
        records = copy.deepcopy(_records(favorites._load()))
    for key, candidate in _candidates.items():
        records.setdefault(key, copy.deepcopy(candidate))
    return {'libraries': list(records.values()), 'speakers': _known_speakers()}


def _response(found: dict[str, str], endpoint: str, data: bytes | None = None) -> ET.Element:
    if endpoint not in favorites.capabilities(found['ip']):
        raise LibraryError('The speaker does not support ' + endpoint + '. Selection was retained.')
    deadline = time.monotonic() + 5.0
    method = command_session.get if data is None else command_session.post
    kwargs: dict[str, Any] = {'timeout': (2.0, 3.0), 'allow_redirects': False,
                              'stream': True, 'headers': {'Accept-Encoding': 'identity'}}
    if data is not None:
        kwargs['data'] = data
        kwargs['headers']['Content-Type'] = 'application/xml'
    response = method(f'http://{found["ip"]}:{SOUNDTOUCH_HTTP_PORT}{endpoint}', **kwargs)
    try:
        body = read_response_body(response, deadline=deadline)
        expected = 'ListMediaServersResponse' if data is None else 'status'
        try:
            parsed = parse_speaker_xml(body, expected)
        except (ValueError, ET.ParseError):
            # Preserve a bounded device error code/name, never unvalidated XML or account text.
            code = re.search(rb'(?:code|name)=["\x27]([A-Z0-9_ -]{1,64})["\x27]', body)
            suffix = ': ' + code[1].decode('ascii') if code else ''
            raise LibraryError('Speaker reported a native library error' + suffix + '.') from None
        if data is not None and (parsed.text or '').strip() != endpoint:
            raise LibraryError('Speaker did not acknowledge ' + endpoint + '. Check Again before retrying.')
        return parsed
    finally:
        response.close()


def discover() -> dict[str, Any]:
    """Explicit native read; results remain transient until registration is requested."""
    errors = []
    with _operations:
        discovered: dict[str, dict[str, Any]] = {}
        for index, speaker in enumerate(_known_speakers()):
            if index >= _MAX_SPEAKERS:
                errors.append({'speaker': speaker['name'], 'reason': 'Native discovery read limit reached. Search Again with fewer known speakers.'})
                continue
            try:
                found = favorites.device(speaker['name'], speaker['device_id'])
                root = _response(found, '/listMediaServers')
                for entry in root.findall('media_server'):
                    raw_id = entry.get('id', '')
                    key = library_id(raw_id)
                    candidate = discovered.setdefault(key, _new(raw_id, entry.get('friendly_name') or 'Music library'))
                    candidate.setdefault('visible_to', []).append(speaker)
            except (ValueError, RequestException, ET.ParseError):
                errors.append({'speaker': speaker['name'], 'reason': 'Native library discovery failed. Check the speaker and try Search Again.'})
        _candidates.clear()
        _candidates.update(discovered)
        result = listing()
        # Stored libraries remain, with this discovery's visibility shown when observed.
        for item in result['libraries']:
            item['visible_to'] = discovered.get(item['id'], {}).get('visible_to', [])
        return {**result, 'discovered': list(discovered), 'errors': errors, 'guidance': GUIDANCE,
                'state': 'failed' if errors and not discovered else 'results' if discovered else 'empty'}


def _read_observation(record: dict[str, Any], speaker: dict[str, str]) -> dict[str, Any]:
    prior = record['observations'].get(speaker['device_id'], {})
    observation = {**prior, 'speaker': speaker['name'], 'state': 'unknown', 'stale': True,
                   'reason': 'Speaker registration could not be read. Check Again.'}
    try:
        found = favorites.device(speaker['name'], speaker['device_id'])
        matches = []
        for source in library.read_sources(found['ip']):
            if source['source'] == 'STORED_MUSIC' and source.get('account'):
                if server_identity(source['account']) == record['server_id']:
                    matches.append(source)
        if len(matches) > 1:
            raise LibraryError('Ambiguous registered source identity.')
        observation.update(observed_at=time.time(), stale=False, reason='')
        if matches:
            source = matches[0]
            observation.update(state='ready' if source['ready'] else 'unavailable',
                               account=source['account'], source_id=source['id'])
        else:
            observation.update(state='not_registered', account='', source_id='')
    except (ValueError, RequestException):
        pass
    return observation


def _reconcile(record: dict[str, Any], extra: dict[str, str] | None = None) -> dict[str, Any]:
    speakers = {s['device_id']: s for s in _known_speakers()}
    if extra:
        speakers[extra['device_id']] = {'name': extra['name'], 'device_id': extra['device_id']}
    for index, speaker in enumerate(speakers.values()):
        if index < _MAX_SPEAKERS:
            record['observations'][speaker['device_id']] = _read_observation(record, speaker)
        else:
            prior = record['observations'].get(speaker['device_id'], {})
            record['observations'][speaker['device_id']] = {**prior, 'speaker': speaker['name'],
                'state': 'unknown', 'stale': True, 'reason': 'Observation read limit reached. Check Again.'}
    pending = record.get('pending')
    if pending:
        target = record['observations'].get(pending['speaker_id'], {})
        wanted = target.get('state') in ('ready', 'unavailable') if pending['action'] == 'add' else target.get('state') == 'not_registered'
        pending['state'] = ('matched' if wanted else 'unknown' if target.get('state') == 'unknown'
                            else 'checking' if pending.get('acknowledged') else 'not_applied')
        if pending['action'] == 'add' and wanted:
            record['added'] = True
            if 'registration_epoch' not in pending:
                epochs = record.setdefault('registration_epochs', {})
                epochs[pending['speaker_id']] = epochs.get(pending['speaker_id'], 0) + 1
                pending['registration_epoch'] = epochs[pending['speaker_id']]
    removal_records = list(record.get('removal_reconciliations', []))
    if pending and pending['action'] == 'remove':
        removal_records.append(pending)
    for removal in removal_records:
        from app.scheduler import jobs
        for device_id, previous in removal.get('previous_accounts', {}).items():
            if device_id in removal.setdefault('reconciled_speakers', []):
                continue
            if record.get('registration_epochs', {}).get(device_id, 0) > removal.get('previous_epochs', {}).get(device_id, 0):
                removal['reconciled_speakers'].append(device_id)
                continue
            observed = record['observations'].get(device_id, {})
            if observed.get('state') == 'unknown':
                continue
            if observed.get('state') == 'not_registered':
                jobs.pause_source_schedules(device_id, source_account=previous, reason='library_removed')
                for slot in removal.get('previous_slots', {}).get(device_id, []):
                    jobs.pause_source_schedules(device_id, slot=slot, reason='library_removed')
                removal.setdefault('paused_speakers', []).append(device_id)
                removal['reconciled_speakers'].append(device_id)
            # A still-present registration does not settle possible delayed firmware
            # propagation. Retain it until observed absent or explicit Add starts a
            # newer registration epoch; no unproven propagation timeout is assumed.
    record['removal_reconciliations'] = [r for r in removal_records if r is not pending
        and set(r.get('previous_accounts', {})) - set(r.get('reconciled_speakers', []))]
    record['reconciliation_pending'] = sorted({device_id for r in removal_records
        for device_id in r.get('previous_accounts', {})
        if device_id not in r.get('reconciled_speakers', [])})
    if removal_records and record['observations'] and all(
            o['state'] == 'not_registered' for o in record['observations'].values()):
        record['added'] = False
    if any(o['state'] in ('ready', 'unavailable') for o in record['observations'].values()):
        record['added'] = True
    _save_record(record)
    return record


def check(key: str) -> dict[str, Any]:
    with _operations:
        record = _reconcile(_get(key))
        pending = record.get('pending', {})
        if pending.get('state') == 'not_applied':
            message = 'Readback found the requested change was not applied. Review and confirm an explicit retry.'
        elif pending.get('state') in ('unknown', 'checking'):
            message = 'Registration result remains unknown. Check Again before retrying.'
        elif pending.get('action') == 'remove' and pending.get('state') == 'matched':
            message = 'Removal observed. Affected schedules remain paused until review.'
        else:
            message = 'Availability checked. Missing registrations require explicit Add Again.'
        return _mutation_result(record, pending.get('speaker_id', ''), message)


def check_all() -> dict[str, Any]:
    """Startup/source refresh hook. Only observes; never registers or plays."""
    with _operations:
        # Import pre-existing native registrations, preserving current working NAS sources.
        for speaker in _known_speakers()[:_MAX_SPEAKERS]:
            try:
                found = favorites.device(speaker['name'], speaker['device_id'])
                for source in library.read_sources(found['ip']):
                    if source['source'] != 'STORED_MUSIC' or not source.get('account'):
                        continue
                    key = library_id(source['account'])
                    try:
                        record = _get(key)
                    except LibraryError:
                        record = _new(source['account'], source['name'])
                    record['added'] = True
                    record['observations'][speaker['device_id']] = {
                        'speaker': speaker['name'], 'state': 'ready' if source['ready'] else 'unavailable',
                        'account': source['account'], 'source_id': source['id'],
                        'observed_at': time.time(), 'stale': False, 'reason': ''}
                    _save_record(record)
            except (ValueError, RequestException):
                continue
        with favorites._lock:
            keys = list(_records(favorites._load()))
        for key in keys:
            check(key)
        return listing()


def _target(speaker: str, speaker_id: str) -> dict[str, str]:
    if not isinstance(speaker, str) or not speaker.strip() or not isinstance(speaker_id, str) or not speaker_id.strip():
        raise LibraryError('Choose a speaker with a verified identity.')
    return favorites.device(speaker, speaker_id)


def _mutation_result(record: dict[str, Any], speaker_id: str, message: str = '') -> dict[str, Any]:
    state = record['observations'].get(speaker_id, {}).get('state', 'unknown')
    pending = record.get('pending', {})
    if pending.get('state') in ('unknown', 'checking'):
        state = 'unknown'
    return {'library': record, 'state': state, 'message': message or (
        'Ready. Browse this library.' if state == 'ready' else
        'Added, Unavailable. Check Again.' if state == 'unavailable' else
        'Not registered. Explicit Add Again is available.' if state == 'not_registered' else
        'Unknown result. Check Again before retrying.'),
        'retry_allowed': pending.get('state') == 'not_applied'}


def _archive_removal(record: dict[str, Any]) -> None:
    pending = record.get('pending', {})
    if pending.get('action') == 'remove' and (
            set(pending.get('previous_accounts', {})) - set(pending.get('reconciled_speakers', []))):
        record.setdefault('removal_reconciliations', []).append(copy.deepcopy(pending))


def add(key: str, speaker: str, speaker_id: str, *, confirmed: bool, retry: bool = False) -> dict[str, Any]:
    if confirmed is not True:
        raise LibraryError('Confirm Add Library on the selected speaker first.')
    with _operations:
        found = _target(speaker, speaker_id)
        record = _get(key)
        if record.get('pending', {}).get('state') in ('unknown', 'checking', 'not_applied'):
            record = _reconcile(record, found)
            pending = record['pending']
            if pending['state'] in ('unknown', 'checking'):
                return _mutation_result(record, speaker_id)
            if pending['state'] == 'not_applied' and not retry:
                return _mutation_result(record, speaker_id, 'Readback complete. Retry requires explicit confirmation.')
        record = _reconcile(record, found)
        if record['observations'][speaker_id]['state'] in ('ready', 'unavailable', 'unknown'):
            return _mutation_result(record, speaker_id)
        if '/setMusicServiceAccount' not in favorites.capabilities(found['ip']):
            raise LibraryError('The speaker does not support native library registration. Selection was retained.')
        _archive_removal(record)
        record['pending'] = {'action': 'add', 'speaker_id': speaker_id, 'state': 'unknown', 'created_at': time.time()}
        _save_record(record)  # Before any native write; an unwritable store prevents mutation.
        credentials = ET.Element('credentials', source='STORED_MUSIC', displayName=record['name'])
        ET.SubElement(credentials, 'user').text = record['server_id'] + '/0'
        ET.SubElement(credentials, 'pass').text = ''
        error = ''
        try:
            found = _target(speaker, speaker_id)  # Reverify identity immediately before the write.
            _response(found, '/setMusicServiceAccount', ET.tostring(credentials, encoding='utf-8'))
            record['pending']['acknowledged'] = True
        except (ValueError, RequestException) as exc:
            error = str(exc) if isinstance(exc, LibraryError) else 'Native registration was not acknowledged.'
        record = _reconcile(record, found)
        return _mutation_result(record, speaker_id, error)


def _impacts(record: dict[str, Any]) -> tuple[list[Any], list[Any], list[str]]:
    from app.scheduler import jobs
    impacts, buttons, unknown = [], [], []
    for device_id, observation in record['observations'].items():
        if observation.get('state') == 'unknown':
            unknown.append(observation['speaker'])
            continue
        if not observation.get('account'):
            continue
        try:
            known = jobs.source_schedule_impacts(device_id, source_account=observation['account'])
            impacts.extend(known)
            if any(impact.get('impact_unknown') for impact in known):
                unknown.append(observation['speaker'])
            target = favorites.device(observation['speaker'], device_id)
            for slot, content in library.read_presets(target['ip']).items():
                if content and content.get('sourceAccount') == observation['account']:
                    buttons.append({'speaker': observation['speaker'], 'speaker_id': device_id,
                                    'slot': slot, 'name': content['name']})
        except (ValueError, RequestException):
            unknown.append(observation['speaker'])
    return impacts, buttons, unknown


def removal_plan(key: str, speaker: str, speaker_id: str) -> dict[str, Any]:
    with _operations:
        found = _target(speaker, speaker_id)
        record = _reconcile(_get(key), found)
        selected = record['observations'][speaker_id]
        if selected['state'] not in ('ready', 'unavailable') or not selected.get('account'):
            raise LibraryError('This registration cannot be verified. Check Again before removing it.')
        impacts, buttons, unknown = _impacts(record)
        value = {'library_id': key, 'speaker': speaker, 'speaker_id': speaker_id,
                 'account': selected['account'], 'previous_accounts': {
                     device_id: o['account'] for device_id, o in record['observations'].items() if o.get('account')},
                 'impacts': impacts, 'buttons': buttons, 'unknown_impacts': unknown}
        plan_id = favorites._token('library-removal', speaker_id, value)
        return {**value, 'plan_id': plan_id, 'library': record, 'warning': WARNING}


def remove(key: str, plan_id: str, *, confirmed: bool, retry: bool = False) -> dict[str, Any]:
    if not isinstance(plan_id, str) or not plan_id:
        raise LibraryError('Review a library removal plan before confirming.')
    if confirmed is not True:
        raise LibraryError('Confirm the displayed library removal and schedule impacts first.')
    with _operations:
        # Plan lookup is bound to its own hardware identity, then live identity is reverified.
        with favorites._lock:
            token = favorites._tokens.get(plan_id)
            device_id = token.get('device_id', '') if token else ''
        plan = favorites._lookup(plan_id, 'library-removal', device_id)
        if plan['library_id'] != key:
            raise LibraryError('This removal plan belongs to another library.')
        found = _target(plan['speaker'], plan['speaker_id'])
        record = _get(key)
        if record.get('pending', {}).get('state') in ('unknown', 'checking', 'not_applied'):
            record = _reconcile(record, found)
            if record['pending']['state'] in ('unknown', 'checking') or (record['pending']['state'] == 'not_applied' and not retry):
                return _mutation_result(record, plan['speaker_id'])
        record = _reconcile(record, found)
        selected = record['observations'][plan['speaker_id']]
        if selected['state'] == 'not_registered':
            return _mutation_result(record, plan['speaker_id'], 'Removal is already observed. No write was repeated.')
        if selected.get('state') == 'unknown' or selected.get('account') != plan['account']:
            raise LibraryError('Registration changed or became unavailable. Review a fresh removal plan.')
        impacts, buttons, unknown = _impacts(record)
        if (impacts != plan['impacts'] or buttons != plan['buttons'] or unknown != plan['unknown_impacts']):
            raise LibraryError('Removal impacts changed. Review a fresh removal plan before confirming.')
        if '/removeMusicServiceAccount' not in favorites.capabilities(found['ip']):
            raise LibraryError('The speaker does not support native registration removal.')
        _archive_removal(record)
        record['pending'] = {'action': 'remove', 'speaker_id': plan['speaker_id'], 'state': 'unknown',
                             'created_at': time.time(), 'previous_accounts': plan['previous_accounts'],
                             'previous_epochs': copy.deepcopy(record.get('registration_epochs', {})),
                             'paused_speakers': [], 'previous_slots': {
                                 device_id: [b['slot'] for b in plan['buttons'] if b['speaker_id'] == device_id]
                                 for device_id in plan['previous_accounts']}}
        _save_record(record)
        credentials = ET.Element('credentials', source='STORED_MUSIC', displayName=record['name'])
        ET.SubElement(credentials, 'user').text = plan['account']
        ET.SubElement(credentials, 'pass').text = ''
        error = ''
        try:
            found = _target(plan['speaker'], plan['speaker_id'])
            _response(found, '/removeMusicServiceAccount', ET.tostring(credentials, encoding='utf-8'))
            record['pending']['acknowledged'] = True
        except (ValueError, RequestException) as exc:
            error = str(exc) if isinstance(exc, LibraryError) else 'Native removal was not acknowledged.'
        record = _reconcile(record, found)
        if error:
            message = error
        elif record['pending']['state'] == 'matched':
            message = 'Removal observed. Affected schedules remain paused until review.'
        else:
            message = 'Removal accepted but not yet observed. Check Again; no write will be repeated automatically.'
        return _mutation_result(record, plan['speaker_id'], message)
