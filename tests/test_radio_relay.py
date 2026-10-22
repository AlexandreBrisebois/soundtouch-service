import threading

import pytest

from app.core import favorites, playback, radio_relay as relay, radio_upstream, direct_radio
from app.scheduler import jobs
from tests.test_direct_radio import device as device  # noqa: F401
from tests.test_direct_radio import SAVED


class Socket:
    def __init__(self):
        self.closed = False
    def settimeout(self, value):
        pass
    def shutdown(self, how):
        self.closed = True
    def close(self):
        self.closed = True


@pytest.fixture
def radio(device, monkeypatch):
    relay.reset()
    streams = []
    monkeypatch.setattr(favorites, 'capabilities', lambda ip: set())
    monkeypatch.setenv('WISP_BASE_URL', 'http://192.0.2.10:9001')
    monkeypatch.setattr(favorites, 'station', lambda *a, **kw: {'url': SAVED})
    class Upstream:
        content_type = 'audio/mpeg'
        def __init__(self):
            self.closed = False
            self.reads = 0
        def read_chunk(self):
            self.reads += 1
            return b'MP3 audio'
        def close(self):
            self.closed = True
    def open_stream(url):
        value = Upstream()
        streams.append(value)
        return value
    monkeypatch.setattr(radio_upstream, 'open_station_stream', open_stream)
    original = direct_radio._soap
    consumers = []
    def soap(ip, action, timeout, **kwargs):
        value = original(ip, action, timeout, **kwargs)
        if action == 'SetAVTransportURI':
            token = kwargs['CurrentURI'].split('/')[-2]
            iterator, cleanup = relay.consumer(token, ip, Socket())
            assert next(iterator) == b''
            assert streams[-1].reads == 0  # headers, never audio, at reset volume 10
            consumers.append((iterator, cleanup))
        return value
    monkeypatch.setattr(direct_radio, '_soap', soap)
    yield streams, consumers
    for _, cleanup in consumers:
        cleanup()
    relay.reset()


def start(name='A', schedule='Morning', station='station', volume=5):
    op = playback.begin(name, schedule, name, allow_radio_idle=True)
    playback.run_on(op, None, volume, fade_in_duration=0, station_id=station)
    return op


def test_scheduled_start_gate_opens_only_after_actual_and_target_zero(device, radio, monkeypatch):
    original = relay.release
    def release(session, owner):
        d = device[0](session['speaker_ip'])
        assert d['volume'] == d['target'] == 0
        assert radio[0][0].reads == 0
        return original(session, owner)
    monkeypatch.setattr(relay, 'release', release)
    op = start()
    assert op['outcome']['state'] == 'playing'
    assert [c[1:] for c in device[1]] == [('SetAVTransportURI', relay.for_device('A')['url']),
                                        ('volume', 0), ('volume', 5)]
    assert next(radio[1][0][0]) == b'MP3 audio'
    assert relay.for_device('A')['gate'].is_set()


def test_relay_http_iterator_never_reads_audio_before_gate(device, monkeypatch):
    class Upstream:
        def read_chunk(self):
            pytest.fail('Read audio before release')
        def close(self):
            pass
    monkeypatch.setattr(radio_upstream, 'open_station_stream', lambda *a: Upstream())
    session = relay.prepare('A', 'A', 'owner', 'station', 'Morning', SAVED, 'http://192.0.2.10:9001')
    iterator, cleanup = relay.consumer(session['token'], 'A', Socket())
    assert next(iterator) == b''
    finished = threading.Event()
    thread = threading.Thread(target=lambda: (list(iterator), finished.set()))
    thread.start()
    assert not finished.wait(.03)
    relay.close(session)
    assert finished.wait(1)
    thread.join()
    cleanup()


def test_scheduled_off_transfers_lease_fades_stops_without_power_toggle(device, radio):
    start()
    session = relay.for_device('A')
    op = playback.begin_radio_off('A', 'Morning', 'A', 'station')
    assert op is not None and not session['closed'].is_set()
    playback.run_off(op, 0)
    assert device[1][-2:] == [('A', 'volume', 0), ('A', 'Stop')]
    assert relay.for_device('A') is None
    assert radio[0][0].closed
    assert op['outcome']['reason'] == 'radio_stop_acknowledged_source_inactive'


