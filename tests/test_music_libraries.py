"""Offline native registration contracts; never a speaker or audibility test."""
import copy
import xml.etree.ElementTree as ET

import pytest
from flask import Flask
from requests.exceptions import Timeout

from app.api.music_libraries import music_libraries_bp
from app.core import favorites, library, music_libraries as ml
from app.scheduler import jobs

A = {'name': 'Bedroom', 'device_id': 'A', 'ip': '192.0.2.1'}
B = {'name': 'Kitchen', 'device_id': 'B', 'ip': '192.0.2.2'}
ACCOUNT = 'server-uuid/0'
SOURCE = {'id': library.source_id('STORED_MUSIC:' + ACCOUNT), 'source': 'STORED_MUSIC',
          'account': ACCOUNT, 'name': 'My music', 'ready': True}
CAPABILITIES = {'/listMediaServers', '/setMusicServiceAccount', '/removeMusicServiceAccount'}


@pytest.fixture
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv('FAVORITES_FILE', str(tmp_path / 'favorites.json'))
    favorites._save({'version': 1, 'favorites': {}, 'stations': {}, 'station_seed_version': 1,
                     'unrelated': {'retain': True}})
    favorites._tokens.clear()
    ml._candidates.clear()
    speakers = [dict(A), dict(B)]
    sources = {A['ip']: [], B['ip']: []}
    writes, pauses = [], []
    monkeypatch.setattr(ml.discovery, 'get_all_cached_devices', lambda: copy.deepcopy(speakers))
    def device(name, device_id=None):
        matches = [s for s in speakers if s['device_id'] == device_id or (device_id is None and s['name'] == name)]
        if len(matches) != 1:
            raise ValueError('Speaker unavailable')
        return dict(matches[0])
    monkeypatch.setattr(favorites, 'device', device)
    monkeypatch.setattr(favorites, 'capabilities', lambda ip: CAPABILITIES)
    def read_sources(ip):
        if sources[ip] is None:
            raise ValueError('Source read failed')
        return copy.deepcopy(sources[ip])
    monkeypatch.setattr(library, 'read_sources', read_sources)
    monkeypatch.setattr(library, 'read_presets', lambda ip: {i: None for i in range(1, 7)})
    monkeypatch.setattr(jobs, 'source_schedule_impacts', lambda *a, **k: [], raising=False)
    monkeypatch.setattr(jobs, 'pause_source_schedules', lambda *a, **k: pauses.append((a, k)) or [], raising=False)
    def response(found, endpoint, data=None):
        if data is None:
            return ET.fromstring('<ListMediaServersResponse><media_server id="uuid:server-uuid" friendly_name="My music"/></ListMediaServersResponse>')
        writes.append((found, endpoint, ET.fromstring(data)))
        if endpoint == '/setMusicServiceAccount':
            sources[found['ip']] = [copy.deepcopy(SOURCE)]
        else:
            sources[found['ip']] = []
        return ET.fromstring('<status>' + endpoint + '</status>')
    monkeypatch.setattr(ml, '_response', response)
    ml._candidates[ml.library_id('server-uuid')] = ml._new('server-uuid', 'My music')
    return {'speakers': speakers, 'sources': sources, 'writes': writes, 'pauses': pauses,
            'key': ml.library_id('server-uuid'), 'response': response}


def test_discovery_deduplicates_stable_ids_and_retains_visibility(rig):
    result = ml.discover()
    assert len(result['libraries']) == 1
    assert result['discovered'] == [rig['key']]
    assert {s['device_id'] for s in result['libraries'][0]['visible_to']} == {'A', 'B'}
    assert not rig['writes']
    assert 'music_libraries' not in favorites._load()


def test_discovery_same_names_different_ids_are_not_merged(rig, monkeypatch):
    monkeypatch.setattr(ml, '_response', lambda found, *a: ET.fromstring(
        '<ListMediaServersResponse><media_server id="uuid:' + found['device_id'] + '" friendly_name="Same"/></ListMediaServersResponse>'))
    assert len(ml.discover()['libraries']) == 2


