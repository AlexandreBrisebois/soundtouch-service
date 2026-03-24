import time
import socket
import threading
from zeroconf import ServiceBrowser, Zeroconf

class SoundTouchListener:
    def __init__(self):
        self.devices = []

    def remove_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            clean_name = name.replace("._soundtouch._tcp.local.", "")
            ip = socket.inet_ntoa(info.addresses[0])
            self.devices.append({"name": clean_name, "ip": ip})

    def update_service(self, zeroconf, type, name):
        pass

def discover_systems(timeout=5):
    """
    Scans the local network for Bose SoundTouch devices using mDNS.
    Returns a list of dictionaries containing device names and IP addresses.
    """
    zeroconf = Zeroconf()
    listener = SoundTouchListener()
    browser = ServiceBrowser(zeroconf, "_soundtouch._tcp.local.", listener)
    time.sleep(timeout)
    zeroconf.close()
    return listener.devices

if __name__ == "__main__":
    print("Discovering SoundTouch devices...")
    devices = discover_systems()
    for d in devices:
        print(f"Found '{d['name']}' at {d['ip']}")

# ---------------------------------------------------------------------------
# Device IP Cache
# ---------------------------------------------------------------------------
_device_cache: dict = {}       # name → IP
_cache_lock = threading.Lock()

def refresh_cache():
    """Run a single mDNS scan and update the cache atomically."""
    devices = discover_systems(timeout=3)
    new_cache = {d["name"]: d["ip"] for d in devices}
    with _cache_lock:
        _device_cache.clear()
        _device_cache.update(new_cache)
    print(f"[Discovery] Cache refreshed: {list(new_cache.keys())}")

def get_device_ip(name: str):
    """Instant O(1) lookup from cache. Falls back to a one-off scan on miss."""
    with _cache_lock:
        ip = _device_cache.get(name)
    if ip is not None:
        return ip
    # Cache miss — run a single scan, then retry
    print(f"[Discovery] Cache miss for '{name}', running fallback scan...")
    refresh_cache()
    with _cache_lock:
        return _device_cache.get(name)

def get_all_cached_devices():
    """Return a list of dicts matching the discover_systems() format."""
    with _cache_lock:
        return [{"name": n, "ip": ip} for n, ip in _device_cache.items()]

def _cache_refresh_loop():
    """Background loop: refresh cache every 5 minutes."""
    while True:
        refresh_cache()
        time.sleep(300)

def start_device_cache():
    """Start the background cache refresh thread. Call once at startup."""
    refresh_cache()  # prime immediately
    t = threading.Thread(target=_cache_refresh_loop, daemon=True)
    t.start()
    print("[Discovery] Background cache refresh thread started.")
