import logging
import threading
import time
from copy import deepcopy
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
DEFAULT_MAX_AGE_SECONDS = 15.0

_speaker_state: dict[str, dict[str, Any]] = {}
# Wall-clock timestamps are returned to clients; elapsed age uses a monotonic clock.
_playback_observed_at: dict[str, float] = {}
_volume_observed_at: dict[str, float] = {}
_state_lock = threading.Lock()
_listener_threads: dict[str, threading.Thread] = {}
_listener_stop_events: dict[str, threading.Event] = {}
_listener_sockets: dict[str, websocket.WebSocketApp] = {}
_listener_addresses: dict[str, str] = {}
_listener_identities: dict[str, str] = {}
_listener_lock = threading.Lock()


def get_speaker_state(
    name: str, max_age: float = DEFAULT_MAX_AGE_SECONDS
) -> dict[str, Any] | None:
    """Return an isolated snapshot only while its playback observation is fresh."""
    with _state_lock:
        observed_at = _playback_observed_at.get(name)
        if observed_at is None or not 0 <= time.monotonic() - observed_at <= max_age:
            return None
        snapshot = deepcopy(_speaker_state.get(name))
        volume_at = _volume_observed_at.get(name)
        if snapshot is not None and (volume_at is None or time.monotonic() - volume_at > max_age):
            snapshot['volume'] = None
        return snapshot


def update_cache(name: str, data: dict[str, Any]) -> None:
    """Update independent playback/volume observations, never refreshing one with the other."""
    with _state_lock:
        current = _speaker_state.setdefault(name, {})
        now = time.time()
        if "status" in data or "source" in data or "raw_state" in data:
            # Playback snapshots replace their old fields, so Standby or an error
            # cannot retain a previous track, content identity, or error message.
            current = {
                key: current[key]
                for key in ("volume", "volume_updated_at")
                if key in current
            }
            current.update(deepcopy(data))
            current["playback_updated_at"] = now
            _playback_observed_at[name] = time.monotonic()
            _speaker_state[name] = current
        if "volume" in data:
            current["volume"] = data["volume"]
            current["volume_updated_at"] = now
            _volume_observed_at[name] = time.monotonic()
        # Kept for API compatibility; this is not used as playback freshness.
        current["updated_at"] = now


def invalidate_cache(name: str) -> None:
    """Discard observations after disconnects, address changes, or removals."""
    with _state_lock:
        _speaker_state.pop(name, None)
        _playback_observed_at.pop(name, None)
        _volume_observed_at.pop(name, None)


def _is_current_listener(
    name: str, stop_event: threading.Event, ws: websocket.WebSocketApp
) -> bool:
    """Called with _listener_lock held; the event is the listener generation."""
    return (
        not stop_event.is_set()
        and _listener_stop_events.get(name) is stop_event
        and _listener_sockets.get(name) is ws
    )


def _update_listener_cache(
    name: str, data: dict[str, Any], stop_event: threading.Event, ws: websocket.WebSocketApp
) -> None:
    # Keep ownership checking and publication atomic against replacement/shutdown.
    with _listener_lock:
        if not _is_current_listener(name, stop_event, ws):
            return
        expected_id = _listener_identities.get(name)
        if expected_id and 'status' in data and data.get('device_id') != expected_id:
            invalidate_cache(name)
            return
        update_cache(name, data)
    # Avoid coupling cache locks to the operation registry/write lock.
    from app.core import playback
    playback.observe_external(name, data)


def _on_open(
    ws: websocket.WebSocketApp, speaker_name: str, ip: str, stop_event: threading.Event
) -> None:
    with _listener_lock:
        if not _is_current_listener(speaker_name, stop_event, ws):
            return
    logger.info("Priming cached state for '%s' at %s.", speaker_name, ip)
    _update_listener_cache(speaker_name, status.get_now_playing(ip), stop_event, ws)
    with _listener_lock:
        if not _is_current_listener(speaker_name, stop_event, ws):
            return
    volume = status.get_volume(ip)
    if volume is not None:
        _update_listener_cache(speaker_name, {"volume": volume}, stop_event, ws)


def _on_message(
    ws: websocket.WebSocketApp,
    message: str,
    speaker_name: str,
    ip: str,
    stop_event: threading.Event,
) -> None:
    with _listener_lock:
        if not _is_current_listener(speaker_name, stop_event, ws):
            return
    try:
        root = ET.fromstring(message)
        for update in root:
            if update.tag == "nowPlayingUpdated":
                now_playing = update.find("nowPlaying")
                if now_playing is not None:
                    _update_listener_cache(
                        speaker_name,
                        status.parse_now_playing_element(now_playing),
                        stop_event,
                        ws,
                    )
            elif update.tag == "volumeUpdated":
                # volumeUpdated is often empty; the HTTP read can outlive this
                # connection, so check its generation again before publishing.
                volume = status.get_volume(ip)
                if volume is not None:
                    _update_listener_cache(speaker_name, {"volume": volume}, stop_event, ws)
    except (ET.ParseError, ValueError) as exc:
        logger.warning("WebSocket message processing failed for %s: %s", speaker_name, exc)


