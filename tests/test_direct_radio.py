"""Mock-only regression coverage for the observed SoundTouch 10 transitions."""
import copy
import xml.etree.ElementTree as ET

import pytest
from flask import Flask
from requests.exceptions import Timeout

from app.core import direct_radio as radio, playback, radio_stream, favorites
from app.api.favorites import favorites_bp
from app.scheduler import jobs

SAVED = next(iter(radio_stream.CANDIDATES))
URL = 'http://93.184.216.34/session.mp3'


@pytest.fixture
def device(monkeypatch):
    playback.reset()
    now = [100.0]
    rooms = {}
    calls = []
    monkeypatch.setattr(radio.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(radio_stream, 'resolve', lambda _: URL)
    monkeypatch.setattr(playback.discovery, 'resolve_device', lambda name, *a:
                        {'ip': name, 'device_id': name, 'name': name})
    monkeypatch.setattr(playback.status, 'get_device_id', lambda ip, **kw: ip)
    monkeypatch.setattr(radio, '_capabilities', lambda op: None)
    def room(ip):
        return rooms.setdefault(ip, {'source': 'STANDBY', 'bose': '', 'volume': 5,
                                    'target': 5, 'muted': 'false', 'uri': '',
                                    'state': 'STOPPED', 'status': 'OK', 'group': False})
    def get_xml(ip, path, root, **kw):
        d = room(ip)
        e = ET.Element(root, deviceID=ip)
        if path == 'getZone':
            if d['group']:
                e.set('master', 'another')
        elif path == 'volume':
            for key, value in [('actualvolume', d['volume']), ('targetvolume', d['target']),
                               ('muteenabled', d['muted'])]:
                ET.SubElement(e, key).text = str(value)
        elif path == 'now_playing':
            e.set('source', d['source'])
            ET.SubElement(e, 'playStatus').text = d['bose']
        return e
    monkeypatch.setattr(radio.status, '_get_xml', get_xml)
    def soap(ip, action, timeout, **args):
        d = room(ip)
        e = ET.Element('response')
        if action == 'SetAVTransportURI':
            calls.append((ip, action, args['CurrentURI']))
            d.update(uri=args['CurrentURI'], source='UPNP', bose='PLAY_STATE',
                     state='PLAYING', volume=10, target=10)
        elif action == 'GetPositionInfo':
            ET.SubElement(e, 'TrackURI').text = d['uri']
            ET.SubElement(e, 'CurrentURI').text = 'qplay://wrapper'
        elif action == 'GetTransportInfo':
            ET.SubElement(e, 'CurrentTransportState').text = d['state']
            ET.SubElement(e, 'CurrentTransportStatus').text = d['status']
        elif action == 'Stop':
            calls.append((ip, action))
            d.update(source='INVALID_SOURCE', bose='', state='PAUSED_PLAYBACK',
                     uri='http://different-dummy.example/no-audio.mp3')
        else:
            pytest.fail('Unexpected action: ' + action)
        return e
    monkeypatch.setattr(radio, '_soap', soap)
    def volume(ip, value, **kwargs):
        calls.append((ip, 'volume', value))
        room(ip).update(volume=value, target=value)
        return True
    monkeypatch.setattr(radio.control, 'set_volume', volume)
    def wait(op, delay):
        now[0] += delay
        return playback.current(op)
    monkeypatch.setattr(playback, 'wait', wait)
    yield room, calls, now
    playback.reset()


def run(name='A'):
    op = playback.begin(name, 'Direct radio test', name)
    radio.run(op, SAVED)
    return playback.last(name)


def test_real_observed_success_does_not_claim_stopped_or_audible(device):
    outcome = run()
    assert device[1] == [('A', 'SetAVTransportURI', URL), ('A', 'volume', 5), ('A', 'Stop')]
    assert outcome['state'] == 'completed'
    assert outcome['reason'] == 'direct_stop_acknowledged_source_inactive'
    assert outcome['audible_confirmed'] is False
    assert outcome['physical_stop_may_be_needed'] is False
    assert device[0]('A')['volume'] == 5  # no restoration


@pytest.mark.parametrize('field,value', [('source', 'STORED_MUSIC'), ('volume', 31),
                                         ('group', True), ('target', 7), ('muted', 'true')])
def test_preflight_fail_closed_without_selection(device, field, value):
    device[0]('A')[field] = value
    outcome = run()
    assert not device[1]
    assert outcome['state'] == 'unknown'
    assert outcome['physical_stop_may_be_needed'] is False


@pytest.mark.parametrize('source,bose', [('INVALID_SOURCE', ''), ('INVALID_SOURCE', 'UNKNOWN'),
                                       ('UPNP', 'STOP_STATE')])
def test_idle_states_are_accepted_for_manual_test(device, source, bose):
    device[0]('A').update(source=source, bose=bose)
    assert run()['state'] == 'completed'


def test_preflight_changes_inside_write_lock_refuse_selection(device, monkeypatch):
    original = radio._idle
    count = [0]
    def idle(op):
        count[0] += 1
        value = original(op)
        return value if count[0] == 1 else b'changed'
    monkeypatch.setattr(radio, '_idle', idle)
    assert run()['reason'] == 'direct_preflight_changed'
    assert not device[1]


@pytest.mark.parametrize('field,value', [('uri', 'http://elsewhere.example/a'), ('source', 'STORED_MUSIC'),
                                         ('volume', 6), ('target', 7), ('group', True),
                                         ('state', 'PAUSED_PLAYBACK'), ('status', 'ERROR_OCCURRED')])
def test_manual_changes_never_cause_restore_or_stale_stop(device, monkeypatch, field, value):
    def wait(op, delay):
        device[2][0] += delay
        device[0]('A')[field] = value
        return True
    monkeypatch.setattr(playback, 'wait', wait)
    outcome = run()
    assert device[1] == [('A', 'SetAVTransportURI', URL), ('A', 'volume', 5)]
    assert outcome['state'] == 'unknown'
    assert outcome['physical_stop_may_be_needed'] is True


def test_same_speaker_supersession_never_stops_new_owner(device, monkeypatch):
    def wait(op, delay):
        playback.begin('A', 'new manual action')
        return False
    monkeypatch.setattr(playback, 'wait', wait)
    run()
    assert device[1] == [('A', 'SetAVTransportURI', URL), ('A', 'volume', 5)]
    assert playback.last('A')['schedule_name'] == 'new manual action'


def test_two_different_speakers_are_independent(device, monkeypatch):
    original_wait = playback.wait
    started = [False]
    def wait(op, delay):
        if op['speaker'] == 'A' and not started[0]:
            started[0] = True
            assert run('B')['state'] == 'completed'
            assert playback.current(op)
        return original_wait(op, delay)
    monkeypatch.setattr(playback, 'wait', wait)
    assert run('A')['state'] == 'completed'
    for name in ('A', 'B'):
        assert [x[1] for x in device[1] if x[0] == name] == ['SetAVTransportURI', 'volume', 'Stop']


def test_uncertain_set_uri_not_retried_or_stopped(device, monkeypatch):
    original = radio._soap
    def soap(ip, action, timeout, **args):
        result = original(ip, action, timeout, **args)
        if action == 'SetAVTransportURI':
            raise Timeout
        return result
    monkeypatch.setattr(radio, '_soap', soap)
    outcome = run()
    assert device[1] == [('A', 'SetAVTransportURI', URL)]
    assert outcome['physical_stop_may_be_needed'] is True
    assert outcome['state'] == 'unknown'


def test_stop_ack_with_old_source_is_not_success(device, monkeypatch):
    original = radio._soap
    def soap(ip, action, timeout, **args):
        if action == 'Stop':
            device[1].append((ip, 'Stop'))
            return ET.Element('StopResponse')
        return original(ip, action, timeout, **args)
    monkeypatch.setattr(radio, '_soap', soap)
    outcome = run()
    assert outcome['reason'] == 'direct_stop_readback_unknown'
    assert device[1][-1] == ('A', 'Stop')
    assert outcome['physical_stop_may_be_needed'] is True


def test_strict_stopped_is_separate_from_observed_inactive(device, monkeypatch):
    original = radio._soap
    def soap(ip, action, timeout, **args):
        result = original(ip, action, timeout, **args)
        if action == 'Stop':
            device[0](ip).update(source='UPNP', uri=URL, bose='STOP_STATE', state='STOPPED')
        return result
    monkeypatch.setattr(radio, '_soap', soap)
    assert run()['reason'] == 'direct_stopped_verified'


def test_identity_loss_before_any_write_refuses(device, monkeypatch):
    monkeypatch.setattr(playback.status, 'get_device_id', lambda *a, **kw: 'OTHER')
    assert run()['state'] == 'unknown'
    assert not device[1]


@pytest.fixture
def api(monkeypatch):
    item = {'id': 'station', 'url': SAVED}
    calls = []
    monkeypatch.setattr(favorites, 'station', lambda _: copy.deepcopy(item))
    monkeypatch.setattr(favorites, 'device', lambda _: {'device_id': 'ABC'})
    monkeypatch.setattr(jobs, 'queue_direct_radio_test', lambda *args: calls.append(args) or {'state': 'accepted'})
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    return app.test_client(), item, calls


@pytest.mark.parametrize('body', [{}, {'confirmed': True}, {'accept_startup_volume_risk': True},
                                  {'confirmed': 1, 'accept_startup_volume_risk': True}])
def test_api_requires_both_explicit_risk_acceptances(api, body):
    response = api[0].post('/api/A/stations/station/direct-test', json=body)
    assert response.status_code == 400
    assert not api[2]


def test_api_uses_selected_station_and_preserves_native_route(api):
    response = api[0].post('/api/A/stations/station/direct-test', json={
        'confirmed': True, 'accept_startup_volume_risk': True})
    assert response.status_code == 202
    assert api[2] == [('A', 'ABC', 'station', SAVED)]
    assert 'remembered volume' in response.json['warning']


def test_api_does_not_substitute_user_edited_station(api):
    api[1]['url'] = 'https://user-edited.example/other.mp3'
    response = api[0].post('/api/A/stations/station/direct-test', json={
        'confirmed': True, 'accept_startup_volume_risk': True})
    assert response.status_code == 400
    assert not api[2]
    info = api[0].get('/api/A/stations/station/direct-test').json
    assert info['available'] is False
    assert info['physical_presets_supported'] is False
    assert info['automatic_schedules_supported'] is False


def test_cross_origin_cannot_start_direct_test(api):
    response = api[0].post('/api/A/stations/station/direct-test', json={
        'confirmed': True, 'accept_startup_volume_risk': True}, headers={'Origin': 'https://evil.example'})
    assert response.status_code == 400
    assert not api[2]


def test_same_identity_alias_supersedes_test(device, monkeypatch):
    original_wait = playback.wait
    started = [False]
    def wait(op, delay):
        if not started[0]:
            started[0] = True
            monkeypatch.setattr(playback.discovery, 'resolve_device', lambda *a:
                                {'ip': 'A', 'device_id': 'A', 'name': 'Alias'})
            other = playback.begin('Alias', 'Other operation', 'A')
            playback._resolve(other)
        return original_wait(op, delay)
    monkeypatch.setattr(playback, 'wait', wait)
    outcome = run()
    assert outcome['state'] == 'canceled'
    assert device[1] == [('A', 'SetAVTransportURI', URL), ('A', 'volume', 5)]


def test_queued_superseded_test_never_resolves_stream(device, monkeypatch):
    op = playback.begin('A', 'Old', 'A')
    playback.begin('A', 'New', 'A')
    monkeypatch.setattr(radio_stream, 'resolve', lambda _: pytest.fail('Stale test fetched stream'))
    radio.run(op, SAVED)
    assert not device[1]


def test_volume_command_timeout_never_retries_or_stops(device, monkeypatch):
    def volume(ip, value, **kw):
        device[1].append((ip, 'volume', value))
        return False
    monkeypatch.setattr(radio.control, 'set_volume', volume)
    assert run()['state'] == 'unknown'
    assert device[1] == [('A', 'SetAVTransportURI', URL), ('A', 'volume', 5)]


def test_queue_worker_unavailable_never_begins_or_cancels(monkeypatch):
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', None)
    monkeypatch.setattr(playback, 'begin', lambda *a: pytest.fail('No worker must not begin'))
    assert jobs.queue_direct_radio_test('A', 'ABC', 'id', SAVED) is None


def test_queue_duplicate_is_idempotent_and_saved_url_is_passed(monkeypatch):
    playback.reset()
    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *args: calls.append(args) or True)
    first = jobs.queue_direct_radio_test('A', 'ABC', 'id', SAVED)
    second = jobs.queue_direct_radio_test('A', 'ABC', 'id', SAVED)
    assert first['operation_id'] == second['operation_id']
    assert len(calls) == 1
    assert calls[0][1] is radio.run
    assert calls[0][-1] == SAVED
    playback.reset()


