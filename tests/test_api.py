import time
import socket
import requests
from zeroconf import ServiceBrowser, Zeroconf

class MyListener:
    def __init__(self, target_name):
        self.target_name = target_name
        self.target_ip = None

    def remove_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            clean_name = name.replace("._soundtouch._tcp.local.", "")
            if clean_name == self.target_name:
                self.target_ip = socket.inet_ntoa(info.addresses[0])

    def update_service(self, zeroconf, type, name):
        pass

def discover_speaker(target_name, timeout=5):
    zeroconf = Zeroconf()
    listener = MyListener(target_name)
    browser = ServiceBrowser(zeroconf, "_soundtouch._tcp.local.", listener)
    time.sleep(timeout)
    zeroconf.close()
    return listener.target_ip

def send_key(ip, key):
    url = f"http://{ip}:8090/key"
    payload_press = f'<?xml version="1.0" ?><key state="press" sender="Gabbo">{key}</key>'
    payload_release = f'<?xml version="1.0" ?><key state="release" sender="Gabbo">{key}</key>'
    requests.post(url, data=payload_press)
    requests.post(url, data=payload_release)

def set_volume(ip, volume):
    url = f"http://{ip}:8090/volume"
    payload = f'<?xml version="1.0" ?><volume>{volume}</volume>'
    requests.post(url, data=payload)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test Bose SoundTouch API commands.")
    parser.add_argument("--speaker", type=str, default="Target Speaker 1", help="The name of your speaker as it appears on the network.")
    args = parser.parse_args()
    
    target = args.speaker
    print(f"Discovering '{target}' on the local network (waiting 5 seconds)...")
    ip = discover_speaker(target)
    
    if not ip:
        print(f"\nFailed to find '{target}'. Make sure the speaker is on the same network.")
    else:
        print(f"\nFound '{target}' at {ip}")
        print("Setting volume to 20%...")
        set_volume(ip, 20)
        time.sleep(1)
        
        print("Playing PRESET_1...")
        send_key(ip, "PRESET_1")
        
        print("Waiting 20 seconds...")
        time.sleep(20)
        
        print("Turning off (sending POWER)...")
        send_key(ip, "POWER")
        print("Test script finished.")
