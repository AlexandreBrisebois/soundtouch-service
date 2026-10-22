"""Supervised ten-second direct-radio diagnostic, never an automatic routine.

SetURI can immediately play at remembered volume. Explicit risk acceptance is
required by the API. No presets, registrations, groups or persistent data change.
Shares normal playback operation ownership and serialized writes. No retries.
"""
import time
import xml.etree.ElementTree as ET
from typing import Any

from requests.exceptions import RequestException
from app.core import control, playback, radio_stream, status
from app.core.http_client import command_session, parse_speaker_xml, read_response_body

SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
SERVICE = 'urn:schemas-upnp-org:service:AVTransport:1'
WARNING = ('Experimental direct test: audio may start at the speaker\'s remembered volume '
           'before Wisp can set volume 5. Keep physical Stop within reach. Wisp attempts '
           'to stop after 10 seconds; closing the app does not stop direct radio. '
           'Stop other controllers and schedules first. No speaker button is changed.')


class TestError(ValueError):
    """Safe outcome code; no stream URLs or raw device responses."""


def _text(root: ET.Element, name: str) -> str:
    return next((e.text or '' for e in root.iter() if e.tag.rsplit('}', 1)[-1] == name), '')


def _soap(ip: str, action: str, timeout: float, **args: str) -> ET.Element:
    envelope = ET.Element(f'{{{SOAP}}}Envelope')
    body = ET.SubElement(envelope, f'{{{SOAP}}}Body')
    call = ET.SubElement(body, f'{{{SERVICE}}}{action}')
    for key, value in {'InstanceID': '0', **args}.items():
        ET.SubElement(call, key).text = value
    response = command_session.post(
        f'http://{ip}:8091/AVTransport/Control', data=ET.tostring(envelope),
        headers={'Content-Type': 'text/xml; charset="utf-8"',
                 'SOAPAction': f'"{SERVICE}#{action}"', 'Accept-Encoding': 'identity'},
        timeout=timeout, allow_redirects=False, stream=True)
    try:
        raw = read_response_body(response, deadline=time.monotonic() + timeout)
    finally:
        response.close()
    root = parse_speaker_xml(raw, f'{{{SOAP}}}Envelope')
    if (root.find(f'{{{SOAP}}}Body/{{{SOAP}}}Fault') is not None
            or root.find(f'{{{SOAP}}}Body/{{{SERVICE}}}{action}Response') is None):
        raise TestError('direct_transport_response_unavailable')
    return root


def _capabilities(op: playback.Operation) -> None:
    timeout = playback._budget(op, 2)
    deadline = time.monotonic() + timeout
    response = command_session.get(
        f'http://{_address(op)}:8091/Xml/AVTransport3.xml', timeout=timeout,
        allow_redirects=False, stream=True, headers={'Accept-Encoding': 'identity'})
    try:
        raw = read_response_body(response, deadline=deadline)
    finally:
        response.close()
    root = parse_speaker_xml(raw, '{urn:schemas-upnp-org:service-1-0}scpd')
    actions = {_text(e, 'name') for e in root.iter() if e.tag.rsplit('}', 1)[-1] == 'action'}
    if not {'SetAVTransportURI', 'Stop', 'GetPositionInfo', 'GetTransportInfo'} <= actions:
        raise TestError('direct_transport_actions_unavailable')


def _address(op: playback.Operation) -> str:
    ip = playback._address(op)
    if ip is None:
        raise TestError('direct_identity_or_ownership_unavailable')
    return ip


def _get(op: playback.Operation, path: str, root: str) -> ET.Element:
    value = status._get_xml(_address(op), path, root, timeout=playback._budget(op, 2))
    if value is None or not playback.current(op):
        raise TestError('direct_observation_unavailable')
    return value


def _ungrouped(op: playback.Operation) -> None:
    zone = _get(op, 'getZone', 'zone')
    if zone.get('master') or zone.findall('.//member'):
        raise TestError('direct_grouped_or_zone_unknown')


def _volume(op: playback.Operation) -> int:
    root = _get(op, 'volume', 'volume')
    if root.get('deviceID') != op['device_id'] or _text(root, 'muteenabled') not in ('false', '0'):
        raise TestError('direct_volume_identity_or_mute_unknown')
    try:
        actual, target = int(_text(root, 'actualvolume')), int(_text(root, 'targetvolume'))
    except ValueError:
        raise TestError('direct_volume_unavailable') from None
    if actual != target or not 0 <= actual <= 100:
        raise TestError('direct_volume_unstable')
    return actual


def _playing(op: playback.Operation) -> ET.Element:
    value = _get(op, 'now_playing', 'nowPlaying')
    if value.get('deviceID') != op['device_id']:
        raise TestError('direct_playback_identity_unavailable')
    return value


def _idle(op: playback.Operation) -> bytes:
    value = _playing(op)
    source, state = value.get('source'), _text(value, 'playStatus')
    if not (source == 'STANDBY' or
            (source == 'INVALID_SOURCE' and state in ('', 'UNKNOWN')) or state == 'STOP_STATE'):
        raise TestError('direct_speaker_not_idle')
    # Compare relevant content only; unrelated metadata timestamps can change.
    content = value.find('ContentItem')
    return repr((source, state, ET.tostring(content) if content is not None else b'')).encode()


