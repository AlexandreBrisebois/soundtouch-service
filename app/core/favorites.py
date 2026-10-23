"""Durable favorites, expiring browse selections, and explicit preset programming.

Single-process local service, like the existing schedule writer. No automatic
repair/retry, registration, network changes, preset rollback or media fetching.
"""
import copy
import ipaddress
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import discovery, library, playback, status

_lock = threading.RLock()
_tokens: dict[str, dict[str, Any]] = {}
TTL = 900.0
MAX_TOKENS = 1000
MAX_STORAGE_BYTES = 2_000_000


class FavoriteError(ValueError):
    pass


def path() -> Path:
    return Path(os.getenv('FAVORITES_FILE', str(Path(os.getenv('CONFIG_FILE', 'config.json')).with_name('favorites.json'))))


def _load() -> dict[str, Any]:
    try:
        if not path().exists():
            return {'version': 1, 'favorites': {}}
        if path().stat().st_size > MAX_STORAGE_BYTES:
            raise ValueError('Oversize')
        value = json.loads(path().read_text())
        if value.get('version') != 1 or not isinstance(value.get('favorites'), dict):
            raise ValueError('Schema')
        if not isinstance(value.get('stations', {}), dict):
            raise ValueError('Station schema')
        return value
    except (OSError, ValueError, TypeError, AttributeError):
        raise FavoriteError('Favorites could not be read. Restore the file before making changes.') from None


def _save(value: dict[str, Any]) -> None:
    dest = path()
    temp = None
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized.encode('utf-8')) > MAX_STORAGE_BYTES:
        raise FavoriteError('Favorite storage is full. Existing saved data was not replaced.')
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=dest.parent,
                                         prefix='.favorites-', delete=False) as output:
            temp = output.name
            output.write(serialized)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, dest)
    except OSError:
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass
        raise FavoriteError('Favorites could not be saved. Check writable storage.') from None


def _token(kind: str, device_id: str, value: Any) -> str:
    now = time.monotonic()
    with _lock:
        for key in list(_tokens):
            if _tokens[key]['expires'] <= now:
                del _tokens[key]
        while len(_tokens) >= MAX_TOKENS:
            del _tokens[next(iter(_tokens))]
        key = uuid.uuid4().hex
        _tokens[key] = {'kind': kind, 'device_id': device_id, 'value': copy.deepcopy(value), 'expires': now + TTL}
        return key


def _lookup(key: str, kind: str, device_id: str) -> Any:
    with _lock:
        token = _tokens.get(key)
        if not token or token['kind'] != kind or token['device_id'] != device_id or token['expires'] <= time.monotonic():
            raise FavoriteError('This selection expired or belongs to another speaker. Refresh and choose again.')
        return copy.deepcopy(token['value'])


def device(speaker: str, device_id: str | None = None) -> dict[str, str]:
    found = discovery.resolve_device(speaker, device_id)
    if not found or not found.get('device_id'):
        raise FavoriteError('Speaker identity is unavailable. Refresh the speaker list.')
    live_id = status.get_device_id(found['ip'])
    if not live_id:
        raise FavoriteError('Speaker did not answer identity verification. Check its connection in the Bose app, then retry.')
    if live_id != found['device_id']:
        raise FavoriteError('Speaker identity changed. Refresh the speaker list and select it again.')
    return found


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value):
        raise FavoriteError('Use a name between 1 and 160 characters.')
    return value.strip()


def _safe_url(value: Any, *, base: bool = False) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(ord(c) <= 32 for c in value):
        raise FavoriteError('Enter a plain HTTP or HTTPS audio stream URL.')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise FavoriteError('Invalid URL.') from None
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise FavoriteError('Use an HTTP(S) URL without credentials, query tokens or fragments.')
    hostname = parsed.hostname.lower()
    allowed = {host.strip().lower() for host in os.getenv('WISP_RADIO_ALLOWED_HOSTS', '').split(',') if host.strip()}
    if not base and hostname not in allowed:
        try:
            if not ipaddress.ip_address(hostname).is_global:
                raise FavoriteError('LAN stream hosts must be explicitly configured in WISP_RADIO_ALLOWED_HOSTS.')
        except ValueError as exc:
            if isinstance(exc, FavoriteError):
                raise
            if hostname == 'localhost' or '.' not in hostname or hostname.endswith(('.local', '.internal', '.localhost')):
                raise FavoriteError('LAN stream hosts must be explicitly configured in WISP_RADIO_ALLOWED_HOSTS.') from None
        if port not in (None, 80, 443):
            raise FavoriteError('Nonstandard stream hosts must be explicitly configured in WISP_RADIO_ALLOWED_HOSTS.')
    if base and parsed.path not in ('', '/'):
        raise FavoriteError('WISP_BASE_URL must be an origin without a path.')
    return value.rstrip('/') if base else value


