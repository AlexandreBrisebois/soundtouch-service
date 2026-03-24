import logging
from typing import Optional, Dict, Any
import requests
import xml.etree.ElementTree as ET
from app.core.constants import HTTP_GET_TIMEOUT_SECONDS, SOUNDTOUCH_HTTP_PORT


logger = logging.getLogger(__name__)
STATUS_MAP = {
    "PLAY_STATE": "Playing",
    "PAUSE_STATE": "Paused",
    "BUFFERING_STATE": "Buffering",
    "STOP_STATE": "Stopped"
}


def parse_now_playing_element(root: ET.Element) -> Dict[str, Any]:
    """Translate a SoundTouch now_playing XML element into API-friendly state."""
    source = root.get("source") or "UNKNOWN"
    if source == "STANDBY":
        return {"status": "Standby", "source": "STANDBY"}

    play_status_elem = root.find("playStatus")
    play_state = play_status_elem.text if play_status_elem is not None else "UNKNOWN"
    human_status = STATUS_MAP.get(play_state, play_state.replace("_STATE", "").capitalize())

    source_display = source.replace("_", " ").title()
    if source == "AUX":
        source_display = "AUX"
    elif source == "INTERNET_RADIO":
        content_item = root.find("ContentItem")
        if content_item is not None:
            item_name = content_item.findtext("itemName")
            if item_name:
                source_display = item_name

    return {
        "status": human_status,
        "source": source_display,
        "track": root.findtext("track"),
        "artist": root.findtext("artist"),
        "album": root.findtext("album"),
        "raw_state": play_state
    }


def parse_now_playing_xml(xml_text: str) -> Dict[str, Any]:
    return parse_now_playing_element(ET.fromstring(xml_text))

def get_now_playing(ip: str) -> Dict[str, Any]:
    """
    Fetches the /now_playing status of a speaker.
    Returns a dictionary of status, source, artist, track, etc.
    """
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/now_playing"
    try:
        response = requests.get(url, timeout=HTTP_GET_TIMEOUT_SECONDS)
        response.raise_for_status()
        return parse_now_playing_xml(response.text)
    except Exception as e:
        logger.warning("Error querying now_playing for %s: %s", ip, e)
        return {"status": "OFFLINE", "error": str(e)}

def get_volume(ip: str) -> Optional[int]:
    """
    Fetches the current volume level of a speaker.
    Returns the integer volume level (0-100), or None if unreachable.
    """
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/volume"
    try:
        response = requests.get(url, timeout=HTTP_GET_TIMEOUT_SECONDS)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        
        actual_volume_elem = root.find('actualvolume')
        if actual_volume_elem is not None:
            return int(actual_volume_elem.text)
            
        return None
    except Exception as e:
        logger.warning("Error getting volume from %s: %s", ip, e)
        return None

if __name__ == "__main__":
    # A quick standalone test usage:
    # print(get_now_playing("192.168.1.199"))
    pass
