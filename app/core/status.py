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

if __name__ == "__main__":
    # A quick standalone test usage:
    # print(get_now_playing("192.168.1.199"))
    pass
