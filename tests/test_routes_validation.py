from flask import Flask
import logging
import pytest

from app.api.routes import api_bp


def create_test_app():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app


def test_add_schedule_rejects_invalid_payload(monkeypatch):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    response = client.post(
        "/api/Living Room/schedules",
        json={
            "name": "",
            "days": ["monayyy"],
            "on_time": "25:00",
            "off_time": "07:61",
            "preset": 9,
            "volume": 101,
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert "errors" in body
    assert not queued


def test_add_schedule_normalizes_aux_payload(monkeypatch):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    response = client.post(
        "/api/Living Room/schedules",
        json={
            "name": "Weekend",
            "days": ["Saturday", "Sunday"],
            "on_time": "09:00",
            "off_time": "10:00",
            "source": "aux",
            "volume": 15,
            "fade_in_duration": 120,
            "fade_out_duration": 30,
        },
    )

    assert response.status_code == 202
    assert queued[0]["data"] == {
        "name": "Weekend",
        "days": ["saturday", "sunday"],
        "on_time": "09:00",
        "off_time": "10:00",
        "source": "AUX",
        "preset": None,
        "volume": 15,
        "fade_in_duration": 120,
        "fade_out_duration": 30,
        "paused": False,
    }
    assert queued[0]["previous_name"] is None


def test_add_schedule_normalizes_preset_payload(monkeypatch):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    response = client.post(
        "/api/Living Room/schedules",
        json={
            "name": "Morning",
            "days": ["Monday", "Tuesday"],
            "on_time": "06:15",
            "off_time": "07:15",
            "preset": 6,
            "source": None,
            "volume": 18,
        },
    )

    assert response.status_code == 202
    assert queued[0]["data"] == {
        "name": "Morning",
        "days": ["monday", "tuesday"],
        "on_time": "06:15",
        "off_time": "07:15",
        "source": None,
        "preset": 6,
        "volume": 18,
        "fade_in_duration": 300,
        "fade_out_duration": 60,
        "paused": False,
    }


def test_add_schedule_preserves_previous_name_for_atomic_rename(monkeypatch):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    response = client.post(
        "/api/Living Room/schedules",
        json={
            "name": "Weekday Morning",
            "previous_name": "Morning Routine",
            "days": ["monday"],
            "on_time": "06:15",
            "off_time": "07:00",
            "preset": 1,
            "volume": 10,
        },
    )

    assert response.status_code == 202
    assert queued[0]["previous_name"] == "Morning Routine"


def test_preset_endpoint_rejects_invalid_preset(monkeypatch):
    app = create_test_app()
    client = app.test_client()

    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.168.1.9")

    response = client.post("/api/Living Room/preset/7")

    assert response.status_code == 400


def test_volume_endpoint_rejects_invalid_volume(monkeypatch):
    app = create_test_app()
    client = app.test_client()

    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.168.1.9")

    response = client.post("/api/Living Room/volume", json={"volume": -1})

    assert response.status_code == 400


def test_volume_endpoint_accepts_valid_volume(monkeypatch):
    app = create_test_app()
    client = app.test_client()
    calls = []

    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.168.1.9")
    def set_volume(ip, volume):
        calls.append((ip, volume))
        return True

    monkeypatch.setattr("app.api.routes.control.set_volume", set_volume)
    monkeypatch.setattr("app.api.routes.jobs.manual_control", lambda _name, callback: callback("192.168.1.9"))

    response = client.post("/api/Living Room/volume", json={"volume": 22})

    assert response.status_code == 200
    assert calls == [("192.168.1.9", 22)]


def test_volume_endpoint_rejects_malformed_json(monkeypatch):
    app = create_test_app()
    client = app.test_client()

    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.168.1.9")

    response = client.post(
        "/api/Living Room/volume",
        data="{bad",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Malformed JSON body."}


def test_add_schedule_logs_structured_event_fields(monkeypatch, caplog):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    with caplog.at_level(logging.INFO, logger="app.api.routes"):
        response = client.post(
            "/api/Living Room/schedules",
            json={
                "name": "Morning",
                "days": ["monday"],
                "on_time": "06:15",
                "off_time": "07:00",
                "preset": 1,
                "volume": 10,
            },
        )

    assert response.status_code == 202
    matching = [
        rec for rec in caplog.records
        if rec.msg == "Schedule queued for processing."
    ]
    assert matching
    assert matching[0].event_fields["speaker"] == "Living Room"
    assert matching[0].event_fields["schedule"] == "Morning"
    assert matching[0].event_fields["action"] == "add_update"


def test_delete_schedule_logs_structured_event_fields(monkeypatch, caplog):
    app = create_test_app()
    client = app.test_client()
    queued = []

    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)

    with caplog.at_level(logging.INFO, logger="app.api.routes"):
        response = client.delete("/api/Living Room/schedules/Weekend")

    assert response.status_code == 202
    matching = [
        rec for rec in caplog.records
        if rec.msg == "Schedule delete queued."
    ]
    assert matching
    assert matching[0].event_fields["speaker"] == "Living Room"
    assert matching[0].event_fields["schedule"] == "Weekend"


@pytest.mark.parametrize("result", [False, None])
@pytest.mark.parametrize("path, control_name, body", [
    ("power", "power_action", None),
    ("preset/2", "play_preset", None),
    ("volume", "set_volume", {"volume": 22}),
])
def test_manual_command_never_reports_unconfirmed_write_as_success(monkeypatch, result, path, control_name, body):
    client = create_test_app().test_client()
    events = []
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.0.2.9")

    def command(ip, *_args, **_kwargs):
        events.append(("command", ip))
        return result

    def manual_control(name, callback):
        events.append(("cancel_and_serialize", name))
        return callback("192.0.2.10")

    monkeypatch.setattr(f"app.api.routes.control.{control_name}", command)
    monkeypatch.setattr("app.api.routes.jobs.manual_control", manual_control)
    response = client.post(f"/api/Living Room/{path}", json=body)

    assert response.status_code == 502
    assert response.get_json()["outcome"] == "unknown"
    assert "message" not in response.get_json()
    assert events == [("cancel_and_serialize", "Living Room"), ("command", "192.0.2.10")]


@pytest.mark.parametrize("path, control_name, body", [
    ("power", "power_action", None),
    ("preset/2", "play_preset", None),
    ("volume", "set_volume", {"volume": 22}),
])
def test_manual_command_cancels_even_when_speaker_is_missing(monkeypatch, path, control_name, body):
    client = create_test_app().test_client()
    canceled = []
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: None)
    monkeypatch.setattr("app.api.routes.jobs.cancel_operation", canceled.append)
    monkeypatch.setattr(f"app.api.routes.control.{control_name}", lambda *_a, **_kw: pytest.fail("Must not send a command"))

    response = client.post(f"/api/Living Room/{path}", json=body)

    assert response.status_code == 404
    assert canceled == ["Living Room"]


def test_preset_acknowledgement_does_not_claim_playback(monkeypatch):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _speaker: "192.0.2.9")
    monkeypatch.setattr("app.api.routes.control.play_preset", lambda *_a, **_kw: True)
    monkeypatch.setattr("app.api.routes.jobs.manual_control", lambda _name, callback: callback("192.0.2.10"))

    response = client.post("/api/Living Room/preset/2")

    assert response.status_code == 200
    assert "not yet confirmed" in response.get_json()["message"]
    assert "Playing" not in response.get_json()["message"]


