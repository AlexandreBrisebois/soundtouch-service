import http.client
import io
import socket
import ssl
import threading
import time
from unittest.mock import Mock

import pytest

from app.core import radio_upstream as u


class Response:
    def __init__(self, body=b'\xff\xfb\x92\x04' + b'x' * 1024, status=200, headers=None):
        self.status = status
        self.headers = {'Content-Type': 'audio/mpeg', **(headers or {})}
        self.body = io.BytesIO(body)
        self.closed = False

    def getheader(self, name):
        return self.headers.get(name)

    def read1(self, n):
        return self.body.read(n)

    def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(u, '_addresses', lambda *args: ['8.8.8.8'])
    responses = []
    connections = []

    class Connection:
        def __init__(self, *args):
            self.args = args
            self.closed = False
            self.response = responses.pop(0)
            connections.append(self)

        def request(self, *args, **kwargs):
            self.request_args = args, kwargs

        def getresponse(self):
            return self.response

        def streaming(self, timeout):
            self.timeout = timeout

        def finish(self):
            self.closed = True

    monkeypatch.setattr(u, '_Connection', Connection)
    return responses, connections


def test_prefix_retained_bounded_and_close(transport):
    responses, connections = transport
    body = b'\xff\xfb\x92\x04' + b'x' * 1024
    responses.append(Response(body))
    stream = u.open_station_stream('https://radio.example/a.mp3')
    assert connections[0].args[:4] == ('8.8.8.8', 'radio.example', 443, True)
    assert connections[0].request_args[1]['headers']['Host'] == 'radio.example'
    assert stream.content_type == 'audio/mpeg'
    assert stream.read_chunk(10) + stream.read_chunk() + stream.read_chunk() == body
    with pytest.raises(ValueError):
        stream.read_chunk(65537)
    stream.close()
    stream.close()
    assert stream.read_chunk() == b''
    assert connections[0].closed


@pytest.mark.parametrize('target', [
    'http://127.0.0.1/a', 'http://169.254.169.254/a', 'http://[::1]/a',
    'file:///x', 'http://user:pass@radio.example/a', 'http://radio.example:8080/a',
    'https://radio.example:80/a', 'http://radio.example/a#fragment',
    'http://radio.example/a\r\nHeader:x'])
def test_unsafe_destination(target, monkeypatch):
    monkeypatch.setattr(u, '_addresses', lambda host, timeout: [host] if host in (
        '127.0.0.1', '169.254.169.254', '::1') else ['8.8.8.8'])
    with pytest.raises(u.UpstreamError, match='unsafe destination'):
        u.open_station_stream(target)


def test_mixed_private_dns_rejected(transport, monkeypatch):
    monkeypatch.setattr(u, '_addresses', lambda *args: ['8.8.8.8', '192.168.1.1'])
    with pytest.raises(u.UpstreamError, match='unsafe destination'):
        u.open_station_stream('https://radio.example/a')
    assert transport[1] == []


def test_redirect_private_dns_revalidated(transport, monkeypatch):
    calls = []

    def addresses(host, timeout):
        calls.append(host)
        return ['8.8.8.8'] if len(calls) == 1 else ['127.0.0.1']

    monkeypatch.setattr(u, '_addresses', addresses)
    transport[0].append(Response(status=302, headers={'Location': '/next'}))
    with pytest.raises(u.UpstreamError, match='unsafe destination'):
        u.open_station_stream('http://radio.example/a')
    assert len(calls) == 2
    assert transport[1][0].closed


@pytest.mark.parametrize('status,headers,body,reason', [
    (403, {}, b'', 'access_denied'), (401, {}, b'', 'access_denied'),
    (500, {}, b'', 'http_status'),
    (200, {'Content-Type': 'application/vnd.apple.mpegurl'}, b'#EXTM3U', 'unsupported_format'),
    (200, {'icy-metaint': '100'}, b'', 'unsupported_framing'),
    (200, {'Content-Encoding': 'gzip'}, b'', 'unsupported_framing'),
    (200, {}, b'not audio' * 200, 'invalid_mp3'),
    (302, {'Location': 'http://radio.example/\nprivate'}, b'', 'invalid_redirect'),
])
def test_classification(transport, status, headers, body, reason):
    transport[0].append(Response(body, status, headers))
    with pytest.raises(u.UpstreamError) as exc:
        u.open_station_stream('http://radio.example/a')
    assert exc.value.reason == reason
    assert 'radio.example' not in str(exc.value)
    assert transport[1][0].closed


