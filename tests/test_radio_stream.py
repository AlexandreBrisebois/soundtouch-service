import pytest

from app.core import radio_stream as stream

SAVED = next(iter(stream.CANDIDATES))


def test_direct_candidates_stay_http_only_and_exclude_chom_https_urls():
    assert stream.CANDIDATES == {
        'https://live.amperwave.net/direct/vox-wezffmmp3-imc':
            'http://live.amperwave.net/direct/vox-wezffmmp3-imc',
        'https://playerservices.streamtheworld.com/api/livestream-redirect/WBTZFM.mp3':
            'http://playerservices.streamtheworld.com/api/livestream-redirect/WBTZFM.mp3',
        'https://cbcradiolive.akamaized.net/hls/live/2041030/ES_R1EMT/master.m3u8':
            'http://playerservices.streamtheworld.com/api/livestream-redirect/CBMEFM_CBC.mp3',
    }
    for url in (
        'https://playerservices.streamtheworld.com/api/livestream-redirect/CHOMFMAAC.aac',
        'https://playerservices.streamtheworld.com/api/livestream-redirect/CHOMFM.mp3',
    ):
        with pytest.raises(stream.StreamError):
            stream.candidate(url)


@pytest.fixture
def network(monkeypatch):
    calls = []
    replies = []
    monkeypatch.setattr(stream, '_addresses', lambda *a: ['93.184.216.34'])
    class Reply:
        def __init__(self, status=200, headers=None, data=b'\xff\xfb\x92\x04audio'):
            self.status = status
            self.headers = headers or {'Content-Type': 'audio/mpeg'}
            self.data = data
        def getheader(self, key):
            return self.headers.get(key)
        def close(self):
            pass
        def read1(self, size):
            calls.append(('read', size))
            return self.data[:size]
    class Connection:
        def __init__(self, host, *, deadline):
            calls.append(('connect', host, 80, deadline))
        def request(self, method, path, headers):
            calls.append(('request', method, path, headers))
        def getresponse(self):
            return replies.pop(0) if replies else Reply()
        def finish(self):
            calls.append(('close',))
    monkeypatch.setattr(stream, '_Connection', Connection)
    return calls, replies, Reply


def test_pins_validated_ip_and_preserves_host_without_proxy(network):
    assert stream.resolve(SAVED) == stream.CANDIDATES[SAVED]
    calls = network[0]
    assert calls[0][1:3] == ('93.184.216.34', 80)
    assert calls[1][3]['Host'] == 'live.amperwave.net'
    assert ('read', 512) in calls
    assert calls[-1] == ('close',)


@pytest.mark.parametrize('url', ['https://unknown.example/radio', SAVED + '?new=station',
                                SAVED.upper(), SAVED + '/different'])
def test_unknown_saved_url_never_fetches(network, url):
    with pytest.raises(stream.StreamError):
        stream.resolve(url)
    assert not network[0]


@pytest.mark.parametrize('ip', ['127.0.0.1', '192.168.1.1', '169.254.169.254', '0.0.0.0',
                               '::1', 'fc00::1', '::ffff:127.0.0.1', '100.64.0.1'])
def test_private_address_or_mixed_public_private_answer_refused(network, monkeypatch, ip):
    monkeypatch.setattr(stream, '_addresses', lambda *a: ['93.184.216.34', ip])
    with pytest.raises(stream.StreamError):
        stream.resolve(SAVED)
    assert not network[0]


@pytest.mark.parametrize('location', ['http://127.0.0.1/audio', 'https://public.example/audio',
                                     'http://user:secret@public.example/audio',
                                     'file:///etc/passwd', 'http://public.example:8090/info',
                                     'http://public.example/audio#fragment', 'http://public.example/a\nb'])
def test_bad_redirect_never_connects_second_destination(network, monkeypatch, location):
    network[1].append(network[2](302, {'Location': location}))
    monkeypatch.setattr(stream, '_addresses', lambda host, *_:
                        ['127.0.0.1'] if host == '127.0.0.1' else ['93.184.216.34'])
    with pytest.raises(stream.StreamError):
        stream.resolve(SAVED)
    assert len([x for x in network[0] if x[0] == 'connect']) == 1
    assert network[0][-1] == ('close',)


def test_dns_rebinding_does_not_change_connected_destination(network, monkeypatch):
    addresses = iter([['93.184.216.34'], ['127.0.0.1']])
    monkeypatch.setattr(stream, '_addresses', lambda *_: next(addresses))
    assert stream.resolve(SAVED)
    # HTTPConnection gets the literal validated address, never resolves the hostname again.
    assert network[0][0][1] == '93.184.216.34'


