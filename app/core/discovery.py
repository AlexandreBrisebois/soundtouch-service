import time
import socket
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
