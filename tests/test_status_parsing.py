"""Fresh SoundTouch identity reads with fake HTTP only."""

import xml.etree.ElementTree as ET

import pytest
from requests import Response
from requests.exceptions import Timeout

from app.core import status


NAS_CONTENT = (
    '<ContentItem source="STORED_MUSIC" sourceAccount="local-library" '
    'location="album:10589" type="album" isPresetable="true">'
    '<itemName>Morning music</itemName></ContentItem>'
)


def response(body, status_code=200):
    result = Response()
    result.status_code = status_code
    result._content = body.encode()
    result._content_consumed = True
    return result


class FakeTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def install_transport(monkeypatch, *results):
    fake = FakeTransport(*results)
    monkeypatch.setattr(status, "session", fake)
    return fake


@pytest.fixture(autouse=True)
def fixed_observation_time(monkeypatch):
    monkeypatch.setattr(status.time, "time", lambda: 1234567890.0)
    monkeypatch.setattr(status.time, "monotonic", lambda: 456.0)


def test_parse_now_playing_element_preserves_aux_display_fields():
    root = ET.fromstring(
        '<nowPlaying deviceID="AABBCC" source="AUX"><playStatus>PLAY_STATE</playStatus>'
        '<track>Console</track><artist>Living Room</artist><album>Input</album></nowPlaying>'
    )
    assert status.parse_now_playing_element(root) == {
        "status": "Playing", "source": "AUX", "track": "Console", "artist": "Living Room",
        "album": "Input", "raw_state": "PLAY_STATE", "device_id": "AABBCC",
        "source_type": "AUX", "content_identity": None, "observed_at": 1234567890.0,
        "observed_monotonic": 456.0,
    }


def test_parse_now_playing_prefers_radio_item_name_without_losing_raw_source():
    parsed = status.parse_now_playing_xml(
        '<nowPlaying source="INTERNET_RADIO"><playStatus>BUFFERING_STATE</playStatus>'
        '<ContentItem source="INTERNET_RADIO" location="station:12">'
        '<itemName>Morning Jazz</itemName></ContentItem></nowPlaying>'
    )
    assert parsed["status"] == "Buffering"
    assert parsed["source"] == "Morning Jazz"
    assert parsed["source_type"] == "INTERNET_RADIO"
    assert parsed["content_identity"] == {"source": "INTERNET_RADIO", "location": "station:12"}


def test_parse_now_playing_standby_keeps_identity_and_timestamps():
    parsed = status.parse_now_playing_xml('<nowPlaying deviceID="AABBCC" source="STANDBY" />')
    assert parsed == {
        "status": "Standby", "source": "STANDBY", "device_id": "AABBCC",
        "source_type": "STANDBY", "content_identity": None, "observed_at": 1234567890.0,
        "observed_monotonic": 456.0,
    }


def test_unknown_state_keeps_legacy_human_readable_value():
    parsed = status.parse_now_playing_xml(
        '<nowPlaying source="SPOTIFY"><playStatus>PAUSED_STATE</playStatus></nowPlaying>'
    )
    assert parsed["status"] == "Paused"
    assert parsed["source"] == "Spotify"
    assert parsed["raw_state"] == "PAUSED_STATE"
    assert parsed["track"] is None


def test_nas_identity_retains_typed_content_attributes_without_titles():
    parsed = status.parse_now_playing_xml(
        '<nowPlaying deviceID="001122AABBCC" source="STORED_MUSIC">'
        f'<playStatus>PLAY_STATE</playStatus>{NAS_CONTENT}</nowPlaying>'
    )
    assert parsed["device_id"] == "001122AABBCC"
    assert parsed["source_type"] == "STORED_MUSIC"
    assert parsed["content_identity"] == {
        "source": "STORED_MUSIC", "sourceAccount": "local-library",
        "location": "album:10589", "type": "album",
    }


@pytest.mark.parametrize("xml", ["<errors/>", "<volume/>", "<wrapper><nowPlaying/></wrapper>"])
def test_parser_rejects_wrong_root(xml):
    with pytest.raises(ValueError):
        status.parse_now_playing_xml(xml)


def test_empty_content_item_is_unknown_not_a_fabricated_identity():
    parsed = status.parse_now_playing_xml(
        '<nowPlaying source="STORED_MUSIC"><ContentItem><itemName>Same title</itemName>'
        '</ContentItem></nowPlaying>'
    )
    assert parsed["content_identity"] is None


@pytest.mark.parametrize(
    "result",
    [response("<nowPlaying source='AUX'/>", 500), response("<nowPlaying/>", 302),
     response("<error>secret-account</error>"), response("not xml"),
     Timeout("http://private-user:private-password@host"),
     response('<!DOCTYPE a [<!ENTITY x "secret">]><nowPlaying source="&x;"/>')],
)
def test_get_now_playing_fails_closed_without_sensitive_errors(monkeypatch, result, caplog):
    fake = install_transport(monkeypatch, result)
    parsed = status.get_now_playing("192.0.2.1")
    assert parsed["status"] == "OFFLINE"
    assert "observed_at" not in parsed
    assert "secret" not in str(parsed) + caplog.text
    assert "private" not in str(parsed) + caplog.text
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["allow_redirects"] is False