def test_api_worker_unavailable_is_503(api, monkeypatch):
    monkeypatch.setattr(jobs, 'queue_direct_radio_test', lambda *a: None)
    response = api[0].post('/api/A/stations/station/direct-test', json={
        'confirmed': True, 'accept_startup_volume_risk': True})
    assert response.status_code == 503


@pytest.fixture
def transport(monkeypatch):
    calls = []
    body = [f'<s:Envelope xmlns:s="{radio.SOAP}"><s:Body><u:StopResponse xmlns:u="{radio.SERVICE}"/></s:Body></s:Envelope>'.encode()]
    class Response:
        status_code = 200
        def iter_content(self, chunk_size):
            yield body[0]
        def close(self):
            calls.append(('close',))
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(radio.command_session, 'post', post)
    return calls, body


def test_soap_escapes_xml_no_redirect_and_closes(transport):
    transport[1][0] = f'<s:Envelope xmlns:s="{radio.SOAP}"><s:Body><u:SetAVTransportURIResponse xmlns:u="{radio.SERVICE}"/></s:Body></s:Envelope>'.encode()
    radio._soap('192.0.2.1', 'SetAVTransportURI', 2, CurrentURI='http://public.example/a?b=1&c=2', CurrentURIMetaData='')
    url, kwargs = transport[0][0]
    assert url == 'http://192.0.2.1:8091/AVTransport/Control'
    assert kwargs['allow_redirects'] is False
    assert kwargs['timeout'] == 2
    assert b'b=1&amp;c=2' in kwargs['data']
    assert transport[0][-1] == ('close',)