def radio_base() -> str | None:
    value = os.getenv('WISP_BASE_URL', '')
    return _safe_url(value, base=True) if value else None


def public(favorite: dict[str, Any]) -> dict[str, Any]:
    return {key: favorite.get(key) for key in ('id', 'name', 'kind', 'slot', 'speaker_id', 'state')}


def _source(ip: str, source_id: str) -> dict[str, Any]:
    matches = [s for s in library.read_sources(ip) if s['id'] == source_id and s['source'] == 'STORED_MUSIC']
    if len(matches) != 1 or not matches[0]['ready'] or not matches[0]['account']:
        raise FavoriteError('This NAS source is not ready on the speaker. No account is registered automatically.')
    return matches[0]


def capabilities(ip: str) -> set[str]:
    root = status._get_xml(ip, 'supportedURLs', 'supportedURLs')
    if root is None:
        return set()
    return {item.get('location', '') for item in root.findall('URL')}


def overview(speaker: str) -> dict[str, Any]:
    found = device(speaker)
    sources = library.read_sources(found['ip'])
    slots = library.read_presets(found['ip'])
    with _lock:
        saved = []
        for favorite in _load()['favorites'].values():
            if favorite.get('speaker_id') != found['device_id']:
                continue
            visible = public(favorite)
            assigned = slots.get(favorite.get('slot'))
            if favorite.get('state') == 'readback_matched' and not library.same_content(assigned, favorite['content']):
                visible['state'] = 'mismatch'
            saved.append(visible)
    base = radio_base()
    ready = any(s['source'] == 'LOCAL_INTERNET_RADIO' and s['ready'] for s in sources)
    supported = capabilities(found['ip'])
    return {'favorites': saved, 'speaker_id': found['device_id'],
            'external_playback': library.external_playback(sources),
            'sources': [{k: s[k] for k in ('id', 'name', 'ready')} for s in sources if s['source'] == 'STORED_MUSIC'],
            'presets': [{'slot': slot, 'name': item['name'] if item else 'Empty'} for slot, item in slots.items()],
            'radio': {'available': False, 'reason': 'Radio plays from Wisp without changing a physical speaker button.',
                      'native_preset': {'available': False, 'blockers': ['radio_preset_assignment_unsupported']},
                      'station_playback': {'available': bool(base and ready and '/select' in supported),
                                           'requires_source': 'LOCAL_INTERNET_RADIO'},
                      'direct_test': {'experimental': True, 'requires_explicit_risk_acceptance': True,
                                      'quiet_start_guaranteed': False, 'automatic_schedules': False,
                                      'physical_presets': False}}}


def browse(speaker: str, data: dict[str, Any]) -> dict[str, Any]:
    found = device(speaker)
    source = _source(found['ip'], str(data.get('source_id', '')))
    start = data.get('start', 1)
    if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 1000000:
        raise FavoriteError('Invalid browse page.')
    container = _lookup(str(data['container_id']), 'item', found['device_id']) if data.get('container_id') else None
    if container and (not container.get('is_dir') or container.get('sourceAccount') != source['account']):
        raise FavoriteError('Choose a folder from this source.')
    result = library.navigate(found['ip'], source, container, start)
    items = []
    for item in result['items']:
        key = _token('item', found['device_id'], item)
        items.append({'id': key, **{k: item[k] for k in ('name', 'is_dir', 'playable', 'presetable')}})
    return {**result, 'items': items}


def plan(speaker: str, data: dict[str, Any]) -> dict[str, Any]:
    if 'station_id' in data or 'radio_url' in data:
        raise FavoriteError('Radio stations play from Wisp and cannot be assigned to a physical speaker button.')
    found = device(speaker)
    slot = data.get('slot')
    if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 6:
        raise FavoriteError('Choose a speaker button from 1 to 6.')
    name = _name(data.get('name'))
    kind = 'nas'
    item = _lookup(str(data.get('item_id', '')), 'item', found['device_id'])
    if (item.get('source') != 'STORED_MUSIC' or not item.get('playable')
            or not item.get('presetable') or not item.get('is_dir')):
        raise FavoriteError('Choose a playable, preset-capable folder or playlist reported by the speaker.')
    favorite_id = uuid.uuid4().hex
    # Refresh source readiness; do not trust an earlier browse page.
    _source(found['ip'], library.source_id('STORED_MUSIC:' + item['sourceAccount']))
    if '/storePreset' not in capabilities(found['ip']):
        raise FavoriteError('Speaker does not advertise native preset programming. Existing buttons are unchanged.')
    slots = library.read_presets(found['ip'])
    # Some firmware moves identical assignments, clearing their former slot.
    if any(existing and library.same_content(existing, item) for key, existing in slots.items() if key != slot):
        raise FavoriteError('This collection is already assigned to another button. Use that button instead to preserve existing presets.')
    value = {'id': favorite_id, 'name': name, 'kind': kind, 'speaker_id': found['device_id'], 'slot': slot,
             'state': 'saved', 'content': item, 'before': slots}
    previous = slots[slot]
    plan_id = _token('plan', found['device_id'], value)
    return {'plan_id': plan_id, 'name': name, 'slot': slot,
            'replaces': previous['name'] if previous else 'Empty',
            'warning': 'This changes the physical speaker button. It does not start audio. Existing automation fades will be canceled. Hardware playback must be tested separately.'}