def test_trigger_returns_accepted_operation_and_reuses_duplicate_identity(monkeypatch):
    client = create_test_app().test_client()
    schedule = {"name": "Morning", "preset": 1}
    accepted = {"operation_id": "run-1", "state": "accepted", "terminal": False}
    calls = []
    monkeypatch.setattr("app.api.routes.jobs.get_current_config", lambda: {"Living Room": [schedule]})

    def queue_on(name, target, force=False):
        calls.append((name, target, force))
        return accepted

    monkeypatch.setattr("app.api.routes.jobs.queue_on", queue_on)
    first = client.post("/api/Living Room/schedules/Morning/trigger")
    second = client.post("/api/Living Room/schedules/Morning/trigger")

    assert first.status_code == second.status_code == 202
    assert first.get_json()["operation"] == second.get_json()["operation"] == accepted
    assert "not yet confirmed" in first.get_json()["message"]
    assert calls == [("Living Room", schedule, True)] * 2


def test_trigger_reports_unavailable_worker_and_does_not_fall_back(monkeypatch):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.jobs.get_current_config", lambda: {"Living Room": [{"name": "Morning"}]})
    monkeypatch.setattr("app.api.routes.jobs.queue_on", lambda *_a, **_kw: None)
    monkeypatch.setattr("app.api.routes.jobs.auto_on_job", lambda *_a, **_kw: pytest.fail("Must not run synchronously"))

    response = client.post("/api/Living Room/schedules/Morning/trigger")

    assert response.status_code == 503
    assert "operation" not in response.get_json()


