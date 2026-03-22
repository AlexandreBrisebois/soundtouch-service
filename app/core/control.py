import requests

def send_key(ip, key):
    """ Sends a key simulated press & release to the SoundTouch speaker """
    url = f"http://{ip}:8090/key"
    payload_press = f'<?xml version="1.0" ?><key state="press" sender="Gabbo">{key}</key>'
    payload_release = f'<?xml version="1.0" ?><key state="release" sender="Gabbo">{key}</key>'
    try:
        requests.post(url, data=payload_press, timeout=3)
        requests.post(url, data=payload_release, timeout=3)
        return True
    except Exception as e:
        print(f"Failed to send key '{key}' to {ip}: {e}")
        return False

def set_volume(ip, volume: int):
    """ Sets a specific 0-100 volume level """
    url = f"http://{ip}:8090/volume"
    payload = f'<?xml version="1.0" ?><volume>{volume}</volume>'
    try:
        requests.post(url, data=payload, timeout=3)
        return True
    except Exception as e:
        print(f"Failed to set volume {volume} on {ip}: {e}")
        return False

def power_action(ip):
    """
    Toggles the speaker power. Note: SoundTouch only has a toggle.
    Therefore, before sending POWER, make sure to check if it's currently ON via status.py!
    """
    return send_key(ip, "POWER")

def stop_action(ip):
    return send_key(ip, "STOP")

def play_preset(ip, preset_num=1):
    return send_key(ip, f"PRESET_{preset_num}")
