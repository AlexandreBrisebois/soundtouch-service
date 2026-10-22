"""Bounded per-device MP3 relay leases. No audio before an explicit volume gate."""
import socket
import ipaddress
import threading
import uuid
from typing import Any, Callable, Iterator, TypedDict
from urllib.parse import urlsplit

from app.core import radio_stream, radio_hls

CHOM_LEGACY_AAC_URL = 'https://playerservices.streamtheworld.com/api/livestream-redirect/CHOMFMAAC.aac'
CHOM_MP3_URL = 'https://playerservices.streamtheworld.com/api/livestream-redirect/CHOMFM.mp3'

MAX_SESSIONS = 8
_lock = threading.RLock()
_sessions: dict[str, 'Session'] = {}
_consumers = threading.BoundedSemaphore(MAX_SESSIONS)


class RelayError(ValueError):
    pass


class Session(TypedDict):
    token: str
    device_id: str
    speaker_ip: str
    owner: str
    station_id: str
    schedule_name: str | None
    url: str
    gate: threading.Event
    connected: threading.Event
    closed: threading.Event
    consumed: bool
    upstream: Any
    downstream: Any


def stream_url(saved_url: str) -> str:
    # Known equivalent aliases, otherwise use an explicitly saved MP3 URL exactly.
    # The suffix is eligibility only: transport must validate actual MPEG frames.
    if saved_url == CHOM_LEGACY_AAC_URL:
        return CHOM_MP3_URL
    if saved_url == radio_hls.SAVED_URL:
        if not radio_hls.available():
            raise RelayError(radio_hls.unavailable_reason() or 'ICI converter support is unavailable.')
        return saved_url
    try:
        return radio_stream.candidate(saved_url)
    except ValueError:
        parsed = urlsplit(saved_url)
        if parsed.scheme in ('http', 'https') and parsed.path.lower().endswith('.mp3'):
            if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                    or parsed.fragment or parsed.port not in (None, 443 if parsed.scheme == 'https' else 80)):
                raise RelayError('MP3 relay requires a public URL without credentials on its standard HTTP/HTTPS port.') from None
            try:
                address = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                if parsed.hostname == 'localhost' or parsed.hostname.endswith(('.localhost', '.local', '.internal')):
                    raise RelayError('MP3 relay requires a public station URL.') from None
            else:
                if not address.is_global or address.is_multicast:
                    raise RelayError('MP3 relay requires a public station URL.')
            return saved_url
        raise RelayError('This station needs a supported MP3 stream or the ICI adapter; other HLS/AAC streams are not supported.') from None


def base_url(value: str | None) -> str:
    if not value:
        raise RelayError('Set WISP_BASE_URL to Wisp\'s HTTP address reachable by the speakers.')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise RelayError('Scheduled radio requires a speaker-reachable HTTP WISP_BASE_URL.')
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        invalid_host = parsed.hostname == 'localhost' or parsed.hostname.endswith('.localhost')
    else:
        invalid_host = address.is_loopback or address.is_unspecified or address.is_multicast
    if invalid_host:
        raise RelayError('WISP_BASE_URL must be a reachable host address, not localhost or a wildcard.')
    return value.rstrip('/')


def for_device(device_id: str | None) -> Session | None:
    with _lock:
        return next((s for s in _sessions.values() if s['device_id'] == device_id
                     and not s['closed'].is_set()), None)


def active(session: Session, owner: str | None = None) -> bool:
    with _lock:
        return (_sessions.get(session['token']) is session and not session['closed'].is_set()
                and (owner is None or session['owner'] == owner))


def transfer(session: Session, owner: str) -> bool:
    with _lock:
        if not active(session):
            return False
        session['owner'] = owner
        return True


def close(session: Session, reason: str = 'canceled') -> None:
    with _lock:
        if session['closed'].is_set():
            return
        session['closed'].set()
        session['gate'].set()
        _sessions.pop(session['token'], None)
        upstream, downstream, owner = session['upstream'], session['downstream'], session['owner']
    # Never hold the registry lock across socket cleanup or a playback callback.
    if upstream is not None:
        try:
            upstream.close()
        except Exception:
            pass  # Continue revoking the downstream even if transport cleanup failed.
    if downstream is not None:
        try:
            downstream.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            downstream.close()
        except OSError:
            pass
    if reason not in ('canceled', 'completed', 'shutdown'):
        from app.core import playback
        playback.relay_ended(owner, reason)


