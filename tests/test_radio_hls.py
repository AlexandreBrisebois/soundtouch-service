import shutil
import sys
import subprocess
import threading
import time

import pytest

from app.core import radio_hls as hls
from app.core.radio_upstream import UpstreamError


def playlist(sequence=100, count=5, discontinuity=1):
    return ('#EXTM3U\n#EXT-X-VERSION:4\n#EXT-X-TARGETDURATION:7\n'
            f'#EXT-X-MEDIA-SEQUENCE:{sequence}\n'
            f'#EXT-X-DISCONTINUITY-SEQUENCE:{discontinuity}\n' + ''.join(
                f'#EXTINF:6.0,\nabc/00001/media_ao_{i}.aac\n'
                for i in range(sequence, sequence + count))).encode()


def test_playlist_live_tail():
    p = hls.parse_playlist(playlist(100, 600))
    assert p.sequence == 100 and len(p.urls) == 600
    assert p.urls[-3].endswith('697.aac')


@pytest.mark.parametrize('tag', ['#EXT-X-KEY:METHOD=AES-128,URI="http://localhost"',
    '#EXT-X-MAP:URI="a"', '#EXT-X-BYTERANGE:50', '#EXT-X-DISCONTINUITY',
    '#EXT-X-ENDLIST', '#EXT-X-STREAM-INF:BANDWIDTH=128000'])
def test_unsupported_tags(tag):
    with pytest.raises(UpstreamError):
        hls.parse_playlist(playlist() + tag.encode() + b'\n')


@pytest.mark.parametrize('url', ['http://rcavliveaudio.akamaized.net' + hls.ROOT + 'x',
    'https://localhost/x', 'https://rcavliveaudio.akamaized.net@127.0.0.1/a',
    hls.PLAYLIST + '?x=1', hls.PLAYLIST + '#x',
    hls.ORIGIN + hls.ROOT + 'adaptive_128/../../secret',
    hls.ORIGIN + hls.ROOT + 'adaptive_128/%2e%2e/1/media_ao_1.aac',
    'https://rcavliveaudio.akamaized.net:443' + hls.ROOT + 'adaptive_128/chunklist_ao.m3u8'])
def test_url_closed_allowlist(url):
    with pytest.raises(UpstreamError):
        hls.validate_url(url)


def test_duplicate_and_truncated_playlist():
    data = playlist()
    for bad in [data + b'#EXTINF:6,\n', data.replace(b'media_ao_101', b'media_ao_100'),
                b'x' * (hls.MAX_PLAYLIST + 1), data.replace(b'6.0', b'nan')]:
        with pytest.raises(UpstreamError):
            hls.parse_playlist(bad)


def test_disabled_and_wrong_station(monkeypatch):
    monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', '0')
    assert not hls.supports_exact_url(hls.SAVED_URL)
    with pytest.raises(UpstreamError):
        hls.open_ici_stream(hls.SAVED_URL)
    monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', '1')
    with pytest.raises(UpstreamError):
        hls.open_ici_stream('https://example.com/custom.m3u8')


