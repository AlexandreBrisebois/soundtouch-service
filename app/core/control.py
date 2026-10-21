import logging
import math
import time
import xml.etree.ElementTree as ET

from requests.exceptions import RequestException

from app.core.constants import HTTP_POST_TIMEOUT_SECONDS, SOUNDTOUCH_HTTP_PORT
from app.core.http_client import command_session as session
from app.core.http_client import parse_speaker_xml, read_response_body


logger = logging.getLogger(__name__)


def _post_command(
    ip: str, endpoint: str, payload: str, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS
) -> bool:
    """Acknowledge one command attempt, never proof that playback has started."""
    if not math.isfinite(timeout) or timeout <= 0:
        return False
    deadline = time.monotonic() + timeout
    url = f"http://{ip}:{SOUNDTOUCH_HTTP_PORT}/{endpoint}"
    try:
        response = session.post(
            url,
            data=payload,
            headers={"Content-Type": "application/xml", "Accept-Encoding": "identity"},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            body = read_response_body(response, deadline=deadline)
        finally:
            response.close()
        # An empty 2xx (including 204) is accepted for compatibility with a bare
        # HTTP acknowledgment rather than <status>/endpoint</status>. This does
        # not prove execution; callers still need fresh state evidence.
        if not body.strip():
            return True
        root = parse_speaker_xml(body, "status")
        if time.monotonic() >= deadline:
            return False
        if list(root) or (root.text or "").strip() not in {f"/{endpoint}", "OK", "SUCCESS"}:
            raise ValueError("Unrecognized command acknowledgment")
        return True
    except (RequestException, ET.ParseError, ValueError) as exc:
        # Requests exceptions and response bodies can contain URLs, accounts, or
        # tokens. Log only the operation and failure class, never their contents.
        logger.warning("SoundTouch %s command failed (%s)", endpoint, type(exc).__name__)
        return False


def send_key(ip: str, key: str, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS) -> bool:
    """Send one simulated press/release pair; never retry an ambiguous POST."""
    if not isinstance(key, str) or not key.strip() or not math.isfinite(timeout) or timeout <= 0:
        return False
    deadline = time.monotonic() + timeout
    for state in ("press", "release"):
        element = ET.Element("key", {"state": state, "sender": "Gabbo"})
        element.text = key
        payload = '<?xml version="1.0" ?>' + ET.tostring(element, encoding="unicode")
        if not _post_command(ip, "key", payload, timeout=deadline - time.monotonic()):
            return False
    return True


def set_volume(ip: str, volume: int, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS) -> bool:
    """Set a 0-100 volume, returning checked command acknowledgment only."""
    if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
        return False
    payload = f'<?xml version="1.0" ?><volume>{volume}</volume>'
    return _post_command(ip, "volume", payload, timeout=timeout)


def power_action(ip: str, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS) -> bool:
    """Toggle power only after the caller establishes fresh, compatible state."""
    return send_key(ip, "POWER", timeout=timeout)


def stop_action(ip: str, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS) -> bool:
    return send_key(ip, "STOP", timeout=timeout)


def play_preset(
    ip: str, preset_num: int = 1, *, timeout: float = HTTP_POST_TIMEOUT_SECONDS
) -> bool:
    if isinstance(preset_num, bool) or not isinstance(preset_num, int) or not 1 <= preset_num <= 6:
        return False
    return send_key(ip, f"PRESET_{preset_num}", timeout=timeout)
