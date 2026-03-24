from app.scheduler import jobs
import json
import logging


def test_auto_on_job_force_from_standby_applies_preset_then_fade(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.discovery, "get_device_ip", lambda _: "192.168.1.20")
    monkeypatch.setattr(jobs.status, "get_now_playing", lambda _: {"status": "STANDBY"})
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)

    def fake_power_action(_ip):
        calls.append(("power_action", None))
        return True

    def fake_play_preset(_ip, preset):
        calls.append(("play_preset", preset))
        return True

    def fake_send_key(_ip, key):
        calls.append(("send_key", key))
        return True

    def fake_set_volume(_ip, volume):
        calls.append(("set_volume", volume))
        return True

    monkeypatch.setattr(jobs.control, "power_action", fake_power_action)
    monkeypatch.setattr(jobs.control, "play_preset", fake_play_preset)
    monkeypatch.setattr(jobs.control, "send_key", fake_send_key)
    monkeypatch.setattr(jobs.control, "set_volume", fake_set_volume)

    jobs.auto_on_job(
        speaker_name="Living Room",
        preset=2,
        volume=3,
        source=None,
        fade_in_duration=0,
        force=True,
    )

    assert calls == [
        ("power_action", None),
        ("play_preset", 2),
        ("set_volume", 0),
        ("set_volume", 3),
    ]


def test_auto_on_job_force_active_applies_aux_then_fade(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.discovery, "get_device_ip", lambda _: "192.168.1.20")
    monkeypatch.setattr(jobs.status, "get_now_playing", lambda _: {"status": "PLAYING"})
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)

    def fake_power_action(_ip):
        calls.append(("power_action", None))
        return True

    def fake_play_preset(_ip, preset):
        calls.append(("play_preset", preset))
        return True

    def fake_send_key(_ip, key):
        calls.append(("send_key", key))
        return True

    def fake_set_volume(_ip, volume):
        calls.append(("set_volume", volume))
        return True

    monkeypatch.setattr(jobs.control, "power_action", fake_power_action)
    monkeypatch.setattr(jobs.control, "play_preset", fake_play_preset)
    monkeypatch.setattr(jobs.control, "send_key", fake_send_key)
    monkeypatch.setattr(jobs.control, "set_volume", fake_set_volume)

    jobs.auto_on_job(
        speaker_name="Living Room",
        preset=1,
        volume=4,
        source="AUX",
        fade_in_duration=0,
        force=True,
    )

    assert calls == [
        ("send_key", "AUX_INPUT"),
        ("set_volume", 0),
        ("set_volume", 4),
    ]


def test_auto_on_job_active_without_force_does_not_interrupt(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.discovery, "get_device_ip", lambda _: "192.168.1.20")
    monkeypatch.setattr(jobs.status, "get_now_playing", lambda _: {"status": "PLAYING"})

    def fake_control_call(*_args, **_kwargs):
        calls.append("called")
        return True

    monkeypatch.setattr(jobs.control, "power_action", fake_control_call)
    monkeypatch.setattr(jobs.control, "play_preset", fake_control_call)
    monkeypatch.setattr(jobs.control, "send_key", fake_control_call)
    monkeypatch.setattr(jobs.control, "set_volume", fake_control_call)

    jobs.auto_on_job(
        speaker_name="Living Room",
        preset=1,
        volume=8,
        source=None,
        fade_in_duration=120,
        force=False,
    )

    assert calls == []


def test_auto_on_job_invalid_preset_and_volume_are_sanitized(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.discovery, "get_device_ip", lambda _: "192.168.1.20")
    monkeypatch.setattr(jobs.status, "get_now_playing", lambda _: {"status": "STANDBY"})
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)
    monkeypatch.setattr(jobs.control, "power_action", lambda _ip: True)
    monkeypatch.setattr(jobs.control, "send_key", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(jobs.control, "play_preset", lambda _ip, preset: calls.append(("play_preset", preset)))
    monkeypatch.setattr(jobs.control, "set_volume", lambda _ip, volume: calls.append(("set_volume", volume)))

    jobs.auto_on_job(
        speaker_name="Living Room",
        preset=99,
        volume=250,
        source=None,
        fade_in_duration=0,
        force=True,
    )

    assert calls == [
        ("play_preset", 6),
        ("set_volume", 0),
        ("set_volume", 100),
    ]


def test_auto_off_job_invalid_current_volume_skips_fade_and_powers_off(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.discovery, "get_device_ip", lambda _: "192.168.1.20")
    monkeypatch.setattr(jobs.status, "get_now_playing", lambda _: {"status": "PLAYING"})
    monkeypatch.setattr(jobs.status, "get_volume", lambda _: "not-a-number")
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)
    monkeypatch.setattr(jobs.control, "set_volume", lambda *_args, **_kwargs: calls.append("set_volume"))
    monkeypatch.setattr(jobs.control, "power_action", lambda _ip: calls.append("power_action"))

    jobs.auto_off_job("Living Room", fade_out_duration=30)

    assert calls == ["power_action"]


