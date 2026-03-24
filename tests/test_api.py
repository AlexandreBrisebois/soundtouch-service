import time
import socket
import requests
import os
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

    print("\n--- Testing Local Flask API ---")
    port = int(os.environ.get("PORT", 9001))
    base_url = f"http://localhost:{port}"
    try:
        req = requests.get(f"{base_url}/api/schedules", timeout=2)
        print(f"GET {base_url}/api/schedules :")
        print(req.json())

        print(f"\nGET {base_url}/api/{target}/status - Checking live status and volume...")
        res = requests.get(f"{base_url}/api/{target}/status", timeout=5)
        print(res.json())

        print(f"\nPOST {base_url}/api/{target}/schedules - Adding 'Test Routine'...")
        res = requests.post(f"{base_url}/api/{target}/schedules", json={
            "name": "Test Routine",
            "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "on_time": "12:00",
            "off_time": "13:00",
            "preset": 1,
            "volume": 20,
            "fade_in_duration": 300,
            "fade_out_duration": 60
        }, timeout=2)
        print(res.json())

        print(f"\nPOST {base_url}/api/{target}/schedules - Adding 'AUX Routine'...")
        res = requests.post(f"{base_url}/api/{target}/schedules", json={
            "name": "AUX Routine",
            "days": ["saturday", "sunday"],
            "on_time": "14:00",
            "off_time": "15:00",
            "source": "AUX",
            "volume": 15,
            "fade_in_duration": 120,
            "fade_out_duration": 30
        }, timeout=2)
        print(res.json())

        time.sleep(1) # wait for IO thread

        print(f"\nPATCH {base_url}/api/{target}/schedules/Test Routine/pause - Pausing 'Test Routine'...")
        res = requests.patch(f"{base_url}/api/{target}/schedules/Test Routine/pause", timeout=2)
        print(res.json())

        time.sleep(1) # wait for IO thread

        print(f"\nGET {base_url}/api/schedules - Verifying 'Test Routine' is paused...")
        req = requests.get(f"{base_url}/api/schedules", timeout=2)
        print(req.json())

        print(f"\nPATCH {base_url}/api/{target}/schedules/Test Routine/resume - Resuming 'Test Routine'...")
        res = requests.patch(f"{base_url}/api/{target}/schedules/Test Routine/resume", timeout=2)
        print(res.json())

        time.sleep(1) # wait for IO thread

        print(f"\nGET {base_url}/api/schedules - Verifying 'Test Routine' is resumed...")
        req = requests.get(f"{base_url}/api/schedules", timeout=2)
        print(req.json())

        time.sleep(1) # wait for IO thread

        print(f"\nDELETE {base_url}/api/{target}/schedules - Removing 'Test Routine'...")
        res = requests.delete(f"{base_url}/api/{target}/schedules/Test Routine", timeout=2)
        print(res.json())

        print(f"\nDELETE {base_url}/api/{target}/schedules - Removing 'AUX Routine'...")
        res = requests.delete(f"{base_url}/api/{target}/schedules/AUX Routine", timeout=2)
        print(res.json())

    except requests.exceptions.RequestException:
        print(f"Flask API not running or unreachable on port {port}. Skipping API tests.")
        
    print("Test script finished.")
