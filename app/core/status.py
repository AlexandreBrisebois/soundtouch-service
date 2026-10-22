import logging
import math
import time
from typing import Required, TypedDict
import xml.etree.ElementTree as ET

from requests.exceptions import RequestException

from app.core.constants import HTTP_GET_TIMEOUT_SECONDS, SOUNDTOUCH_HTTP_PORT
from app.core.http_client import (
    parse_speaker_xml,
    read_response_body,
    session,
    validate_speaker_element,
)


logger = logging.getLogger(__name__)
STATUS_MAP = {
    "PLAY_STATE": "Playing",
    "PAUSE_STATE": "Paused",
    "BUFFERING_STATE": "Buffering",
    "STOP_STATE": "Stopped",
}


class ContentIdentity(TypedDict, total=False):
    """Raw Bose identity attributes, internal only, never a display title.

    Missing attributes stay missing. In particular sourceAccount/location can
    contain private identifiers or credentials and must not enter logs/API output.
    """

    source: str
    sourceAccount: str
    location: str
    type: str


class PlaybackState(TypedDict, total=False):
    status: Required[str]
    source: str
    track: str | None
    artist: str | None
    album: str | None
    raw_state: str
    device_id: str | None
    source_type: str
    content_identity: ContentIdentity | None
    observed_at: float
    observed_monotonic: float
    error: str


def _content_identity(element: ET.Element | None) -> ContentIdentity | None:
    if element is None:
        return None
    identity: ContentIdentity = {}
    # Explicit keys keep this a typed identity, not a copy of arbitrary XML data.
    if value := element.get("source"):
        identity["source"] = value
    if value := element.get("sourceAccount"):
        identity["sourceAccount"] = value
    if value := element.get("location"):
        identity["location"] = value
    if value := element.get("type"):
        identity["type"] = value
    return identity or None


def parse_now_playing_element(root: ET.Element) -> PlaybackState:
    """Preserve display fields while retaining evidence for operation verification.

    Timestamps describe when this response was observed, not a device timestamp.
    Cached/WebSocket states must not substitute for a fresh operation HTTP read.
    """
    validate_speaker_element(root, "nowPlaying")
    source = root.get("source") or "UNKNOWN"
    content_item = root.find("ContentItem")
    result: PlaybackState = {
        "status": "Standby" if source == "STANDBY" else "Unknown",
        "source": source,
        "device_id": root.get("deviceID") or None,
        "source_type": source,
        "content_identity": _content_identity(content_item),
        "observed_at": time.time(),
        "observed_monotonic": time.monotonic(),
    }
    if source == "STANDBY":
        return result

    play_state = root.findtext("playStatus") or "UNKNOWN"
    human_status = STATUS_MAP.get(play_state, play_state.replace("_STATE", "").capitalize())
    source_display = source.replace("_", " ").title()
    if source == "AUX":
        source_display = "AUX"
    elif source == "INTERNET_RADIO" and content_item is not None:
        source_display = content_item.findtext("itemName") or source_display

    result.update({
        "status": human_status,
        "source": source_display,
        "track": root.findtext("track"),
        "artist": root.findtext("artist"),
        "album": root.findtext("album"),
        "raw_state": play_state,
    })
    return result


def parse_now_playing_xml(xml_text: str | bytes) -> PlaybackState:
    return parse_now_playing_element(parse_speaker_xml(xml_text, "nowPlaying"))


def _get_xml(
    ip: str, endpoint: str, expected_root: str, *, timeout: float = HTTP_GET_TIMEOUT_SECONDS
) -> ET.Element | None:
    """One fresh, bounded read; no cache, redirects, or hidden transport retries."""
    if not math.isfinite(timeout) or timeout <= 0:
        return None
    deadline = time.monotonic() + timeout
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/{endpoint}"
    try:
        response = session.get(
            url, timeout=timeout, allow_redirects=False, stream=True,
            headers={"Accept-Encoding": "identity"},
        )
        try:
            body = read_response_body(response, deadline=deadline)
        finally:
            response.close()
        root = parse_speaker_xml(body, expected_root)
        return root if time.monotonic() < deadline else None
    except (RequestException, ET.ParseError, ValueError) as exc:
        logger.warning("SoundTouch %s read failed (%s)", endpoint, type(exc).__name__)
        return None


def get_now_playing(ip: str, *, timeout: float = HTTP_GET_TIMEOUT_SECONDS) -> PlaybackState:
    """Fetch fresh playback evidence, or a redacted offline state without freshness."""
    root = _get_xml(ip, "now_playing", "nowPlaying", timeout=timeout)
    if root is None:
        return {"status": "OFFLINE", "error": "Speaker status unavailable"}
    return parse_now_playing_element(root)


def get_volume(ip: str, *, timeout: float = HTTP_GET_TIMEOUT_SECONDS) -> int | None:
    """Read actual 0-100 volume, never treating a malformed value as confirmation."""
    root = _get_xml(ip, "volume", "volume", timeout=timeout)
    if root is None:
        return None
    try:
        value = int(root.findtext("actualvolume") or "")
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def get_preset_identity(
    ip: str, preset_num: int, *, timeout: float = HTTP_GET_TIMEOUT_SECONDS
) -> ContentIdentity | None:
    """Read an existing occupied preset slot. This never creates/changes a preset."""
    if isinstance(preset_num, bool) or not isinstance(preset_num, int) or not 1 <= preset_num <= 6:
        return None
    root = _get_xml(ip, "presets", "presets", timeout=timeout)
    if root is None:
        return None
    matches = [preset for preset in root.findall("preset") if preset.get("id") == str(preset_num)]
    # Duplicate slot IDs are ambiguous and cannot identify the intended content.
    if len(matches) != 1:
        return None
    return _content_identity(matches[0].find("ContentItem"))


def get_device_id(ip: str, *, timeout: float = HTTP_GET_TIMEOUT_SECONDS) -> str | None:
    """Read the stable hardware identity rather than trusting an IP/name match."""
    root = _get_xml(ip, "info", "info", timeout=timeout)
    if root is None:
        return None
    return root.get("deviceID") or None


def get_device_info(ip: str) -> dict[str, str] | None:
    """Read identity and name for an explicitly configured LAN speaker."""
    root = _get_xml(ip, "info", "info")
    if root is None:
        return None
    device_id = (root.get("deviceID") or "").strip()
    name = (root.findtext("name") or "").strip()
    if not device_id or not name or len(name) > 256 or len(device_id) > 128:
        return None
    return {"name": name, "ip": ip, "device_id": device_id}
