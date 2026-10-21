import threading

import pytest

from app.core import speaker_cache


class FakeThread:
    def __init__(self, target=None, args=(), daemon=False):
        self.target = target
        self.args = args
        self.started = False
        self.joined = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and not self.joined

    def join(self, timeout=None):
        self.joined = True


class FakeSocket:
    def __init__(self, *args, **kwargs):
        self.callbacks = kwargs
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    for attribute in (
        "_speaker_state", "_playback_observed_at", "_volume_observed_at", "_listener_threads",
        "_listener_stop_events", "_listener_sockets", "_listener_addresses", "_listener_identities",
    ):
        monkeypatch.setattr(speaker_cache, attribute, {})
    monkeypatch.setattr(speaker_cache.threading, "Thread", FakeThread)

    def unexpected_network(*args, **kwargs):
        pytest.fail("Speaker-cache tests must not contact real speakers")

    monkeypatch.setattr(speaker_cache.status, "get_now_playing", unexpected_network)
    monkeypatch.setattr(speaker_cache.status, "get_volume", unexpected_network)
    monkeypatch.setattr(speaker_cache.websocket, "WebSocketApp", unexpected_network)


@pytest.fixture
def clock(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(speaker_cache.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(speaker_cache.time, "time", lambda: 1000.0 + elapsed[0])
    return elapsed


def register_listener(name="Office", ip="192.0.2.10"):
    speaker_cache.start_ws_listeners([{"name": name, "ip": ip}])
    event = speaker_cache._listener_stop_events[name]
    socket = FakeSocket()
    speaker_cache._listener_sockets[name] = socket
    return event, socket


def test_missing_and_volume_only_observations_are_not_playback(clock):
    assert speaker_cache.get_speaker_state("Office") is None
    speaker_cache.update_cache("Office", {"volume": 40})
    assert speaker_cache.get_speaker_state("Office") is None
    assert speaker_cache._speaker_state["Office"]["volume_updated_at"] == 1000.0
    assert "playback_updated_at" not in speaker_cache._speaker_state["Office"]


def test_playback_cache_expires_at_bounded_age(clock):
    speaker_cache.update_cache("Office", {"status": "Playing", "source": "AUX"})
    clock[0] = 15.0
    assert speaker_cache.get_speaker_state("Office")["status"] == "Playing"
    clock[0] = 15.01
    assert speaker_cache.get_speaker_state("Office") is None
    assert speaker_cache.get_speaker_state("Office", max_age=20)["source"] == "AUX"
    assert speaker_cache.get_speaker_state("Office", max_age=-1) is None
    assert speaker_cache.get_speaker_state("Office", max_age=float("nan")) is None


def test_volume_updates_do_not_freshen_playback(clock):
    speaker_cache.update_cache("Office", {"status": "Playing", "volume": 20})
    clock[0] = 10.0
    speaker_cache.update_cache("Office", {"volume": 30})
    cached = speaker_cache.get_speaker_state("Office")
    assert cached["playback_updated_at"] == 1000.0
    assert cached["volume_updated_at"] == 1010.0
    assert cached["updated_at"] == 1010.0
    clock[0] = 16.0
    speaker_cache.update_cache("Office", {"volume": 40})
    assert speaker_cache.get_speaker_state("Office") is None


def test_cache_copies_input_and_returned_nested_content(clock):
    observation = {"status": "Playing", "content_item": {"location": "original"}}
    speaker_cache.update_cache("Office", observation)
    observation["content_item"]["location"] = "mutated input"
    result = speaker_cache.get_speaker_state("Office")
    result["content_item"]["location"] = "mutated return"
    result["status"] = "Stopped"
    assert speaker_cache.get_speaker_state("Office")["content_item"] == {"location": "original"}
    assert speaker_cache.get_speaker_state("Office")["status"] == "Playing"


def test_playback_snapshot_replaces_old_track_identity_and_error(clock):
    speaker_cache.update_cache("Office", {
        "status": "Playing", "track": "old", "content_item": {"location": "old"},
        "error": "old", "volume": 20,
    })
    clock[0] = 1.0
    speaker_cache.update_cache("Office", {"status": "Standby", "source": "STANDBY"})
    cached = speaker_cache.get_speaker_state("Office")
    assert "track" not in cached
    assert "content_item" not in cached
    assert "error" not in cached
    assert cached["volume"] == 20
    assert cached["volume_updated_at"] == 1000.0
    assert cached["playback_updated_at"] == 1001.0


def test_elapsed_age_ignores_wall_clock_changes(clock, monkeypatch):
    speaker_cache.update_cache("Office", {"status": "Playing"})
    monkeypatch.setattr(speaker_cache.time, "time", lambda: -1000.0)
    clock[0] = 16.0
    assert speaker_cache.get_speaker_state("Office") is None


def test_invalidate_discards_playback_and_volume(clock):
    speaker_cache.update_cache("Office", {"status": "Playing", "volume": 30})
    speaker_cache.invalidate_cache("Office")
    assert speaker_cache.get_speaker_state("Office") is None
    assert "Office" not in speaker_cache._speaker_state
    assert "Office" not in speaker_cache._playback_observed_at


def test_playback_notification_updates_current_listener(clock):
    event, socket = register_listener()
    speaker_cache._on_message(
        socket,
        '<updates><nowPlayingUpdated><nowPlaying source="AUX">'
        '<playStatus>PLAY_STATE</playStatus></nowPlaying></nowPlayingUpdated></updates>',
        "Office", "192.0.2.10", event,
    )
    assert speaker_cache.get_speaker_state("Office")["status"] == "Playing"
    speaker_cache._on_message(socket, "invalid XML", "Office", "192.0.2.10", event)
    assert speaker_cache.get_speaker_state("Office")["status"] == "Playing"


def test_volume_notification_does_not_refresh_playback(clock, monkeypatch):
    event, socket = register_listener()
    speaker_cache.update_cache("Office", {"status": "Playing"})
    monkeypatch.setattr(speaker_cache.status, "get_volume", lambda ip: 30)
    clock[0] = 16.0
    speaker_cache._on_message(
        socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", event,
    )
    assert speaker_cache.get_speaker_state("Office") is None
    assert speaker_cache._speaker_state["Office"]["volume"] == 30


@pytest.mark.parametrize("callback", ["close", "error"])
def test_disconnect_immediately_invalidates_and_rejects_late_notifications(clock, callback):
    event, socket = register_listener()
    speaker_cache.update_cache("Office", {"status": "Playing", "volume": 20})
    if callback == "close":
        speaker_cache._on_close(socket, 1000, "done", "Office", event)
    else:
        speaker_cache._on_error(socket, RuntimeError("lost"), "Office", event)
        assert socket.closed
    assert speaker_cache.get_speaker_state("Office") is None
    speaker_cache._on_message(
        socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", event,
    )
    assert speaker_cache.get_speaker_state("Office") is None


def test_same_address_is_idempotent_but_new_address_replaces_listener(clock):
    old_event, old_socket = register_listener()
    old_thread = speaker_cache._listener_threads["Office"]
    speaker_cache.update_cache("Office", {"status": "Playing"})
    speaker_cache.start_ws_listeners([{"name": "Office", "ip": "192.0.2.10"}])
    assert speaker_cache._listener_threads["Office"] is old_thread
    assert not old_event.is_set()
    speaker_cache.start_ws_listeners([{"name": "Office", "ip": "192.0.2.11"}])
    assert old_event.is_set()
    assert old_socket.closed
    assert speaker_cache._listener_threads["Office"] is not old_thread
    assert speaker_cache._listener_threads["Office"].started
    assert speaker_cache._listener_addresses["Office"] == "192.0.2.11"
    assert speaker_cache.get_speaker_state("Office") is None
    speaker_cache.update_cache("Office", {"status": "Standby"})
    speaker_cache._on_close(old_socket, 1000, "late", "Office", old_event)
    speaker_cache._on_message(
        old_socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", old_event,
    )
    assert speaker_cache.get_speaker_state("Office")["status"] == "Standby"


def test_removed_speaker_stops_and_invalidates(clock):
    event, socket = register_listener()
    speaker_cache.update_cache("Office", {"status": "Playing"})
    speaker_cache.start_ws_listeners([])
    assert event.is_set()
    assert socket.closed
    assert speaker_cache.get_speaker_state("Office") is None
    assert speaker_cache._listener_threads == {}
    assert speaker_cache._listener_stop_events == {}
    assert speaker_cache._listener_addresses == {}
    assert speaker_cache._listener_sockets == {}


def test_in_flight_volume_from_old_address_cannot_overwrite_new_state(clock, monkeypatch):
    event, socket = register_listener()

    def finish_after_replacement(ip):
        speaker_cache.start_ws_listeners([{"name": "Office", "ip": "192.0.2.11"}])
        speaker_cache.update_cache("Office", {"status": "Standby", "volume": 10})
        return 99

    monkeypatch.setattr(speaker_cache.status, "get_volume", finish_after_replacement)
    speaker_cache._on_message(
        socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", event,
    )
    assert speaker_cache.get_speaker_state("Office")["volume"] == 10


def test_in_flight_prime_cannot_publish_after_removal(clock, monkeypatch):
    event, socket = register_listener()

    def finish_after_removal(ip):
        speaker_cache.start_ws_listeners([])
        return {"status": "Playing"}

    monkeypatch.setattr(speaker_cache.status, "get_now_playing", finish_after_removal)
    speaker_cache._on_open(socket, "Office", "192.0.2.10", event)
    assert speaker_cache.get_speaker_state("Office") is None


def test_old_socket_with_same_generation_cannot_publish_or_invalidate(clock):
    event, old_socket = register_listener()
    speaker_cache._listener_sockets["Office"] = FakeSocket()
    speaker_cache.update_cache("Office", {"status": "Standby", "volume": 10})
    speaker_cache._on_message(
        old_socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", event,
    )
    speaker_cache._on_close(old_socket, None, "late", "Office", event)
    assert speaker_cache.get_speaker_state("Office")["volume"] == 10


@pytest.mark.parametrize("disconnect", ["callback", "return", "exception"])
def test_reconnect_reprimes_and_all_disconnect_paths_invalidate(clock, monkeypatch, disconnect):
    event, _ = register_listener()
    snapshots = []
    status_reads = []
    volume_reads = []
    sockets = []

    def get_playback(ip):
        status_reads.append(ip)
        return {"status": "Playing", "track": str(len(status_reads))}

    def get_volume(ip):
        volume_reads.append(ip)
        return len(volume_reads)

    class ConnectingSocket(FakeSocket):
        def run_forever(self, **kwargs):
            sockets.append(self)
            self.callbacks["on_open"](self)
            snapshots.append(speaker_cache.get_speaker_state("Office"))
            if disconnect == "callback":
                self.callbacks["on_close"](self, 1000, "disconnected")
                assert speaker_cache.get_speaker_state("Office") is None
            elif disconnect == "exception":
                raise RuntimeError("connection failed")

    waits = []

    def wait(delay):
        assert speaker_cache.get_speaker_state("Office") is None
        waits.append(delay)
        return len(waits) >= 2

    monkeypatch.setattr(event, "wait", wait)
    monkeypatch.setattr(speaker_cache.status, "get_now_playing", get_playback)
    monkeypatch.setattr(speaker_cache.status, "get_volume", get_volume)
    monkeypatch.setattr(speaker_cache.websocket, "WebSocketApp", ConnectingSocket)
    speaker_cache.listen_to_speaker("Office", "192.0.2.10", event)
    assert len(status_reads) == len(volume_reads) == len(sockets) == 2
    assert [snapshot["track"] for snapshot in snapshots] == ["1", "2"]
    assert [snapshot["volume"] for snapshot in snapshots] == [1, 2]
    assert all(socket.closed for socket in sockets)
    assert speaker_cache._listener_sockets == {}
    assert speaker_cache.get_speaker_state("Office") is None


def test_shutdown_rejects_callbacks_and_clears_all_observations(clock):
    event, socket = register_listener()
    thread = speaker_cache._listener_threads["Office"]
    speaker_cache.update_cache("Office", {"status": "Playing"})
    speaker_cache.stop_ws_listeners(timeout=0)
    assert event.is_set()
    assert socket.closed
    assert thread.joined
    assert speaker_cache._speaker_state == {}
    assert speaker_cache._playback_observed_at == {}
    speaker_cache._on_message(
        socket, "<updates><volumeUpdated /></updates>", "Office", "192.0.2.10", event,
    )


def test_unregistered_generation_never_connects(monkeypatch):
    event = threading.Event()
    constructed = []

    class UnexpectedConnection(FakeSocket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            constructed.append(self)

        def run_forever(self, **kwargs):
            pytest.fail("An obsolete listener must not connect")

    monkeypatch.setattr(speaker_cache.websocket, "WebSocketApp", UnexpectedConnection)
    speaker_cache.listen_to_speaker("Office", "192.0.2.10", event)
    assert len(constructed) == 1


def test_volume_expires_independently_of_fresh_playback(clock):
    speaker_cache.update_cache('Office', {'volume': 7, 'status': 'Playing'})
    clock[0] = 20
    speaker_cache.update_cache('Office', {'status': 'Playing'})
    assert speaker_cache.get_speaker_state('Office')['volume'] is None


def test_same_name_address_new_identity_replaces_listener():
    speaker_cache.start_ws_listeners([{'name': 'Office', 'ip': 'fake', 'device_id': 'A'}])
    old_event = speaker_cache._listener_stop_events['Office']
    speaker_cache.start_ws_listeners([{'name': 'Office', 'ip': 'fake', 'device_id': 'B'}])
    assert old_event.is_set()
    assert speaker_cache._listener_identities['Office'] == 'B'


def test_mismatched_listener_identity_cannot_publish():
    event, socket = register_listener()
    speaker_cache._listener_identities['Office'] = 'A'
    speaker_cache._update_listener_cache('Office', {'status': 'Playing', 'device_id': 'B'},
                                         event, socket)
    assert speaker_cache.get_speaker_state('Office') is None


def test_duplicate_names_start_no_arbitrary_listener():
    speaker_cache.start_ws_listeners([{'name': 'Room', 'ip': 'one', 'device_id': 'A'},
                                      {'name': 'Room', 'ip': 'two', 'device_id': 'B'}])
    assert not speaker_cache._listener_threads
