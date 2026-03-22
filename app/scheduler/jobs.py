import os
import json
import time
import threading
import queue
from app.core import discovery, status, control

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")
config_queue = queue.Queue()

# In-memory config accessed by scheduler and API GETs
current_config = {}

def get_default_config():
    return {
        "Target Speaker 1": [
            {
                "name": "Morning Routine",
                "on_time": "06:15",
                "off_time": "07:30",
                "preset": 1,
                "volume": 10
            }
        ]
    }

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = get_default_config()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            print(f"[Scheduler] Error creating config: {e}")
        return default_config
        
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Scheduler] Error reading config: {e}")
        return {}

def config_io_worker():
    """Background thread to process configuration changes sequentially."""
    print("[IO Manager] Started background config writer thread.")
    while True:
        try:
            mutation = config_queue.get()
            if mutation is None:
                break
            
            # Action: 'add_update', 'delete'
            action = mutation.get("action")
            speaker = mutation.get("speaker")
            schedule_name = mutation.get("schedule_name")
            data = mutation.get("data")
            
            # Read latest from disk
            config = load_config()
            
            if speaker not in config:
                config[speaker] = []
                
            schedules = config[speaker]
            
            if action == 'add_update':
                # Remove existing with same name if it exists, then append
                schedules = [s for s in schedules if s.get("name") != schedule_name]
                schedules.append(data)
                config[speaker] = schedules
                
            elif action == 'delete':
                schedules = [s for s in schedules if s.get("name") != schedule_name]
                if not schedules:
                    del config[speaker]
                else:
                    config[speaker] = schedules

            # -----------------------------------------------------------------
            # IMPORTANT DOCKER CAVEAT:
            # We must NOT use `os.replace` if config.json is bind-mounted 
            # natively as a single file (e.g. `- ./config.json:/app/config.json`).
            # `os.replace` changes the inode, which breaks the Docker volume 
            # link to the host system.
            # 
            # To maintain the data link to the Synology Host, we write directly to the 
            # opened file object, which truncates and overwrites the existing inode inline. 
            # -----------------------------------------------------------------
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            
            print(f"[IO Manager] Successfully applied '{action}' for {speaker} - {schedule_name}")
            
            # Update in-memory config
            global current_config
            current_config = config
            
            config_queue.task_done()
        except Exception as e:
            print(f"[IO Manager] Error processing mutation: {e}")

def auto_on_job(speaker_name, preset, volume):
    print(f"[Scheduler] Auto-ON triggered for '{speaker_name}'...")
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
        print(f"[Scheduler] '{speaker_name}' is already active. Ignoring ON event to prevent interruption.")
        return
        
    print(f"[Scheduler] '{speaker_name}' is STANDBY. Turning on...")
    if control.power_action(target_ip):
        # Wait a moment for speaker to boot and accept additional commands
        time.sleep(3)
        print(f"[Scheduler] '{speaker_name}' setting volume to {volume}...")
        control.set_volume(target_ip, volume)
        time.sleep(1)
        print(f"[Scheduler] '{speaker_name}' playing preset {preset}...")
        control.play_preset(target_ip, preset)

def auto_off_job(speaker_name):
    print(f"[Scheduler] Auto-OFF triggered for '{speaker_name}'...")
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
    global current_config
    current_config = load_config()
    print(f"[Scheduler] Initialized. Dynamic configuration loaded from '{CONFIG_FILE}'.")
    last_processed_minute = None
    
    while True:
        now = time.localtime()
        current_time_str = time.strftime("%H:%M", now)
        
        if current_time_str != last_processed_minute:
            last_processed_minute = current_time_str
            
            # Fast in-memory check instead of disk read
            config = current_config
            for speaker_name, schedules in config.items():
                if not isinstance(schedules, list):
                    continue
                    
                for schedule in schedules:
                    on_time = schedule.get("on_time")
                    off_time = schedule.get("off_time")
                    
                    if current_time_str == on_time:
                        threading.Thread(
                            target=auto_on_job, 
                            args=(speaker_name, schedule.get("preset", 1), schedule.get("volume", 20)), 
                            daemon=True
                        ).start()
                        
                    if current_time_str == off_time:
                        threading.Thread(
                            target=auto_off_job, 
                            args=(speaker_name,), 
                            daemon=True
                        ).start()
                    
        time.sleep(10)

def start_daemon():
    # Start the IO worker
    threading.Thread(target=config_io_worker, daemon=True).start()
    # Start the scheduler
    threading.Thread(target=run_scheduler_loop, daemon=True).start()

def get_current_config():
    global current_config
    if not current_config:
         current_config = load_config()
    return current_config