def test_empty_discovery_differs_from_failure(rig, monkeypatch):
    monkeypatch.setattr(ml, '_response', lambda *a: ET.fromstring('<ListMediaServersResponse/>'))
    result = ml.discover()
    assert result['state'] == 'empty' and not result['errors'] and result['guidance']
    monkeypatch.setattr(ml, '_response', lambda *a: (_ for _ in ()).throw(ValueError('bad XML')))
    result = ml.discover()
    assert result['state'] == 'failed' and len(result['errors']) == 2
    assert not rig['writes']


def test_empty_new_discovery_does_not_present_retained_catalog_as_found(rig, monkeypatch):
    ml.discover()
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    monkeypatch.setattr(ml, '_response', lambda *a: ET.fromstring('<ListMediaServersResponse/>'))
    app = Flask(__name__)
    app.register_blueprint(music_libraries_bp)
    result = app.test_client().post('/api/music-libraries/discover', json={})
    assert result.status_code == 200
    assert result.json['state'] == 'empty' and result.json['discovered'] == []
    retained = result.json['libraries'][0]
    assert retained['id'] == rig['key'] and retained['added']
    assert retained['visible_to'] == []  # Old scan visibility cannot masquerade as current discovery.
    assert retained['observations']['A']['state'] == 'ready'
    assert len(rig['writes']) == 1


def test_new_discovery_replaces_old_speaker_visibility(rig, monkeypatch):
    ml.discover()
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    def response(found, *args):
        if found['device_id'] == 'A':
            return ET.fromstring('<ListMediaServersResponse/>')
        return rig['response'](found, *args)
    monkeypatch.setattr(ml, '_response', response)
    result = ml.discover()
    assert result['discovered'] == [rig['key']]
    assert [speaker['device_id'] for speaker in result['libraries'][0]['visible_to']] == ['B']


def test_failed_discovery_retains_added_library_but_has_no_current_found_ids(rig, monkeypatch):
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    monkeypatch.setattr(ml, '_response', lambda *a: (_ for _ in ()).throw(ValueError('bad read')))
    result = ml.discover()
    assert result['state'] == 'failed' and result['discovered'] == [] and result['errors']
    assert result['libraries'][0]['added'] and result['libraries'][0]['visible_to'] == []
    assert len(rig['writes']) == 1


def test_add_requires_confirmation_and_retains_other_store_data(rig):
    with pytest.raises(ValueError, match='Confirm'):
        ml.add(rig['key'], A['name'], 'A', confirmed=False)
    assert not rig['writes']
    result = ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert result['state'] == 'ready'
    assert result['library']['observations']['B']['state'] == 'not_registered'
    assert favorites._load()['unrelated'] == {'retain': True}
    _, endpoint, xml = rig['writes'][0]
    assert endpoint == '/setMusicServiceAccount'
    assert xml.attrib == {'source': 'STORED_MUSIC', 'displayName': 'My music'}
    assert xml.findtext('user') == ACCOUNT
    assert xml.find('pass') is not None and not xml.findtext('pass')


def test_registered_unavailable_is_added_not_ready(rig, monkeypatch):
    def response(found, endpoint, data=None):
        rig['response'](found, endpoint, data)
        rig['sources'][found['ip']][0]['ready'] = False
    monkeypatch.setattr(ml, '_response', response)
    result = ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert result['state'] == 'unavailable' and result['library']['added']
    assert 'Check Again' in result['message']


def test_lost_add_response_reads_back_and_never_repeats(rig, monkeypatch):
    def response(found, endpoint, data=None):
        rig['response'](found, endpoint, data)
        raise Timeout('lost acknowledgement')
    monkeypatch.setattr(ml, '_response', response)
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True)['state'] == 'ready'
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True)['state'] == 'ready'
    assert len(rig['writes']) == 1


def test_unknown_add_blocks_writes_until_readback_and_explicit_retry(rig, monkeypatch):
    def response(found, endpoint, data=None):
        rig['writes'].append(endpoint)
        rig['sources'][found['ip']] = None
        raise Timeout('unknown')
    monkeypatch.setattr(ml, '_response', response)
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True)['state'] == 'unknown'
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True, retry=True)['state'] == 'unknown'
    assert len(rig['writes']) == 1
    rig['sources'][A['ip']] = []
    checked = ml.check(rig['key'])
    assert checked['state'] == 'not_registered' and checked['retry_allowed']
    assert len(rig['writes']) == 1  # Check is read-only even when retry becomes available.
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True)['retry_allowed']
    assert len(rig['writes']) == 1
    monkeypatch.setattr(ml, '_response', rig['response'])
    assert ml.add(rig['key'], A['name'], 'A', confirmed=True, retry=True)['state'] == 'ready'
    assert len(rig['writes']) == 2