def test_trigger_missing_schedule_does_not_queue(monkeypatch):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.jobs.get_current_config", lambda: {})
    monkeypatch.setattr("app.api.routes.jobs.queue_on", lambda *_a, **_kw: pytest.fail("Must not queue missing schedule"))
    assert client.post("/api/Living Room/schedules/Morning/trigger").status_code == 404


def test_outcome_and_runtime_remain_readable_without_speaker_discovery(monkeypatch):
    client = create_test_app().test_client()
    outcome = {"state": "unknown", "operation_id": "run-1", "reason": "speaker_unavailable", "terminal": True}
    runtime = [{"schedule_name": "Morning", "next_run": "2026-10-22T06:15:00+02:00", "timezone": "Europe/Paris", "paused": False}]
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda *_a: pytest.fail("Must not query LAN"))
    monkeypatch.setattr("app.api.routes.jobs.get_last_outcome", lambda _name: outcome)
    monkeypatch.setattr("app.api.routes.jobs.get_schedule_runtime", lambda _name: runtime)

    response = client.get("/api/Living Room/operations")
    assert response.status_code == 200
    assert response.get_json()["last_outcome"] == outcome
    response = client.get("/api/Living Room/schedules/runtime")
    assert response.status_code == 200
    assert response.get_json()["schedules"] == runtime


def test_cancel_invalidates_only_and_does_not_touch_speaker(monkeypatch):
    client = create_test_app().test_client()
    calls = []
    monkeypatch.setattr("app.api.routes.jobs.cancel_operation", lambda name, reason: calls.append((name, reason)))
    monkeypatch.setattr("app.api.routes.jobs.get_last_outcome", lambda _name: {"state": "canceled", "terminal": True})
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda *_a: pytest.fail("Must not query LAN"))
    monkeypatch.setattr("app.api.routes.control.power_action", lambda *_a: pytest.fail("Must not toggle power"))

    response = client.post("/api/Living Room/cancel")

    assert response.status_code == 200
    assert calls == [("Living Room", "user_cancelled")]
    assert response.get_json()["last_outcome"]["state"] == "canceled"
    assert "Audio may continue" in response.get_json()["message"]


@pytest.mark.parametrize("cached", [True, False])
def test_status_redacts_private_identity_without_losing_display_fields(monkeypatch, cached):
    client = create_test_app().test_client()
    state = {
        "status": "Buffering", "source": "Local Radio", "track": "Song", "artist": "Artist",
        "raw_state": "BUFFERING_STATE", "volume": 12,
        "content_identity": {"sourceAccount": "private-account", "location": "private-url"},
        "sourceAccount": "private-account", "location": "private-url",
        "nested": [{"source_account": "private-account", "keep": "display"}],
    }
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda _name: "192.0.2.9")
    monkeypatch.setattr("app.api.routes.speaker_cache.get_speaker_state", lambda _name: state if cached else None)
    monkeypatch.setattr("app.api.routes.status.get_now_playing", lambda _ip: state)
    monkeypatch.setattr("app.api.routes.status.get_volume", lambda _ip: 12)

    response = client.get("/api/Living Room/status")
    body = response.get_json()

    assert response.status_code == 200
    for key in ("status", "source", "track", "artist", "raw_state", "volume"):
        assert body[key] == state[key]
    assert body["nested"] == [{"keep": "display"}]
    assert "private-" not in response.get_data(as_text=True)
    assert "content_identity" in state  # Serialization must not mutate the cache.


