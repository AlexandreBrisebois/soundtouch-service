import requests
import xml.etree.ElementTree as ET

def get_now_playing(ip):
    """
    Fetches the /now_playing status of a speaker.
    Returns:
      - 'STANDBY' if powered off/standby
      - 'PLAY_STATE' if actively playing audio
      - 'PAUSE_STATE' or 'STOP_STATE' depending on other statuses
      - None if unreachable
    """
    url = f"http://{ip}:8090/now_playing"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        
        # The 'source' attribute usually equals 'STANDBY' if it is off
        source = root.get('source')
        if source == "STANDBY":
            return "STANDBY"
            
        play_status_elem = root.find('playStatus')
        if play_status_elem is not None:
            return play_status_elem.text
        
        return "UNKNOWN"
    except Exception as e:
        print(f"Error querying {ip}: {e}")
        return None

def get_volume(ip):
    """
    Fetches the current volume level of a speaker.
    Returns the integer volume level (0-100), or None if unreachable.
    """
    url = f"http://{ip}:8090/volume"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        
        actual_volume_elem = root.find('actualvolume')
        if actual_volume_elem is not None:
            return int(actual_volume_elem.text)
            
        return None
    except Exception as e:
        print(f"Error getting volume from {ip}: {e}")
        return None

if __name__ == "__main__":
    # A quick standalone test usage:
    # print(get_now_playing("192.168.1.199"))
    pass
