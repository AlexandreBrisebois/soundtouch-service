"""Opt-in ICI packed-AAC adapter; no general HLS or FFmpeg network access."""
import http.client
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from app.core.radio_upstream import UpstreamError, _Connection, _destination

ORIGIN = 'https://rcavliveaudio.akamaized.net'
ROOT = '/hls/live/2006635/P-2QMTL0_MTL/'
SAVED_URL = ORIGIN + ROOT + 'master.m3u8'
PLAYLIST = ORIGIN + ROOT + 'adaptive_128/chunklist_ao.m3u8'
MAX_PLAYLIST = 128 * 1024
MAX_SEGMENT = 256 * 1024
MAX_CHUNK = 64 * 1024
_SLOTS = threading.BoundedSemaphore(2)
_SEGMENT = re.compile(r'adaptive_128/[A-Za-z0-9_-]+/[0-9]+/media_ao_[0-9]+\.aac\Z')


def available() -> bool:
    return (os.environ.get('WISP_ENABLE_HLS_RADIO') == '1'
            and sys.platform == 'linux' and shutil.which('ffmpeg') is not None)


def validate_url(url: str) -> None:
    p = urlsplit(url)
    if (p.scheme != 'https' or p.netloc != 'rcavliveaudio.akamaized.net'
            or p.query or p.fragment or not p.path.startswith(ROOT)
            or not (p.path == ROOT + 'adaptive_128/chunklist_ao.m3u8'
                    or _SEGMENT.fullmatch(p.path[len(ROOT):]))):
        raise UpstreamError('hls_unsupported_destination')


@dataclass(frozen=True)
class Playlist:
    sequence: int
    discontinuity: int
    duration: int
    urls: tuple[str, ...]


def parse_playlist(data: bytes) -> Playlist:
    if len(data) > MAX_PLAYLIST:
        raise UpstreamError('hls_playlist_too_large')
    try:
        lines = data.decode('utf-8').splitlines()
        if not lines or lines[0] != '#EXTM3U':
            raise ValueError
        sequence = None
        discontinuity = 0
        duration = None
        urls: list[str] = []
        pending = False
        seen = set()
        for line in lines[1:]:
            if not line:
                continue
            if line.startswith(('#EXT-X-MEDIA-SEQUENCE:', '#EXT-X-DISCONTINUITY-SEQUENCE:',
                                '#EXT-X-TARGETDURATION:', '#EXT-X-VERSION:')):
                tag, value = line.split(':', 1)
                if tag in seen or not value.isdecimal() or len(value) > 12:
                    raise ValueError
                seen.add(tag)
                number = int(value)
                if tag == '#EXT-X-MEDIA-SEQUENCE':
                    sequence = number
                elif tag == '#EXT-X-DISCONTINUITY-SEQUENCE':
                    discontinuity = number
                elif tag == '#EXT-X-TARGETDURATION':
                    duration = number
                elif number != 4:
                    raise ValueError
            elif line.startswith('#EXTINF:'):
                if pending:
                    raise ValueError
                seconds = float(line[8:].split(',', 1)[0])
                if not 0 < seconds <= 10:
                    raise ValueError
                pending = True
            elif line.startswith('#'):
                # Keys/maps/discontinuity/byterange/endlist etc. need another adapter.
                raise ValueError
            else:
                if not pending or len(urls) >= 2048:
                    raise ValueError
                url = urljoin(PLAYLIST, line)
                validate_url(url)
                if url in urls:
                    raise ValueError
                urls.append(url)
                pending = False
        if (pending or sequence is None or duration is None or not 1 <= duration <= 10
                or len(urls) < 3):
            raise ValueError
        return Playlist(sequence, discontinuity, duration, tuple(urls))
    except (ValueError, UnicodeError):
        raise UpstreamError('hls_unsupported_playlist') from None