def cancel_owner(owner: str) -> None:
    with _lock:
        targets = [s for s in _sessions.values() if s['owner'] == owner]
    for session in targets:
        close(session)


def reset() -> None:
    with _lock:
        targets = list(_sessions.values())
    for session in targets:
        close(session, 'shutdown')


def prepare(device_id: str, ip: str, owner: str, station_id: str,
            schedule_name: str | None, saved_url: str, base: str) -> Session:
    from app.core.radio_upstream import open_station_stream
    upstream_url = stream_url(saved_url)
    base = base_url(base)
    with _lock:
        if len(_sessions) >= MAX_SESSIONS or for_device(device_id) is not None:
            raise RelayError('Radio relay is busy for this speaker.')
        token = uuid.uuid4().hex
        session: Session = {'token': token, 'device_id': device_id, 'speaker_ip': ip,
                            'owner': owner, 'station_id': station_id, 'schedule_name': schedule_name,
                            'url': f'{base}/api/radio-sessions/{token}/stream.mp3',
                            'gate': threading.Event(), 'connected': threading.Event(),
                            'closed': threading.Event(), 'consumed': False,
                            'upstream': None, 'downstream': None}
        _sessions[token] = session
    try:
        upstream = (radio_hls.open_ici_stream(upstream_url) if upstream_url == radio_hls.SAVED_URL
                    else open_station_stream(upstream_url))
        with _lock:
            accepted = active(session, owner)
            if accepted:
                session['upstream'] = upstream
        if not accepted:
            upstream.close()
            raise RelayError('Radio relay preparation was superseded.')
        return session
    except Exception:
        close(session)
        raise


def release(session: Session, owner: str) -> bool:
    with _lock:
        if not active(session, owner) or not session['connected'].is_set():
            return False
        session['gate'].set()
        return True


def consumer(token: str, peer: str | None, downstream: Any) -> tuple[Iterator[bytes], Callable[[], None]]:
    """One HTTP consumer, bound to the selected speaker IP. No arbitrary URLs."""
    with _lock:
        session = _sessions.get(token)
        if (session is None or not active(session) or session['speaker_ip'] != peer
                or session['consumed'] or downstream is None or not _consumers.acquire(False)):
            raise RelayError('Radio stream is unavailable.')
        try:
            downstream.settimeout(10)
        except OSError:
            _consumers.release()
            raise RelayError('Radio stream connection unavailable.') from None
        session['consumed'] = True
        session['downstream'] = downstream
    release_lock = threading.Lock()
    released = False
    def cleanup(reason: str = 'radio_client_disconnected') -> None:
        nonlocal released
        with release_lock:
            if released:
                return
            released = True
        try:
            close(session, reason)
        finally:
            _consumers.release()
    def generate() -> Iterator[bytes]:
        reason = 'radio_client_disconnected'
        try:
            session['connected'].set()
            yield b''  # Send HTTP headers without a single audio byte.
            if not session['gate'].wait(30) or not active(session):
                reason = 'radio_gate_not_released'
                return
            while active(session):
                data = session['upstream'].read_chunk()
                if not data:
                    reason = 'radio_upstream_ended'
                    return
                if not active(session):
                    return
                yield data
        except (OSError, ValueError, TimeoutError):
            reason = 'radio_upstream_unavailable'
        finally:
            cleanup(reason)
    return generate(), cleanup


def readiness(saved_url: str, ip: str) -> dict[str, Any]:
    """Read-only prerequisites, never a stream probe or hardware certification."""
    from app.core import favorites, library
    result: dict[str, Any] = {'available': False, 'mode': 'unavailable',
                              'requires_wisp_running': True, 'hardware_verified': False}
    try:
        base = favorites.radio_base()
        if not base:
            raise RelayError("Set WISP_BASE_URL to Wisp's HTTP address reachable by the speakers.")
        if ('/select' in favorites.capabilities(ip)
                and any(s['source'] == 'LOCAL_INTERNET_RADIO' and s['ready']
                        for s in library.read_sources(ip))):
            return {**result, 'available': True, 'mode': 'native',
                    'reason': 'Native radio source is ready; playback still needs testing.'}
        base_url(base)
        stream_url(saved_url)
        return {**result, 'available': True, 'mode': 'relay', 'volume_gated': True, 'requires_idle': True,
                'reason': 'Wisp will validate the audio stream before starting and gate audio until volume is verified. Playback still needs testing.'}
    except ValueError as exc:
        return {**result, 'reason': str(exc)}
