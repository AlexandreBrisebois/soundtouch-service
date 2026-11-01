"""Durable native collection intent; browse tokens never establish target access."""
import copy
import time
from typing import Any

from app.core import favorites, library, music_libraries

COLLECTION_TYPES = {'dir', 'folder', 'playlist'}


def _content(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict) or value.get('source') != 'STORED_MUSIC'
            or str(value.get('type', '')).lower() not in COLLECTION_TYPES
            or any(not isinstance(value.get(key), str) or not value[key]
                   or len(value[key]) > 2048 for key in ('sourceAccount', 'location', 'name'))):
        raise favorites.FavoriteError('Choose a valid native folder or playlist. No fallback source is used.')
    return {key: copy.deepcopy(value[key]) for key in
            ('source', 'sourceAccount', 'location', 'type', 'name', 'playable', 'presetable',
             'preview_available') if key in value}


def validate_binding(value: Any, speaker_name: str | None = None) -> dict[str, Any]:
    """Structural validation is intentionally usable during offline store reload."""
    if (not isinstance(value, dict) or value.get('version') != 1
            or isinstance(value.get('version'), bool)
            or any(not isinstance(value.get(key), str) or not value[key]
                   or len(value[key]) > 160 for key in ('library_id', 'speaker_id'))
            or not isinstance(value.get('ancestors'), list) or len(value['ancestors']) > 32):
        raise favorites.FavoriteError('Unsupported or incomplete collection binding. Replace music; no preset fallback is used.')
    result = {key: value[key] for key in ('version', 'library_id', 'speaker_id')}
    if isinstance(value.get('library_name'), str) and value['library_name'].strip():
        result['library_name'] = favorites._name(value['library_name'])
    result['content'] = _content(value.get('content'))
    result['ancestors'] = [_content(item) for item in value['ancestors']]
    if any(item['sourceAccount'] != result['content']['sourceAccount'] for item in result['ancestors']):
        raise favorites.FavoriteError('Collection hierarchy has conflicting source accounts.')
    if music_libraries.library_id(result['content']['sourceAccount']) != result['library_id']:
        raise favorites.FavoriteError('Collection does not belong to this library.')
    if result['content'].get('playable') is not True:
        raise favorites.FavoriteError('The speaker did not report this collection playable.')
    return result


def _source(found: dict[str, str], library_id: str) -> dict[str, Any]:
    matches = [item for item in library.read_sources(found['ip'])
               if item['source'] == 'STORED_MUSIC'
               and music_libraries.library_id(item['account']) == library_id]
    if len(matches) != 1 or not matches[0]['ready']:
        raise favorites.FavoriteError('This library is unavailable or not registered on the selected speaker. Check Again or Add Again.')
    return matches[0]


def _find(ip: str, source: dict[str, Any], parent: dict[str, Any] | None,
          wanted: dict[str, Any], deadline: float) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    start: int | None = 1
    # Bounded resolution must finish the search to exclude duplicate names.
    for _ in range(20):
        if start is None:
            break
        if time.monotonic() >= deadline:
            raise favorites.FavoriteError('Collection access check timed out. Retry or choose another speaker.')
        page = library.navigate(ip, source, parent, start)
        matches.extend(item for item in page['items']
                       if item.get('name') == wanted['name']
                       and str(item.get('type', '')).lower() == wanted['type'].lower())
        start = page['next_start']
    if start is not None:
        raise favorites.FavoriteError('Collection access could not be verified within the bounded browse. Refine the library hierarchy and retry.')
    if len(matches) != 1:
        raise favorites.FavoriteError('Collection is missing or ambiguous. Replace music; no other source was selected.')
    return matches[0]