class Fetcher:
    """Finite public-pinned HTTPS requests, interruptible by close()."""
    def __init__(self):
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.connection = None

    def close(self):
        self.closed.set()
        with self.lock:
            connection = self.connection
        if connection is not None:
            connection.finish()

    def fetch(self, url: str, limit: int) -> bytes:
        deadline = time.monotonic() + 10
        visited = set()
        for _ in range(3):
            validate_url(url)
            if self.closed.is_set():
                raise UpstreamError('hls_canceled')
            if url in visited or time.monotonic() >= deadline:
                raise UpstreamError('hls_fetch_timeout')
            visited.add(url)
            ip, hostname, host, port, path, secure = _destination(url, 2)
            connection = _Connection(ip, hostname, port, secure, deadline)
            response = None
            with self.lock:
                if self.closed.is_set():
                    raise UpstreamError('hls_canceled')
                self.connection = connection
            try:
                connection.request('GET', path, headers={'Host': host,
                    'User-Agent': 'Wisp-radio/1', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location or len(location) > 4096:
                        raise UpstreamError('hls_invalid_redirect')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise UpstreamError('hls_upstream_unavailable')
                if response.getheader('Content-Encoding') not in (None, 'identity'):
                    raise UpstreamError('hls_encoded_response')
                result = bytearray()
                while True:
                    if self.closed.is_set():
                        raise UpstreamError('hls_canceled')
                    if time.monotonic() >= deadline:
                        raise UpstreamError('hls_fetch_timeout')
                    chunk = response.read1(min(16384, limit + 1 - len(result)))
                    if not chunk:
                        return bytes(result)
                    result.extend(chunk)
                    if len(result) > limit:
                        raise UpstreamError('hls_response_too_large')
            except (OSError, http.client.HTTPException, ValueError):
                raise UpstreamError('hls_fetch_failed') from None
            finally:
                try:
                    connection.finish()
                finally:
                    try:
                        if response is not None:
                            response.close()
                    finally:
                        with self.lock:
                            if self.connection is connection:
                                self.connection = None
        raise UpstreamError('hls_redirect_limit')


class ICIStream:
    content_type = 'audio/mpeg'

    def __init__(self, fetcher: Fetcher, process: subprocess.Popen):
        self.fetcher = fetcher
        self.process = process
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.cleanup_lock = threading.Lock()
        self.worker_done = threading.Event()
        self.process_reaped = False
        self.error = None
        self.prefix = b''
        self.read_timeout = 15
        self.startup_deadline: float | None = time.monotonic() + 15
        self.slot_released = False
        self.worker = threading.Thread(target=self._feed, daemon=True, name='ici-aac-feed')
        self.worker.start()

    def _write(self, data: bytes):
        assert self.process.stdin is not None
        view = memoryview(data)
        deadline = time.monotonic() + 20
        with selectors.DefaultSelector() as poll:
            poll.register(self.process.stdin, selectors.EVENT_WRITE)
            while view:
                if self.closed.is_set():
                    return
                if time.monotonic() >= deadline:
                    raise UpstreamError('hls_transcoder_stalled')
                if poll.select(.1):
                    try:
                        count = os.write(self.process.stdin.fileno(), view[:16384])
                    except BlockingIOError:
                        continue
                    view = view[count:]

    def _feed(self):
        try:
            previous = None
            next_sequence = None
            unchanged_since = time.monotonic()
            while not self.closed.is_set():
                playlist = parse_playlist(self.fetcher.fetch(PLAYLIST, MAX_PLAYLIST))
                end = playlist.sequence + len(playlist.urls)
                if previous is not None:
                    old_end = previous.sequence + len(previous.urls)
                    if (playlist.sequence < previous.sequence or end < old_end
                            or playlist.discontinuity != previous.discontinuity):
                        raise UpstreamError('hls_sequence_changed')
                    overlap = max(playlist.sequence, previous.sequence)
                    for seq in range(overlap, min(end, old_end)):
                        if (playlist.urls[seq - playlist.sequence]
                                != previous.urls[seq - previous.sequence]):
                            raise UpstreamError('hls_sequence_changed')
                    if end > old_end:
                        unchanged_since = time.monotonic()
                    if time.monotonic() - unchanged_since > 3 * playlist.duration:
                        raise UpstreamError('hls_playlist_stale')
                if next_sequence is None:
                    next_sequence = end - 3
                if next_sequence < playlist.sequence:
                    raise UpstreamError('hls_segment_gap')
                for seq in range(next_sequence, end):
                    if self.closed.is_set():
                        return
                    segment = self.fetcher.fetch(playlist.urls[seq - playlist.sequence], MAX_SEGMENT)
                    if not segment or not (segment.startswith(b'ID3')
                                           or segment[:1] == b'\xff'):
                        raise UpstreamError('hls_invalid_audio')
                    self._write(segment)
                    next_sequence = seq + 1
                previous = playlist
                # No retry after errors; only poll a successful advancing playlist.
                if self.closed.wait(playlist.duration / 2):
                    return
        except Exception:
            if not self.closed.is_set():
                self.error = UpstreamError('hls_stream_failed')
            # Reader will see EOF/error. It owns close/reap and slot release.
            if self.process.stdin is not None:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
        finally:
            self.worker_done.set()
            if self.closed.is_set():
                self._release_slot()

    def _release_slot(self):
        with self.lock:
            if (self.process_reaped and self.worker_done.is_set()
                    and not self.slot_released):
                self.slot_released = True
                _SLOTS.release()

    def read_chunk(self, size: int = MAX_CHUNK) -> bytes:
        if not isinstance(size, int) or not 1 <= size <= MAX_CHUNK:
            raise ValueError('Invalid chunk size.')
        if self.closed.is_set():
            return b''
        if self.prefix:
            data, self.prefix = self.prefix[:size], self.prefix[size:]
            return data
        assert self.process.stdout is not None
        deadline = (self.startup_deadline if self.startup_deadline is not None
                    else time.monotonic() + self.read_timeout)
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(self.process.stdout, selectors.EVENT_READ)
                while not self.closed.is_set():
                    if self.error:
                        raise self.error
                    if time.monotonic() >= deadline:
                        raise UpstreamError('hls_transcoder_timeout')
                    if poll.select(.1):
                        chunk = os.read(self.process.stdout.fileno(), size)
                        if chunk:
                            return chunk
                        raise UpstreamError('hls_transcoder_ended')
            return b''
        except (OSError, ValueError, UpstreamError):
            if self.closed.is_set():
                return b''
            self.close()
            raise UpstreamError('hls_stream_failed') from None

    def close(self):
        self.closed.set()
        # Repeated calls may retry an unconfirmed reap; closed never means reaped.
        with self.cleanup_lock:
            try:
                self.fetcher.close()
            except Exception:
                pass
            try:
                if self.process.poll() is None:
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except OSError:
                        pass
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    self.process.wait(timeout=1)
                self.process_reaped = True
            except Exception:
                # Retain capacity until a later close confirms process death.
                pass
            self.worker.join(timeout=2)
            for pipe in (self.process.stdin, self.process.stdout):
                if pipe is not None:
                    try:
                        pipe.close()
                    except Exception:
                        pass
            self._release_slot()


def supports_exact_url(saved_url: str) -> bool:
    return saved_url == SAVED_URL and available()


def open_ici_stream(saved_url: str) -> ICIStream:
    if saved_url != SAVED_URL:
        raise UpstreamError('hls_station_unsupported')
    if not available():
        raise UpstreamError('hls_not_enabled_or_ffmpeg_missing')
    if not _SLOTS.acquire(blocking=False):
        raise UpstreamError('hls_capacity_exhausted')
    fetcher = Fetcher()
    process = None
    stream = None
    try:
        process = subprocess.Popen([sys.executable, '-m', 'app.core.radio_transcoder'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, bufsize=0)
        assert process.stdin is not None and process.stdout is not None
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        stream = ICIStream(fetcher, process)
        try:
            prefix = b''
            while len(prefix) < 4:
                chunk = stream.read_chunk(4096)
                if not chunk:
                    raise UpstreamError('hls_transcoder_ended')
                prefix += chunk
            if (len(prefix) < 4 or prefix[0] != 0xff or prefix[1] & 0xe0 != 0xe0
                    or prefix[1] & 6 != 2 or prefix[1] & 0x18 == 0x08
                    or prefix[2] & 0x0c == 0x0c or prefix[2] & 0xf0 in (0, 0xf0)):
                raise UpstreamError('hls_invalid_mp3_output')
            stream.prefix = prefix
            stream.read_timeout = 20
            stream.startup_deadline = None
            return stream
        except Exception:
            stream.close()
            raise
    except Exception:
        if stream is not None:
            stream.close()
        else:
            try:
                fetcher.close()
            except Exception:
                pass
            reaped = process is None
            if process is not None:
                try:
                    process.kill()
                    process.wait(timeout=1)
                    reaped = True
                except Exception:
                    pass
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except Exception:
                            pass
            if reaped:
                _SLOTS.release()
        raise UpstreamError('hls_transcoder_unavailable') from None