@pytest.fixture
def net(monkeypatch):
    replies, calls = [], []
    class Reply:
        status = 200
        headers = {}
        def __init__(self, data=b'abc', status=200, headers=None):
            self.data, self.status, self.headers = data, status, headers or {}
        def getheader(self, name):
            return self.headers.get(name)
        def read1(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data
        def close(self):
            pass
    class Connection:
        def __init__(self, *args):
            calls.append(args)
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return replies.pop(0)
        def finish(self):
            pass
    monkeypatch.setattr(hls, '_destination', lambda url, timeout:
        ('1.1.1.1', 'rcavliveaudio.akamaized.net', 'rcavliveaudio.akamaized.net',
         443, '/allowed', True))
    monkeypatch.setattr(hls, '_Connection', Connection)
    return replies, calls, Reply


def test_fetch_caps_redirects_and_cancel(net):
    replies, calls, Reply = net
    f = hls.Fetcher()
    replies.append(Reply(b'abcdef'))
    with pytest.raises(UpstreamError):
        f.fetch(hls.PLAYLIST, 4)
    replies.append(Reply(status=302, headers={'Location': 'https://127.0.0.1/private'}))
    with pytest.raises(UpstreamError):
        f.fetch(hls.PLAYLIST, 20)
    assert len(calls) == 2  # unapproved redirect never connects
    f.close()
    with pytest.raises(UpstreamError):
        f.fetch(hls.PLAYLIST, 20)
    assert len(calls) == 2


class DummyPipe:
    def close(self):
        pass


class DummyProcess:
    stdin = DummyPipe()


@pytest.mark.parametrize('second', [playlist(99), playlist(101, discontinuity=2),
    playlist(200), playlist().replace(b'media_ao_104', b'media_ao_999')])
def test_sequence_failures(second):
    calls = []
    class Fetch:
        def fetch(self, url, limit):
            if url == hls.PLAYLIST:
                calls.append('playlist')
                return playlist() if calls.count('playlist') == 1 else second
            return b'ID3test'
    stream = hls.ICIStream.__new__(hls.ICIStream)
    stream.fetcher, stream.process = Fetch(), DummyProcess()
    stream.closed = threading.Event()
    stream.error = None
    stream.worker_done = threading.Event()
    stream._write = lambda data: None
    # Replace wait to poll immediately; bounded invalid second playlist ends loop.
    stream.closed.wait = lambda timeout: False
    stream._feed()
    assert stream.error is not None


def test_no_segment_replay_and_tail_start():
    calls = []
    class Fetch:
        def fetch(self, url, limit):
            calls.append(url)
            if url == hls.PLAYLIST:
                return playlist()
            return b'ID3test'
    stream = hls.ICIStream.__new__(hls.ICIStream)
    stream.fetcher, stream.process = Fetch(), DummyProcess()
    stream.closed = threading.Event()
    stream.error = None
    stream.worker_done = threading.Event()
    stream._write = lambda data: None
    def wait(timeout):
        if calls.count(hls.PLAYLIST) == 2:
            return True
        return False
    stream.closed.wait = wait
    stream._feed()
    assert [u.rsplit('_', 1)[-1] for u in calls if u != hls.PLAYLIST] == [
        '102.aac', '103.aac', '104.aac']


@pytest.mark.skipif(sys.platform != 'linux' or shutil.which('ffmpeg') is None,
                    reason='Linux FFmpeg adapter unavailable')
def test_real_pipe_transcoder_two_sessions_cancel_isolation(monkeypatch):
    # Synthetic tone only: no broadcaster content, network, speaker, or recording.
    result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        'sine=frequency=440:duration=6', '-c:a', 'aac', '-f', 'adts', 'pipe:1'],
        capture_output=True, check=True, timeout=10)
    class Fetch:
        def __init__(self):
            self.closed = False
        def fetch(self, url, limit):
            if self.closed:
                raise UpstreamError('canceled')
            return playlist() if url == hls.PLAYLIST else result.stdout
        def close(self):
            self.closed = True
    monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', '1')
    monkeypatch.setattr(hls, 'Fetcher', Fetch)
    a = hls.open_ici_stream(hls.SAVED_URL)
    b = hls.open_ici_stream(hls.SAVED_URL)
    try:
        with pytest.raises(UpstreamError):
            hls.open_ici_stream(hls.SAVED_URL)
        assert a.read_chunk(4096).startswith(b'\xff')
        start = time.monotonic()
        a.close()
        a.close()
        assert time.monotonic() - start < 4
        assert a.process.poll() is not None
        assert b.read_chunk(4096)
        assert a.read_chunk() == b''
    finally:
        a.close()
        b.close()
    assert b.process.poll() is not None
    assert not a.worker.is_alive() and not b.worker.is_alive()


