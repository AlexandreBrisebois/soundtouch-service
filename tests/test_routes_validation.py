from flask import Flask

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
    monkeypatch.setattr("app.api.routes.control.set_volume", lambda ip, volume: calls.append((ip, volume)))

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