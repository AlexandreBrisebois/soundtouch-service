import logging
from typing import Optional

import requests
from app.core.constants import HTTP_POST_TIMEOUT_SECONDS, SOUNDTOUCH_HTTP_PORT


logger = logging.getLogger(__name__)

def send_key(ip: str, key: str) -> bool:
    """ Sends a key simulated press & release to the SoundTouch speaker """
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/key"
    payload_press = f'<?xml version="1.0" ?><key state="press" sender="Gabbo">{key}</key>'
    payload_release = f'<?xml version="1.0" ?><key state="release" sender="Gabbo">{key}</key>'
    try:
        requests.post(url, data=payload_press, timeout=HTTP_POST_TIMEOUT_SECONDS)
        requests.post(url, data=payload_release, timeout=HTTP_POST_TIMEOUT_SECONDS)
        return True
    except Exception as e:
        logger.error("Failed to send key '%s' to %s: %s", key, ip, e)
        return False

def set_volume(ip: str, volume: int) -> bool:
    """ Sets a specific 0-100 volume level """
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/volume"
    payload = f'<?xml version="1.0" ?><volume>{volume}</volume>'
    try:
        requests.post(url, data=payload, timeout=HTTP_POST_TIMEOUT_SECONDS)
        return True
    except Exception as e:
        logger.error("Failed to set volume %s on %s: %s", volume, ip, e)
        return False

def power_action(ip: str) -> bool:
    """
    Toggles the speaker power. Note: SoundTouch only has a toggle.
    Therefore, before sending POWER, make sure to check if it's currently ON via status.py!
    """
    return send_key(ip, "POWER")

def stop_action(ip: str) -> bool:
    return send_key(ip, "STOP")

def play_preset(ip: str, preset_num: int = 1) -> bool:
    return send_key(ip, f"PRESET_{preset_num}")