def test_schedule_edit_preserves_existing_identity_binding(monkeypatch):
    client = create_test_app().test_client()
    queued = []
    monkeypatch.setattr("app.api.routes.jobs.get_current_config", lambda: {
        "Living Room": [{"name": "Morning", "speaker_id": "AA:BB:CC:DD:EE:FF"}],
    })
    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)
    response = client.post("/api/Living Room/schedules", json={
        "name": "Renamed", "previous_name": "Morning", "days": ["monday"],
        "on_time": "06:15", "off_time": "07:00", "preset": 1,
    })
    assert response.status_code == 202
    assert queued[0]["data"]["speaker_id"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_pause_and_resume_preserve_identity_binding(monkeypatch, action):
    client = create_test_app().test_client()
    queued = []
    monkeypatch.setattr("app.api.routes.jobs.get_current_config", lambda: {
        "Living Room": [{"name": "Morning", "speaker_id": "AA:BB:CC:DD:EE:FF"}],
    })
    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", queued.append)
    response = client.patch(f"/api/Living Room/schedules/Morning/{action}")
    assert response.status_code == 202
    assert queued[0]["data"]["speaker_id"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("speaker_id", [None, "", "   ", 17, False, []])
def test_schedule_rejects_invalid_explicit_identity(monkeypatch, speaker_id):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", lambda *_a: pytest.fail("Invalid payload must not be queued"))
    response = client.post("/api/Living Room/schedules", json={
        "name": "Morning", "speaker_id": speaker_id, "days": ["monday"],
        "on_time": "06:15", "off_time": "07:00", "preset": 1,
    })
    assert response.status_code == 400
    assert "speaker_id" in response.get_json()["errors"]


@pytest.mark.parametrize("field", ["fade_in_duration", "fade_out_duration"])
@pytest.mark.parametrize("duration", [float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", -1, 3601])
def test_schedule_rejects_nonfinite_or_unbounded_fade_duration(monkeypatch, field, duration):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.jobs.config_queue.put", lambda *_a: pytest.fail("Invalid duration must not be queued"))
    response = client.post("/api/Living Room/schedules", json={
        "name": "Morning", "days": ["monday"], "on_time": "06:15", "off_time": "07:00",
        "preset": 1, field: duration,
    })
    assert response.status_code == 400
    assert "1 hour" in response.get_json()["errors"][field]


@pytest.mark.parametrize("volume", [float("nan"), float("inf"), float("-inf")])
def test_manual_volume_rejects_nonfinite_input_without_server_error(monkeypatch, volume):
    client = create_test_app().test_client()
    monkeypatch.setattr("app.api.routes.discovery.get_device_ip", lambda *_a: pytest.fail("Invalid input must not query LAN"))
    response = client.post("/api/Living Room/volume", json={"volume": volume})
    assert response.status_code == 400

@pytest.mark.parametrize('explicit', [True, False])
def test_saved_favorite_canonicalizes_slot_and_preserves_legacy_edit(monkeypatch, explicit):
    favorite_id = 'a' * 32
    queued = []
    monkeypatch.setattr('app.api.routes.jobs.config_queue.put', queued.append)
    monkeypatch.setattr('app.api.routes.jobs.get_current_config', lambda: {'Room': [{'name': 'Morning', 'favorite_id': favorite_id}]})
    monkeypatch.setattr('app.api.routes.favorites.schedule_binding', lambda id, speaker: {'speaker_id': 'ABC', 'slot': 3} if id == favorite_id and speaker == 'Room' else None)
    payload = {'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'preset': 1, 'volume': 10}
    if explicit:
        payload['favorite_id'] = favorite_id
    result = create_test_app().test_client().post('/api/Room/schedules', json=payload)
    assert result.status_code == 202
    assert queued[0]['data']['favorite_id'] == favorite_id
    assert queued[0]['data']['speaker_id'] == 'ABC'
    assert queued[0]['data']['preset'] == 3


def test_explicit_numbered_preset_removes_favorite_binding(monkeypatch):
    queued = []
    monkeypatch.setattr('app.api.routes.jobs.config_queue.put', queued.append)
    monkeypatch.setattr('app.api.routes.jobs.get_current_config', lambda: {'Room': [{'name': 'Morning', 'favorite_id': 'a' * 32}]})
    result = create_test_app().test_client().post('/api/Room/schedules', json={'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'preset': 1, 'volume': 10, 'favorite_id': ''})
    assert result.status_code == 202
    assert 'favorite_id' not in queued[0]['data']

@pytest.mark.parametrize('legacy', [False, True])
def test_station_schedule_keeps_archived_binding_and_device_pin(monkeypatch, legacy):
    from app.core import favorites
    id = 'b' * 32
    queued, reads, devices = [], [], []
    monkeypatch.setattr('app.api.routes.jobs.config_queue.put', queued.append)
    monkeypatch.setattr('app.api.routes.jobs.get_current_config', lambda: {'Room': [{'name': 'Morning', 'station_id': id, 'speaker_id': 'ABC'}]})
    monkeypatch.setattr(favorites, 'station', lambda key, **kw: reads.append((key, kw)) or {'id': id})
    monkeypatch.setattr(favorites, 'device', lambda name, pin: devices.append((name, pin)) or {'device_id': pin})
    payload = {'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'volume': 10, 'preset': None, 'source': None}
    if not legacy:
        payload['station_id'] = id
    response = create_test_app().test_client().post('/api/Room/schedules', json=payload)
    assert response.status_code == 202
    assert reads == [(id, {'allow_removed': True})]
    assert devices == [('Room', 'ABC')]
    assert queued[0]['data']['station_id'] == id
    assert queued[0]['data']['preset'] is None and queued[0]['data']['source'] is None


def test_station_schedule_rejects_same_name_replacement_speaker(monkeypatch):
    from app.core import favorites
    id = 'b' * 32
    queued = []
    monkeypatch.setattr('app.api.routes.jobs.config_queue.put', queued.append)
    monkeypatch.setattr('app.api.routes.jobs.get_current_config', lambda: {'Room': [{'name': 'Morning', 'station_id': id, 'speaker_id': 'ABC'}]})
    monkeypatch.setattr(favorites, 'station', lambda *args, **kwargs: {})
    def resolve(name, pin):
        assert pin == 'ABC'
        raise favorites.FavoriteError('Speaker identity unavailable')
    monkeypatch.setattr(favorites, 'device', resolve)
    response = create_test_app().test_client().post('/api/Room/schedules', json={'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'volume': 10, 'station_id': id})
    assert response.status_code == 400
    assert not queued


def test_new_station_schedule_needs_no_preset_and_rejects_dual_binding(monkeypatch):
    from app.core import favorites
    id = 'b' * 32
    queued, reads = [], []
    monkeypatch.setattr('app.api.routes.jobs.config_queue.put', queued.append)
    monkeypatch.setattr('app.api.routes.jobs.get_current_config', lambda: {})
    monkeypatch.setattr(favorites, 'station', lambda key, **kw: reads.append((key, kw)) or {'id': id})
    monkeypatch.setattr(favorites, 'device', lambda name, pin: {'device_id': 'ABC'})
    payload = {'name': 'Morning', 'days': ['monday'], 'on_time': '07:00', 'off_time': '08:00', 'volume': 10, 'station_id': id, 'preset': None, 'source': None}
    response = create_test_app().test_client().post('/api/Room/schedules', json=payload)
    assert response.status_code == 202
    assert reads == [(id, {'allow_removed': False})]
    assert queued[0]['data']['station_id'] == id
    assert queued[0]['data']['preset'] is None
    payload['favorite_id'] = 'a' * 32
    assert create_test_app().test_client().post('/api/Room/schedules', json=payload).status_code == 400