def test_partial_prefix(transport):
    response = Response()
    original = response.read1
    response.read1 = lambda n: original(min(1, n))
    transport[0].append(response)
    stream = u.open_station_stream('http://radio.example/a')
    assert stream.read_chunk() == b'\xff\xfb\x92'
    stream.close()


def test_eight_stream_cap_and_release(transport):
    streams = []
    try:
        for _ in range(8):
            transport[0].append(Response())
            streams.append(u.open_station_stream('http://radio.example/a'))
        with pytest.raises(u.UpstreamError, match='capacity exhausted'):
            u.open_station_stream('http://radio.example/a')
        streams.pop().close()
        transport[0].append(Response())
        streams.append(u.open_station_stream('http://radio.example/a'))
    finally:
        for stream in streams:
            stream.close()


def test_read_timeout_no_retry(transport):
    response = Response()
    transport[0].append(response)
    stream = u.open_station_stream('http://radio.example/a')
    stream.read_chunk()
    response.read1 = Mock(side_effect=TimeoutError())
    with pytest.raises(u.UpstreamError) as exc:
        stream.read_chunk()
    assert exc.value.reason == 'read_timeout'
    assert len(transport[1]) == 1
    assert transport[1][0].closed


def test_tls_verified_hostname_and_pinned_connect(monkeypatch):
    raw, wrapped = Mock(), Mock()
    context = Mock()
    context.wrap_socket.return_value = wrapped
    factory = Mock(return_value=context)
    monkeypatch.setattr(ssl, 'create_default_context', factory)
    create = Mock(return_value=raw)
    monkeypatch.setattr(socket, 'create_connection', create)
    def connect(conn):
        conn.sock = socket.create_connection((conn.host, conn.port), conn.timeout)
    monkeypatch.setattr(http.client.HTTPConnection, 'connect', connect)
    connection = u._Connection('8.8.8.8', 'radio.example', 443, True, time.monotonic() + 15)
    connection.connect()
    try:
        assert create.call_args.args[0] == ('8.8.8.8', 443)
        factory.assert_called_once_with()
        context.wrap_socket.assert_called_once_with(
            raw, server_hostname='radio.example', do_handshake_on_connect=False)
        wrapped.do_handshake.assert_called_once_with()
    finally:
        connection.finish()


def test_real_default_context_verifies_certificates():
    context = ssl.create_default_context()
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_tls_failure_not_retried(transport):
    response = Response()
    transport[0].append(response)
    response.read1 = Mock(side_effect=ssl.SSLCertVerificationError())
    with pytest.raises(u.UpstreamError) as exc:
        u.open_station_stream('https://radio.example/a')
    assert exc.value.reason == 'tls_verification_failed'
    assert len(transport[1]) == 1


def test_close_interrupts_blocked_socket_read():
    # Local socketpair only; no external network or speaker.
    local, peer = socket.socketpair()
    connection = u._Connection('8.8.8.8', 'radio.example', 80, False, time.monotonic() + 15)
    connection.transport = local
    response = Mock()
    entered = threading.Event()

    def read(n):
        entered.set()
        return local.recv(n)

    response.read1 = read
    assert u._SLOTS.acquire(blocking=False)
    stream = u.RadioUpstream(connection, response, b'')
    result = []
    reader = threading.Thread(target=lambda: result.append(stream.read_chunk()))
    reader.start()
    assert entered.wait(1)
    stream.close()
    reader.join(1)
    peer.close()
    assert not reader.is_alive()
    assert result == [b'']


