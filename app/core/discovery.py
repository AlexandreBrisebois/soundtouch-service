import logging
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, cast
from zeroconf import ServiceBrowser, Zeroconf
from app.core import status
from app.core.constants import (
    DISCOVERY_REFRESH_INTERVAL_SECONDS,
    DISCOVERY_REFRESH_TIMEOUT_SECONDS,
    DISCOVERY_SCAN_TIMEOUT_SECONDS,
    HTTP_GET_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)

# Identity enrichment has a single wall-clock budget, not one timeout per speaker.
# A process-wide limit also bounds outstanding requests after a timed-out scan.
_IDENTITY_MAX_WORKERS = 8
_IDENTITY_MAX_READS = 64
_IDENTITY_LOOKUP_BUDGET_SECONDS = float(HTTP_GET_TIMEOUT_SECONDS)
_identity_slots = threading.BoundedSemaphore(_IDENTITY_MAX_WORKERS)
_SERVICE_INFO_TIMEOUT_MS = 1000
_SERVICE_SUFFIX = "._soundtouch._tcp.local."


class SoundTouchListener:
    def __init__(self) -> None:
        self.devices: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        clean_name = name.removesuffix(_SERVICE_SUFFIX)
        with self._lock:
            self.devices[:] = [d for d in self.devices if d["name"] != clean_name]

    def _read_service(self, zeroconf: Zeroconf, type: str, name: str) -> list[dict[str, str]]:
        info = zeroconf.get_service_info(type, name, timeout=_SERVICE_INFO_TIMEOUT_MS)
        if info is None:
            return []
        clean_name = name.removesuffix(_SERVICE_SUFFIX)
        # SoundTouch HTTP control currently uses IPv4. Ignore IPv6-only services.
        return [
            {"name": clean_name, "ip": socket.inet_ntoa(address)}
            for address in info.addresses
            if len(address) == 4
        ]

    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        devices = self._read_service(zeroconf, type, name)
        with self._lock:
            for device in devices:
                if device not in self.devices:
                    self.devices.append(device)

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        devices = self._read_service(zeroconf, type, name)
        if not devices:
            return
        clean_name = name.removesuffix(_SERVICE_SUFFIX)
        with self._lock:
            self.devices[:] = [d for d in self.devices if d["name"] != clean_name]
            self.devices.extend(devices)


def _read_device_id(ip: str) -> str:
    slots = _identity_slots
    if not slots.acquire(blocking=False):
        return ""
    try:
        return status.get_device_id(ip) or ""
    except Exception as exc:
        # One malformed/offline speaker must not discard all other discoveries.
        logger.warning("Unable to identify speaker at %s: %s", ip, exc)
        return ""
    finally:
        slots.release()


def _with_device_ids(devices: list[dict[str, str]]) -> list[dict[str, str]]:
    ips = list(dict.fromkeys(device["ip"] for device in devices))
    if not ips:
        return []
    if len(ips) > _IDENTITY_MAX_READS:
        logger.warning("Identity lookup limited to %s discovered endpoints.", _IDENTITY_MAX_READS)
    executor = ThreadPoolExecutor(max_workers=_IDENTITY_MAX_WORKERS)
    futures = {
        executor.submit(_read_device_id, ip): ip for ip in ips[:_IDENTITY_MAX_READS]
    }
    identities: dict[str, str] = {}
    try:
        completed, _pending = wait(futures, timeout=_IDENTITY_LOOKUP_BUDGET_SECONDS)
        for future in completed:
            identities[futures[future]] = future.result()
    finally:
        # Do not wait once per queued/offline speaker. Unfinished results cannot
        # mutate this scan's snapshot, and the global semaphore bounds live reads.
        executor.shutdown(wait=False, cancel_futures=True)
    return [
        {"name": device["name"], "ip": device["ip"],
         "device_id": identities.get(device["ip"], "")}
        for device in devices
    ]


