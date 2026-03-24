import logging
import time
import socket
import threading
from typing import Callable
from zeroconf import ServiceBrowser, Zeroconf
from app.core.constants import (
    DISCOVERY_REFRESH_INTERVAL_SECONDS,
    DISCOVERY_REFRESH_TIMEOUT_SECONDS,
    DISCOVERY_SCAN_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)

class SoundTouchListener:
    def __init__(self) -> None:
        self.devices: list[dict[str, str]] = []

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        pass

    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        info = zeroconf.get_service_info(type, name)
        if info:
            clean_name = name.replace("._soundtouch._tcp.local.", "")
            ip = socket.inet_ntoa(info.addresses[0])
            self.devices.append({"name": clean_name, "ip": ip})

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        pass

def discover_systems(timeout: float = DISCOVERY_SCAN_TIMEOUT_SECONDS) -> list[dict[str, str]]:
    """
    Scans the local network for Bose SoundTouch devices using mDNS.
    Returns a list of dictionaries containing device names and IP addresses.
    """
    zeroconf = Zeroconf()
    listener = SoundTouchListener()
    ServiceBrowser(zeroconf, "_soundtouch._tcp.local.", listener)
    time.sleep(timeout)
    zeroconf.close()
    return listener.devices

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    logger.info("Discovering SoundTouch devices...")
    devices = discover_systems()
    for d in devices:
        logger.info("Found '%s' at %s", d['name'], d['ip'])

# ---------------------------------------------------------------------------
# Device IP Cache
# ---------------------------------------------------------------------------
_device_cache: dict[str, str] = {}       # name → IP
_cache_lock = threading.Lock()

def refresh_cache() -> None:
    """Run a single mDNS scan and update the cache atomically."""
    devices = discover_systems(timeout=DISCOVERY_REFRESH_TIMEOUT_SECONDS)
    new_cache = {d["name"]: d["ip"] for d in devices}
    with _cache_lock:
        _device_cache.clear()
        _device_cache.update(new_cache)
    logger.info("Discovery cache refreshed with speakers: %s", list(new_cache.keys()))


def safe_refresh_cache() -> bool:
    """Best-effort cache refresh that never raises to callers/threads."""
    try:
        refresh_cache()
        return True
    except Exception as exc:
        logger.warning("Discovery cache refresh failed: %s", exc)
        return False

def get_device_ip(name: str):
    """Instant O(1) lookup from cache. Falls back to a one-off scan on miss."""
    with _cache_lock:
        ip = _device_cache.get(name)
    if ip is not None:
        return ip
    # Cache miss — run a single scan, then retry
    logger.info("Discovery cache miss for '%s'; running fallback scan.", name)
    if not safe_refresh_cache():
        return None
    with _cache_lock:
        return _device_cache.get(name)

def get_all_cached_devices() -> list[dict[str, str]]:
    """Return a list of dicts matching the discover_systems() format."""
    with _cache_lock:
        return [{"name": n, "ip": ip} for n, ip in _device_cache.items()]

def _cache_refresh_loop(on_refresh: Callable[[list[dict[str, str]]], None] | None = None, delay_first: bool = False) -> None:
    """Background loop: refresh cache every 5 minutes."""
    if delay_first:
        time.sleep(DISCOVERY_REFRESH_INTERVAL_SECONDS)
    while True:
        refreshed = safe_refresh_cache()
        if refreshed and on_refresh is not None:
            on_refresh(get_all_cached_devices())
        time.sleep(DISCOVERY_REFRESH_INTERVAL_SECONDS)

def start_device_cache(on_refresh: Callable[[list[dict[str, str]]], None] | None = None) -> None:
    """Start the background cache refresh thread. Call once at startup."""
    initial_refresh_ok = safe_refresh_cache()
    if initial_refresh_ok and on_refresh is not None:
        on_refresh(get_all_cached_devices())

    t = threading.Thread(
        target=_cache_refresh_loop,
        kwargs={"on_refresh": on_refresh, "delay_first": initial_refresh_ok},
        daemon=True
    )
    t.start()
    logger.info("Background discovery cache refresh thread started.")
