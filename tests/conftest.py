"""Unit tests must never contact speakers, discovery networks, or WebSockets."""
import http.client
import socket

import pytest
import requests

from app.core import discovery, speaker_cache


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail('Live network access is forbidden in the isolated test suite')
    monkeypatch.setattr(requests.Session, 'request', denied)
    monkeypatch.setattr(discovery, 'Zeroconf', denied)
    monkeypatch.setattr(speaker_cache.websocket, 'WebSocketApp', denied)

    monkeypatch.setattr(http.client.HTTPConnection, 'connect', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)
