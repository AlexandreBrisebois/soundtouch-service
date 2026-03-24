import sys
import os
import threading
import time
from flask import Flask, jsonify

# Ensure we can import from the app directory
sys.path.append(os.getcwd())

from app.main import create_app
from app.core import discovery, status, speaker_cache
from app.scheduler import jobs

# --- MONKEY PATCHES ---

def mock_get_all_cached_devices():
    return [
        {"name": "Living Room", "ip": "192.168.1.100"},
        {"name": "Kitchen", "ip": "192.168.1.101"},
        {"name": "Bedroom", "ip": "192.168.1.102"}
    ]

def mock_get_device_ip(name):
    ips = {
        "Living Room": "192.168.1.100",
        "Kitchen": "192.168.1.101",
        "Bedroom": "192.168.1.102"
    }
    return ips.get(name)

def mock_get_now_playing(ip):
    if ip == "192.168.1.100":
        return {
            "status": "Playing",
            "source": "Spotify",
            "track": "Morning Coffee",
            "artist": "The Jazz Trio",
            "album": "Sunrise Sessions"
        }
    elif ip == "192.168.1.101":
        return {"status": "Standby", "source": "STANDBY"}
    else:
        return {"status": "Paused", "source": "Bluetooth", "track": "Night Owls", "artist": "Lo-Fi Beats"}

def mock_get_volume(ip):
    if ip == "192.168.1.100": return 25
    if ip == "192.168.1.101": return 15
    return 10

def mock_get_speaker_state(name):
    if name == "Living Room":
        return {
            "status": "Playing",
            "source": "Spotify",
            "track": "Morning Coffee",
            "artist": "The Jazz Trio",
            "volume": 25,
            "updated_at": time.time()
        }
    return None

def mock_load_config():
    return {
        "Living Room": [
            {
                "name": "Morning Routine",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "on_time": "06:15",
                "off_time": "07:30",
                "preset": 1,
                "volume": 12,
                "fade_in_duration": 300,
                "fade_out_duration": 60,
                "paused": False
            },
            {
                "name": "Evening Chill",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "on_time": "18:00",
                "off_time": "22:00",
                "preset": 3,
                "volume": 15,
                "fade_in_duration": 600,
                "fade_out_duration": 300,
                "paused": True
            }
        ],
        "Kitchen": [
             {
                "name": "Cooking Mix",
                "days": ["saturday", "sunday"],
                "on_time": "11:00",
                "off_time": "14:00",
                "preset": 2,
                "volume": 30,
                "fade_in_duration": 60,
                "fade_out_duration": 60,
                "paused": False
            }
        ]
    }

# Apply patches
discovery.get_all_cached_devices = mock_get_all_cached_devices
discovery.get_device_ip = mock_get_device_ip
discovery.refresh_cache = lambda: None
discovery.start_device_cache = lambda: None

status.get_now_playing = mock_get_now_playing
status.get_volume = mock_get_volume

speaker_cache.get_speaker_state = mock_get_speaker_state
speaker_cache.start_ws_listeners = lambda devices: None

jobs.load_config = mock_load_config
jobs.get_current_config = mock_load_config
jobs.start_daemon = lambda: None

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=9001, debug=False)
