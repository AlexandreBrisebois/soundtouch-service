import threading

from app.core import discovery, speaker_cache
from app import main as app_main


class _FakeThread:
    creations = 0

    def __init__(self, *args, **kwargs):
        self.target = kwargs.get("target")
        self.kwargs = kwargs.get("kwargs", {})
        self.daemon = kwargs.get("daemon", False)
        self.started = False
        self.joined = False
        self.alive = True
        _FakeThread.creations += 1

    def start(self):
        self.started = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.joined = True
        self.alive = False


class _JoinableThread:
    def __init__(self):
        self.joined = False
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.joined = True
        self.alive = False


class _ClosableSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_discovery_start_and_stop_cache_thread_is_idempotent(monkeypatch):
    _FakeThread.creations = 0
    callback_calls = []

    monkeypatch.setattr(discovery.threading, "Thread", _FakeThread)
    monkeypatch.setattr(discovery, "safe_refresh_cache", lambda: True)
    monkeypatch.setattr(discovery, "get_all_cached_devices", lambda: [{"name": "LR", "ip": "1.1.1.1"}])
    monkeypatch.setattr(discovery, "_cache_refresh_thread", None)
    monkeypatch.setattr(discovery, "_cache_stop_event", threading.Event())

    discovery.start_device_cache(on_refresh=lambda devices: callback_calls.append(devices))
    discovery.start_device_cache(on_refresh=lambda devices: callback_calls.append(devices))

    assert _FakeThread.creations == 1
    assert callback_calls == [[{"name": "LR", "ip": "1.1.1.1"}]]

    thread = discovery._cache_refresh_thread
    assert thread is not None
    discovery.stop_device_cache(timeout=0.0)

    assert discovery._cache_stop_event.is_set()
    assert thread.joined


def test_stop_ws_listeners_stops_threads_and_closes_sockets(monkeypatch):
    ev_one = threading.Event()
    ev_two = threading.Event()
    th_one = _JoinableThread()
    th_two = _JoinableThread()
    ws_one = _ClosableSocket()
    ws_two = _ClosableSocket()

    monkeypatch.setattr(speaker_cache, "_listener_stop_events", {"A": ev_one, "B": ev_two})
    monkeypatch.setattr(speaker_cache, "_listener_threads", {"A": th_one, "B": th_two})
    monkeypatch.setattr(speaker_cache, "_listener_sockets", {"A": ws_one, "B": ws_two})

    speaker_cache.stop_ws_listeners(timeout=0.0)

    assert ev_one.is_set()
    assert ev_two.is_set()
    assert ws_one.closed
    assert ws_two.closed
    assert th_one.joined
    assert th_two.joined
    assert speaker_cache._listener_stop_events == {}
    assert speaker_cache._listener_threads == {}
    assert speaker_cache._listener_sockets == {}


def test_register_shutdown_once_is_idempotent(monkeypatch):
    handlers = []

    monkeypatch.setattr(app_main, "_shutdown_registered", False)
    monkeypatch.setattr(app_main.atexit, "register", lambda fn: handlers.append(fn))

    app_main._register_shutdown_once()
    app_main._register_shutdown_once()

    assert len(handlers) == 1