def confirm(speaker: str, plan_id: str) -> dict[str, Any]:
    found = device(speaker)
    with _lock:
        value = _lookup(plan_id, 'plan', found['device_id'])
        # A submitted plan is single-use, including ambiguous failures.
        del _tokens[plan_id]
    result: dict[str, Any] = {'state': 'unknown', 'message': 'Programming was not confirmed. Refresh before trying again.'}

    def program(ip: str) -> bool:
        if status.get_device_id(ip) != value['speaker_id']:
            raise FavoriteError('Speaker changed. No preset was programmed.')
        before = library.read_presets(ip)
        if any(not library.same_content(item, value['before'].get(slot)) for slot, item in before.items()):
            raise FavoriteError('Presets changed since the preview. Review them again before overwriting.')
        sources = library.read_sources(ip)
        content = value['content']
        if not any(s['source'] == content['source'] and s['ready'] and (s['source'] != 'STORED_MUSIC' or s['account'] == content.get('sourceAccount')) for s in sources):
            raise FavoriteError('Music source is no longer ready. No preset was programmed.')
        if '/storePreset' not in capabilities(ip):
            raise FavoriteError('Preset programming capability is unavailable.')
        value.pop('before')
        value['state'] = 'unknown'
        # Durable intent is written before the device command. Restart cannot turn
        # an ambiguous write into confirmed success or silently replay it.
        with _lock:
            document = _load()
            if len(document['favorites']) >= 500:
                raise FavoriteError('Favorite storage is full. No preset was programmed.')
            document['favorites'][value['id']] = value
            _save(document)
        acknowledged = library.store_preset(ip, value['slot'], content)
        try:
            after = library.read_presets(ip)
        except ValueError:
            after = None
        collateral = False
        if after is not None:
            collateral = any(not library.same_content(item, after.get(slot)) for slot, item in before.items() if slot != value['slot'])
        selected = after.get(value['slot']) if after is not None else None
        matched = library.same_content(selected, content)
        value['state'] = 'readback_matched' if acknowledged and matched and not collateral else 'unknown'
        with _lock:
            document = _load()
            if value['state'] == 'readback_matched':
                for previous in document['favorites'].values():
                    if previous.get('speaker_id') == value['speaker_id'] and previous.get('slot') == value['slot']:
                        previous['state'] = 'superseded'
            document['favorites'][value['id']] = value
            try:
                _save(document)
            except FavoriteError:
                result.update(favorite=public({**value, 'state': 'unknown'}), state='unknown',
                              message='Speaker may have changed, but final confirmation could not be saved. Inspect the buttons; do not retry blindly.')
                return True
        result.update(favorite=public(value), state=value['state'], message=(
            'Speaker preset readback matched. Test the physical button and scheduled playback separately.' if value['state'] == 'readback_matched' else
            'Another preset changed too. Inspect all speaker buttons; Wisp will not automatically restore or retry.' if collateral else
            'Assignment could not be confirmed. It may have changed; refresh and inspect before retrying.'))
        return True

    playback.manual(speaker, program)
    return result


def get(favorite_id: str) -> dict[str, Any]:
    with _lock:
        value = _load()['favorites'].get(favorite_id)
        if not isinstance(value, dict):
            raise FavoriteError('Favorite not found.')
        return copy.deepcopy(value)


def schedule_binding(favorite_id: str, speaker: str) -> dict[str, Any]:
    value = get(favorite_id)
    found = device(speaker)
    if value.get('state') != 'readback_matched' or value.get('speaker_id') != found['device_id']:
        raise FavoriteError('Only readback-matched favorites for this speaker can be scheduled.')
    assigned = library.read_presets(found['ip']).get(value['slot'])
    if not library.same_content(assigned, value['content']):
        raise FavoriteError('The speaker button has changed. Review its assignment before scheduling.')
    return value