def test_remove_timeout_check_response_exposes_explicit_retry_without_writing(rig, monkeypatch):
    rig['sources'][A['ip']] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    def response(found, endpoint, data=None):
        rig['writes'].append(endpoint)
        rig['sources'][found['ip']] = None
        raise Timeout('unknown removal result')
    monkeypatch.setattr(ml, '_response', response)
    result = ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert result['state'] == 'unknown' and not result['retry_allowed']
    checked = ml.check(rig['key'])
    assert checked['state'] == 'unknown' and not checked['retry_allowed']
    assert len(rig['writes']) == 1
    rig['sources'][A['ip']] = [SOURCE]  # Fresh conclusive read: removal was not applied.
    app = Flask(__name__)
    app.register_blueprint(music_libraries_bp)
    checked = app.test_client().post('/api/music-libraries/' + rig['key'] + '/check', json={})
    assert checked.status_code == 200
    assert checked.json['state'] == 'ready' and checked.json['retry_allowed'] is True
    assert len(rig['writes']) == 1
    fresh_plan = ml.removal_plan(rig['key'], A['name'], 'A')
    ml.remove(rig['key'], fresh_plan['plan_id'], confirmed=True)
    assert len(rig['writes']) == 1  # A fresh plan alone cannot bypass explicit Retry.
    monkeypatch.setattr(ml, '_response', rig['response'])
    retried = ml.remove(rig['key'], fresh_plan['plan_id'], confirmed=True, retry=True)
    assert retried['state'] == 'not_registered' and not retried['retry_allowed']
    assert len(rig['writes']) == 2


def test_add_timeout_check_api_returns_pending_target_retry_state(rig, monkeypatch):
    def response(found, endpoint, data=None):
        rig['writes'].append(endpoint)
        rig['sources'][found['ip']] = None
        raise Timeout('unknown add result')
    monkeypatch.setattr(ml, '_response', response)
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    rig['sources'][A['ip']] = []
    app = Flask(__name__)
    app.register_blueprint(music_libraries_bp)
    checked = app.test_client().post('/api/music-libraries/' + rig['key'] + '/check', json={})
    assert checked.status_code == 200
    assert checked.json['state'] == 'not_registered' and checked.json['retry_allowed'] is True
    assert checked.json['library']['pending']['speaker_id'] == 'A'
    assert len(rig['writes']) == 1


def test_unreadable_registration_before_first_add_is_not_a_write(rig):
    rig['sources'][A['ip']] = None
    result = ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert result['state'] == 'unknown' and not rig['writes']


def test_unsupported_registration_does_not_write(rig, monkeypatch):
    monkeypatch.setattr(favorites, 'capabilities', lambda ip: set())
    with pytest.raises(ValueError, match='does not support'):
        ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert not rig['writes']


def test_failed_intent_persistence_prevents_native_write(rig, monkeypatch):
    monkeypatch.setattr(favorites, '_save', lambda *a: (_ for _ in ()).throw(ValueError('unwritable')))
    with pytest.raises(ValueError, match='unwritable'):
        ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert not rig['writes']


def test_startup_imports_existing_registrations_and_retains_offline(rig):
    rig['sources'][A['ip']] = [copy.deepcopy(SOURCE)]
    ml.check_all()
    assert ml.get(rig['key'])['observations']['A']['state'] == 'ready'
    ml._candidates.clear()  # Simulated restart does not lose the persisted library.
    rig['sources'][A['ip']] = None
    result = ml.check(rig['key'])['library']
    assert result['added'] and result['observations']['A']['state'] == 'unknown'
    assert result['observations']['A']['account'] == ACCOUNT
    rig['sources'][A['ip']] = [{**SOURCE, 'ready': False}]
    assert ml.check(rig['key'])['library']['observations']['A']['state'] == 'unavailable'
    rig['sources'][A['ip']] = [SOURCE]
    assert ml.check(rig['key'])['library']['observations']['A']['state'] == 'ready'
    assert not rig['writes']


