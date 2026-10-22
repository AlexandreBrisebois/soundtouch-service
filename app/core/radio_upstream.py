"""Bounded live MP3 transport. Caller selects an allowlisted station URL.

Each redirect is resolved afresh and pinned to a public address. HTTPS retains
certificate/hostname verification and SNI. This module never retries or records.
"""
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

from app.core.radio_stream import StreamError, _addresses

MAX_CHUNK = 64 * 1024
_SLOTS = threading.BoundedSemaphore(8)


class UpstreamError(StreamError):
    """URL-free public failure with a stable classification."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__('Radio upstream: ' + reason.replace('_', ' ') + '.')


def _destination(url: str, timeout: float) -> tuple[str, str, str, int, str, bool]:
    try:
        p = urlsplit(url)
        if (len(url) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in url)
                or p.scheme not in ('http', 'https') or not p.hostname
                or p.username is not None or p.password is not None or p.fragment
                or p.port not in (None, 443 if p.scheme == 'https' else 80)):
            raise ValueError
        addresses = _addresses(p.hostname, timeout)
        if not addresses or any(not ipaddress.ip_address(ip).is_global
                                or ipaddress.ip_address(ip).is_multicast
                                or '%' in ip for ip in addresses):
            raise ValueError
        return (addresses[0], p.hostname, p.netloc, 443 if p.scheme == 'https' else 80,
                (p.path or '/') + ('?' + p.query if p.query else ''), p.scheme == 'https')
    except StreamError:
        raise UpstreamError('address_lookup_failed') from None
    except (ValueError, UnicodeError):
        raise UpstreamError('unsafe_destination') from None


class _Connection(http.client.HTTPConnection):
    def __init__(self, ip: str, hostname: str, port: int, secure: bool, deadline: float):
        super().__init__(ip, port, timeout=max(.001, min(2, deadline - time.monotonic())))
        self.hostname = hostname
        self.secure = secure
        self.deadline = deadline
        self.transport: socket.socket | None = None
        self.timer: threading.Timer | None = None

    def connect(self) -> None:
        super().connect()
        self.transport = self.sock
        self.timer = threading.Timer(max(0, self.deadline - time.monotonic()), self.abort)
        self.timer.daemon = True
        self.timer.start()
        if self.secure:
            # Default context verifies CA chain and hostname; connect target is pinned,
            # while server_hostname remains the original host (not its numeric IP).
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.hostname, do_handshake_on_connect=False)
            self.transport = self.sock
            self.sock.do_handshake()

    def abort(self) -> None:
        sock = self.transport
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def streaming(self, idle_timeout: float) -> None:
        if self.timer is not None:
            self.timer.cancel()
        if self.transport is not None:
            self.transport.settimeout(idle_timeout)

    def finish(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
        try:
            self.abort()
        finally:
            super().close()


def _dispose(connection: _Connection | None,
             response: http.client.HTTPResponse | None) -> None:
    try:
        if connection is not None:
            connection.finish()
    finally:
        if response is not None:
            response.close()


class RadioUpstream:
    content_type = 'audio/mpeg'

    def __init__(self, connection: _Connection, response: http.client.HTTPResponse,
                 prefix: bytes):
        self._connection = connection
        self._response = response
        self._prefix = prefix
        self._closed = False
        self._lock = threading.Lock()

    def read_chunk(self, size: int = MAX_CHUNK) -> bytes:
        """Single consumer; close may interrupt a blocked read from another thread."""
        if not isinstance(size, int) or not 1 <= size <= MAX_CHUNK:
            raise ValueError('Chunk size must be between 1 and 65536.')
        if self._closed:
            return b''
        if self._prefix:
            chunk, self._prefix = self._prefix[:size], self._prefix[size:]
            return chunk
        try:
            chunk = self._response.read1(size)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            was_closed = self._closed
            self.close()
            if was_closed:
                return b''
            raise UpstreamError('read_timeout' if isinstance(exc, TimeoutError)
                                else 'read_failed') from None
        if not chunk:
            self.close()
        return chunk

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            # Shutdown first: response.close alone can wait for a blocked reader.
            try:
                _dispose(self._connection, self._response)
            finally:
                self._prefix = b''
                _SLOTS.release()


def open_station_stream(stream_url: str, *, startup_timeout: float = 15,
                        idle_timeout: float = 15) -> RadioUpstream:
    """Open/qualify before speaker mutation. Caller must close returned stream.

    URL selection belongs to the station policy layer. No arbitrary URL should
    be accepted from a relay client. This layer additionally enforces public DNS,
    standard ports, six hops, bounded headers (http.client), and eight streams.
    """
    if not 0 < startup_timeout <= 30 or not 0 < idle_timeout <= 30:
        raise ValueError('Timeout must be greater than zero and at most 30 seconds.')
    if not _SLOTS.acquire(blocking=False):
        raise UpstreamError('capacity_exhausted')
    deadline = time.monotonic() + startup_timeout
    connection = None
    response = None
    transferred = False
    try:
        seen: set[str] = set()
        url = stream_url
        for _ in range(6):
            if time.monotonic() >= deadline:
                raise UpstreamError('startup_timeout')
            if url in seen:
                raise UpstreamError('redirect_loop')
            seen.add(url)
            ip, hostname, host, port, path, secure = _destination(
                url, min(2, max(.001, deadline - time.monotonic())))
            if time.monotonic() >= deadline:
                raise UpstreamError('startup_timeout')
            connection = _Connection(ip, hostname, port, secure, deadline)
            connection.request('GET', path, headers={
                'Host': host, 'User-Agent': 'Wisp-radio/1', 'Icy-MetaData': '0',
                'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if (not location or len(location) > 4096
                        or any(ord(c) <= 32 or ord(c) == 127 for c in location)):
                    raise UpstreamError('invalid_redirect')
                redirected = urljoin(url, location)
                if secure and urlsplit(redirected).scheme != 'https':
                    raise UpstreamError('tls_downgrade_refused')
                url = redirected
                _dispose(connection, response)
                connection, response = None, None
                continue
            if response.status in (401, 403):
                raise UpstreamError('access_denied')
            if response.status != 200:
                raise UpstreamError('http_status')
            if (response.getheader('Content-Type') or '').split(';')[0].lower() not in (
                    'audio/mpeg', 'audio/mp3'):
                raise UpstreamError('unsupported_format')
            if (response.getheader('icy-metaint') not in (None, '0')
                    or response.getheader('Content-Encoding') not in (None, 'identity')):
                raise UpstreamError('unsupported_framing')
            prefix = bytearray()
            while len(prefix) < 512:
                chunk = response.read1(512 - len(prefix))
                if time.monotonic() >= deadline:
                    raise UpstreamError('startup_timeout')
                if not chunk:
                    break
                prefix.extend(chunk)
                if any(prefix[i] == 255 and prefix[i + 1] & 0xE0 == 0xE0
                       and prefix[i + 1] & 6 == 2  # MPEG Layer III only
                       and prefix[i + 1] & 0x18 != 0x08  # no reserved MPEG version
                       and prefix[i + 2] & 0x0C != 0x0C  # no reserved sample rate
                       and prefix[i + 2] & 0xF0 not in (0, 0xF0)
                       for i in range(len(prefix) - 2)):
                    connection.streaming(idle_timeout)
                    result = RadioUpstream(connection, response, bytes(prefix))
                    transferred = True
                    return result
            raise UpstreamError('invalid_mp3')
        raise UpstreamError('redirect_limit')
    except ssl.SSLError:
        raise UpstreamError('tls_verification_failed') from None
    except TimeoutError:
        raise UpstreamError('startup_timeout') from None
    except (OSError, http.client.HTTPException):
        raise UpstreamError('connection_failed') from None
    finally:
        if not transferred:
            try:
                _dispose(connection, response)
            finally:
                _SLOTS.release()