def discover_systems(timeout: float = DISCOVERY_SCAN_TIMEOUT_SECONDS) -> list[dict[str, str]]:
    """Scan mDNS, then enrich names/IPs with bounded read-only /info identities.

    An empty device_id means identity could not be verified, not a new identity.
    Duplicate names remain visible so callers can request an explicit device ID.
    """
    zeroconf = Zeroconf()
    listener = SoundTouchListener()
    try:
        _browser = ServiceBrowser(zeroconf, "_soundtouch._tcp.local.", cast(Any, listener))
        time.sleep(timeout)
    finally:
        zeroconf.close()
    return _with_device_ids(listener.devices)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    logger.info("Discovering SoundTouch devices...")
    devices = discover_systems()
    for d in devices:
        logger.info("Found '%s' at %s", d['name'], d['ip'])

# ---------------------------------------------------------------------------
# Device IP Cache
# ---------------------------------------------------------------------------
_device_cache: dict[str, str] = {}  # Unique name → IP, for legacy callers.
_cached_devices: list[dict[str, str]] = []
_devices_by_name: dict[str, dict[str, str]] = {}
_devices_by_id: dict[str, dict[str, str]] = {}
_ambiguous_names: set[str] = set()
_ambiguous_ids: set[str] = set()
_cache_lock = threading.Lock()
_cache_generation = 0
_CACHE_REFRESH_WAIT_SECONDS = (
    DISCOVERY_REFRESH_TIMEOUT_SECONDS + _IDENTITY_LOOKUP_BUDGET_SECONDS
    + _SERVICE_INFO_TIMEOUT_MS / 1000
)
_scan_lock = threading.Lock()
_cache_refresh_thread: threading.Thread | None = None
_cache_refresh_lock = threading.Lock()
_cache_stop_event = threading.Event()


def refresh_cache() -> None:
    """Atomically replace current endpoints without collapsing duplicate names.

    IDs, rather than display names, index devices across a rename or DHCP change.
    Absent IDs are removed: an old IP must not silently become another speaker.
    """
    global _cache_generation

    with _cache_lock:
        generation = _cache_generation
    if not _scan_lock.acquire(timeout=_CACHE_REFRESH_WAIT_SECONDS):
        raise TimeoutError("Another discovery scan is still in progress")
    try:
        with _cache_lock:
            if generation != _cache_generation:
                # Concurrent misses share the completed scan, rather than each
                # queuing another full network scan for the same snapshot.
                return
        devices = discover_systems(timeout=DISCOVERY_REFRESH_TIMEOUT_SECONDS)
        # Repeated mDNS announcements of one endpoint do not make it ambiguous.
        records = {
            (d["name"], d["ip"], d.get("device_id") or ""): {
                "name": d["name"], "ip": d["ip"], "device_id": d.get("device_id") or ""
            }
            for d in devices
        }
        by_name: dict[str, list[dict[str, str]]] = {}
        by_id: dict[str, list[dict[str, str]]] = {}
        for device in records.values():
            by_name.setdefault(device["name"], []).append(device)
            if device["device_id"]:
                by_id.setdefault(device["device_id"], []).append(device)
        ambiguous_names = {name for name, entries in by_name.items() if len(entries) != 1}
        # Multiple names for the same ID/IP are harmless aliases during rename.
        # The same ID at multiple IPs is not safe to choose between automatically.
        ambiguous_ids = {
            device_id for device_id, entries in by_id.items()
            if len({entry["ip"] for entry in entries}) != 1
        }
        unique_names = {
            name: entries[0] for name, entries in by_name.items() if name not in ambiguous_names
        }
        unique_ids = {
            device_id: entries[0] for device_id, entries in by_id.items()
            if device_id not in ambiguous_ids
        }
        with _cache_lock:
            _cached_devices[:] = records.values()
            _device_cache.clear()
            _device_cache.update({name: d["ip"] for name, d in unique_names.items()})
            _devices_by_name.clear()
            _devices_by_name.update(unique_names)
            _devices_by_id.clear()
            _devices_by_id.update(unique_ids)
            _ambiguous_names.clear()
            _ambiguous_names.update(ambiguous_names)
            _ambiguous_ids.clear()
            _ambiguous_ids.update(ambiguous_ids)
            _cache_generation += 1
    finally:
        _scan_lock.release()
    logger.info("Discovery cache refreshed with speakers: %s", list(by_name))
    if ambiguous_names or ambiguous_ids:
        logger.warning("Ambiguous discovery targets: names=%s, IDs=%s",
                       sorted(ambiguous_names), sorted(ambiguous_ids))


