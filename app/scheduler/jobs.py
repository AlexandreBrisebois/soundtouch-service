import os
import json
import time
import threading
from app.core import discovery, status, control

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {"Target Speaker 1": "22:30"}
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)
        except Exception:
            pass
        return default_config
        
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Scheduler] Error reading config: {e}")
        return {}

def auto_sleep_job(speaker_name):
    print(f"[Scheduler] Auto-sleep triggered for '{speaker_name}'...")
    devices = discovery.discover_systems(timeout=5)
    
    target_ip = None
    for d in devices:
        if d['name'] == speaker_name:
            target_ip = d['ip']
            break
            
    if not target_ip:
        print(f"[Scheduler] '{speaker_name}' not found on the local network. Aborting.")
        return

    speaker_status = status.get_now_playing(target_ip)
    print(f"[Scheduler] '{speaker_name}' current status is '{speaker_status}'")
    
    if speaker_status != "STANDBY":
        print(f"[Scheduler] Speaker is active. Sending power off signal.")
        control.power_action(target_ip)
    else:
        print(f"[Scheduler] Speaker is already in STANDBY mode. No action needed.")

def run_scheduler_loop():
    print(f"[Scheduler] Initialized. Dynamic configuration loaded from '{CONFIG_FILE}'.")
    last_processed_minute = None
    
    while True:
        now = time.localtime()
        current_time_str = time.strftime("%H:%M", now)
        
        if current_time_str != last_processed_minute:
            last_processed_minute = current_time_str
            
            # Read config directly from disk so updates take effect immediately without restarting!
            config = load_config()
            for speaker_name, sleep_time in config.items():
                if current_time_str == sleep_time:
                    # Thread the discovery so multiple speakers with the exact same sleep time don't block each other
                    threading.Thread(target=auto_sleep_job, args=(speaker_name,), daemon=True).start()
                    
        time.sleep(10)

def start_daemon():
    scheduler_thread = threading.Thread(target=run_scheduler_loop, daemon=True)
    scheduler_thread.start()
