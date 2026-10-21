import socket
import threading
import time
from types import SimpleNamespace

import pytest

from app.core import discovery


@pytest.fixture(autouse=True)
def isolated_discovery(monkeypatch):
    for name in ("_device_cache", "_devices_by_name", "_devices_by_id"):
        monkeypatch.setattr(discovery, name, {})
    monkeypatch.setattr(discovery, "_cached_devices", [])
    monkeypatch.setattr(discovery, "_cache_generation", 0)
    monkeypatch.setattr(discovery, "_ambiguous_names", set())
    monkeypatch.setattr(discovery, "_ambiguous_ids", set())
    monkeypatch.setattr(discovery, "_identity_slots", threading.BoundedSemaphore(8))
    # Any unexpected miss must remain completely offline.
    monkeypatch.setattr(discovery, "discover_systems", lambda **kwargs: [])
    monkeypatch.setattr(discovery.status, "get_device_id", lambda ip: None, raising=False)


def populate(monkeypatch, devices):
    monkeypatch.setattr(discovery, "discover_systems", lambda **kwargs: devices)
    discovery.refresh_cache()


def test_duplicate_names_remain_visible_but_never_resolve_by_name(monkeypatch):
    devices = [
        {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"},
        {"name": "Kitchen", "ip": "192.0.2.2", "device_id": "TWO"},
    ]
    populate(monkeypatch, devices)

    assert discovery.get_all_cached_devices() == devices
    assert discovery.resolve_device("Kitchen") is None
    assert discovery.get_device_ip("Kitchen") is None
    assert discovery.resolve_device("Kitchen", "ONE") == devices[0]
    assert discovery.resolve_device("Kitchen", "TWO") == devices[1]


def test_repeated_announcements_do_not_create_false_ambiguity(monkeypatch):
    device = {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}
    populate(monkeypatch, [device, dict(device)])

    assert discovery.get_all_cached_devices() == [device]
    assert discovery.get_device_ip("Kitchen") == "192.0.2.1"


def test_bound_identity_survives_rename_and_address_change(monkeypatch):
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}])
    renamed = {"name": "Dining Room", "ip": "192.0.2.20", "device_id": "ONE"}
    populate(monkeypatch, [renamed])

    assert discovery.resolve_device("Kitchen", "ONE") == renamed
    assert discovery.resolve_device("Kitchen") is None
    assert discovery.resolve_device("Dining Room", "ONE") == renamed


def test_missing_bound_id_does_not_retarget_same_name_or_previous_ip(monkeypatch):
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}])
    replacement = {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "TWO"}
    populate(monkeypatch, [replacement])

    assert discovery.resolve_device("Kitchen", "ONE") is None
    assert discovery.resolve_device("Kitchen", "TWO") == replacement


def test_failed_identity_read_cannot_restore_a_previous_binding(monkeypatch):
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}])
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1"}])

    assert discovery.resolve_device("Kitchen", "ONE") is None
    assert discovery.resolve_device("Kitchen") == {
        "name": "Kitchen", "ip": "192.0.2.1", "device_id": ""
    }
    assert discovery.get_device_ip("Kitchen") == "192.0.2.1"


@pytest.mark.parametrize("device_id", ["", "  "])
def test_explicit_empty_identity_never_falls_back_to_name(monkeypatch, device_id):
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}])

    assert discovery.resolve_device("Kitchen", device_id) is None