def safe_refresh_cache() -> bool:
    """Best-effort cache refresh that never raises to callers/threads."""
    try:
        refresh_cache()
        return True
    except Exception as exc:
        logger.warning("Discovery cache refresh failed: %s", exc)
        return False


def _cached_resolution(name: str, device_id: str | None) -> tuple[dict[str, str] | None, bool]:
    with _cache_lock:
        if device_id is not None:
            device = _devices_by_id.get(device_id)
            ambiguous = device_id in _ambiguous_ids
        else:
            device = _devices_by_name.get(name)
            ambiguous = name in _ambiguous_names
            if device is not None and device["device_id"] in _ambiguous_ids:
                device, ambiguous = None, True
        return (dict(device) if device is not None else None), ambiguous


def resolve_device(name: str, device_id: str | None = None) -> dict[str, str] | None:
    """Resolve a current endpoint, failing closed on ambiguous or missing IDs.

    A supplied ID is authoritative even when the name changes. It never falls
    back to a same-name replacement. Name-only resolution is for legacy callers
    and initial binding; consumers must persist a successful ID themselves and
    verify /info immediately before writes to guard against stale DHCP leases.
    """
    if device_id is not None and not device_id.strip():
        return None
    device, ambiguous = _cached_resolution(name, device_id)
    if device is not None or ambiguous:
        return device
    logger.info("Discovery cache miss for '%s' (ID %s); running fallback scan.", name, device_id)
    if not safe_refresh_cache():
        return None
    return _cached_resolution(name, device_id)[0]


def get_device_ip(name: str) -> str | None:
    """Resolve a unique legacy name; never pick a winner among duplicate names."""
    device = resolve_device(name)
    return device["ip"] if device is not None else None


def get_all_cached_devices() -> list[dict[str, str]]:
    """Return all name/IP/device_id records, including duplicate display names."""
    with _cache_lock:
        return [dict(device) for device in _cached_devices]

def _cache_refresh_loop(stop_event: threading.Event, on_refresh: Callable[[list[dict[str, str]]], None] | None = None, delay_first: bool = False) -> None:
    """Background loop: refresh cache every 5 minutes."""
    if delay_first and stop_event.wait(DISCOVERY_REFRESH_INTERVAL_SECONDS):
        return
    while not stop_event.is_set():
        refreshed = safe_refresh_cache()
        if refreshed and on_refresh is not None:
            on_refresh(get_all_cached_devices())
        if stop_event.wait(DISCOVERY_REFRESH_INTERVAL_SECONDS):
            break

def start_device_cache(on_refresh: Callable[[list[dict[str, str]]], None] | None = None) -> None:
    """Start the background cache refresh thread. Call once at startup."""
    global _cache_refresh_thread

    with _cache_refresh_lock:
        if _cache_refresh_thread is not None and _cache_refresh_thread.is_alive():
            return

        _cache_stop_event.clear()
        initial_refresh_ok = safe_refresh_cache()
        if initial_refresh_ok and on_refresh is not None:
            on_refresh(get_all_cached_devices())

        _cache_refresh_thread = threading.Thread(
            target=_cache_refresh_loop,
            kwargs={
                "stop_event": _cache_stop_event,
                "on_refresh": on_refresh,
                "delay_first": initial_refresh_ok,
            },
            daemon=True,
        )
        _cache_refresh_thread.start()
        logger.info("Background discovery cache refresh thread started.")


def stop_device_cache(timeout: float = 3.0) -> None:
    """Stop the background cache refresh thread if running."""
    global _cache_refresh_thread

    with _cache_refresh_lock:
        _cache_stop_event.set()
        thread = _cache_refresh_thread
        _cache_refresh_thread = None

    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)