@pytest.mark.parametrize('schedule,station', [('Different routine', 'station'), ('Morning', 'different')])
def test_wrong_scheduled_off_never_touches_another_lease(device, radio, schedule, station):
    original = start()
    calls = list(device[1])
    assert playback.begin_radio_off('A', schedule, 'A', station) is None
    assert playback.current(original)
    assert relay.for_device('A') is not None
    assert device[1] == calls


def test_two_different_stations_speakers_survive_other_off(device, radio):
    start('A', 'Morning A', 'station-a')
    start('B', 'Morning B', 'station-b')
    first, second = relay.for_device('A'), relay.for_device('B')
    assert first['url'] != second['url']
    off = playback.begin_radio_off('A', 'Morning A', 'A', 'station-a')
    playback.run_off(off, 0)
    assert first['closed'].is_set() and not second['closed'].is_set()
    assert not radio[0][1].closed
    assert next(radio[1][1][0]) == b'MP3 audio'


def test_manual_override_and_shutdown_close_only_owned_upstreams(device, radio):
    start('A')
    start('B')
    playback.cancel('A')
    assert radio[0][0].closed and not radio[0][1].closed
    playback.reset()
    assert radio[0][1].closed


def test_uncertain_zero_volume_never_opens_gate(device, radio, monkeypatch):
    original = direct_radio.control.set_volume
    def volume(ip, target, **kw):
        original(ip, target, **kw)
        if target == 0:
            device[0](ip)['target'] = 10
        return True
    monkeypatch.setattr(direct_radio.control, 'set_volume', volume)
    op = start()
    assert op['outcome']['state'] == 'unknown'
    assert radio[0][0].reads == 0
    assert radio[0][0].closed
    assert all(call != ('A', 'volume', 5) for call in device[1])


def test_off_source_takeover_closes_feed_without_speaker_write(device, radio):
    start()
    before = list(device[1])
    device[0]('A').update(source='STORED_MUSIC', uri='other')
    off = playback.begin_radio_off('A', 'Morning', 'A', 'station')
    playback.run_off(off, 0)
    assert device[1] == before
    assert radio[0][0].closed
    assert off['outcome']['state'] == 'unknown'


def test_consumer_denies_wrong_peer_and_reconnect(device, radio):
    start()
    session = relay.for_device('A')
    with pytest.raises(relay.RelayError):
        relay.consumer(session['token'], 'OTHER', Socket())
    with pytest.raises(relay.RelayError):
        relay.consumer(session['token'], 'A', Socket())


def test_background_on_does_not_supersede_existing_radio(device, radio, monkeypatch):
    op = start()
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    schedule = {'name': 'Later', 'speaker_id': 'A'}
    result = jobs.queue_on('A', schedule)
    assert result['operation_id'] == op['outcome']['operation_id']
    assert playback.current(op)
    assert not radio[0][0].closed


def test_preparation_canceled_while_opening_closes_late_result_no_set_uri(device, radio, monkeypatch):
    entered, resume = threading.Event(), threading.Event()
    original = radio_upstream.open_station_stream
    def opening(url):
        value = original(url)
        entered.set()
        assert resume.wait(1)
        return value
    monkeypatch.setattr(radio_upstream, 'open_station_stream', opening)
    thread = threading.Thread(target=start)
    thread.start()
    assert entered.wait(1)
    replacement = playback.begin('A', 'Replacement', 'A')
    playback.finish(replacement, 'failed', 'worker_unavailable')
    resume.set()
    thread.join(1)
    assert not thread.is_alive()
    assert radio[0][0].closed
    assert not device[1]
    assert relay.for_device('A') is None


def test_failed_replacement_revokes_previous_stream_no_stale_stop(device, radio, monkeypatch):
    start()
    before = list(device[1])
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *a: False)
    assert jobs.queue_on('A', {'name': 'Replacement', 'speaker_id': 'A', 'volume': 5, 'fade_in_duration': 0}, force=True) is None
    assert radio[0][0].closed
    assert relay.for_device('A') is None
    assert device[1] == before