def test_duplicate_identity_at_different_ips_is_ambiguous(monkeypatch):
    populate(monkeypatch, [
        {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"},
        {"name": "Dining Room", "ip": "192.0.2.2", "device_id": "ONE"},
    ])

    assert discovery.resolve_device("Kitchen", "ONE") is None
    assert discovery.resolve_device("Kitchen") is None
    assert discovery.get_device_ip("Dining Room") is None


def test_same_identity_and_ip_with_rename_alias_can_resolve(monkeypatch):
    populate(monkeypatch, [
        {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"},
        {"name": "Dining Room", "ip": "192.0.2.1", "device_id": "ONE"},
    ])

    assert discovery.resolve_device("Old Name", "ONE")["ip"] == "192.0.2.1"


def test_cache_results_are_defensive_copies(monkeypatch):
    device = {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}
    populate(monkeypatch, [device])
    discovery.get_all_cached_devices()[0]["ip"] = "192.0.2.99"
    discovery.resolve_device("Kitchen", "ONE")["ip"] = "192.0.2.100"

    assert discovery.resolve_device("Kitchen", "ONE") == device


def test_cache_miss_performs_one_refresh_and_resolves_identity(monkeypatch):
    calls = []
    device = {"name": "New Name", "ip": "192.0.2.7", "device_id": "ONE"}

    def scan(**kwargs):
        calls.append(kwargs)
        return [device]

    monkeypatch.setattr(discovery, "discover_systems", scan)
    assert discovery.resolve_device("Old Name", "ONE") == device
    assert calls == [{"timeout": discovery.DISCOVERY_REFRESH_TIMEOUT_SECONDS}]


def test_scan_error_on_missing_identity_fails_closed(monkeypatch):
    populate(monkeypatch, [{"name": "Kitchen", "ip": "192.0.2.1", "device_id": "TWO"}])

    def failed_scan(**kwargs):
        raise OSError("No multicast interface")

    monkeypatch.setattr(discovery, "discover_systems", failed_scan)
    assert discovery.resolve_device("Kitchen", "ONE") is None
    assert discovery.get_all_cached_devices()[0]["device_id"] == "TWO"


def test_identity_enrichment_queries_each_ip_once_and_isolates_failures(monkeypatch):
    calls = []

    def info(ip):
        calls.append(ip)
        if ip == "192.0.2.2":
            raise ValueError("malformed info")
        return "ONE"

    monkeypatch.setattr(discovery.status, "get_device_id", info)
    devices = discovery._with_device_ids([
        {"name": "Kitchen", "ip": "192.0.2.1"},
        {"name": "Kitchen Alias", "ip": "192.0.2.1"},
        {"name": "Office", "ip": "192.0.2.2"},
    ])

    assert sorted(calls) == ["192.0.2.1", "192.0.2.2"]
    assert [device["device_id"] for device in devices] == ["ONE", "ONE", ""]


def test_identity_enrichment_caps_number_of_reads(monkeypatch):
    calls = []
    monkeypatch.setattr(discovery, "_IDENTITY_MAX_READS", 3)
    monkeypatch.setattr(discovery.status, "get_device_id", lambda ip: calls.append(ip) or ip)
    devices = discovery._with_device_ids([
        {"name": str(i), "ip": f"192.0.2.{i}"} for i in range(1, 9)
    ])

    assert len(calls) == 3
    assert len(devices) == 8
    assert [device["device_id"] for device in devices[3:]] == [""] * 5


def test_identity_time_budget_does_not_wait_for_every_speaker(monkeypatch):
    release = threading.Event()
    finished = threading.Event()
    started = threading.Event()
    monkeypatch.setattr(discovery, "_IDENTITY_LOOKUP_BUDGET_SECONDS", 0.02)
    monkeypatch.setattr(discovery, "_IDENTITY_MAX_WORKERS", 1)
    monkeypatch.setattr(discovery, "_identity_slots", threading.BoundedSemaphore(1))
    calls = []

    def slow_info(ip):
        calls.append(ip)
        started.set()
        try:
            release.wait(2)
            return "LATE"
        finally:
            finished.set()

    monkeypatch.setattr(discovery.status, "get_device_id", slow_info)
    before = time.monotonic()
    try:
        devices = discovery._with_device_ids([
            {"name": str(i), "ip": f"192.0.2.{i}"} for i in range(1, 9)
        ])
        assert time.monotonic() - before < 0.5
        assert started.is_set()
        assert len(calls) == 1
        assert all(device["device_id"] == "" for device in devices)
        # Another scan cannot start more reads while the previous read is outstanding.
        assert discovery._with_device_ids([{"name": "Another", "ip": "192.0.2.99"}]) == [
            {"name": "Another", "ip": "192.0.2.99", "device_id": ""}
        ]
        assert len(calls) == 1
    finally:
        release.set()
        assert finished.wait(1)
    # A late result never changes a snapshot that has already been returned.
    assert all(device["device_id"] == "" for device in devices)


def test_listener_uses_bounded_mdns_reads_and_handles_changes():
    addresses = [socket.inet_aton("192.0.2.1"), bytes(16)]
    calls = []

    class FakeZeroconf:
        def get_service_info(self, service_type, name, timeout):
            calls.append(timeout)
            return SimpleNamespace(addresses=addresses)

    listener = discovery.SoundTouchListener()
    zc = FakeZeroconf()
    name = "Kitchen._soundtouch._tcp.local."
    listener.add_service(zc, "_soundtouch._tcp.local.", name)
    listener.add_service(zc, "_soundtouch._tcp.local.", name)
    assert listener.devices == [{"name": "Kitchen", "ip": "192.0.2.1"}]
    addresses[:] = [socket.inet_aton("192.0.2.2")]
    listener.update_service(zc, "_soundtouch._tcp.local.", name)
    assert listener.devices == [{"name": "Kitchen", "ip": "192.0.2.2"}]
    listener.remove_service(zc, "_soundtouch._tcp.local.", name)
    assert listener.devices == []
    assert calls == [discovery._SERVICE_INFO_TIMEOUT_MS] * 3


# Capture the real function before the autouse fixture replaces network discovery.
_discover_systems = discovery.discover_systems


def test_mdns_scan_enriches_info_and_closes_zeroconf(monkeypatch):
    zc = SimpleNamespace(closed=False)
    zc.close = lambda: setattr(zc, "closed", True)
    sleeps = []
    monkeypatch.setattr(discovery, "Zeroconf", lambda: zc)
    monkeypatch.setattr(discovery.time, "sleep", sleeps.append)
    monkeypatch.setattr(discovery.status, "get_device_id", lambda ip: "ONE")

    def browser(zeroconf, service_type, listener):
        assert zeroconf is zc
        assert service_type == "_soundtouch._tcp.local."
        listener.devices.append({"name": "Kitchen", "ip": "192.0.2.1"})

    monkeypatch.setattr(discovery, "ServiceBrowser", browser)
    assert _discover_systems(timeout=0.3) == [
        {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}
    ]
    assert sleeps == [0.3]
    assert zc.closed


def test_mdns_scan_closes_zeroconf_when_browser_fails(monkeypatch):
    zc = SimpleNamespace(closed=False)
    zc.close = lambda: setattr(zc, "closed", True)
    monkeypatch.setattr(discovery, "Zeroconf", lambda: zc)

    def failed_browser(*args):
        raise OSError("No interface")

    monkeypatch.setattr(discovery, "ServiceBrowser", failed_browser)
    with pytest.raises(OSError, match="No interface"):
        _discover_systems()
    assert zc.closed


def test_concurrent_cache_misses_share_one_scan(monkeypatch):
    scan_started = threading.Event()
    second_waiting = threading.Event()
    release_scan = threading.Event()
    calls = []
    results = []
    device = {"name": "Kitchen", "ip": "192.0.2.1", "device_id": "ONE"}

    class TrackingLock:
        def __init__(self):
            self.lock = threading.Lock()
            self.acquisitions = 0

        def acquire(self, timeout):
            self.acquisitions += 1
            if self.acquisitions == 2:
                second_waiting.set()
            return self.lock.acquire(timeout=timeout)

        def release(self):
            self.lock.release()

    def scan(**kwargs):
        calls.append(kwargs)
        scan_started.set()
        assert release_scan.wait(1)
        return [device]

    monkeypatch.setattr(discovery, "_scan_lock", TrackingLock())
    monkeypatch.setattr(discovery, "discover_systems", scan)
    first = threading.Thread(target=lambda: results.append(discovery.resolve_device("Kitchen")))
    second = threading.Thread(target=lambda: results.append(discovery.resolve_device("Kitchen")))
    first.start()
    try:
        assert scan_started.wait(1)
        second.start()
        assert second_waiting.wait(1)
    finally:
        release_scan.set()
        first.join(timeout=1)
        if second.ident is not None:
            second.join(timeout=1)

    assert not first.is_alive() and not second.is_alive()
    assert results == [device, device]
    assert len(calls) == 1


def test_wait_for_an_existing_scan_is_bounded(monkeypatch):
    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setattr(discovery, "_scan_lock", lock)
    monkeypatch.setattr(discovery, "_CACHE_REFRESH_WAIT_SECONDS", 0.01)
    before = time.monotonic()
    try:
        assert discovery.safe_refresh_cache() is False
    finally:
        lock.release()
    assert time.monotonic() - before < 0.5
