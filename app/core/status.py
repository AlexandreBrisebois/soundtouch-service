import requests
import xml.etree.ElementTree as ET

def get_now_playing(ip):
    """
    Fetches the /now_playing status of a speaker.
    Returns a dictionary of status, source, artist, track, etc.
    """
    url = f"http://{ip}:8090/now_playing"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        
        source = root.get('source')
        if source == "STANDBY":
            return {"status": "STANDBY", "source": "STANDBY"}
            
        play_status_elem = root.find('playStatus')
        play_state = play_status_elem.text if play_status_elem is not None else "UNKNOWN"
        
        # Map raw statuses to human-readable strings
        status_map = {
            "PLAY_STATE": "Playing",
            "PAUSE_STATE": "Paused",
            "BUFFERING_STATE": "Buffering",
            "STOP_STATE": "Stopped"
        }
        human_status = status_map.get(play_state, play_state.replace("_STATE", "").capitalize())

        # Extract metadata
        track = root.findtext('track')
        artist = root.findtext('artist')
        album = root.findtext('album')
        
        # Source display name refinements
        source_display = source.replace("_", " ").title()
        if source == "AUX":
            source_display = "AUX"
        elif source == "INTERNET_RADIO":
            content_item = root.find('ContentItem')
            if content_item is not None:
                item_name = content_item.findtext('itemName')
                if item_name:
                    source_display = item_name

        return {
            "status": human_status,
            "source": source_display,
            "track": track,
            "artist": artist,
            "album": album,
            "raw_state": play_state
        }
    except Exception as e:
        print(f"Error querying {ip}: {e}")
        return {"status": "OFFLINE", "error": str(e)}

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