def test_off_transfer_during_fade_is_not_closed_by_old_worker_finally(device, radio, monkeypatch):
    off = []
    def wait(op, delay):
        if not off:
            off.append(playback.begin_radio_off('A', 'Morning', 'A', 'station'))
        return False
    monkeypatch.setattr(playback, 'wait', wait)
    op = playback.begin('A', 'Morning', 'A')
    playback.run_on(op, None, 5, fade_in_duration=10, station_id='station')
    assert off[0] is not None
    assert not radio[0][0].closed
    assert relay.for_device('A')['owner'] == off[0]['outcome']['operation_id']
    monkeypatch.setattr(playback, 'wait', lambda *a: True)
    playback.run_off(off[0], 0)
    assert radio[0][0].closed
    assert device[1][-1] == ('A', 'Stop')


def test_upstream_error_is_diagnostic_and_no_device_change(device, radio, monkeypatch):
    def denied(url):
        raise radio_upstream.UpstreamError('access_denied')
    monkeypatch.setattr(radio_upstream, 'open_station_stream', denied)
    op = start()
    assert not device[1]
    assert op['outcome']['reason'] == 'radio_upstream_access_denied'
    assert relay.for_device('A') is None


def test_upstream_eof_revokes_previous_playing_outcome(device, radio):
    op = start()
    radio[0][0].read_chunk = lambda: b''
    assert list(radio[1][0][0]) == []
    assert op['outcome']['state'] == 'unknown'
    assert op['outcome']['reason'] == 'radio_upstream_ended'
    assert op['outcome']['relay_active'] is False
    assert not any(c[1] == 'Stop' for c in device[1])


def test_stream_cleanup_without_iteration_releases_capacity_once(device, radio):
    for _ in range(12):
        session = relay.prepare('C', 'C', 'owner', 's', 'routine', SAVED, 'http://192.0.2.10:9001')
        _, cleanup = relay.consumer(session['token'], 'C', Socket())
        cleanup()
        cleanup()
        assert session['closed'].is_set()


def test_capacity_is_bounded_and_reset_closes_all_prepared_streams(device, radio):
    for i in range(relay.MAX_SESSIONS):
        relay.prepare(str(i), str(i), str(i), 's', 'r', SAVED, 'http://192.0.2.10:9001')
    with pytest.raises(relay.RelayError):
        relay.prepare('overflow', 'overflow', 'overflow', 's', 'r', SAVED, 'http://192.0.2.10:9001')
    assert len(radio[0]) == relay.MAX_SESSIONS
    relay.reset()
    assert all(s.closed for s in radio[0])


def test_cleanup_transport_exception_does_not_leak_consumer_slot(device, radio):
    def broken():
        raise OSError('local failure')
    for _ in range(12):
        session = relay.prepare('C', 'C', 'owner', 's', 'routine', SAVED, 'http://192.0.2.10:9001')
        socket = Socket()
        _, cleanup = relay.consumer(session['token'], 'C', socket)
        session['upstream'].close = broken
        cleanup()
        assert socket.closed


def test_stream_route_rejects_head_wrong_ip_and_server_without_socket(device, radio):
    from flask import Flask
    from app.api.favorites import favorites_bp
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    session = relay.prepare('C', '192.0.2.2', 'owner', 's', 'r', SAVED, 'http://192.0.2.10:9001')
    path = '/api/radio-sessions/' + session['token'] + '/stream.mp3'
    client = app.test_client()
    assert client.head(path).status_code == 405
    assert client.get(path).status_code == 410
    assert client.get(path, environ_overrides={'REMOTE_ADDR': '192.0.2.2'}).status_code == 410
    assert not session['consumed']
    response = client.get(path, environ_overrides={'REMOTE_ADDR': '192.0.2.2',
                                                   'werkzeug.socket': Socket()}, buffered=False)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Content-Type'] == 'audio/mpeg'
    response.close()
    assert session['closed'].is_set()


@pytest.mark.parametrize('base', [None, 'http://localhost:9001', 'https://192.0.2.1',
                                  'http://192.0.2.1/subpath', 'http://192.0.2.1/?secret=x'])
def test_relay_base_requires_explicit_reachable_http_origin(base):
    with pytest.raises(relay.RelayError):
        relay.base_url(base)


def test_saved_custom_mp3_url_is_used_exactly_never_guessed():
    url = 'https://radio.example/user-picked.mp3?token=public'
    assert relay.stream_url(url) == url
    with pytest.raises(relay.RelayError):
        relay.stream_url('https://radio.example/live.m3u8')


