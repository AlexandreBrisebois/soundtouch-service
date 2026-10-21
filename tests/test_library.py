import xml.etree.ElementTree as ET

import pytest
import requests
from app.core import library


def reply(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result._content_consumed = True
    return result


def test_navigate_uses_own_content_not_nested_parent(monkeypatch):
    body = '''<navigateResponse source="STORED_MUSIC" sourceAccount="server"><totalItems>2</totalItems><items>
    <item Playable="1"><name>My album</name><type>dir</type><ContentItem source="STORED_MUSIC" sourceAccount="server" location="opaque-child" isPresetable="true"/><mediaItemContainer><ContentItem source="STORED_MUSIC" sourceAccount="server" location="parent"/></mediaItemContainer></item>
    <item Playable="1"><name>Bad</name><type>dir</type><mediaItemContainer><ContentItem source="STORED_MUSIC" sourceAccount="server" location="parent"/></mediaItemContainer></item>
    </items></navigateResponse>'''
    calls = []
    monkeypatch.setattr(library.command_session, 'post', lambda *a, **kw: calls.append(kw) or reply(body))
    result = library.navigate('fake', {'account': 'server'}, None, 1)
    assert len(result['items']) == 1
    assert result['items'][0]['location'] == 'opaque-child'
    assert result['items'][0]['is_dir'] and result['items'][0]['presetable']
    assert result['next_start'] is None
    assert calls[0]['allow_redirects'] is False


@pytest.mark.parametrize('body,status', [('<error>bad</error>', 200), ('<navigateResponse/>', 200), ('<navigateResponse/>', 302)])
def test_invalid_browse_fail_closed(monkeypatch, body, status):
    monkeypatch.setattr(library.command_session, 'post', lambda *a, **kw: reply(body, status))
    with pytest.raises(ValueError, match='Cannot browse'):
        library.navigate('fake', {'account': 'server'}, None, 1)


@pytest.mark.parametrize('body,expected', [('<presets/>', True), ('<status>/storePreset</status>', True), ('', True), ('<error/>', False), ('<status>unknown</status>', False)])
def test_store_ack_is_bounded_not_a_playback_claim(monkeypatch, body, expected):
    calls = []
    monkeypatch.setattr(library.command_session, 'post', lambda *a, **kw: calls.append(kw) or reply(body))
    item = {'source': 'STORED_MUSIC', 'sourceAccount': 'server', 'location': 'opaque&folder', 'type': 'dir', 'name': '<calm>', 'presetable': True}
    assert library.store_preset('fake', 2, item) is expected
    xml = ET.fromstring(calls[0]['data'])
    assert xml.get('id') == '2'
    assert xml.find('ContentItem').get('location') == 'opaque&folder'
    assert xml.findtext('ContentItem/itemName') == '<calm>'
    assert calls[0]['allow_redirects'] is False


def test_incomplete_occupied_preset_is_not_empty(monkeypatch):
    monkeypatch.setattr(library.status, '_get_xml', lambda *a: ET.fromstring('<presets><preset id="1"><ContentItem source="STORED_MUSIC"/></preset></presets>'))
    with pytest.raises(ValueError, match='incomplete'):
        library.read_presets('fake')


def test_direct_select_uses_xml_and_never_store_preset(monkeypatch):
    from app.core import control
    calls = []
    monkeypatch.setattr(control, '_post_command', lambda *args, **kwargs: calls.append((args, kwargs)) or True)
    content = {'source': 'LOCAL_INTERNET_RADIO', 'type': 'stationurl', 'location': 'http://wisp/station', 'name': 'Jazz & calm', 'presetable': True}
    assert control.select_content('fake', content, timeout=1.2)
    args, kwargs = calls[0]
    assert args[1] == 'select'
    assert ET.fromstring(args[2]).findtext('itemName') == 'Jazz & calm'
    assert kwargs['timeout'] == 1.2