def _resolve(value: dict[str, Any], speaker: str, *, rebind: bool = False) -> dict[str, Any]:
    found = favorites.device(speaker, None if rebind else value['speaker_id'])
    if not rebind and found['device_id'] != value['speaker_id']:
        raise favorites.FavoriteError('Speaker identity changed. Select and verify the speaker again.')
    source = _source(found, value['library_id'])
    parent = None
    ancestors = []
    deadline = time.monotonic() + 15
    for descriptor in [*value['ancestors'], value['content']]:
        item = _find(found['ip'], source, parent, descriptor, deadline)
        if found['device_id'] == value['speaker_id'] and not library.same_content(item, descriptor):
            raise favorites.FavoriteError('Collection identity changed. Replace music; no same-name replacement was selected.')
        if parent is not None:
            ancestors.append(parent)
        parent = item
    if parent is None or parent.get('playable') is not True:
        raise favorites.FavoriteError('This collection is no longer playable on the selected speaker.')
    return {'version': 1, 'library_id': value['library_id'], 'speaker_id': found['device_id'],
            'content': _content(parent), 'ancestors': [_content(item) for item in ancestors]}


def resolve(binding: Any, speaker_name: str) -> dict[str, Any]:
    return _resolve(validate_binding(binding), speaker_name)['content']


def choose(data: dict[str, Any]) -> dict[str, Any]:
    speaker = data.get('speaker')
    if not isinstance(speaker, str) or not speaker:
        raise favorites.FavoriteError('Choose a target speaker.')
    if data.get('collection') is not None:
        value = validate_binding(data['collection'])
    else:
        token = favorites._lookup(str(data.get('item_id', '')), 'collection', str(data.get('library_id', '')))
        value = validate_binding(token)
    if data.get('library_id') and value['library_id'] != data['library_id']:
        raise favorites.FavoriteError('Collection belongs to another library.')
    resolved = _resolve(value, speaker, rebind=True)
    record = music_libraries.get(value['library_id'])
    resolved['library_name'] = favorites._name(record.get('name') or value.get('library_name') or 'Music library')
    item = {**resolved['content'], 'is_dir': resolved['content']['type'].lower() in {'dir', 'folder'},
            'is_collection': True}
    key = favorites._token('item', resolved['speaker_id'], item)
    return {'collection': resolved, 'browse_item_id': key, 'speaker_id': resolved['speaker_id']}


def browse(data: dict[str, Any]) -> dict[str, Any]:
    library_id = data.get('library_id')
    if not isinstance(library_id, str) or not library_id:
        raise favorites.FavoriteError('Choose a music library.')
    speaker = data.get('speaker')
    if not speaker:
        record = music_libraries.get(library_id)
        ready = [item for item in record.get('observations', {}).values() if item.get('state') == 'ready']
        if not ready:
            raise favorites.FavoriteError('No ready speaker can browse this library. Check Again or Add Again.')
        speaker = ready[0]['speaker']
    found = favorites.device(speaker)
    source = _source(found, library_id)
    start = data.get('start', 1)
    if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 1000000:
        raise favorites.FavoriteError('Invalid browse page.')
    container = None
    ancestors: list[dict[str, Any]] = []
    if data.get('container_id'):
        value = favorites._lookup(str(data['container_id']), 'collection', library_id)
        if value['speaker_id'] != found['device_id']:
            raise favorites.FavoriteError('Browse context changed. Reopen the library.')
        container, ancestors = value['content'], value['ancestors']
        if str(container.get('type', '')).lower() not in COLLECTION_TYPES:
            raise favorites.FavoriteError('Individual tracks are inspect-only in this version.')
    current = {'name': container['name'] if container else source['name'],
               'path': ' / '.join([source['name'], *[item['name'] for item in ancestors],
                                   *([container['name']] if container else [])])}
    if container and container.get('preview_available') is False:
        return {'items': [], 'total': None, 'start': start, 'next_start': None,
                'preview_unavailable': True, 'current': current, 'speaker': speaker}
    page = library.navigate(found['ip'], source, container, start)
    items = []
    for item in page['items']:
        hierarchy = [*ancestors, *([container] if container else [])]
        value = {'version': 1, 'library_id': library_id, 'speaker_id': found['device_id'],
                 'content': item, 'ancestors': hierarchy}
        key = favorites._token('collection', library_id, value)
        items.append({'id': key, **{k: item.get(k) for k in
                      ('name', 'type', 'is_dir', 'is_collection', 'playable', 'presetable', 'preview_available')}})
    return {**page, 'items': items, 'current': current, 'speaker': speaker}
