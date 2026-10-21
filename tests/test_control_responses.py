"""Offline transport contract tests; never send requests to a real speaker."""

import pytest
from requests import Response
from requests.exceptions import ConnectionError, Timeout

from app.core import control, http_client


def response(body="<status>/volume</status>", status_code=200):
    result = Response()
    result.status_code = status_code
    result._content = body.encode()
    result._content_consumed = True
    return result


class FakeTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def install_transport(monkeypatch, *results):
    fake = FakeTransport(*results)
    monkeypatch.setattr(control, "session", fake)
    return fake


@pytest.mark.parametrize("code", [200, 201, 202, 204])
def test_empty_success_is_transport_ack_only(monkeypatch, code):
    fake = install_transport(monkeypatch, response("", code))
    assert control.set_volume("192.0.2.1", 12) is True
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["timeout"] > 0
    assert fake.calls[0][1]["allow_redirects"] is False
    assert fake.calls[0][1]["stream"] is True


def test_valid_key_ack_requires_press_and_release(monkeypatch):
    fake = install_transport(
        monkeypatch, response("<status>/key</status>"), response("<status>/key</status>")
    )
    assert control.send_key("192.0.2.1", "PLAY") is True
    assert len(fake.calls) == 2
    assert 'state="press"' in fake.calls[0][1]["data"]
    assert 'state="release"' in fake.calls[1][1]["data"]


@pytest.mark.parametrize(
    "result",
    [
        response("<status>/volume</status>", 500),
        response("<status>/volume</status>", 302),
        response('<errors deviceID="private"><error>secret URL</error></errors>'),
        response('<status><error code="1000">secret account</error></status>'),
        response("<status>ERROR</status>"),
        response("<html>Login</html>"),
        response("not xml"),
        response("<status>/key</status>"),
        response("<status>"),
        response("<status>" + "x" * 65536 + "</status>"),
        Timeout("secret URL or account"),
        ConnectionError("private URL"),
    ],
)
def test_command_rejects_ambiguous_and_negative_ack_without_retry(monkeypatch, result, caplog):
    fake = install_transport(monkeypatch, result)
    assert control.set_volume("192.0.2.1", 12) is False
    assert len(fake.calls) == 1
    assert "secret" not in caplog.text
    assert "private" not in caplog.text


def test_failed_press_does_not_issue_another_command(monkeypatch):
    fake = install_transport(monkeypatch, Timeout("possibly sent"))
    assert control.send_key("192.0.2.1", "POWER") is False
    assert len(fake.calls) == 1


def test_failed_release_does_not_repeat_press(monkeypatch):
    fake = install_transport(monkeypatch, response("<status>/key</status>"), Timeout())
    assert control.send_key("192.0.2.1", "POWER") is False
    assert len(fake.calls) == 2


def test_xml_key_content_is_escaped(monkeypatch):
    fake = install_transport(
        monkeypatch, response("<status>/key</status>"), response("<status>/key</status>")
    )
    assert control.send_key("192.0.2.1", "A&B") is True
    assert "A&amp;B" in fake.calls[0][1]["data"]


@pytest.mark.parametrize("volume", [-1, 101, True, 2.5, "12"])
def test_invalid_volume_never_sends(monkeypatch, volume):
    fake = install_transport(monkeypatch)
    assert control.set_volume("192.0.2.1", volume) is False
    assert fake.calls == []


def test_command_session_has_no_hidden_connect_or_status_retries():
    for scheme in ("http://", "https://"):
        retries = http_client.command_session.get_adapter(scheme).max_retries
        assert retries.total == 0
        assert retries.connect == 0
        assert retries.read == 0
        assert retries.status == 0


def test_get_session_also_leaves_retry_budget_to_operation_loop():
    for scheme in ("http://", "https://"):
        retries = http_client.session.get_adapter(scheme).max_retries
        assert retries.total == 0
        assert retries.connect == 0
        assert retries.read == 0
        assert retries.status == 0


@pytest.mark.parametrize("preset", [0, 7, True, "1"])
def test_invalid_preset_command_never_sends(monkeypatch, preset):
    fake = install_transport(monkeypatch)
    assert control.play_preset("192.0.2.1", preset) is False
    assert fake.calls == []


def test_stream_is_closed_on_oversized_response(monkeypatch):
    class LargeResponse:
        status_code = 200
        closed = False
        chunks_read = 0

        def iter_content(self, chunk_size):
            for _ in range(70000):
                self.chunks_read += 1
                yield b"x" * chunk_size

        def close(self):
            self.closed = True

    result = LargeResponse()
    install_transport(monkeypatch, result)
    assert control.set_volume("192.0.2.1", 12) is False
    assert result.closed is True
    assert result.chunks_read == 65537


def test_key_pair_shares_one_timeout_budget(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(control.time, "monotonic", lambda: now[0])
    press = response("<status>/key</status>")

    def slow_press(chunk_size):
        now[0] += 1.0
        yield b"<status>/key</status>"

    monkeypatch.setattr(press, "iter_content", slow_press)
    fake = install_transport(monkeypatch, press, response("<status>/key</status>"))
    assert control.send_key("192.0.2.1", "PLAY", timeout=2.5) is True
    assert fake.calls[0][1]["timeout"] == 2.5
    assert fake.calls[1][1]["timeout"] == 1.5


def test_slow_stream_expires_without_repeating_or_releasing_key(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(control.time, "monotonic", lambda: now[0])
    press = response("<status>/key</status>")

    def slow_press(chunk_size):
        now[0] += 3.0
        yield b"<status>/key</status>"

    monkeypatch.setattr(press, "iter_content", slow_press)
    fake = install_transport(monkeypatch, press)
    assert control.send_key("192.0.2.1", "POWER", timeout=2.5) is False
    assert len(fake.calls) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_exhausted_or_invalid_command_budget_never_sends(monkeypatch, timeout):
    fake = install_transport(monkeypatch)
    assert control.set_volume("192.0.2.1", 12, timeout=timeout) is False
    assert control.send_key("192.0.2.1", "PLAY", timeout=timeout) is False
    assert fake.calls == []