def test_missing_registration_retained_and_add_again_explicit(rig):
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    rig['sources'][A['ip']] = []
    result = ml.check(rig['key'])['library']
    assert result['added'] and result['observations']['A']['state'] == 'not_registered'
    assert len(rig['writes']) == 1


def test_independent_removal_retains_library_on_other_speaker_and_pauses_only_removed(rig):
    rig['sources'][A['ip']] = [SOURCE]
    rig['sources'][B['ip']] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    assert plan['warning'] and not rig['writes'] and not rig['pauses']
    result = ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert result['library']['added']
    assert result['library']['observations']['A']['state'] == 'not_registered'
    assert result['library']['observations']['B']['state'] == 'ready'
    assert rig['pauses'] == [(('A',), {'source_account': ACCOUNT, 'reason': 'library_removed'})]
    xml = rig['writes'][0][2]
    assert xml.findtext('user') == ACCOUNT and xml.find('pass') is not None
    ml.check(rig['key'])
    assert len(rig['pauses']) == 1


def test_propagated_removal_pauses_each_confirmed_speaker_and_prunes_added_only(rig, monkeypatch):
    for ip in rig['sources']:
        rig['sources'][ip] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    def response(found, endpoint, data=None):
        rig['response'](found, endpoint, data)
        rig['sources'][B['ip']] = []
    monkeypatch.setattr(ml, '_response', response)
    result = ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert not result['library']['added']
    assert {args[0] for args, _ in rig['pauses']} == {'A', 'B'}
    assert ml.get(rig['key'])  # Recovery tombstone retained; no music-file or preset write.
    assert len(rig['writes']) == 1


def test_unreadable_other_speaker_reconciles_pause_later(rig, monkeypatch):
    for ip in rig['sources']:
        rig['sources'][ip] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    def response(found, endpoint, data=None):
        rig['response'](found, endpoint, data)
        rig['sources'][B['ip']] = None
        raise Timeout('lost')
    monkeypatch.setattr(ml, '_response', response)
    result = ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert result['library']['added'] and len(rig['pauses']) == 1
    rig['sources'][B['ip']] = []
    assert not ml.check(rig['key'])['library']['added']
    assert len(rig['pauses']) == 2


def test_cancel_and_changed_impacts_do_not_remove(rig, monkeypatch):
    rig['sources'][A['ip']] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    with pytest.raises(ValueError, match='Confirm'):
        ml.remove(rig['key'], plan['plan_id'], confirmed=False)
    monkeypatch.setattr(jobs, 'source_schedule_impacts', lambda *a, **k: [{'name': 'New routine'}])
    with pytest.raises(ValueError, match='impacts changed'):
        ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert not rig['writes'] and not rig['pauses']


def test_device_replacement_and_expired_plan_fail_closed(rig, monkeypatch):
    rig['sources'][A['ip']] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    favorites._tokens[plan['plan_id']]['expires'] = 0
    with pytest.raises(ValueError, match='expired'):
        ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert not rig['writes']


def test_removal_retains_reviewed_slot_impacts_if_firmware_clears_presets(rig, monkeypatch):
    rig['sources'][A['ip']] = [SOURCE]
    slots = {i: None for i in range(1, 7)}
    slots[3] = {'sourceAccount': ACCOUNT, 'name': 'Old music'}
    monkeypatch.setattr(library, 'read_presets', lambda ip: copy.deepcopy(slots) if ip == A['ip'] else {})
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    def response(found, endpoint, data=None):
        rig['response'](found, endpoint, data)
        slots[3] = None
    monkeypatch.setattr(ml, '_response', response)
    ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert (('A',), {'slot': 3, 'reason': 'library_removed'}) in rig['pauses']


def test_delayed_propagation_still_pauses_later_missing_registration(rig):
    for ip in rig['sources']:
        rig['sources'][ip] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert len(rig['pauses']) == 1
    rig['sources'][B['ip']] = []
    assert 'B' in ml.get(rig['key'])['reconciliation_pending']
    ml.check(rig['key'])
    assert len(rig['pauses']) == 2