def test_sanitize_config_normalizes_legacy_entries():
    config = {
        "Living Room": [
            {
                "name": " Weekend Alarm ",
                "days": ["Saturday", "SUNDAY", "noday"],
                "on_time": "09:00",
                "off_time": "10:30",
                "preset": "9",
                "volume": "500",
                "fade_in_duration": "15",
                "fade_out_duration": -4,
                "paused": 1,
            },
            {
                "name": "Bad",
                "days": ["noday"],
                "on_time": "bad",
                "off_time": None,
            },
        ],
        "Bedroom": "not-a-list",
    }

    assert jobs.sanitize_config(config) == {
        "Living Room": [
            {
                "name": "Weekend Alarm",
                "days": ["saturday", "sunday"],
                "on_time": "09:00",
                "off_time": "10:30",
                "preset": 6,
                "source": None,
                "volume": 100,
                "fade_in_duration": 15.0,
                "fade_out_duration": 0.0,
                "paused": True,
            }
        ]
    }


def test_load_config_migrates_legacy_document_to_versioned_format(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    legacy = {
        "Living Room": [
            {
                "name": "Morning",
                "days": ["monday"],
                "on_time": "06:15",
                "off_time": "07:00",
                "preset": 1,
                "volume": 10,
            }
        ]
    }
    config_path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setattr(jobs, "CONFIG_FILE_PATH", config_path)

    loaded = jobs.load_config()
    assert loaded is not None
    assert "Living Room" in loaded

    document = json.loads(config_path.read_text(encoding="utf-8"))
    assert document["version"] == jobs.CONFIG_SCHEMA_VERSION
    assert "schedules" in document


def test_load_config_reads_versioned_document(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    versioned = {
        "version": jobs.CONFIG_SCHEMA_VERSION,
        "schedules": {
            "Bedroom": [
                {
                    "name": "Wind Down",
                    "days": ["sunday"],
                    "on_time": "21:00",
                    "off_time": "22:00",
                    "source": "AUX",
                    "volume": 15,
                }
            ]
        },
    }
    config_path.write_text(json.dumps(versioned), encoding="utf-8")
    monkeypatch.setattr(jobs, "CONFIG_FILE_PATH", config_path)

    loaded = jobs.load_config()
    assert loaded == {
        "Bedroom": [
            {
                "name": "Wind Down",
                "days": ["sunday"],
                "on_time": "21:00",
                "off_time": "22:00",
                "preset": None,
                "source": "AUX",
                "volume": 15,
                "fade_in_duration": jobs.DEFAULT_FADE_IN_DURATION_SECONDS,
                "fade_out_duration": jobs.DEFAULT_FADE_OUT_DURATION_SECONDS,
                "paused": False,
            }
        ]
    }


def test_sanitize_config_emits_structured_warning_fields(caplog):
    bad_config = {
        "Living Room": [
            {
                "name": "Bad",
                "days": ["notaday"],
                "on_time": "06:15",
                "off_time": "07:00",
            }
        ]
    }

    with caplog.at_level(logging.WARNING, logger="app.scheduler.jobs"):
        result = jobs.sanitize_config(bad_config)

    assert result == {}
    matching = [
        rec for rec in caplog.records
        if rec.msg == "Skipping schedule: no valid day names."
    ]
    assert matching
    assert matching[0].event_fields["speaker"] == "Living Room"
    assert matching[0].event_fields["schedule"] == "Bad"


def test_background_worker_pool_recreated_after_shutdown(monkeypatch):
    """Verify that start_daemon() recreates the pool after shutdown_daemon() teardown."""
    monkeypatch.setattr(jobs, "_config_worker_thread", None)
    monkeypatch.setattr(jobs, "_scheduler_thread", None)
    monkeypatch.setattr(jobs, "BACKGROUND_WORKER_POOL", None)

    # Prevent real threads from starting
    class FakeThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def is_alive(self):
            return False
        def join(self, timeout=None):
            pass

    monkeypatch.setattr(jobs.threading, "Thread", FakeThread)

    # start_daemon() should create the pool when it is None
    jobs.start_daemon()
    assert jobs.BACKGROUND_WORKER_POOL is not None
    pool_first = jobs.BACKGROUND_WORKER_POOL

    # shutdown_daemon() should shut down and reset the pool to None
    jobs.shutdown_daemon(timeout=0.1)
    assert jobs.BACKGROUND_WORKER_POOL is None

    # start_daemon() should recreate the pool after shutdown
    jobs.start_daemon()
    assert jobs.BACKGROUND_WORKER_POOL is not None
    assert jobs.BACKGROUND_WORKER_POOL is not pool_first

    # Cleanup
    jobs.shutdown_daemon(timeout=0.1)


def test_submit_background_task_drops_task_when_pool_is_none(monkeypatch, caplog):
    """Verify submit_background_task() logs a warning and returns when pool is None."""
    monkeypatch.setattr(jobs, "BACKGROUND_WORKER_POOL", None)

    called = []

    with caplog.at_level(logging.WARNING, logger="app.scheduler.jobs"):
        jobs.submit_background_task(lambda: called.append(True))

    assert not called
    assert any(
        rec.levelname == "WARNING" and "task dropped" in rec.message
        for rec in caplog.records
    )