def test_startup_deadline(transport, monkeypatch):
    transport[0].append(Response())
    ticks = iter([0, 0, 0, 0, 16])
    monkeypatch.setattr(u.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(u.UpstreamError, match='startup timeout'):
        u.open_station_stream('http://radio.example/a')


@pytest.mark.parametrize('ip', ['224.0.0.1', 'ff02::1', 'fe80::1%eth0'])
def test_multicast_and_scoped_addresses_rejected(transport, monkeypatch, ip):
    monkeypatch.setattr(u, '_addresses', lambda *args: [ip])
    with pytest.raises(u.UpstreamError, match='unsafe destination'):
        u.open_station_stream('http://radio.example/a')


def test_https_redirect_cannot_silently_downgrade(transport):
    transport[0].append(Response(status=302, headers={'Location': 'http://other.example/a'}))
    with pytest.raises(u.UpstreamError, match='tls downgrade refused'):
        u.open_station_stream('https://radio.example/a')
    assert len(transport[1]) == 1


def test_redirect_loop(transport):
    transport[0].append(Response(status=302, headers={'Location': '/a'}))
    with pytest.raises(u.UpstreamError, match='redirect loop'):
        u.open_station_stream('http://radio.example/a')


def test_redirect_limit(transport):
    transport[0].extend(Response(status=302, headers={'Location': f'/{i}'}) for i in range(6))
    with pytest.raises(u.UpstreamError, match='redirect limit'):
        u.open_station_stream('http://radio.example/a')
    assert len(transport[1]) == 6
    assert all(c.closed for c in transport[1])


def test_absolute_timer_interrupts_socket_read(monkeypatch):
    local, peer = socket.socketpair()
    monkeypatch.setattr(http.client.HTTPConnection, 'connect', lambda self: setattr(self, 'sock', local))
    connection = u._Connection('8.8.8.8', 'radio.example', 80, False, time.monotonic() + .05)
    connection.connect()
    try:
        assert local.recv(1) == b''
    finally:
        connection.finish()
        peer.close()


def test_dns_error_is_classified(transport, monkeypatch):
    monkeypatch.setattr(u, '_addresses', Mock(side_effect=u.StreamError('DNS busy')))
    with pytest.raises(u.UpstreamError) as exc:
        u.open_station_stream('http://radio.example/a')
    assert exc.value.reason == 'address_lookup_failed'


@pytest.mark.parametrize('header', [
    b'\xff\xfd\x92',  # Layer II
    b'\xff\xff\x92',  # Layer I
    b'\xff\xeb\x92',  # reserved MPEG version
    b'\xff\xfb\x9c',  # reserved sample rate
    b'\xff\xfb\x02',  # free bitrate unsupported
    b'\xff\xfb\xf2',  # invalid bitrate
    b'\xff\xf1\x92',  # AAC ADTS, no MPEG layer
])
def test_non_mp3_frames_rejected_before_return(transport, header):
    transport[0].append(Response(header + b'x' * 600))
    with pytest.raises(u.UpstreamError, match='invalid mp3'):
        u.open_station_stream('http://radio.example/a')
    assert transport[1][0].closed


@pytest.mark.parametrize('header', [b'\xff\xfb\x92', b'\xff\xf3\x92', b'\xff\xe3\x42'])
def test_mpeg_1_2_25_layer3_supported(transport, header):
    transport[0].append(Response(header + b'x' * 600))
    stream = u.open_station_stream('http://radio.example/a')
    try:
        assert stream.read_chunk().startswith(header)
    finally:
        stream.close()


@pytest.mark.parametrize('failure', ['connection', 'response'])
def test_close_failure_releases_slot_once(transport, monkeypatch, failure):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(u, '_SLOTS', slots)
    response = Response()
    transport[0].append(response)
    stream = u.open_station_stream('http://radio.example/a')
    if failure == 'connection':
        transport[1][0].finish = Mock(side_effect=RuntimeError('close failed'))
    else:
        response.close = Mock(side_effect=RuntimeError('close failed'))
    with pytest.raises(RuntimeError):
        stream.close()
    stream.close()
    assert slots.acquire(blocking=False)
    assert not slots.acquire(blocking=False)
    if failure == 'connection':
        assert response.closed


def test_startup_close_failure_releases_slot(transport, monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(u, '_SLOTS', slots)
    response = Response(status=403)
    response.close = Mock(side_effect=RuntimeError('close failed'))
    transport[0].append(response)
    with pytest.raises(RuntimeError):
        u.open_station_stream('http://radio.example/a')
    assert slots.acquire(blocking=False)
    assert transport[1][0].closed