def test_schedule_readiness_preserves_native_but_explains_relay_prerequisites(device, radio, monkeypatch):
    from app.core import library
    ready = relay.readiness(SAVED, 'A')
    assert ready['available'] and ready['mode'] == 'relay'
    assert ready['hardware_verified'] is False
    monkeypatch.delenv('WISP_BASE_URL')
    assert 'WISP_BASE_URL' in relay.readiness(SAVED, 'A')['reason']
    monkeypatch.setenv('WISP_BASE_URL', 'http://192.0.2.10:9001')
    assert relay.readiness('https://radio.example/live.aac', 'A')['available'] is False
    monkeypatch.setattr(favorites, 'capabilities', lambda _: {'/select'})
    monkeypatch.setattr(library, 'read_sources', lambda _: [{'source': 'LOCAL_INTERNET_RADIO', 'ready': True}])
    assert relay.readiness('https://radio.example/live.aac', 'A')['mode'] == 'native'


def test_exact_ici_adapter_uses_same_volume_gate_and_reports_disabled(device, radio, monkeypatch):
    from app.core import radio_hls
    monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', '0')
    readiness = relay.readiness(radio_hls.SAVED_URL, 'A')
    assert not readiness['available'] and 'WISP_ENABLE_HLS_RADIO' in readiness['reason']
    monkeypatch.setattr(radio_hls, 'available', lambda: True)
    assert relay.readiness(radio_hls.SAVED_URL, 'A')['mode'] == 'relay'
    calls = []
    def hls(url):
        calls.append(url)
        return radio_upstream.open_station_stream(url)
    monkeypatch.setattr(radio_hls, 'open_ici_stream', hls)
    monkeypatch.setattr(favorites, 'station', lambda *a, **kw: {'url': radio_hls.SAVED_URL})
    op = start()
    assert calls == [radio_hls.SAVED_URL]
    assert op['outcome']['state'] == 'playing'
    assert device[1][1:3] == [('A', 'volume', 0), ('A', 'volume', 5)]


@pytest.mark.parametrize('url', ['https://user:password@radio.example/live.mp3',
                               'https://radio.example:8443/live.mp3',
                               'http://127.0.0.1/live.mp3', 'http://192.168.1.1/live.mp3',
                               'http://localhost/live.mp3', 'http://speaker.local/live.mp3',
                               'https://radio.example/live.mp3#fragment'])
def test_readiness_rejects_known_unsupported_relay_destinations_without_dns(url):
    with pytest.raises(relay.RelayError):
        relay.stream_url(url)


@pytest.mark.parametrize('url', ['http://127.0.0.2:9001', 'http://0.0.0.0:9001',
                               'http://[::]:9001', 'http://224.0.0.1:9001'])
def test_base_rejects_loopback_wildcard_multicast(url):
    with pytest.raises(relay.RelayError):
        relay.base_url(url)


@pytest.mark.parametrize('name', ['Older NAS routine', 'Older AUX routine', 'Older preset routine'])
def test_unrelated_nonradio_schedule_off_never_revokes_radio(device, radio, monkeypatch, name):
    active = start(schedule='Test station')
    before = list(device[1])
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    result = jobs.queue_off('A', {'name': name, 'speaker_id': 'A', 'fade_out_duration': 0})
    assert result['state'] == 'skipped'
    assert playback.current(active)
    assert not radio[0][0].closed
    assert device[1] == before


def test_eof_between_last_guard_and_finish_cannot_resurrect_playing_metadata(device, radio, monkeypatch):
    from app.core import relay_playback
    original = relay_playback._guard
    count = 0
    def guard(op, session, volume=None):
        nonlocal count
        value = original(op, session, volume)
        if volume == 5:
            count += 1
            if count == 2:
                relay.close(session, 'radio_upstream_ended')
        return value
    monkeypatch.setattr(relay_playback, '_guard', guard)
    op = start()
    assert op['outcome']['state'] == 'unknown'
    assert op['outcome']['relay_active'] is False


def test_readiness_api_is_read_only_and_has_no_cache_or_stream_probe(device, radio):
    from flask import Flask
    from app.api.favorites import favorites_bp
    app = Flask(__name__)
    app.register_blueprint(favorites_bp)
    response = app.test_client().get('/api/A/stations/station/readiness')
    assert response.status_code == 200
    assert response.json['mode'] == 'relay'
    assert response.json['requires_idle'] is True
    assert response.json['hardware_verified'] is False
    assert response.headers['Cache-Control'] == 'no-store'
    assert not radio[0] and not device[1]


