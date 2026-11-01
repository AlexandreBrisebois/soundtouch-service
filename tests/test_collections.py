"""Offline native collection resolution and composed API contracts."""
import copy
import xml.etree.ElementTree as ET
import pytest
from flask import Flask
from app.api.collections import collections_bp
from app.core import collections, favorites, library, music_libraries

ACCOUNT = 'server/0'
LIBRARY = music_libraries.library_id(ACCOUNT)
DEVICE = {'name': 'Room', 'device_id': 'ABC', 'ip': '192.0.2.1'}
ITEM = {'source': 'STORED_MUSIC', 'sourceAccount': ACCOUNT, 'location': 'original',
        'type': 'dir', 'name': 'Calm', 'playable': True, 'presetable': True, 'is_dir': True,
        'is_collection': True, 'preview_available': True}
BINDING = {'version': 1, 'library_id': LIBRARY, 'speaker_id': 'ABC',
           'content': ITEM, 'ancestors': []}


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    favorites._tokens.clear()
    monkeypatch.setattr(favorites, 'device', lambda *args: copy.deepcopy(DEVICE))
    monkeypatch.setattr(library, 'read_sources', lambda ip: [{'source': 'STORED_MUSIC',
        'account': ACCOUNT, 'name': 'NAS', 'ready': True}])
    monkeypatch.setattr(library, 'navigate', lambda *args: {'items': [copy.deepcopy(ITEM)],
        'total': 1, 'start': 1, 'next_start': None})
    monkeypatch.setattr(music_libraries, 'get', lambda key: {'name': 'Shared music', 'observations': {
        'ABC': {'speaker': 'Room', 'state': 'ready'}}})
    app = Flask(__name__)
    app.register_blueprint(collections_bp)
    return app.test_client()


def test_browse_is_inspection_and_target_rebinds_native_identity(rig, monkeypatch):
    page = rig.post('/api/collections/browse', json={'library_id': LIBRARY}).json
    assert page['speaker'] == 'Room' and page['current']['name'] == 'NAS'
    token = page['items'][0]['id']
    monkeypatch.setattr(favorites, 'device', lambda *args: {**DEVICE, 'device_id': 'XYZ'})
    monkeypatch.setattr(library, 'navigate', lambda *args: {'items': [{**ITEM, 'location': 'target-token'}],
        'total': 1, 'start': 1, 'next_start': None})
    selected = rig.post('/api/collections/resolve', json={'library_id': LIBRARY,
                         'item_id': token, 'speaker': 'Other'}).json
    assert selected['collection']['content']['location'] == 'target-token'
    assert selected['speaker_id'] == 'XYZ'
    assert selected['collection']['library_name'] == 'Shared music'
    assert collections.validate_binding(selected['collection'])['library_name'] == 'Shared music'
    assert favorites._lookup(selected['browse_item_id'], 'item', 'XYZ')['location'] == 'target-token'
    with pytest.raises(ValueError, match='another speaker'):
        favorites._lookup(selected['browse_item_id'], 'item', 'ABC')


def test_resolution_survives_token_clear_but_rejects_missing_or_duplicate(rig, monkeypatch):
    favorites._tokens.clear()
    assert collections.resolve(BINDING, 'Room')['location'] == ITEM['location']
    for items in ([], [ITEM, ITEM]):
        monkeypatch.setattr(library, 'navigate', lambda *args, items=items: {
            'items': items, 'next_start': None})
        with pytest.raises(ValueError, match='missing or ambiguous'):
            collections.resolve(BINDING, 'Room')


def test_target_identity_and_registration_fail_without_any_selection(rig, monkeypatch):
    monkeypatch.setattr(favorites, 'device', lambda *args: {**DEVICE, 'device_id': 'other'})
    with pytest.raises(ValueError, match='identity changed'):
        collections.resolve(BINDING, 'Room')
    monkeypatch.setattr(favorites, 'device', lambda *args: DEVICE)
    monkeypatch.setattr(library, 'read_sources', lambda ip: [])
    with pytest.raises(ValueError, match='not registered'):
        collections.resolve(BINDING, 'Room')