def test_each_redirect_is_revalidated(network, monkeypatch):
    network[1].append(network[2](302, {'Location': 'http://second.example/live.mp3'}))
    addresses = iter([['93.184.216.34'], ['127.0.0.1']])
    monkeypatch.setattr(stream, '_addresses', lambda *_: next(addresses))
    with pytest.raises(stream.StreamError):
        stream.resolve(SAVED)
    assert len([x for x in network[0] if x[0] == 'connect']) == 1


def test_good_redirect_checks_audio_and_returns_transient_without_storage(network):
    network[1].append(network[2](302, {'Location': 'http://second.example/live.mp3?temporary=1'}))
    assert stream.resolve(SAVED) == 'http://second.example/live.mp3?temporary=1'
    assert len([x for x in network[0] if x[0] == 'connect']) == 2


@pytest.mark.parametrize('status,headers,data', [
    (403, {'Content-Type': 'audio/mpeg'}, b'\xff\xfb\x92'),
    (200, {'Content-Type': 'text/html'}, b'\xff\xfb\x92'),
    (200, {'Content-Type': 'audio/mpeg'}, b'<html>not audio'),
    (200, {'Content-Type': 'audio/mpeg', 'icy-metaint': '100'}, b'\xff\xfb\x92'),
    (200, {'Content-Type': 'audio/mpeg', 'Content-Encoding': 'gzip'}, b'\xff\xfb\x92'),
])
def test_non_audio_or_unsupported_framing_refused(network, status, headers, data):
    network[1].append(network[2](status, headers, data))
    with pytest.raises(stream.StreamError):
        stream.resolve(SAVED)
    assert network[0][-1] == ('close',)


def test_redirect_loop_refused(network):
    network[1].append(network[2](302, {'Location': stream.CANDIDATES[SAVED]}))
    with pytest.raises(stream.StreamError, match='loop'):
        stream.resolve(SAVED)
    assert len([x for x in network[0] if x[0] == 'connect']) == 1


def test_redirect_count_bounded(network):
    network[1].extend(network[2](302, {'Location': f'http://public.example/{i}'}) for i in range(7))
    with pytest.raises(stream.StreamError, match='limit'):
        stream.resolve(SAVED)
    assert len([x for x in network[0] if x[0] == 'connect']) == 6


def test_deadline_timer_survives_connection_close_header_until_response_finishes(monkeypatch):
    events = []
    class Socket:
        def shutdown(self, how):
            events.append('shutdown')
        def close(self):
            events.append('socket_close')
    class Timer:
        def __init__(self, delay, callback):
            self.callback = callback
            events.append(('timer', delay))
        def start(self):
            events.append('start')
        def cancel(self):
            events.append('cancel')
    monkeypatch.setattr(stream.http.client.HTTPConnection, 'connect', lambda self: setattr(self, 'sock', Socket()))
    monkeypatch.setattr(stream.threading, 'Timer', Timer)
    monkeypatch.setattr(stream.time, 'monotonic', lambda: 100)
    connection = stream._Connection('93.184.216.34', deadline=115)
    connection.connect()
    assert ('timer', 15) in events
    connection.close()  # http.client can detach a Connection:close socket after headers.
    assert 'cancel' not in events
    connection.timer.callback()
    assert 'shutdown' in events
    connection.finish()
    assert events[-1] == 'cancel'


def test_dns_timeout_holds_bounded_slot_until_lookup_finishes(monkeypatch):
    import threading
    from concurrent.futures import Future
    slots = threading.BoundedSemaphore(1)
    future = Future()
    monkeypatch.setattr(stream, '_DNS_SLOTS', slots)
    monkeypatch.setattr(stream._DNS_POOL, 'submit', lambda *a, **kw: future)
    with pytest.raises(stream.StreamError, match='unavailable'):
        stream._addresses('public.example', 0)
    with pytest.raises(stream.StreamError, match='busy'):
        stream._addresses('public.example', 0)
    future.set_result([])
    assert slots.acquire(blocking=False)


def test_short_reads_accumulate_a_frame_without_exceeding_sample(network):
    reply = network[2]()
    parts = iter([b'\xff', b'\xfb', b'\x92\x04'])
    sizes = []
    def read(size):
        sizes.append(size)
        return next(parts)
    reply.read1 = read
    network[1].append(reply)
    assert stream.resolve(SAVED)
    assert sizes == [512, 511, 510]