def test_get_now_playing_reads_fresh_each_time(monkeypatch):
    fake = install_transport(
        monkeypatch, response('<nowPlaying source="AUX"/>'),
        response('<nowPlaying source="STANDBY"/>'),
    )
    assert status.get_now_playing("192.0.2.1")["source_type"] == "AUX"
    assert status.get_now_playing("192.0.2.1")["source_type"] == "STANDBY"
    assert len(fake.calls) == 2


def test_get_preset_identity_reads_occupied_nas_slot_without_writing(monkeypatch):
    fake = install_transport(
        monkeypatch, response(f'<presets><preset id="1">{NAS_CONTENT}</preset></presets>')
    )
    assert status.get_preset_identity("192.0.2.1", 1) == {
        "source": "STORED_MUSIC", "sourceAccount": "local-library",
        "location": "album:10589", "type": "album",
    }
    assert fake.calls[0][0].endswith("/presets")
    assert len(fake.calls) == 1


@pytest.mark.parametrize("body", [
    '<presets><preset id="2"><ContentItem source="STORED_MUSIC"/></preset></presets>',
    '<presets><preset id="1"/></presets>',
    '<presets><preset id="1"><ContentItem/></preset></presets>',
    '<nowPlaying/>', '<errors><error>private</error></errors>',
])
def test_missing_or_invalid_preset_is_unknown(monkeypatch, body):
    install_transport(monkeypatch, response(body))
    assert status.get_preset_identity("192.0.2.1", 1) is None


@pytest.mark.parametrize("preset", [0, 7, True, "1"])
def test_invalid_preset_never_reads(monkeypatch, preset):
    fake = install_transport(monkeypatch)
    assert status.get_preset_identity("192.0.2.1", preset) is None
    assert fake.calls == []


def test_info_reads_stable_device_id(monkeypatch):
    install_transport(monkeypatch, response('<info deviceID="001122AABBCC"><name>Kitchen</name></info>'))
    assert status.get_device_id("192.0.2.1") == "001122AABBCC"


@pytest.mark.parametrize("body", ['<info/>', '<nowPlaying deviceID="wrong"/>', '<info>'])
def test_invalid_info_has_no_device_id(monkeypatch, body):
    install_transport(monkeypatch, response(body))
    assert status.get_device_id("192.0.2.1") is None


@pytest.mark.parametrize("body, expected", [
    ('<volume><actualvolume>0</actualvolume></volume>', 0),
    ('<volume><actualvolume>100</actualvolume></volume>', 100),
    ('<volume><actualvolume>101</actualvolume></volume>', None),
    ('<volume><actualvolume>-1</actualvolume></volume>', None),
    ('<volume><actualvolume>nope</actualvolume></volume>', None),
    ('<volume/>', None), ('<error><actualvolume>10</actualvolume></error>', None),
])
def test_volume_validates_root_and_range(monkeypatch, body, expected):
    install_transport(monkeypatch, response(body))
    assert status.get_volume("192.0.2.1") == expected


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_xml_declarations_are_rejected_even_with_alternate_encoding(encoding):
    body = '<!DOCTYPE a [<!ENTITY x "secret">]><nowPlaying source="&x;"/>'
    with pytest.raises(ValueError):
        status.parse_now_playing_xml(body.encode(encoding))


def test_duplicate_preset_ids_are_not_trusted(monkeypatch):
    install_transport(monkeypatch, response(
        f'<presets><preset id="1">{NAS_CONTENT}</preset>'
        f'<preset id="1">{NAS_CONTENT}</preset></presets>'
    ))
    assert status.get_preset_identity("192.0.2.1", 1) is None


def test_bose_error_nested_in_now_playing_is_not_playback_evidence(monkeypatch):
    install_transport(monkeypatch, response(
        '<nowPlaying source="STORED_MUSIC"><playStatus>PLAY_STATE</playStatus>'
        '<error>private response content</error></nowPlaying>'
    ))
    assert status.get_now_playing("192.0.2.1")["status"] == "OFFLINE"


def test_read_uses_caller_timeout_budget(monkeypatch):
    fake = install_transport(monkeypatch, response('<nowPlaying source="AUX"/>'))
    assert status.get_now_playing("192.0.2.1", timeout=0.5)["source_type"] == "AUX"
    assert fake.calls[0][1]["timeout"] == 0.5


def test_status_stream_past_deadline_is_not_fresh_evidence(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(status.time, "monotonic", lambda: now[0])
    result = response('<nowPlaying source="AUX"/>')

    def slow_body(chunk_size):
        now[0] += 1.0
        yield b'<nowPlaying source="AUX"/>'

    monkeypatch.setattr(result, "iter_content", slow_body)
    fake = install_transport(monkeypatch, result)
    assert status.get_now_playing("192.0.2.1", timeout=0.5)["status"] == "OFFLINE"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_exhausted_or_invalid_read_budget_never_reads(monkeypatch, timeout):
    fake = install_transport(monkeypatch)
    assert status.get_now_playing("192.0.2.1", timeout=timeout)["status"] == "OFFLINE"
    assert status.get_volume("192.0.2.1", timeout=timeout) is None
    assert status.get_device_id("192.0.2.1", timeout=timeout) is None
    assert status.get_preset_identity("192.0.2.1", 1, timeout=timeout) is None
    assert fake.calls == []
