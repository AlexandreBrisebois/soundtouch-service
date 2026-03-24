import xml.etree.ElementTree as ET

from app.core import status


def test_parse_now_playing_element_handles_aux_source():
    root = ET.fromstring(
        """
        <nowPlaying source="AUX">
          <playStatus>PLAY_STATE</playStatus>
          <track>Console</track>
          <artist>Living Room</artist>
          <album>Input</album>
        </nowPlaying>
        """
    )

    assert status.parse_now_playing_element(root) == {
        "status": "Playing",
        "source": "AUX",
        "track": "Console",
        "artist": "Living Room",
        "album": "Input",
        "raw_state": "PLAY_STATE",
    }


def test_parse_now_playing_element_prefers_radio_item_name():
    root = ET.fromstring(
        """
        <nowPlaying source="INTERNET_RADIO">
          <playStatus>BUFFERING_STATE</playStatus>
          <track>Track</track>
          <artist>Artist</artist>
          <album>Album</album>
          <ContentItem>
            <itemName>Morning Jazz</itemName>
          </ContentItem>
        </nowPlaying>
        """
    )

    assert status.parse_now_playing_element(root) == {
        "status": "Buffering",
        "source": "Morning Jazz",
        "track": "Track",
        "artist": "Artist",
        "album": "Album",
        "raw_state": "BUFFERING_STATE",
    }


def test_parse_now_playing_element_handles_standby():
    root = ET.fromstring('<nowPlaying source="STANDBY" />')

    assert status.parse_now_playing_element(root) == {
        "status": "Standby",
        "source": "STANDBY",
    }


def test_parse_now_playing_xml_handles_unknown_state():
    parsed = status.parse_now_playing_xml(
        """
        <nowPlaying source="SPOTIFY">
          <playStatus>PAUSED_STATE</playStatus>
        </nowPlaying>
        """
    )

    assert parsed == {
        "status": "Paused",
        "source": "Spotify",
        "track": None,
        "artist": None,
        "album": None,
        "raw_state": "PAUSED_STATE",
    }