def test_later_add_preserves_other_speaker_pending_removal_reconciliation(rig):
    for ip in rig['sources']:
        rig['sources'][ip] = [SOURCE]
    ml.check_all()
    plan = ml.removal_plan(rig['key'], A['name'], 'A')
    ml.remove(rig['key'], plan['plan_id'], confirmed=True)
    assert len(rig['pauses']) == 1
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert ml.get(rig['key'])['registration_epochs']['A'] == 1
    rig['sources'][B['ip']] = []
    ml.check(rig['key'])
    assert len(rig['pauses']) == 2
    # The earlier intent cannot affect A's new explicit registration epoch.
    rig['sources'][A['ip']] = []
    ml.check(rig['key'])
    assert len(rig['pauses']) == 2


def test_api_library_responses_keep_native_account_and_journals_private(rig):
    ml.add(rig['key'], A['name'], 'A', confirmed=True)
    app = Flask(__name__)
    app.register_blueprint(music_libraries_bp)
    result = app.test_client().get('/api/music-libraries')
    assert result.status_code == 200
    record = result.json['libraries'][0]
    assert 'server_id' not in record and 'account' not in record['observations']['A']
    assert record['observations']['A']['source_id'] == SOURCE['id']
    assert set(record['pending']) <= {'action', 'speaker_id', 'state', 'created_at'}


def test_acknowledged_but_unobserved_add_only_offers_checking(rig, monkeypatch):
    calls = []
    def response(found, endpoint, data=None):
        calls.append(endpoint)
        return ET.fromstring('<status>' + endpoint + '</status>')
    monkeypatch.setattr(ml, '_response', response)
    result = ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert result['state'] == 'unknown' and not result['retry_allowed']
    ml.add(rig['key'], A['name'], 'A', confirmed=True, retry=True)
    assert len(calls) == 1


def test_failed_add_keeps_selection_without_claiming_added(rig, monkeypatch):
    monkeypatch.setattr(ml, '_response', lambda *a: (_ for _ in ()).throw(ml.LibraryError('Speaker error 1022')))
    result = ml.add(rig['key'], A['name'], 'A', confirmed=True)
    assert result['state'] == 'not_registered' and not result['library']['added']
    assert result['library']['id'] == rig['key'] and '1022' in result['message']


class NativeResponse:
    status_code = 200
    def __init__(self, body):
        self.body, self.closed = body, False
    def iter_content(self, chunk_size):
        yield self.body
    def close(self):
        self.closed = True


@pytest.mark.parametrize('xml', [b'<error code="1022" name="MARGE_SET_CRED_FAILED"/>',
                                b'<status><error>failed</error></status>',
                                b'<status>/wrongOperation</status>', b'<html/>'])
def test_native_http_success_errors_are_failures_and_responses_close(rig, monkeypatch, xml):
    real = NativeResponse(xml)
    monkeypatch.setattr(ml.command_session, 'post', lambda *a, **k: real)
    # Fixture replaces _response; invoke the actual native parser saved on the module below.
    with pytest.raises(ValueError, match='Speaker'):
        NATIVE_RESPONSE(A, '/setMusicServiceAccount', b'<credentials/>')
    assert real.closed


def test_native_transport_is_bounded_escaped_and_has_no_redirects(rig, monkeypatch):
    calls = []
    response = NativeResponse(b'<ListMediaServersResponse/>')
    def get(*a, **k):
        calls.append((a, k))
        return response
    monkeypatch.setattr(ml.command_session, 'get', get)
    assert NATIVE_RESPONSE(A, '/listMediaServers').tag == 'ListMediaServersResponse'
    assert calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['timeout'] == (2.0, 3.0) and response.closed


def test_api_writes_require_confirmation_and_same_origin(rig):
    app = Flask(__name__)
    app.register_blueprint(music_libraries_bp)
    client = app.test_client()
    url = '/api/music-libraries/' + rig['key'] + '/add'
    assert client.post(url, json={'speaker': A['name'], 'speaker_id': 'A'}).status_code == 400
    assert client.post(url, json={'confirmed': True}, headers={'Origin': 'https://other.test'}).status_code == 400
    assert not rig['writes']
    result = client.post(url, json={'speaker': A['name'], 'speaker_id': 'A', 'confirmed': True})
    assert result.status_code == 200 and result.json['state'] == 'ready'


NATIVE_RESPONSE = ml._response