def _disconnect_listener(
    name: str, stop_event: threading.Event, ws: websocket.WebSocketApp
) -> bool:
    with _listener_lock:
        if _is_current_listener(name, stop_event, ws):
            _listener_sockets.pop(name, None)
            invalidate_cache(name)
            return True
    return False


def _on_error(
    ws: websocket.WebSocketApp, error: Exception, speaker_name: str,
    stop_event: threading.Event,
) -> None:
    if _disconnect_listener(speaker_name, stop_event, ws):
        # Callback errors do not always terminate run_forever themselves. Close
        # this connection so the loop can reconnect instead of ignoring it forever.
        _close_sockets([ws])
    logger.warning("WebSocket error for %s: %s", speaker_name, error)


def _on_close(
    ws: websocket.WebSocketApp, close_status_code: int | None, close_msg: str | None,
    speaker_name: str, stop_event: threading.Event,
) -> None:
    _disconnect_listener(speaker_name, stop_event, ws)
    logger.info(
        "WebSocket closed for %s (code=%s, message=%s).",
        speaker_name, close_status_code, close_msg,
    )


def listen_to_speaker(name: str, ip: str, stop_event: threading.Event) -> None:
    """Maintain a WebSocket connection, re-priming on every successful connection."""
    while not stop_event.is_set():
        ws = None
        retry_delay = WEBSOCKET_CLOSE_RETRY_DELAY_SECONDS
        try:
            ws = websocket.WebSocketApp(
                f"ws://{ip}:{SOUNDTOUCH_WEBSOCKET_PORT}",
                subprotocols=["gabbo"],
                on_open=lambda socket: _on_open(socket, name, ip, stop_event),
                on_message=lambda socket, msg: _on_message(socket, msg, name, ip, stop_event),
                on_error=lambda socket, err: _on_error(socket, err, name, stop_event),
                on_close=lambda socket, code, msg: _on_close(socket, code, msg, name, stop_event),
            )
            with _listener_lock:
                if stop_event.is_set() or _listener_stop_events.get(name) is not stop_event:
                    break
                _listener_sockets[name] = ws
            logger.info("Connecting WebSocket listener for '%s'.", name)
            ws.run_forever(
                ping_interval=WEBSOCKET_PING_INTERVAL_SECONDS,
                ping_timeout=WEBSOCKET_PING_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            retry_delay = WEBSOCKET_LOOP_RETRY_DELAY_SECONDS
            logger.warning(
                "WebSocket listener loop error for %s: %s. Retrying in %ss.",
                name, type(exc).__name__, retry_delay,
            )
        finally:
            if ws is not None:
                _disconnect_listener(name, stop_event, ws)
                _close_sockets([ws])
        if stop_event.wait(retry_delay):
            break


def _close_sockets(sockets: list[websocket.WebSocketApp]) -> None:
    for ws in sockets:
        try:
            ws.close()
        except Exception as exc:
            logger.debug("Ignoring socket close error during shutdown: %s", exc)


def start_ws_listeners(devices: list[dict[str, str]]) -> None:
    """Reconcile listeners with discovery, including changed addresses and removals."""
    # Names may collide: never pick the last advertised speaker silently.
    counts: dict[str, int] = {}
    for device in devices:
        counts[device.get('name', '')] = counts.get(device.get('name', ''), 0) + 1
    desired = {device['name']: (device['ip'], device.get('device_id', ''))
               for device in devices if device.get('name') and device.get('ip')
               and counts[device['name']] == 1}
    sockets_to_close = []
    threads_to_start = []
    with _listener_lock:
        for name in list(_listener_threads):
            if (name in desired
                    and (_listener_addresses.get(name), _listener_identities.get(name, ''))
                    == desired[name]):
                continue
            _listener_stop_events.pop(name).set()
            _listener_threads.pop(name, None)
            _listener_addresses.pop(name, None)
            _listener_identities.pop(name, None)
            ws = _listener_sockets.pop(name, None)
            if ws is not None:
                sockets_to_close.append(ws)
            invalidate_cache(name)
        for name, (ip, identity) in desired.items():
            if name in _listener_threads:
                continue
            invalidate_cache(name)
            stop_event = threading.Event()
            thread = threading.Thread(
                target=listen_to_speaker, args=(name, ip, stop_event), daemon=True
            )
            _listener_stop_events[name] = stop_event
            _listener_threads[name] = thread
            _listener_addresses[name] = ip
            _listener_identities[name] = identity
            threads_to_start.append(thread)
    _close_sockets(sockets_to_close)
    for thread in threads_to_start:
        thread.start()


def stop_ws_listeners(timeout: float = 3.0) -> None:
    """Stop all speaker listeners and invalidate their observations immediately."""
    with _listener_lock:
        threads = list(_listener_threads.values())
        sockets = list(_listener_sockets.values())
        for stop_event in _listener_stop_events.values():
            stop_event.set()
        _listener_stop_events.clear()
        _listener_threads.clear()
        _listener_sockets.clear()
        _listener_addresses.clear()
        _listener_identities.clear()
        with _state_lock:
            _speaker_state.clear()
            _playback_observed_at.clear()
            _volume_observed_at.clear()
    _close_sockets(sockets)
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=timeout)
