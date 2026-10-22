"""Read-only MP3 qualification for a small, explicit direct-test candidate set.

Never persist resolved URLs. Every HTTP hop is pinned to a validated public IP,
with no environment proxy, credentials, TLS downgrade heuristic, or retries.
"""
import http.client
import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from urllib.parse import urljoin, urlsplit

# Exact saved URLs only: a user-edited URL must not silently select another stream.
CANDIDATES = {
    'https://live.amperwave.net/direct/vox-wezffmmp3-imc':
        'http://live.amperwave.net/direct/vox-wezffmmp3-imc',
    'https://playerservices.streamtheworld.com/api/livestream-redirect/WBTZFM.mp3':
        'http://playerservices.streamtheworld.com/api/livestream-redirect/WBTZFM.mp3',
    'https://cbcradiolive.akamaized.net/hls/live/2041030/ES_R1EMT/master.m3u8':
        'http://playerservices.streamtheworld.com/api/livestream-redirect/CBMEFM_CBC.mp3',
}
_DNS_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='radio-dns')
_DNS_SLOTS = threading.BoundedSemaphore(2)


class StreamError(ValueError):
    """Deliberately public, URL-free error."""


def candidate(saved_url: str) -> str:
    value = CANDIDATES.get(saved_url)
    if value is None and saved_url in CANDIDATES.values():
        value = saved_url
    if value is None:
        raise StreamError('No verified HTTP MP3 candidate for this saved station.')
    return value


def _addresses(host: str, timeout: float) -> list[str]:
    if not _DNS_SLOTS.acquire(blocking=False):
        raise StreamError('Radio address lookup is busy. No speaker command was sent.')
    future = _DNS_POOL.submit(socket.getaddrinfo, host, 80, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        return list(dict.fromkeys(str(item[4][0]) for item in future.result(timeout=timeout)))
    except (TimeoutError, OSError):
        raise StreamError('Radio address lookup unavailable.') from None


def _destination(url: str, timeout: float) -> tuple[str, str, str]:
    try:
        parsed = urlsplit(url)
        if (len(url) > 4096 or any(ord(c) <= 32 for c in url)
                or parsed.scheme != 'http' or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 80) or parsed.fragment):
            raise ValueError
        addresses = _addresses(parsed.hostname, timeout)
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError
        return addresses[0], parsed.netloc, (parsed.path or '/') + (
            '?' + parsed.query if parsed.query else '')
    except (ValueError, UnicodeError):
        raise StreamError('Radio destination is not ordinary public HTTP.') from None


class _Connection(http.client.HTTPConnection):
    """Close the connected socket at the absolute budget, including slow headers."""
    def __init__(self, host: str, *, deadline: float):
        self.deadline = deadline
        self.timer: threading.Timer | None = None
        super().__init__(host, 80, timeout=min(2, max(.001, deadline - time.monotonic())))

    def connect(self) -> None:
        super().connect()
        sock = self.sock
        def expire() -> None:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        self.timer = threading.Timer(max(0, self.deadline - time.monotonic()), expire)
        self.timer.daemon = True
        self.timer.start()

    def finish(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
        super().close()


def resolve(saved_url: str) -> str:
    """At most six pinned HTTP requests, 512 audio bytes, and a 15-second budget."""
    url = candidate(saved_url)
    seen: set[str] = set()
    deadline = time.monotonic() + 15
    for _ in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or url in seen:
            raise StreamError('Radio redirect deadline or loop.')
        seen.add(url)
        ip, host, path = _destination(url, min(2, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StreamError('Radio lookup deadline.')
        connection = _Connection(ip, deadline=deadline)
        response = None
        try:
            connection.request('GET', path, headers={
                'Host': host, 'User-Agent': 'Wisp-direct-test/1',
                'Icy-MetaData': '0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or len(location) > 4096 or any(ord(c) <= 32 for c in location):
                    raise StreamError('Radio redirect has no destination.')
                url = urljoin(url, location)
                continue
            content_type = (response.getheader('Content-Type') or '').split(';')[0].lower()
            if response.status != 200 or content_type not in ('audio/mpeg', 'audio/mp3'):
                raise StreamError('Radio did not return HTTP 200 MP3 audio.')
            if (response.getheader('icy-metaint') not in (None, '0')
                    or response.getheader('Content-Encoding') not in (None, 'identity')):
                raise StreamError('Radio returned unsupported audio framing.')
            data = bytearray()
            while len(data) < 512 and time.monotonic() < deadline:
                chunk = response.read1(512 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
                frame = any(data[i] == 255 and data[i + 1] & 0xE0 == 0xE0
                            and data[i + 1] & 6 != 0 and data[i + 2] & 0xF0 not in (0, 0xF0)
                            for i in range(len(data) - 2))
                if frame and time.monotonic() < deadline:
                    return url
            raise StreamError('Radio MP3 validation failed or timed out.')
        except (OSError, http.client.HTTPException):
            raise StreamError('Radio stream could not be checked.') from None
        finally:
            if response is not None:
                response.close()
            connection.finish()
    raise StreamError('Radio exceeded the redirect limit.')
