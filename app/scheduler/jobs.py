import logging
import os
import json
import time
import threading
import queue
import re
from typing import Optional, Dict, Any, List
from app.core.constants import (
    DEFAULT_FADE_IN_DURATION_SECONDS,
    DEFAULT_FADE_OUT_DURATION_SECONDS,
    DEFAULT_PRESET,
    DEFAULT_VOLUME,
    FADE_STATUS_RECHECK_STEP_INTERVAL,
    SCHEDULER_LOOP_INTERVAL_SECONDS,
    SOURCE_SETTLE_DELAY_SECONDS,
    SPEAKER_BOOT_DELAY_SECONDS,
)
from app.core import discovery, status, control

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")
config_queue = queue.Queue()
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

# In-memory config accessed by scheduler and API GETs
current_config: Dict[str, List[Dict[str, Any]]] = {}
logger = logging.getLogger(__name__)

def get_default_config() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "Target Speaker 1": [
            {
                "name": "Morning Routine",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                "on_time": "06:15",
                "off_time": "07:30",
                "preset": DEFAULT_PRESET,
                "volume": 10,
                "fade_in_duration": DEFAULT_FADE_IN_DURATION_SECONDS,
                "fade_out_duration": DEFAULT_FADE_OUT_DURATION_SECONDS,
                "paused": False
            }
        ]
    }


def _coerce_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        coerced = default

    if minimum is not None:
        coerced = max(minimum, coerced)
    if maximum is not None:
        coerced = min(maximum, coerced)
    return coerced


def _coerce_non_negative_float(value: Any, default: float) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        coerced = default
    return max(0.0, coerced)