@pytest.mark.parametrize('change', [{'version': 2}, {'version': True}, {'library_id': 'wrong'},
    {'speaker_id': ''}, {'ancestors': 'not-a-list'}, {'content': {**ITEM, 'type': 'track'}},
    {'content': {**ITEM, 'playable': False}}, {'content': {**ITEM, 'source': 'AUX'}}])
def test_unsupported_bindings_never_become_preset(rig, change):
    with pytest.raises(ValueError):
        collections.validate_binding({**BINDING, **change})


def test_playlist_without_preview_keeps_actions_and_network_failure_is_not_empty(rig, monkeypatch):
    playlist = {**ITEM, 'type': 'playlist', 'is_dir': False, 'preview_available': False}
    key = favorites._token('collection', LIBRARY, {**BINDING, 'content': playlist})
    result = collections.browse({'library_id': LIBRARY, 'container_id': key})
    assert result['preview_unavailable'] and result['total'] is None
    monkeypatch.setattr(library, 'navigate', lambda *args: (_ for _ in ()).throw(ValueError('network failure')))
    with pytest.raises(ValueError, match='network failure'):
        collections.browse({'library_id': LIBRARY})


def test_play_is_explicit_and_only_queues_direct_collection(rig, monkeypatch):
    from app.api import collections as api
    calls = []
    monkeypatch.setattr(api.jobs, 'queue_on', lambda *args, **kw: calls.append((args, kw)) or {'state': 'accepted'})
    data = {'collection': BINDING, 'speaker_id': 'ABC', 'volume': 8, 'confirmed': True}
    assert rig.post('/api/Room/collections/play', json={**data, 'confirmed': False}).status_code == 400
    assert rig.post('/api/Room/collections/play', json={**data, 'volume': True}).status_code == 400
    assert calls == []
    assert rig.post('/api/Room/collections/play', json=data).status_code == 202
    schedule = calls[0][0][1]
    assert 'preset' not in schedule and 'favorite_id' not in schedule
    assert schedule['collection']['library_id'] == LIBRARY and calls[0][1]['force'] is True


def test_stale_stop_is_conflict_and_does_not_use_generic_power(rig, monkeypatch):
    from app.api import collections as api
    monkeypatch.setattr(api.jobs, 'queue_collection_stop', lambda *args: None)
    response = rig.post('/api/Room/collections/stop', json={'speaker_id': 'ABC', 'operation_id': 'old'})
    assert response.status_code == 409


def test_parser_preserves_playlist_axes_and_native_request_type(monkeypatch):
    import requests
    def reply(body):
        result = requests.Response()
        result.status_code = 200
        result._content = body.encode()
        result._content_consumed = True
        return result
    body = '<navigateResponse source="STORED_MUSIC" sourceAccount="server/0"><totalItems>1</totalItems><items><item Playable="1" Navigable="0"><name>Playlist</name><type>playlist</type><ContentItem source="STORED_MUSIC" sourceAccount="server/0" location="native-playlist" isPresetable="false"/></item></items></navigateResponse>'
    calls=[]
    monkeypatch.setattr(library.command_session, 'post', lambda *a, **kw: calls.append(kw) or reply(body))
    item=library.navigate('fake', {'account': ACCOUNT}, {**ITEM,'type':'playlist'}, 1)['items'][0]
    assert item['is_collection'] and not item['is_dir'] and item['playable'] and not item['presetable']
    assert item['preview_available'] is False
    assert ET.fromstring(calls[0]['data']).findtext('item/type') == 'playlist'


def test_same_name_replacement_cannot_inherit_a_direct_schedule(rig, monkeypatch):
    monkeypatch.setattr(library, 'navigate', lambda *args: {
        'items': [{**ITEM, 'location': 'different-native-object'}], 'next_start': None})
    with pytest.raises(ValueError, match='identity changed'):
        collections.resolve(BINDING, 'Room')