@pytest.mark.parametrize('body', [
    b'<html>error</html>',
    b'<!DOCTYPE foo><foo/>',
    f'<s:Envelope xmlns:s="{radio.SOAP}"><s:Body><s:Fault/></s:Body></s:Envelope>'.encode(),
    f'<s:Envelope xmlns:s="{radio.SOAP}"><s:Body><u:PlayResponse xmlns:u="{radio.SERVICE}"/></s:Body></s:Envelope>'.encode(),
])
def test_soap_rejects_ambiguous_response_and_closes(transport, body):
    transport[1][0] = body
    with pytest.raises(ValueError):
        radio._soap('192.0.2.1', 'Stop', 2)
    assert transport[0][-1] == ('close',)


def test_write_reverifies_address_after_guard(device, monkeypatch):
    # The write primitive's earlier address must not outlive lengthy guard reads.
    original_write = playback._write
    def write(op, callback):
        return original_write(op, lambda _ip: callback('STALE_ADDRESS'))
    monkeypatch.setattr(playback, '_write', write)
    assert run()['state'] == 'completed'
    assert {call[0] for call in device[1]} == {'A'}


@pytest.mark.parametrize('missing', [None, 'Stop', 'SetAVTransportURI', 'GetPositionInfo'])
def test_advertised_transport_actions_gate_selection(monkeypatch, missing):
    calls = []
    actions = {'SetAVTransportURI', 'Stop', 'GetPositionInfo', 'GetTransportInfo'} - {missing}
    payload = ('<scpd xmlns="urn:schemas-upnp-org:service-1-0"><actionList>' + ''.join(
        '<action><name>' + action + '</name></action>' for action in actions) + '</actionList></scpd>').encode()
    class Response:
        status_code = 200
        def iter_content(self, chunk_size):
            yield payload
        def close(self):
            calls.append('closed')
    monkeypatch.setattr(radio.command_session, 'get', lambda *a, **kw: Response())
    monkeypatch.setattr(radio, '_address', lambda op: '192.0.2.1')
    monkeypatch.setattr(playback, '_budget', lambda *a: 2)
    if missing:
        with pytest.raises(radio.TestError, match='actions_unavailable'):
            radio._capabilities({})
    else:
        radio._capabilities({})
    assert calls == ['closed']