def descriptor(favorite_id: str) -> dict[str, Any]:
    value = get(favorite_id)
    if value.get('kind') != 'radio':
        raise FavoriteError('Radio favorite not found.')
    stream = {'hasPlaylist': True, 'isRealtime': True, 'streamUrl': _safe_url(value['radio_url'])}
    return {'artist': {}, 'audio': {**stream, 'streams': [stream]}, 'imageUrl': '',
            'name': value['name'], 'streamType': 'liveRadio'}


REMOVAL_NOTICE = 'Remove from the station library only. Existing speaker presets, schedules and current audio stay intact. Playback metadata is retained privately so those links keep working.'


def stations(*, seed_warnings: list[str] | None = None) -> list[dict[str, Any]]:
    with _lock:
        document = _load()
        try:
            document = _seed_stations(copy.deepcopy(document))
        except FavoriteError as exc:
            # A seed failure must not disable existing records or playback links.
            if seed_warnings is not None:
                seed_warnings.append(str(exc))
        return [copy.deepcopy(value) for value in document.get('stations', {}).values() if not value.get('removed')]


def add_station(name: Any, url: Any) -> dict[str, Any]:
    value = {'id': uuid.uuid4().hex, 'name': _name(name), 'url': _safe_url(url)}
    with _lock:
        document = _load()
        entries = document.setdefault('stations', {})
        existing = next((item for item in entries.values() if not item.get('removed') and item['url'] == value['url']), None)
        if existing:
            raise FavoriteError('That stream is already in your station library.')
        if len(entries) >= 500:
            raise FavoriteError('Station storage is full. No station was added.')
        entries[value['id']] = value
        _save(document)
    return copy.deepcopy(value)


def _seed_stations(document: dict[str, Any]) -> dict[str, Any]:
    """Apply the bundled library seed once, including upgrades from empty stores.

    Called under _lock only when listing the station library. Archived entries participate in
    deduplication, so an earlier deliberate removal is never resurrected.
    """
    if document.get('station_seed_version') is not None:
        return document
    try:
        seed = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'stations.seed.json').read_text(encoding='utf-8'))
        if seed['version'] != 1 or not isinstance(seed['stations'], list):
            raise ValueError('Seed schema')
        entries = document.setdefault('stations', {})
        urls = {item['url'] for item in entries.values()}
        names = {item['name'].strip().casefold() for item in entries.values()}
        additions = []
        for item in seed['stations']:
            name, url = _name(item['name']), _safe_url(item['url'])
            if url in urls or name.casefold() in names:
                continue
            additions.append({'id': uuid.uuid4().hex, 'name': name, 'url': url})
            urls.add(url)
            names.add(name.casefold())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise FavoriteError('Station seed could not be loaded. Existing saved data was not replaced.') from None
    if len(entries) + len(additions) > 500:
        raise FavoriteError('Station storage is full. The seed was not applied; existing saved data was not replaced.')
    entries.update({item['id']: item for item in additions})
    document['station_seed_version'] = 1
    _save(document)
    return document


def station(station_id: str, *, allow_removed: bool = False) -> dict[str, Any]:
    with _lock:
        value = _load().get('stations', {}).get(station_id)
        if not isinstance(value, dict) or (value.get('removed') and not allow_removed):
            raise FavoriteError('Station not found in the library.')
        return copy.deepcopy(value)


def remove_station(station_id: str) -> None:
    with _lock:
        document = _load()
        value = document.get('stations', {}).get(station_id)
        if not isinstance(value, dict) or value.get('removed'):
            raise FavoriteError('Station not found in the library.')
        # Speakers may refetch descriptors after a library removal. Archive the
        # record; never erase a live device reference or issue a device command.
        value['removed'] = True
        _save(document)


def station_content(station_id: str, *, allow_removed: bool = False) -> dict[str, Any]:
    value = station(station_id, allow_removed=allow_removed)
    base = radio_base()
    if not base:
        raise FavoriteError('Configure a stable WISP_BASE_URL reachable by the speaker before playing radio.')
    return {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl', 'presetable': True,
            'name': value['name'], 'location': f'{base}/api/stations/{station_id}/stream'}


def station_descriptor(station_id: str) -> dict[str, Any]:
    value = station(station_id, allow_removed=True)
    stream = {'hasPlaylist': True, 'isRealtime': True, 'streamUrl': _safe_url(value['url'])}
    return {'artist': {}, 'audio': {**stream, 'streams': [stream]}, 'imageUrl': '',
            'name': value['name'], 'streamType': 'liveRadio'}