def test_close_interrupts_reader_waiting_for_audio(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(hls, '_SLOTS', slots)
    def feed(stream):
        stream.closed.wait()
        stream.worker_done.set()
        stream._release_slot()
    monkeypatch.setattr(hls.ICIStream, '_feed', feed)
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True, bufsize=0)
    stream = hls.ICIStream(hls.Fetcher(), process)
    result = []
    reader = threading.Thread(target=lambda: result.append(stream.read_chunk()))
    reader.start()
    try:
        time.sleep(.05)
        stream.close()
        reader.join(timeout=2)
        assert not reader.is_alive() and result == [b'']
        assert process.poll() is not None
        assert slots.acquire(blocking=False)
    finally:
        stream.close()


def test_fetch_close_interrupts_active_connection(monkeypatch):
    entered, canceled = threading.Event(), threading.Event()
    class Connection:
        def __init__(self, *args):
            pass
        def request(self, *args, **kwargs):
            entered.set()
            assert canceled.wait(2)
            raise OSError('interrupted')
        def finish(self):
            canceled.set()
    monkeypatch.setattr(hls, '_Connection', Connection)
    monkeypatch.setattr(hls, '_destination', lambda *args:
        ('1.1.1.1', 'rcavliveaudio.akamaized.net', 'rcavliveaudio.akamaized.net',
         443, '/allowed', True))
    f = hls.Fetcher()
    errors = []
    def run():
        try:
            f.fetch(hls.PLAYLIST, 100)
        except UpstreamError as exc:
            errors.append(exc)
    worker = threading.Thread(target=run)
    worker.start()
    assert entered.wait(1)
    f.close()
    worker.join(timeout=1)
    assert not worker.is_alive() and len(errors) == 1


def test_transcoder_has_only_pipe_protocol_and_child_resource_limits(monkeypatch):
    from app.core import radio_transcoder as transcoder
    limits, calls = [], []
    monkeypatch.setattr(transcoder.resource, 'setrlimit', lambda *args: limits.append(args))
    monkeypatch.setattr(transcoder.shutil, 'which', lambda name: '/usr/bin/ffmpeg')
    monkeypatch.setattr(transcoder.os, 'execv', lambda *args: calls.append(args))
    transcoder.main()
    command = calls[0][1]
    assert command[command.index('-protocol_whitelist') + 1] == 'pipe'
    assert command[command.index('-i') + 1] == 'pipe:0'
    assert command[-1] == 'pipe:1'
    assert not any('http' in arg for arg in command)
    assert (transcoder.resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2) in limits


