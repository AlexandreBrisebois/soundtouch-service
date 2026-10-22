from app.scheduler import jobs
import json
import logging


def test_auto_on_job_sanitizes_arguments_and_uses_operation(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.playback, 'begin', lambda name, **kwargs: {'speaker': name})
    monkeypatch.setattr(jobs.playback, 'run_on', lambda *args: calls.append(args))
    jobs.auto_on_job('Room', 99, 250, fade_in_duration=-1, force=True)
    assert calls == [({'speaker': 'Room'}, 6, 100, None, 0.0, True)]


def test_auto_off_job_uses_cancelable_operation(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.playback, 'begin', lambda name, **kwargs: {'speaker': name})
    monkeypatch.setattr(jobs.playback, 'run_off', lambda *args: calls.append(args))
    jobs.auto_off_job('Room', fade_out_duration=30)
    assert calls == [({'speaker': 'Room'}, 30)]


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



def test_queue_on_coalesces_pending_double_click(monkeypatch):
    jobs.playback.reset()
    class Pool:
        def submit(self, *args, **kwargs):
            calls.append(args)
            class Future:
                def add_done_callback(self, cb):
                    pass
            return Future()
    calls = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', Pool())
    schedule = jobs.get_default_config()['Target Speaker 1'][0]
    first = jobs.queue_on('Room', schedule, force=True)
    second = jobs.queue_on('Room', schedule, force=True)
    assert first['operation_id'] == second['operation_id']
    assert len(calls) == 1
    jobs.cancel_operation('Room')
    calls[0][0](*calls[0][1:])
    assert jobs.get_last_outcome('Room')['state'] == 'canceled'


def test_worker_exception_finishes_operation(monkeypatch):
    jobs.playback.reset()
    op = jobs.playback.begin('Room')
    def fail(_):
        raise RuntimeError('private URL must not escape')
    jobs._execute_operation(fail, op)
    assert jobs.get_last_outcome('Room')['state'] == 'failed'
    assert jobs.get_last_outcome('Room')['reason'] == 'internal_error'


def test_explicit_speaker_identity_survives_normalization():
    raw = jobs.get_default_config()
    raw['Target Speaker 1'][0]['speaker_id'] = 'ABC123'
    normalized = jobs.sanitize_config(raw)
    assert normalized['Target Speaker 1'][0]['speaker_id'] == 'ABC123'


def test_nonfinite_fades_are_bounded():
    assert jobs._coerce_non_negative_float(float('inf'), 300) == 300
    assert jobs._coerce_non_negative_float(float('nan'), 300) == 300
    assert jobs._coerce_non_negative_float(99999999, 300) == jobs.playback.MAX_FADE_SECONDS


def test_concurrent_run_now_admission_submits_once(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    jobs.playback.reset()
    calls = []
    class Pool:
        def submit(self, *args):
            calls.append(args)
            class Future:
                def add_done_callback(self, callback):
                    pass
            return Future()
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', Pool())
    schedule = jobs.get_default_config()['Target Speaker 1'][0]
    barrier = threading.Barrier(2)
    def request():
        barrier.wait(timeout=2)
        return jobs.queue_on('Room', schedule, force=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(request) for _ in range(2)]
        results = [future.result(timeout=2) for future in futures]
    assert len(calls) == 1
    assert results[0]['operation_id'] == results[1]['operation_id']


def scheduler_frames(monkeypatch, stamps, schedule):
    import time
    frames = [time.strptime(stamp, '%Y-%m-%d %H:%M') for stamp in stamps]
    index = [0]
    class Stop:
        def is_set(self):
            return index[0] >= len(frames)
        def wait(self, _):
            index[0] += 1
    monkeypatch.setattr(jobs, '_stop_event', Stop())
    monkeypatch.setattr(jobs, '_processed_occurrences', set())
    monkeypatch.setattr(jobs, 'load_config', lambda: {'Room': [schedule]})
    monkeypatch.setattr(jobs.time, 'localtime', lambda: frames[index[0]])
    calls = []
    monkeypatch.setattr(jobs, 'queue_on', lambda *a: calls.append('on'))
    monkeypatch.setattr(jobs, 'queue_off', lambda *a: calls.append('off'))
    jobs.run_scheduler_loop()
    return calls


def test_scheduler_skips_missed_minutes_and_paused_schedules(monkeypatch):
    schedule = jobs.get_default_config()['Target Speaker 1'][0]
    assert scheduler_frames(monkeypatch, ['2026-10-21 06:14', '2026-10-21 06:16'], schedule) == []
    schedule['paused'] = True
    assert scheduler_frames(monkeypatch, ['2026-10-21 06:15'], schedule) == []


def test_fall_back_wall_minute_fires_once_per_date(monkeypatch):
    schedule = jobs.get_default_config()['Target Speaker 1'][0]
    schedule['on_time'] = '01:30'
    assert scheduler_frames(monkeypatch, ['2026-11-01 01:29', '2026-11-01 01:30',
                                          '2026-11-01 01:00', '2026-11-01 01:30'], schedule) == ['on']


def test_spring_gap_has_no_catchup(monkeypatch):
    schedule = jobs.get_default_config()['Target Speaker 1'][0]
    schedule['on_time'] = '02:30'
    assert scheduler_frames(monkeypatch, ['2026-03-08 01:59', '2026-03-08 03:00'], schedule) == []


def test_next_run_has_offset_zone_and_skips_dst_gap(monkeypatch):
    import os
    import time
    from datetime import datetime, timezone
    previous = os.environ.get('TZ')
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    try:
        schedule = jobs.get_default_config()['Target Speaker 1'][0]
        schedule.update(on_time='02:30', off_time=None)
        monkeypatch.setattr(jobs, 'current_config', {'Room': [schedule]})
        monkeypatch.setattr(jobs, '_processed_occurrences', set())
        instant = datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc).timestamp()
        monkeypatch.setattr(jobs.time, 'time', lambda: instant)
        runtime = jobs.get_schedule_runtime('Room')[0]
        assert runtime['timezone'] == 'America/New_York'
        assert runtime['next_run'] == '2026-03-09T02:30:00-04:00'
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()


def test_station_queue_preserves_direct_binding_and_routine_parameters(monkeypatch):
    from app.core import playback
    playback.reset()
    queued = []
    monkeypatch.setattr(jobs, 'BACKGROUND_WORKER_POOL', object())
    monkeypatch.setattr(jobs, 'submit_background_task', lambda *args: queued.append(args) or True)
    schedule = jobs._normalize_schedule({'name': 'Radio', 'on_time': '07:00', 'off_time': '08:00', 'station_id': 'b' * 32, 'speaker_id': 'ABC', 'volume': 17, 'fade_in_duration': 20}, 'Room', 0)
    assert schedule['preset'] is None and schedule['source'] is None
    jobs.queue_on('Room', schedule)
    args = queued[0]
    assert args[1] is playback.run_on
    assert args[3:] == (None, 17, None, 20, False, None, 'b' * 32, True)
    assert args[2]['device_id'] == 'ABC'
