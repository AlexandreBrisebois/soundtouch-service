import logging
import threading
import time
from typing import Any
import xml.etree.ElementTree as ET
import websocket
from app.core.constants import (
    SOUNDTOUCH_WEBSOCKET_PORT,
    WEBSOCKET_CLOSE_RETRY_DELAY_SECONDS,
    WEBSOCKET_LOOP_RETRY_DELAY_SECONDS,
    WEBSOCKET_PING_INTERVAL_SECONDS,
    WEBSOCKET_PING_TIMEOUT_SECONDS,
)
from app.core import status


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global Speaker State Store
# ---------------------------------------------------------------------------
# { "Speaker Name": { "status": "...", "source": "...", "volume": 20, "updated_at": ... } }
_speaker_state: dict[str, dict[str, Any]] = {}
_state_lock = threading.Lock()
_listener_threads: dict[str, threading.Thread] = {}
_listener_lock = threading.Lock()

def get_speaker_state(name: str) -> dict[str, Any] | None:
    """Return the cached state for a speaker, or None if not cached."""
    with _state_lock:
        return _speaker_state.get(name)

def update_cache(name: str, data: dict[str, Any]) -> None:
    """Atomically update the cache with new data."""
    with _state_lock:
        if name not in _speaker_state:
            _speaker_state[name] = {}
        _speaker_state[name].update(data)
        _speaker_state[name]["updated_at"] = time.time()

# ---------------------------------------------------------------------------
# WebSocket Listener
# ---------------------------------------------------------------------------

def _on_message(ws: websocket.WebSocketApp, message: str, speaker_name: str, ip: str) -> None:
    try:
        root = ET.fromstring(message)
        # Notifications arrive inside <updates> tags
        for update in root:
            if update.tag == "nowPlayingUpdated":
                now_playing = update.find("nowPlaying")
                if now_playing is not None:
                    update_cache(speaker_name, status.parse_now_playing_element(now_playing))

            elif update.tag == "volumeUpdated":
                # volumeUpdated is often an empty tag, need to fetch the real volume
                vol = status.get_volume(ip)
                if vol is not None:
                    update_cache(speaker_name, {"volume": vol})
                    
    except ET.ParseError as e:
        logger.warning("WebSocket message processing failed for %s: %s", speaker_name, e)

def _on_error(ws: websocket.WebSocketApp, error: Exception, speaker_name: str) -> None:
    logger.warning("WebSocket error for %s: %s", speaker_name, error)

def _on_close(ws: websocket.WebSocketApp, close_status_code: int | None, close_msg: str | None, speaker_name: str) -> None:
    logger.info("WebSocket closed for %s (code=%s, message=%s). Reconnecting in %ss.", speaker_name, close_status_code, close_msg, WEBSOCKET_CLOSE_RETRY_DELAY_SECONDS)
    time.sleep(WEBSOCKET_CLOSE_RETRY_DELAY_SECONDS)

def listen_to_speaker(name: str, ip: str) -> None:
    """Maintain a persistent WebSocket connection to a speaker."""
    initial_prime = True  # Track if this is the first attempt
    while True:
        try:
            # 1. Prime the cache with initial HTTP reads on first connection only
            if initial_prime:
                logger.info("Priming cached state for '%s' at %s.", name, ip)
                initial_status = status.get_now_playing(ip)
                initial_volume = status.get_volume(ip)
                update_cache(name, {**initial_status, "volume": initial_volume})
                initial_prime = False
            
            # 2. Open WebSocket
            ws_url = f"ws://{ip}:{SOUNDTOUCH_WEBSOCKET_PORT}"
            ws = websocket.WebSocketApp(
                ws_url,
                subprotocols=["gabbo"],
                on_message=lambda ws, msg: _on_message(ws, msg, name, ip),
                on_error=lambda ws, err: _on_error(ws, err, name),
                on_close=lambda ws, code, msg: _on_close(ws, code, msg, name)
            )
            logger.info("Connecting WebSocket listener for '%s'.", name)
            ws.run_forever(
                ping_interval=WEBSOCKET_PING_INTERVAL_SECONDS,
                ping_timeout=WEBSOCKET_PING_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logger.warning("WebSocket listener loop error for %s: %s. Retrying in %ss.", name, e, WEBSOCKET_LOOP_RETRY_DELAY_SECONDS)
            time.sleep(WEBSOCKET_LOOP_RETRY_DELAY_SECONDS)

def start_ws_listeners(devices: list[dict[str, str]]) -> None:
    """Start a listener thread for each discovered device."""
    with _listener_lock:
        existing_names = set(_listener_threads.keys())
    
    for d in devices:
        name = d.get('name')
        ip = d.get('ip')
        if not name or not ip:
            continue
        
        # Skip if already running a listener for this speaker
        if name in existing_names:
            logger.debug("Listener already active for '%s', skipping duplicate.", name)
            continue
        
        # Atomically register and start the listener
        with _listener_lock:
            if name in _listener_threads:
                # Double-check in case another thread started one
                logger.debug("Listener already registered for '%s', skipping.", name)
                continue
            t = threading.Thread(target=listen_to_speaker, args=(name, ip), daemon=True)
            _listener_threads[name] = t
        
        t.start()
        logger.info("Started WebSocket listener for '%s'.", name)