def test_cleanup_exceptions_do_not_skip_reap_and_slots_need_both_barriers(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(hls, '_SLOTS', slots)
    class BadClose:
        def close(self):
            raise OSError('close failed')
    class Worker:
        def join(self, timeout):
            pass
    class Process:
        pid = 42
        stdin = stdout = BadClose()
        count = 0
        def poll(self):
            return None
        def wait(self, timeout):
            self.count += 1
            if self.count == 1:
                raise subprocess.TimeoutExpired('ffmpeg', timeout)
            return 0
    signals = []
    monkeypatch.setattr(hls.os, 'killpg', lambda pid, sig: signals.append(sig))
    stream = hls.ICIStream.__new__(hls.ICIStream)
    stream.closed = threading.Event()
    stream.worker_done = threading.Event()
    stream.lock = threading.Lock()
    stream.cleanup_lock = threading.Lock()
    stream.process_reaped = stream.slot_released = False
    stream.fetcher, stream.process, stream.worker = BadClose(), Process(), Worker()
    stream.close()
    assert len(signals) == 2
    assert stream.process_reaped
    assert not slots.acquire(blocking=False)  # process reaped, worker still pending
    stream.worker_done.set()
    stream._release_slot()
    assert slots.acquire(blocking=False)
    stream.close()
    assert not slots.acquire(blocking=False)  # idempotent release


def test_capacity_held_when_reap_unconfirmed(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(hls, '_SLOTS', slots)
    monkeypatch.setattr(hls.os, 'killpg', lambda *args: None)
    class Worker:
        def join(self, timeout):
            pass
    class Process:
        pid = 42
        stdin = stdout = DummyPipe()
        def poll(self):
            return None
        def wait(self, timeout):
            raise subprocess.TimeoutExpired('ffmpeg', timeout)
    stream = hls.ICIStream.__new__(hls.ICIStream)
    stream.closed = threading.Event()
    stream.worker_done = threading.Event()
    stream.worker_done.set()
    stream.lock = threading.Lock()
    stream.cleanup_lock = threading.Lock()
    stream.process_reaped = stream.slot_released = False
    stream.fetcher, stream.process, stream.worker = hls.Fetcher(), Process(), Worker()
    stream.close()
    assert not slots.acquire(blocking=False)
    stream.process.wait = lambda timeout: 0
    stream.close()
    assert slots.acquire(blocking=False)


def test_spawn_failure_releases_capacity_even_fetch_close_throws(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(hls, '_SLOTS', slots)
    monkeypatch.setattr(hls, 'available', lambda: True)
    class Fetch:
        def close(self):
            raise OSError('cleanup failed')
    monkeypatch.setattr(hls, 'Fetcher', Fetch)
    def spawn(*args, **kwargs):
        raise OSError('spawn failed')
    monkeypatch.setattr(hls.subprocess, 'Popen', spawn)
    with pytest.raises(UpstreamError):
        hls.open_ici_stream(hls.SAVED_URL)
    assert slots.acquire(blocking=False)


@pytest.mark.parametrize('failure', ['setblocking', 'constructor'])
def test_pre_stream_failure_reaps_and_releases(monkeypatch, failure):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(hls, '_SLOTS', slots)
    monkeypatch.setattr(hls, 'available', lambda: True)
    class Pipe:
        closed = False
        def fileno(self):
            return 99
        def close(self):
            self.closed = True
    class Process:
        stdin, stdout = Pipe(), Pipe()
        killed = waited = False
        def kill(self):
            self.killed = True
        def wait(self, timeout):
            self.waited = True
    process = Process()
    monkeypatch.setattr(hls.subprocess, 'Popen', lambda *args, **kwargs: process)
    def fail(*args, **kwargs):
        raise OSError('setup failure')
    monkeypatch.setattr(hls.os, 'set_blocking', fail if failure == 'setblocking'
                        else lambda *args: None)
    if failure == 'constructor':
        monkeypatch.setattr(hls, 'ICIStream', fail)
    with pytest.raises(UpstreamError):
        hls.open_ici_stream(hls.SAVED_URL)
    assert process.killed and process.waited and process.stdin.closed and process.stdout.closed
    assert slots.acquire(blocking=False)


@pytest.mark.parametrize('flag', [None, '1'])
def test_ici_available_automatically_with_requirements(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv('WISP_ENABLE_HLS_RADIO', raising=False)
    else:
        monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', flag)
    monkeypatch.setattr(hls.sys, 'platform', 'linux')
    monkeypatch.setattr(hls.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    assert hls.available()
    assert hls.supports_exact_url(hls.SAVED_URL)
    assert hls.unavailable_reason() is None


@pytest.mark.parametrize(('platform', 'executable', 'flag', 'reason'), [
    ('darwin', '/usr/bin/ffmpeg', None, 'Linux container'),
    ('linux', None, None, 'requires FFmpeg'),
    ('linux', '/usr/bin/ffmpeg', '0', 'disabled by WISP_ENABLE_HLS_RADIO=0'),
])
def test_ici_missing_requirements_explain_remedy(monkeypatch, platform, executable, flag, reason):
    monkeypatch.delenv('WISP_ENABLE_HLS_RADIO', raising=False)
    if flag is not None:
        monkeypatch.setenv('WISP_ENABLE_HLS_RADIO', flag)
    monkeypatch.setattr(hls.sys, 'platform', platform)
    monkeypatch.setattr(hls.shutil, 'which', lambda _: executable)
    assert not hls.available()
    assert not hls.supports_exact_url(hls.SAVED_URL)
    assert reason in hls.unavailable_reason()
    with pytest.raises(UpstreamError, match='converter unavailable'):
        hls.open_ici_stream(hls.SAVED_URL)
