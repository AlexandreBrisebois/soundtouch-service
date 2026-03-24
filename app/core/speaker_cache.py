import threading
import time
import json
import xml.etree.ElementTree as ET
import websocket
from app.core import status

# ---------------------------------------------------------------------------
# Global Speaker State Store
# ---------------------------------------------------------------------------
# { "Speaker Name": { "status": "...", "source": "...", "volume": 20, "updated_at": ... } }
_speaker_state = {}
_state_lock = threading.Lock()

def get_speaker_state(name):
    """Return the cached state for a speaker, or None if not cached."""
    with _state_lock:
        return _speaker_state.get(name)

def update_cache(name, data):
    """Atomically update the cache with new data."""
    with _state_lock:
        if name not in _speaker_state:
            _speaker_state[name] = {}
        _speaker_state[name].update(data)
        _speaker_state[name]["updated_at"] = time.time()

# ---------------------------------------------------------------------------
# WebSocket Listener
# ---------------------------------------------------------------------------

def _on_message(ws, message, speaker_name, ip):
    try:
        root = ET.fromstring(message)
        # Notifications arrive inside <updates> tags
        for update in root:
            if update.tag == "nowPlayingUpdated":
                now_playing = update.find("nowPlaying")
                if now_playing is not None:
                    # Reuse the parsing logic from status.py by passing the XML string
                    # But since status.py expects to make a request, let's just parse it here.
                    source = now_playing.get('source')
                    play_status_elem = now_playing.find('playStatus')
                    play_state = play_status_elem.text if play_status_elem is not None else "UNKNOWN"
                    
                    status_map = {
                        "PLAY_STATE": "Playing",
                        "PAUSE_STATE": "Paused",
                        "BUFFERING_STATE": "Buffering",
                        "STOP_STATE": "Stopped"
                    }
                    human_status = status_map.get(play_state, play_state.replace("_STATE", "").capitalize())
                    
                    source_display = source.replace("_", " ").title()
                    if source == "INTERNET_RADIO":
                        content_item = now_playing.find('ContentItem')
                        if content_item is not None:
                            item_name = content_item.findtext('itemName')
                            if item_name:
                                source_display = item_name

                    update_cache(speaker_name, {
                        "status": human_status,
                        "source": source_display,
                        "track": now_playing.findtext('track'),
                        "artist": now_playing.findtext('artist'),
                        "album": now_playing.findtext('album'),
                        "raw_state": play_state
                    })

            elif update.tag == "volumeUpdated":
                # volumeUpdated is often an empty tag, need to fetch the real volume
                vol = status.get_volume(ip)
                if vol is not None:
                    update_cache(speaker_name, {"volume": vol})
                    
    except Exception as e:
        print(f"[WS Cache] Error processing message from {speaker_name}: {e}")

def _on_error(ws, error, speaker_name):
    print(f"[WS Cache] WebSocket error for {speaker_name}: {error}")

def _on_close(ws, close_status_code, close_msg, speaker_name):
    print(f"[WS Cache] WebSocket closed for {speaker_name}. Reconnecting in 5s...")
    time.sleep(5)

def listen_to_speaker(name, ip):
    """Maintain a persistent WebSocket connection to a speaker."""
    while True:
        try:
            # 1. Prime the cache with initial HTTP reads
            print(f"[WS Cache] Priming '{name}' at {ip}...")
            initial_status = status.get_now_playing(ip)
            initial_volume = status.get_volume(ip)
            update_cache(name, {**initial_status, "volume": initial_volume})
            
            # 2. Open WebSocket
            ws_url = f"ws://{ip}:8080"
            ws = websocket.WebSocketApp(
                ws_url,
                subprotocols=["gabbo"],
                on_message=lambda ws, msg: _on_message(ws, msg, name, ip),
                on_error=lambda ws, err: _on_error(ws, err, name),
                on_close=lambda ws, code, msg: _on_close(ws, code, msg, name)
            )
            print(f"[WS Cache] Connecting to {name} WebSocket...")
            ws.run_forever()
        except Exception as e:
            print(f"[WS Cache] Loop error for {name}: {e}. Retrying in 10s...")
            time.sleep(10)

def start_ws_listeners(devices):
    """Start a listener thread for each discovered device."""
    for d in devices:
        name = d['name']
        ip = d['ip']
        t = threading.Thread(target=listen_to_speaker, args=(name, ip), daemon=True)
        t.start()
        print(f"[WS Cache] Started listener for '{name}'")
