"""Speaker-native browsing and preset XML. No NAS mounts, audio proxy or accounts."""
import copy
import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Any

from requests.exceptions import RequestException
from app.core import status
from app.core.constants import SOUNDTOUCH_HTTP_PORT
from app.core.http_client import command_session, parse_speaker_xml, read_response_body

PAGE_SIZE = 50
IDENTITY_KEYS = ('source', 'sourceAccount', 'location')


def identity(item: dict[str, Any]) -> dict[str, str]:
    return {key: item[key] for key in IDENTITY_KEYS if item.get(key)}


def same_content(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return left is right
    if identity(left) != identity(right):
        return False
    first, second = left.get('type'), right.get('type')
    return first == second or (left.get('source') == 'STORED_MUSIC' and (not first or not second))


def parse_content(element: ET.Element | None) -> dict[str, Any] | None:
    if element is None or not element.get('source') or not element.get('location'):
        return None
    if element.get('source') == 'INVALID_SOURCE':
        return None
    result: dict[str, Any] = {key: element.get(key) for key in (*IDENTITY_KEYS, 'type') if element.get(key)}
    result['name'] = (element.findtext('itemName') or 'Unnamed item')[:160]
    result['presetable'] = element.get('isPresetable') == 'true'
    return result


def content_xml(item: dict[str, Any]) -> ET.Element:
    attrs = {key: str(item[key]) for key in (*IDENTITY_KEYS, 'type') if item.get(key)}
    attrs['isPresetable'] = 'true' if item.get('presetable') else 'false'
    element = ET.Element('ContentItem', attrs)
    ET.SubElement(element, 'itemName').text = item['name']
    return element


def read_presets(ip: str) -> dict[int, dict[str, Any] | None]:
    root = status._get_xml(ip, 'presets', 'presets')
    if root is None:
        raise ValueError('Preset readback unavailable. No assignment was changed.')
    result: dict[int, dict[str, Any] | None] = {slot: None for slot in range(1, 7)}
    seen: set[int] = set()
    for preset in root.findall('preset'):
        try:
            slot = int(preset.get('id', '0'))
        except ValueError:
            raise ValueError('Speaker returned an invalid preset map.') from None
        element = preset.find('ContentItem')
        content = parse_content(element)
        if element is not None and element.get('source') not in (None, '', 'INVALID_SOURCE') and content is None:
            raise ValueError('Speaker returned an incomplete preset identity.')
        # Known empty firmware placeholders use id=0.
        if slot == 0 and content is None:
            continue
        if slot not in result or slot in seen:
            raise ValueError('Speaker returned an ambiguous preset map.')
        seen.add(slot)
        result[slot] = content
    return result


def source_id(account: str) -> str:
    return hashlib.sha256(account.encode()).hexdigest()[:32]


def read_sources(ip: str) -> list[dict[str, Any]]:
    root = status._get_xml(ip, 'sources', 'sources')
    if root is None:
        raise ValueError('Speaker sources unavailable. Check the speaker and music server.')
    result = []
    for item in root.findall('sourceItem'):
        source, account = item.get('source', ''), item.get('sourceAccount', '')
        if source not in {'STORED_MUSIC', 'LOCAL_INTERNET_RADIO'}:
            continue
        result.append({'id': source_id(source + ':' + account), 'source': source,
                       'account': account, 'name': (item.text or source).strip()[:160],
                       'ready': item.get('status') == 'READY'})
    return result


def navigate(ip: str, source: dict[str, Any], container: dict[str, Any] | None,
             start: int) -> dict[str, Any]:
    root = ET.Element('navigate', {'source': 'STORED_MUSIC', 'sourceAccount': source['account']})
    ET.SubElement(root, 'startItem').text = str(start)
    ET.SubElement(root, 'numItems').text = str(PAGE_SIZE)
    if container:
        entry = ET.SubElement(root, 'item', {'Playable': '1'})
        ET.SubElement(entry, 'name').text = container['name']
        ET.SubElement(entry, 'type').text = 'dir'
        entry.append(content_xml(container))
    deadline = time.monotonic() + 5.0
    try:
        response = command_session.post(
            f'http://{ip}:{SOUNDTOUCH_HTTP_PORT}/navigate',
            data=ET.tostring(root, encoding='utf-8'),
            headers={'Content-Type': 'application/xml', 'Accept-Encoding': 'identity'},
            timeout=5.0, allow_redirects=False, stream=True)
        try:
            body = read_response_body(response, deadline=deadline)
        finally:
            response.close()
        parsed = parse_speaker_xml(body, 'navigateResponse')
        if time.monotonic() >= deadline:
            raise ValueError('Browse deadline exceeded')
        if parsed.get('source') != 'STORED_MUSIC' or parsed.get('sourceAccount') != source['account']:
            raise ValueError('Browse source did not match')
        total = int(parsed.findtext('totalItems') or '')
        if not 0 <= total <= 1000000:
            raise ValueError('Invalid item count')
        items = []
        entries = parsed.findall('items/item')
        if len(entries) > PAGE_SIZE:
            raise ValueError('Browse page exceeded requested size')
        for entry in entries:
            # Deliberately not .//ContentItem: mediaItemContainer is the parent.
            content = parse_content(entry.find('ContentItem'))
            if not content or content.get('source') != 'STORED_MUSIC':
                continue
            if content.get('sourceAccount') != source['account']:
                continue
            content = copy.deepcopy(content)
            content['name'] = (entry.findtext('name') or content['name'])[:160]
            content['type'] = entry.findtext('type') or content.get('type', '')
            content['is_dir'] = content['type'] == 'dir'
            content['playable'] = entry.get('Playable') == '1'
            items.append(content)
        next_start = start + len(entries) if entries and start + len(entries) <= total else None
        return {'items': items, 'total': total, 'start': start, 'next_start': next_start}
    except (RequestException, ET.ParseError, ValueError, TypeError):
        raise ValueError('Cannot browse this music source. No playback or preset was changed.') from None


def store_preset(ip: str, slot: int, item: dict[str, Any]) -> bool:
    now = str(int(time.time()))
    root = ET.Element('preset', {'id': str(slot), 'createdOn': now, 'updatedOn': now})
    root.append(content_xml(item))
    deadline = time.monotonic() + 5.0
    try:
        response = command_session.post(
            f'http://{ip}:{SOUNDTOUCH_HTTP_PORT}/storePreset',
            data=ET.tostring(root, encoding='utf-8'),
            headers={'Content-Type': 'application/xml', 'Accept-Encoding': 'identity'},
            timeout=5.0, allow_redirects=False, stream=True)
        try:
            body = read_response_body(response, deadline=deadline)
        finally:
            response.close()
        if not body.strip():
            return time.monotonic() < deadline
        # Firmware may return the updated preset map instead of /storePreset status.
        try:
            parsed = parse_speaker_xml(body, 'presets')
        except ValueError:
            parsed = parse_speaker_xml(body, 'status')
            if list(parsed) or (parsed.text or '').strip() not in {'/storePreset', 'OK', 'SUCCESS'}:
                return False
        return time.monotonic() < deadline
    except (RequestException, ET.ParseError, ValueError):
        return False