def test_next_scheduled_radio_cycle_accepts_only_own_fresh_inactive_stop(device, radio):
    start()
    off = playback.begin_radio_off('A', 'Morning', 'A', 'station')
    playback.run_off(off, 0)
    assert device[0]('A')['source'] == 'INVALID_SOURCE'
    second = start(schedule='Next morning')
    assert second['outcome']['state'] == 'playing'
    assert len(radio[0]) == 2
    assert radio[0][0].closed and not radio[0][1].closed
    second_off = playback.begin_radio_off('A', 'Next morning', 'A', 'station')
    playback.run_off(second_off, 0)
    assert second_off['outcome']['state'] == 'completed'
    assert all(stream.closed for stream in radio[0])


@pytest.mark.parametrize('change', ['restart', 'manual', 'event', 'volume', 'transport', 'group'])
def test_radio_idle_provenance_never_survives_override_or_ambiguous_state(device, radio, change):
    start()
    off = playback.begin_radio_off('A', 'Morning', 'A', 'station')
    playback.run_off(off, 0)
    before = list(device[1])
    if change == 'restart':
        playback.reset()
    elif change == 'manual':
        playback.cancel('A')
    elif change == 'event':
        playback.observe_external('A', {'source_type': 'AUX', 'status': 'Playing'})
    elif change == 'volume':
        device[0]('A').update(volume=4, target=4)
    elif change == 'transport':
        device[0]('A')['state'] = 'PLAYING'
    else:
        device[0]('A')['group'] = True
    second = start(schedule='Next morning')
    assert second['outcome']['state'] != 'playing'
    assert device[1] == before


def test_owned_idle_permission_is_consumed_by_failed_start(device, radio):
    start()
    playback.run_off(playback.begin_radio_off('A', 'Morning', 'A', 'station'), 0)
    playback.observe_external('A', {'volume': 0})  # expected own-volume echo is harmless
    device[0]('A').update(volume=4, target=4)
    assert start(schedule='Failed start')['outcome']['state'] != 'playing'
    device[0]('A').update(volume=0, target=0)
    before = list(device[1])
    assert start(schedule='No retry permission')['outcome']['state'] != 'playing'
    assert device[1] == before


@pytest.mark.parametrize('changed', [False, True])
def test_inflight_idle_permission_revoked_by_changed_event_even_if_source_returns(device, radio, monkeypatch, changed):
    start()
    playback.run_off(playback.begin_radio_off('A', 'Morning', 'A', 'station'), 0)
    original = radio_upstream.open_station_stream
    def opening(url):
        upstream = original(url)
        playback.observe_external('A', {'source_type': 'AUX', 'status': 'Playing'} if changed else {'volume': 0})
        return upstream
    monkeypatch.setattr(radio_upstream, 'open_station_stream', opening)
    before = list(device[1])
    result = start(schedule='Next morning')
    if changed:
        assert result['outcome']['state'] != 'playing'
        assert radio[0][-1].closed
        assert device[1] == before
    else:
        assert result['outcome']['state'] == 'playing'


@pytest.mark.parametrize(('platform', 'executable', 'message'), [
    ('linux', '/usr/bin/ffmpeg', None),
    ('darwin', '/usr/bin/ffmpeg', 'Linux container'),
    ('linux', None, 'requires FFmpeg'),
])
def test_ici_readiness_without_activation_flag(device, radio, monkeypatch, platform, executable, message):
    from app.core import radio_hls
    monkeypatch.delenv('WISP_ENABLE_HLS_RADIO', raising=False)
    monkeypatch.setattr(radio_hls.sys, 'platform', platform)
    monkeypatch.setattr(radio_hls.shutil, 'which', lambda _: executable)
    readiness = relay.readiness(radio_hls.SAVED_URL, 'A')
    if message is None:
        assert readiness['available'] and readiness['mode'] == 'relay'
        assert readiness['hardware_verified'] is False
    else:
        assert not readiness['available'] and message in readiness['reason']
        assert 'WISP_ENABLE_HLS_RADIO=1' not in readiness['reason']