def _snapshot(op: playback.Operation) -> dict[str, Any]:
    _ungrouped(op)
    position = _soap(_address(op), 'GetPositionInfo', playback._budget(op, 2))
    transport = _soap(_address(op), 'GetTransportInfo', playback._budget(op, 2))
    playing = _playing(op)
    return {'uri': _text(position, 'TrackURI'), 'state': _text(transport, 'CurrentTransportState'),
            'transport_status': _text(transport, 'CurrentTransportStatus'),
            'source': playing.get('source'), 'bose_state': _text(playing, 'playStatus'),
            'volume': _volume(op)}


def _owned(snapshot: dict[str, Any], url: str, volume: int | None = None) -> bool:
    return (snapshot['uri'] == url and snapshot['source'] == 'UPNP'
            and snapshot['state'] == 'PLAYING' and snapshot['transport_status'] == 'OK'
            and snapshot['bose_state'] in ('BUFFERING_STATE', 'PLAY_STATE')
            and (volume is None or snapshot['volume'] == volume))


def _guard(op: playback.Operation, url: str, volume: int | None = None) -> dict[str, Any]:
    value = _snapshot(op)
    if not playback.current(op) or not _owned(value, url, volume):
        raise TestError('direct_source_or_volume_changed')
    return value


def _write(op: playback.Operation, callback: Any) -> None:
    if not playback._write(op, callback):
        raise TestError('direct_command_or_ownership_unconfirmed')


def run(op: playback.Operation, saved_url: str) -> None:
    """One bounded experiment. Any uncertainty stops further writes, never replays."""
    playback.finish(op, 'starting', 'checking_direct_radio')
    if playback._resolve(op) is None:
        return
    # Includes stream qualification, preflight and cleanup. Never extend on retries.
    op['deadline'] = time.monotonic() + 60
    selected = False
    op['outcome']['physical_stop_may_be_needed'] = False
    op['outcome']['warning'] = WARNING
    try:
        url = radio_stream.resolve(saved_url)
        initial, initial_volume = _idle(op), _volume(op)
        if initial_volume > 30:
            raise TestError('direct_initial_volume_too_high')
        _ungrouped(op)
        _capabilities(op)
        # Verify the actual transport route responds before any writes.
        _soap(_address(op), 'GetPositionInfo', playback._budget(op, 2))
        _soap(_address(op), 'GetTransportInfo', playback._budget(op, 2))

        def select(ip: str) -> bool:
            nonlocal selected
            _ungrouped(op)
            if _idle(op) != initial or _volume(op) != initial_volume or not playback.current(op):
                raise TestError('direct_preflight_changed')
            selected = True  # A failed request might still have reached the speaker.
            op['outcome']['physical_stop_may_be_needed'] = True
            _soap(_address(op), 'SetAVTransportURI', playback._budget(op, 2),
                  CurrentURI=url, CurrentURIMetaData='')
            return True
        _write(op, select)
        after = _guard(op, url)

        def lower(ip: str) -> bool:
            _guard(op, url, after['volume'])
            return playback.current(op) and control.set_volume(_address(op), 5, timeout=playback._budget(op, 2))
        _write(op, lower)
        _guard(op, url, 5)
        playback.finish(op, 'starting', 'direct_test_observing')
        until = time.monotonic() + 10
        while time.monotonic() < until:
            _guard(op, url, 5)
            if not playback.wait(op, .5):
                return

        def stop(ip: str) -> bool:
            _guard(op, url, 5)
            if not playback.current(op):
                return False
            _soap(_address(op), 'Stop', playback._budget(op, 2))
            return True
        _write(op, stop)
        end = _snapshot(op)
        if end['volume'] != 5 or end['transport_status'] != 'OK':
            raise TestError('direct_stop_readback_unknown')
        inactive = (end['source'] == 'INVALID_SOURCE' and end['bose_state'] == ''
                    and end['state'] == 'PAUSED_PLAYBACK')
        stopped = (end['uri'] == url and end['source'] == 'UPNP'
                   and end['state'] == 'STOPPED' and end['bose_state'] == 'STOP_STATE')
        if not inactive and not stopped:
            raise TestError('direct_stop_readback_unknown')
        op['outcome']['physical_stop_may_be_needed'] = False
        playback.finish(op, 'completed', 'direct_stop_acknowledged_source_inactive' if inactive
                        else 'direct_stopped_verified')
    except TestError as error:
        playback.finish(op, 'unknown', str(error))
    except (radio_stream.StreamError, RequestException, ET.ParseError, ValueError):
        # No cleanup on lost identity/ownership or uncertain commands; stale tests
        # must never stop a newer station or undo a person's volume/source change.
        playback.finish(op, 'unknown', 'direct_test_unconfirmed_physical_stop_may_be_needed'
                        if selected else 'direct_test_preflight_failed')