def _normalize_time(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if TIME_PATTERN.fullmatch(candidate):
        return candidate
    return None


def _normalize_schedule(schedule: Any, speaker_name: str, index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(schedule, dict):
        logger.warning("Skipping invalid schedule #%s for '%s': expected an object.", index + 1, speaker_name)
        return None

    name = schedule.get("name")
    if not isinstance(name, str) or not name.strip():
        logger.warning("Skipping schedule #%s for '%s': missing valid name.", index + 1, speaker_name)
        return None

    on_time = _normalize_time(schedule.get("on_time"))
    off_time = _normalize_time(schedule.get("off_time"))
    if on_time is None and off_time is None:
        logger.warning("Skipping schedule '%s' for '%s': no valid on/off time.", name, speaker_name)
        return None

    days = schedule.get("days")
    normalized_days = None
    if days is not None:
        if not isinstance(days, list):
            logger.warning("Skipping schedule '%s' for '%s': days must be a list.", name, speaker_name)
            return None
        normalized_days = []
        for day in days:
            if not isinstance(day, str):
                continue
            normalized_day = day.strip().lower()
            if normalized_day in VALID_DAYS and normalized_day not in normalized_days:
                normalized_days.append(normalized_day)
        if not normalized_days:
            logger.warning("Skipping schedule '%s' for '%s': no valid day names.", name, speaker_name)
            return None

    source = schedule.get("source")
    if isinstance(source, str) and source.strip().upper() == "AUX":
        normalized_source = "AUX"
        preset = None
    else:
        normalized_source = None
        preset = _coerce_int(schedule.get("preset", 1), 1, minimum=1, maximum=6)

    return {
        "name": name.strip(),
        "days": normalized_days,
        "on_time": on_time,
        "off_time": off_time,
        "preset": preset,
        "source": normalized_source,
        "volume": _coerce_int(schedule.get("volume", DEFAULT_VOLUME), DEFAULT_VOLUME, minimum=0, maximum=100),
        "fade_in_duration": _coerce_non_negative_float(schedule.get("fade_in_duration", DEFAULT_FADE_IN_DURATION_SECONDS), DEFAULT_FADE_IN_DURATION_SECONDS),
        "fade_out_duration": _coerce_non_negative_float(schedule.get("fade_out_duration", DEFAULT_FADE_OUT_DURATION_SECONDS), DEFAULT_FADE_OUT_DURATION_SECONDS),
        "paused": bool(schedule.get("paused", False)),
    }


def sanitize_config(config: Any) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if config is None:
        return None
    if not isinstance(config, dict):
        logger.warning("Config root must be an object. Falling back to an empty configuration.")
        return {}

    sanitized = {}
    for speaker_name, schedules in config.items():
        if not isinstance(speaker_name, str) or not speaker_name.strip():
            logger.warning("Skipping config entry with invalid speaker name.")
            continue
        if not isinstance(schedules, list):
            logger.warning("Skipping speaker '%s': schedules must be a list.", speaker_name)
            continue

        normalized_schedules = []
        for index, schedule in enumerate(schedules):
            normalized = _normalize_schedule(schedule, speaker_name, index)
            if normalized is not None:
                normalized_schedules.append(normalized)

        if normalized_schedules:
            sanitized[speaker_name] = normalized_schedules

    return sanitized

def load_config() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not os.path.exists(CONFIG_FILE):
        default_config = get_default_config()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            logger.error("Error creating config file %s: %s", CONFIG_FILE, e)
        return default_config
        
    try:
        with open(CONFIG_FILE, "r") as f:
            return sanitize_config(json.load(f))
    except Exception as e:
        logger.error("Error reading config file %s: %s", CONFIG_FILE, e)
        return None

def config_io_worker() -> None:
    """Background thread to process configuration changes sequentially."""
    logger.info("Started background config writer thread.")
    while True:
        mutation = config_queue.get()
        try:
            if mutation is None:
                break
            
            # Action: 'add_update', 'delete'
            action = mutation.get("action")
            speaker = mutation.get("speaker")
            schedule_name = mutation.get("schedule_name")
            previous_name = mutation.get("previous_name")
            data = mutation.get("data")
            
            # Read latest from disk
            config = load_config()
            if config is None:
                logger.warning("Skipping config mutation because the config file could not be loaded.")
                continue
            
            if speaker not in config:
                config[speaker] = []
                
            schedules = config[speaker]
            
            if action == 'add_update':
                # Remove existing with same name if it exists, then append
                names_to_replace = {schedule_name}
                if previous_name:
                    names_to_replace.add(previous_name)
                schedules = [s for s in schedules if s.get("name") not in names_to_replace]
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
            # natively as a single file (e.g. `- ./config.json:/workspace/config.json`).
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
            
            logger.info("Applied config mutation '%s' for speaker '%s' schedule '%s'.", action, speaker, schedule_name)
            
            # Update in-memory config
            global current_config
            current_config = config
        except Exception as e:
            logger.exception("Error processing config mutation: %s", e)
        finally:
            config_queue.task_done()

def auto_on_job(speaker_name: str, preset: Optional[int], volume: int, source: Optional[str] = None, fade_in_duration: float = DEFAULT_FADE_IN_DURATION_SECONDS, force: bool = False) -> None:
    logger.info("Auto-ON triggered for '%s'.", speaker_name)
    target_ip = discovery.get_device_ip(speaker_name)

    if not target_ip:
        logger.warning("Speaker '%s' not found in cache or on network. Aborting auto-on.", speaker_name)
        return

    status_data = status.get_now_playing(target_ip)
    speaker_status = status_data.get("status", "OFFLINE")
    logger.info("Speaker '%s' current status is '%s'.", speaker_name, speaker_status)
    
    is_active = speaker_status.upper() not in ["STANDBY", "OFFLINE"]

    volume = _coerce_int(volume, DEFAULT_VOLUME, minimum=0, maximum=100)
    fade_in_duration = _coerce_non_negative_float(fade_in_duration, DEFAULT_FADE_IN_DURATION_SECONDS)
    
    if is_active and not force:
        logger.info("Speaker '%s' is already active. Ignoring ON event to prevent interruption.", speaker_name)
        return
        
    if not is_active:
        logger.info("Speaker '%s' is %s. Turning on.", speaker_name, speaker_status)
        if control.power_action(target_ip):
            # Wait a moment for speaker to boot and accept additional commands
            time.sleep(SPEAKER_BOOT_DELAY_SECONDS)
    else:
        logger.info("Speaker '%s' is active, but force=True was provided. Proceeding with routine.", speaker_name)

    if source == "AUX":
        logger.info("Speaker '%s' switching to AUX input.", speaker_name)
        control.send_key(target_ip, "AUX_INPUT")
    else:
        preset = _coerce_int(preset, DEFAULT_PRESET, minimum=1, maximum=6)
        logger.info("Speaker '%s' playing preset %s.", speaker_name, preset)
        control.play_preset(target_ip, preset)

    # Give source selection a moment before starting fade.
    time.sleep(SOURCE_SETTLE_DELAY_SECONDS)

    logger.info("Speaker '%s' starting volume fade-in to %s over %ss.", speaker_name, volume, fade_in_duration)
    # Always begin from 0 so manual trigger tests the configured fade profile.
    control.set_volume(target_ip, 0)

    if fade_in_duration <= 0 or volume <= 0:
        control.set_volume(target_ip, volume)
        return

    sleep_interval = fade_in_duration / volume

    for v in range(1, volume + 1):
        time.sleep(sleep_interval)

        if v % FADE_STATUS_RECHECK_STEP_INTERVAL == 0 or sleep_interval > FADE_STATUS_RECHECK_STEP_INTERVAL:
            status_data = status.get_now_playing(target_ip)
            if status_data.get("status", "").upper() == "STANDBY":
                logger.info("Fade-in aborted for '%s': speaker was manually turned off mid-fade.", speaker_name)
                return

        control.set_volume(target_ip, v)

    logger.info("Speaker '%s' achieved target volume %s.", speaker_name, volume)

def auto_off_job(speaker_name: str, fade_out_duration: float = DEFAULT_FADE_OUT_DURATION_SECONDS) -> None:
    logger.info("Auto-OFF triggered for '%s'.", speaker_name)
    target_ip = discovery.get_device_ip(speaker_name)

    if not target_ip:
        logger.warning("Speaker '%s' not found in cache or on network. Aborting auto-off.", speaker_name)
        return

    status_data = status.get_now_playing(target_ip)
    speaker_status = status_data.get("status", "OFFLINE")
    logger.info("Speaker '%s' current status is '%s'.", speaker_name, speaker_status)

    fade_out_duration = _coerce_non_negative_float(fade_out_duration, DEFAULT_FADE_OUT_DURATION_SECONDS)
    
    if speaker_status.upper() not in ["STANDBY", "OFFLINE"]:
        logger.info("Speaker '%s' is active. Starting volume fade-out over %ss.", speaker_name, fade_out_duration)
        
        current_volume = status.get_volume(target_ip)
        try:
            current_volume = int(current_volume) if current_volume is not None else None
        except (TypeError, ValueError):
            current_volume = None
        if current_volume is not None:
            current_volume = max(0, min(100, current_volume))
        if current_volume is not None and current_volume > 0 and fade_out_duration > 0:
            sleep_interval = fade_out_duration / current_volume
            for v in range(current_volume - 1, -1, -1):
                time.sleep(sleep_interval)
                
                if v % FADE_STATUS_RECHECK_STEP_INTERVAL == 0 or sleep_interval > FADE_STATUS_RECHECK_STEP_INTERVAL:
                    status_data = status.get_now_playing(target_ip)
                    if status_data.get("status", "").upper() == "STANDBY":
                        logger.info("Fade-out aborted for '%s': speaker was already turned off.", speaker_name)
                        return
                        
                control.set_volume(target_ip, v)
                
        logger.info("Sending power off signal to '%s'.", speaker_name)
        control.power_action(target_ip)
    else:
        logger.info("Speaker '%s' is already in standby/offline mode. No action needed.", speaker_name)


def run_scheduler_loop() -> None:
    global current_config
    current_config = load_config() or {}
    logger.info("Scheduler initialized. Dynamic configuration loaded from '%s'.", CONFIG_FILE)
    for speaker, schedules in current_config.items():
        if isinstance(schedules, list):
            logger.info("Loaded %s schedule(s) for '%s': %s", len(schedules), speaker, [s.get('name') for s in schedules])
    last_processed_minute = None
    
    while True:
        now = time.localtime()
        current_time_str = time.strftime("%H:%M", now)
        current_day = time.strftime("%A", now).lower()
        
        if current_time_str != last_processed_minute:
            last_processed_minute = current_time_str
            
            # Fast in-memory check instead of disk read
            config = current_config
            for speaker_name, schedules in config.items():
                if not isinstance(schedules, list):
                    continue
                    
                for schedule in schedules:
                    if not isinstance(schedule, dict):
                        continue
                    if schedule.get("paused", False):
                        continue

                    days = schedule.get("days")
                    if days and current_day not in days:
                        continue
                        
                    on_time = schedule.get("on_time")
                    off_time = schedule.get("off_time")
                    
                    if current_time_str == on_time:
                        preset = schedule.get("preset", DEFAULT_PRESET)
                        volume = schedule.get("volume", DEFAULT_VOLUME)
                        source = schedule.get("source")
                        fade_in_duration = schedule.get("fade_in_duration", DEFAULT_FADE_IN_DURATION_SECONDS)
                        source_log = f"Source: {source}" if source else f"Preset: {preset}"
                        logger.info("[%s] '%s' for '%s' ON event triggered (%s, target volume=%s, fade=%ss).", current_time_str, schedule.get('name'), speaker_name, source_log, volume, fade_in_duration)
                        threading.Thread(
                            target=auto_on_job, 
                            args=(speaker_name, preset, volume, source, fade_in_duration), 
                            daemon=True
                        ).start()
                        
                    if current_time_str == off_time:
                        fade_out_duration = schedule.get("fade_out_duration", DEFAULT_FADE_OUT_DURATION_SECONDS)
                        logger.info("[%s] '%s' for '%s' OFF event triggered (fade=%ss).", current_time_str, schedule.get('name'), speaker_name, fade_out_duration)
                        threading.Thread(
                            target=auto_off_job, 
                            args=(speaker_name, fade_out_duration), 
                            daemon=True
                        ).start()
                    
        time.sleep(SCHEDULER_LOOP_INTERVAL_SECONDS)

def start_daemon() -> None:
    # Start the IO worker
    threading.Thread(target=config_io_worker, daemon=True).start()
    # Start the scheduler
    threading.Thread(target=run_scheduler_loop, daemon=True).start()

def get_current_config() -> Dict[str, List[Dict[str, Any]]]:
    global current_config
    if not current_config:
        current_config = load_config() or {}
    return current_config
