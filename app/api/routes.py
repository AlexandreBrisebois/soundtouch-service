import re
import logging
import math
from typing import Any, Mapping
from flask import Blueprint, jsonify, request, render_template, current_app, send_from_directory, make_response
from app.core.constants import (
  DEFAULT_FADE_IN_DURATION_SECONDS,
  DEFAULT_FADE_OUT_DURATION_SECONDS,
  DEFAULT_PRESET,
  DEFAULT_VOLUME,
)
from app.core import discovery, status, control, speaker_cache, favorites
from app.core.models import ConfigMutation, Schedule, SchedulePayload
from app.scheduler import jobs

api_bp = Blueprint('api', __name__)
VALID_DAYS = {
  "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
logger = logging.getLogger(__name__)


def _log_with_fields(level: int, message: str, **fields: Any) -> None:
  logger.log(level, message, extra={"event_fields": fields})


def _public_state(value: Any) -> Any:
  """Keep private content matching data out of every public status response."""
  if isinstance(value, dict):
    private = {
      "contentidentity", "sourceaccount", "location", "relaytoken", "relayurl",
      "savedurl", "priorurl", "recoverygeneration", "generation", "token",
    }
    return {
      key: _public_state(item)
      for key, item in value.items()
      if key.replace("_", "").lower() not in private
    }
  if isinstance(value, list):
    return [_public_state(item) for item in value]
  return value


def _command_unconfirmed() -> tuple[Any, int]:
  return jsonify({
    "error": "Command delivery could not be confirmed. The speaker's state is unknown.",
    "outcome": "unknown",
  }), 502


def _to_schedule(payload: Mapping[str, Any]) -> Schedule:
  schedule: Schedule = {
    "name": str(payload["name"]),
    "days": payload.get("days"),
    "on_time": payload.get("on_time"),
    "off_time": payload.get("off_time"),
    "volume": int(payload.get("volume", DEFAULT_VOLUME)),
    "fade_in_duration": float(payload.get("fade_in_duration", DEFAULT_FADE_IN_DURATION_SECONDS)),
    "fade_out_duration": float(payload.get("fade_out_duration", DEFAULT_FADE_OUT_DURATION_SECONDS)),
    "paused": bool(payload.get("paused", False)),
  }
  if payload.get("speaker_id"):
    schedule["speaker_id"] = str(payload["speaker_id"])
  if payload.get("station_id"):
    schedule["station_id"] = str(payload["station_id"])
  if payload.get("favorite_id"):
    schedule["favorite_id"] = str(payload["favorite_id"])
  if not payload.get("station_id"):
    schedule["preset"] = payload.get("preset")
    schedule["source"] = payload.get("source")
  return schedule


def _coerce_int(value: Any, field_name: str, errors: dict[str, str], minimum: int | None = None, maximum: int | None = None) -> int | None:
  if isinstance(value, bool):
    errors[field_name] = f"'{field_name}' must be an integer."
    return None
  try:
    coerced = int(value)
  except (TypeError, ValueError, OverflowError):
    errors[field_name] = f"'{field_name}' must be an integer."
    return None

  if minimum is not None and coerced < minimum:
    errors[field_name] = f"'{field_name}' must be between {minimum} and {maximum}."
    return None
  if maximum is not None and coerced > maximum:
    errors[field_name] = f"'{field_name}' must be between {minimum} and {maximum}."
    return None
  return coerced


def _coerce_non_negative_number(value: Any, field_name: str, errors: dict[str, str], default_value: int | float) -> int | float | None:
  if value is None:
    return default_value
  if isinstance(value, bool):
    errors[field_name] = f"'{field_name}' must be a number."
    return None
  try:
    coerced = float(value)
  except (TypeError, ValueError, OverflowError):
    errors[field_name] = f"'{field_name}' must be a number."
    return None
  if not math.isfinite(coerced) or not 0 <= coerced <= 3600:
    errors[field_name] = f"'{field_name}' must be between 0 and 3600 seconds (1 hour)."
    return None
  if coerced.is_integer():
    return int(coerced)
  return coerced


def _validate_schedule_payload(data: Any) -> tuple[SchedulePayload | None, dict[str, str] | None]:
  if not isinstance(data, dict):
    return None, {"body": "Expected a JSON object."}

  errors: dict[str, str] = {}
  normalized: SchedulePayload = {}

  name = data.get("name")
  if not isinstance(name, str) or not name.strip():
    errors["name"] = "'name' is required."
  else:
    normalized["name"] = name.strip()

  if "speaker_id" in data:
    speaker_id = data["speaker_id"]
    if not isinstance(speaker_id, str) or not speaker_id.strip():
      errors["speaker_id"] = "'speaker_id' must be a non-empty string when provided."
    else:
      normalized["speaker_id"] = speaker_id.strip()

  if data.get("station_id"):
    if not isinstance(data["station_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", data["station_id"]):
      errors["station_id"] = "Choose a valid saved station."
    else:
      normalized["station_id"] = data["station_id"]

  if data.get("favorite_id"):
    if not isinstance(data["favorite_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", data["favorite_id"]):
      errors["favorite_id"] = "Choose a valid saved favorite."
    else:
      normalized["favorite_id"] = data["favorite_id"]

  explicit_kinds = [
    bool(data.get("station_id")),
    bool(data.get("favorite_id")),
    data.get("preset") not in ("", None),
    data.get("source") not in ("", None),
  ]
  if sum(explicit_kinds) > 1:
    errors["playback"] = "Choose exactly one station, favorite, speaker button, or AUX input."

  previous_name = data.get("previous_name")
  if previous_name in (None, ""):
    normalized["previous_name"] = None
  elif not isinstance(previous_name, str) or not previous_name.strip():
    errors["previous_name"] = "'previous_name' must be a non-empty string when provided."
  else:
    normalized["previous_name"] = previous_name.strip()

  days = data.get("days")
  if not isinstance(days, list) or not days:
    errors["days"] = "'days' must be a non-empty array."
  else:
    normalized_days = []
    for day in days:
      if not isinstance(day, str):
        errors["days"] = "'days' must contain valid weekday names."
        break
      normalized_day = day.strip().lower()
      if normalized_day not in VALID_DAYS:
        errors["days"] = "'days' must contain valid weekday names."
        break
      normalized_days.append(normalized_day)
    if "days" not in errors:
      normalized["days"] = normalized_days

  for field_name in ("on_time", "off_time"):
    raw_value = data.get(field_name)
    if not isinstance(raw_value, str) or not TIME_PATTERN.fullmatch(raw_value.strip()):
      errors[field_name] = f"'{field_name}' must use HH:MM 24-hour format."
    else:
      normalized[field_name] = raw_value.strip()

  source = data.get("source")
  if source in ("", None):
    source = None
  elif not isinstance(source, str):
    errors["source"] = "'source' must be a string."
    source = None
  else:
    source = source.strip().upper()
    if source != "AUX":
      errors["source"] = "'source' must be 'AUX' when provided."
      source = None

  preset = data.get("preset")
  if preset in ("", None):
    preset = None
  else:
    preset = _coerce_int(preset, "preset", errors, minimum=1, maximum=6)

  if data.get("station_id") or data.get("favorite_id"):
    source = None
    preset = None
  else:
    if source is not None and preset is not None:
      errors["source"] = "'source' and 'preset' are mutually exclusive."
    if source is None and preset is None:
      preset = DEFAULT_PRESET
    normalized["source"] = source
    normalized["preset"] = None if source is not None else preset

  volume = _coerce_int(data.get("volume", DEFAULT_VOLUME), "volume", errors, minimum=0, maximum=100)
  if volume is not None:
    normalized["volume"] = volume
  fade_in_duration = _coerce_non_negative_number(
    data.get("fade_in_duration", DEFAULT_FADE_IN_DURATION_SECONDS), "fade_in_duration", errors, DEFAULT_FADE_IN_DURATION_SECONDS
  )
  if fade_in_duration is not None:
    normalized["fade_in_duration"] = fade_in_duration
  fade_out_duration = _coerce_non_negative_number(
    data.get("fade_out_duration", DEFAULT_FADE_OUT_DURATION_SECONDS), "fade_out_duration", errors, DEFAULT_FADE_OUT_DURATION_SECONDS
  )

  if fade_out_duration is not None:
    normalized["fade_out_duration"] = fade_out_duration

  paused = data.get("paused", False)
  if not isinstance(paused, bool):
    errors["paused"] = "'paused' must be a boolean."
  else:
    normalized["paused"] = paused

  if errors:
    return None, errors
  return normalized, None

@api_bp.route("/", methods=["GET"])
def ui_root() -> tuple[Any, int, dict[str, str]]:
    """Serve the Web UI single-page application."""
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@api_bp.route("/sw.js")
def serve_sw() -> Any:
    if current_app.static_folder is None:
      return jsonify({"error": "Static assets not configured."}), 404
    return send_from_directory(current_app.static_folder, "sw.js")

@api_bp.route("/api/info", methods=["GET"])
def api_root() -> Any:
    """
    Service Info Endpoint
    Returns general metadata about the service.
    ---
    responses:
      200:
        description: Returns service name and current memory configuration.
    """
    return jsonify({"service": "SoundTouch-Service", "config": jobs.get_current_config()})

@api_bp.route("/api/schedules", methods=["GET"])
def api_get_schedules() -> Any:
    """
    Get all schedules
    Retrieve the current schedules configured for all SoundTouch speakers.
    ---
    responses:
      200:
        description: A dictionary of speakers mapping to a list of schedules.
    """
    return jsonify(jobs.get_current_config())

@api_bp.route("/api/<speaker_name>/schedules", methods=["POST"])
def api_add_schedule(speaker_name: str) -> tuple[Any, int]:
    """
    Add or Update a Schedule
    Push a new schedule or update an existing schedule by name for the given speaker. 
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The precise broadcast name of the SoundTouch speaker
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "Morning Routine"
            days:
              type: array
              items:
                type: string
              example: ["monday", "tuesday", "wednesday", "thursday", "friday"]
            on_time:
              type: string
              example: "06:15"
            off_time:
              type: string
              example: "07:30"
            source:
              type: string
              example: "AUX"
            preset:
              type: integer
              example: 1
            volume:
              type: integer
              example: 10
    responses:
      202:
        description: Schedule update is accepted and queued for IO processing.
    """
    data = request.get_json(silent=True)
    normalized, errors = _validate_schedule_payload(data)
    if errors:
      return jsonify({"errors": errors}), 400

    assert normalized is not None

    previous_name = normalized.get("previous_name") or normalized["name"]
    existing = next((item for item in jobs.get_current_config().get(speaker_name, [])
                     if item.get("name") == previous_name), None)
    # Older clients omit favorite_id; do not silently remove protection on edit.
    if isinstance(data, dict) and "favorite_id" not in data and existing and existing.get("favorite_id"):
      normalized["favorite_id"] = existing["favorite_id"]
    if isinstance(data, dict) and "station_id" not in data and existing and existing.get("station_id"):
      normalized["station_id"] = existing["station_id"]
    if normalized.get("station_id") and normalized.get("favorite_id"):
      return jsonify({"errors": {"station_id": "Choose a station or a preset favorite, not both."}}), 400
    if normalized.get("station_id"):
      try:
        station = favorites.station(normalized["station_id"], allow_removed=bool(existing and existing.get("station_id") == normalized["station_id"]))
        pinned_id = existing.get("speaker_id") if existing else normalized.get("speaker_id")
        found = favorites.device(speaker_name, pinned_id)
        if not normalized.get("paused"):
          from app.core import radio_relay
          ready = radio_relay.readiness(station['url'], found['ip'])
          if not ready['available']:
            raise favorites.FavoriteError(ready['reason'])
      except ValueError as exc:
        return jsonify({"errors": {"station_id": str(exc)}}), 400
      normalized["speaker_id"] = found["device_id"]
      normalized.pop("favorite_id", None)
      normalized.pop("preset", None)
      normalized.pop("source", None)
    if normalized.get("favorite_id"):
      try:
        binding = favorites.schedule_binding(normalized["favorite_id"], speaker_name)
      except ValueError as exc:
        return jsonify({"errors": {"favorite_id": str(exc)}}), 400
      normalized["speaker_id"] = binding["speaker_id"]
      normalized["preset"] = binding["slot"]
      normalized.pop("station_id", None)
      normalized["source"] = None

    # Editing a legacy client payload must not silently drop an existing identity binding.
    if "speaker_id" not in normalized:
      previous_name = normalized.get("previous_name") or normalized["name"]
      existing = next((item for item in jobs.get_current_config().get(speaker_name, [])
                       if item.get("name") == previous_name), None)
      if existing and existing.get("speaker_id"):
        normalized["speaker_id"] = existing["speaker_id"]
        
    jobs.config_queue.put(ConfigMutation(
        action="add_update",
        speaker=speaker_name,
        schedule_name=normalized["name"],
        previous_name=normalized.get("previous_name"),
        data=_to_schedule(normalized),
    ))

    _log_with_fields(
      logging.INFO,
      "Schedule queued for processing.",
      speaker=speaker_name,
      schedule=normalized["name"],
      action="add_update",
    )
    
    return jsonify({"message": f"Schedule '{normalized['name']}' queued for processing on '{speaker_name}'"}), 202

@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>", methods=["DELETE"])
def api_delete_schedule(speaker_name: str, schedule_name: str) -> tuple[Any, int]:
    """
    Delete a Schedule
    Remove a schedule from a specific speaker by its exact name.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The precise broadcast name of the SoundTouch speaker
      - in: path
        name: schedule_name
        type: string
        required: true
        description: The name of the routine to delete
    responses:
      202:
        description: Deletion request is accepted and queued for IO processing.
    """
    jobs.config_queue.put(ConfigMutation(
        action="delete",
        speaker=speaker_name,
        schedule_name=schedule_name,
        previous_name=None,
    ))

    _log_with_fields(logging.INFO, "Schedule delete queued.", speaker=speaker_name, schedule=schedule_name)
    
    return jsonify({"message": f"Delete request for schedule '{schedule_name}' queued for processing on '{speaker_name}'"}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/pause", methods=["PATCH"])
def api_pause_schedule(speaker_name: str, schedule_name: str) -> tuple[Any, int]:
    """
    Pause a Schedule
    Temporarily pause a schedule by name. The schedule is kept but skipped by the scheduler until resumed.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The precise broadcast name of the SoundTouch speaker
      - in: path
        name: schedule_name
        type: string
        required: true
        description: The name of the routine to pause
    responses:
      202:
        description: Pause request is accepted and queued for IO processing.
      404:
        description: Schedule not found for the given speaker.
    """
    config = jobs.get_current_config()
    schedules = config.get(speaker_name, [])
    target = next((s for s in schedules if s.get("name") == schedule_name), None)
    if target is None:
        return jsonify({"error": f"Schedule '{schedule_name}' not found for speaker '{speaker_name}'"}), 404

    updated = _to_schedule(dict(target))
    updated["paused"] = True
    jobs.config_queue.put(ConfigMutation(
      action="add_update",
      speaker=speaker_name,
      schedule_name=schedule_name,
      previous_name=None,
      data=updated,
    ))
    _log_with_fields(logging.INFO, "Schedule pause queued.", speaker=speaker_name, schedule=schedule_name)
    return jsonify({"message": f"Schedule '{schedule_name}' on '{speaker_name}' is now paused."}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/resume", methods=["PATCH"])
def api_resume_schedule(speaker_name: str, schedule_name: str) -> tuple[Any, int]:
    """
    Resume a Schedule
    Resume a previously paused schedule so the scheduler will execute it again.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The precise broadcast name of the SoundTouch speaker
      - in: path
        name: schedule_name
        type: string
        required: true
        description: The name of the routine to resume
    responses:
      202:
        description: Resume request is accepted and queued for IO processing.
      404:
        description: Schedule not found for the given speaker.
    """
    config = jobs.get_current_config()
    schedules = config.get(speaker_name, [])
    target = next((s for s in schedules if s.get("name") == schedule_name), None)
    if target is None:
        return jsonify({"error": f"Schedule '{schedule_name}' not found for speaker '{speaker_name}'"}), 404

    updated = _to_schedule(dict(target))
    updated["paused"] = False
    jobs.config_queue.put(ConfigMutation(
      action="add_update",
      speaker=speaker_name,
      schedule_name=schedule_name,
      previous_name=None,
      data=updated,
    ))
    _log_with_fields(logging.INFO, "Schedule resume queued.", speaker=speaker_name, schedule=schedule_name)
    return jsonify({"message": f"Schedule '{schedule_name}' on '{speaker_name}' has been resumed."}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/trigger", methods=["POST"])
def api_trigger_schedule(speaker_name: str, schedule_name: str) -> tuple[Any, int]:
    """
    Manually Trigger a Schedule
    Immediately execute the 'ON' sequence for a specific schedule.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
      - in: path
        name: schedule_name
        type: string
        required: true
    responses:
      202:
        description: Trigger request accepted.
      404:
        description: Schedule not found.
      503:
        description: Playback worker is unavailable; no run was accepted.
    """
    config = jobs.get_current_config()
    schedules = config.get(speaker_name, [])
    target = next((s for s in schedules if s.get("name") == schedule_name), None)
    if target is None:
        return jsonify({"error": f"Schedule '{schedule_name}' not found for speaker '{speaker_name}'"}), 404

    operation = jobs.queue_on(speaker_name, target, force=True)
    if operation is None:
      return jsonify({"error": "Playback worker unavailable. No run was accepted."}), 503
    _log_with_fields(logging.INFO, "Manual trigger queued.", speaker=speaker_name, schedule=schedule_name)

    return jsonify({
      "message": "Run accepted. Playback is not yet confirmed.",
      "operation": _public_state(operation),
    }), 202


@api_bp.route("/api/<speaker_name>/operations", methods=["GET"])
def api_operations(speaker_name: str) -> Any:
    """Read the latest operation even when the speaker is unavailable."""
    return jsonify({"speaker": speaker_name, "last_outcome": _public_state(jobs.get_last_outcome(speaker_name))})


@api_bp.route("/api/<speaker_name>/schedules/runtime", methods=["GET"])
def api_schedule_runtime(speaker_name: str) -> Any:
    """Return server-computed next occurrences with explicit time zones."""
    return jsonify({"speaker": speaker_name, "schedules": _public_state(jobs.get_schedule_runtime(speaker_name))})


@api_bp.route("/api/<speaker_name>/cancel", methods=["POST"])
def api_cancel(speaker_name: str) -> Any:
    """Invalidate automation, without sending a power or playback command."""
    jobs.cancel_operation(speaker_name, reason="user_cancelled")
    return jsonify({
      "message": "Automation cancelled. Audio may continue; use Power to change speaker power.",
      "last_outcome": _public_state(jobs.get_last_outcome(speaker_name)),
    })


@api_bp.route("/api/discover", methods=["GET"])
def api_discover() -> Any:
    """
    Discover SoundTouch Speakers
    Return all cached speakers from the background mDNS discovery. Force a cache refresh with ?refresh=true.
    ---
    responses:
      200:
        description: A list of discovered devices containing their names and IP addresses.
    """
    force_refresh = request.args.get("refresh", "").lower() == "true"
    if force_refresh:
      if not discovery.safe_refresh_cache():
        return jsonify({"error": "Speaker discovery failed. Check the network and refresh again."}), 503

    devices = discovery.get_all_cached_devices()
    if not devices and not force_refresh:
      # Best-effort warmup for first page load when background scan is not ready yet.
      discovery.safe_refresh_cache()
      devices = discovery.get_all_cached_devices()

    return jsonify(devices)

@api_bp.route("/api/<speaker_name>/status", methods=["GET"])
def api_status(speaker_name: str) -> tuple[Any, int]:
    """
    Get Speaker Status
    Query a device to see what it is currently playing or if it is in STANDBY.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The broadcast name of the SoundTouch speaker
    responses:
      200:
        description: Status successfully retrieved.
      404:
        description: Speaker not found on the local network.
    """
    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        return jsonify({"error": "Speaker not found"}), 404
        
    # Phase 2: Prioritize memory cache (WebSocket push)
    cached = speaker_cache.get_speaker_state(speaker_name)
    if cached:
        return jsonify(_public_state({"speaker": speaker_name, "ip": ip, **cached}))
        
    # Fallback status check if cache not ready
    status_data = status.get_now_playing(ip)
    volume      = status.get_volume(ip)
    return jsonify(_public_state({"speaker": speaker_name, "ip": ip, "volume": volume, **status_data}))

@api_bp.route("/api/<speaker_name>/power", methods=["POST"])
def api_power(speaker_name: str) -> tuple[Any, int]:
    """
    Toggle Speaker Power
    Toggles the power state of the speaker. Note that SoundTouch APIs only offer a power toggle.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The broadcast name of the SoundTouch speaker
    responses:
      200:
        description: Power signal successfully sent.
      404:
        description: Speaker not found on the local network.
    """
    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        jobs.cancel_operation(speaker_name)
        return jsonify({"error": "Speaker not found"}), 404
    if not jobs.manual_control(speaker_name, lambda current_ip: control.power_action(current_ip)):
        return _command_unconfirmed()
    return jsonify({"message": f"Sent POWER toggle signal to {speaker_name}"})

@api_bp.route("/api/<speaker_name>/preset/<int:preset_id>", methods=["POST"])
def api_preset(speaker_name: str, preset_id: int) -> tuple[Any, int]:
    """
    Play Speaker Preset
    Triggers one of the 6 numeric preset shortcut buttons on the speaker.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The broadcast name of the SoundTouch speaker
      - in: path
        name: preset_id
        type: integer
        required: true
        description: Preset 1-6
    responses:
      200:
        description: Preset signal successfully sent.
      404:
        description: Speaker not found on the local network.
    """
    if not 1 <= preset_id <= 6:
      return jsonify({"error": "Preset must be between 1 and 6."}), 400
    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        jobs.cancel_operation(speaker_name)
        return jsonify({"error": "Speaker not found"}), 404
    if not jobs.manual_control(speaker_name, lambda current_ip: control.play_preset(current_ip, preset_num=preset_id)):
        return _command_unconfirmed()
    return jsonify({"message": f"Sent PRESET_{preset_id} command to {speaker_name}. Playback is not yet confirmed."})

@api_bp.route("/api/<speaker_name>/volume", methods=["POST"])
def api_volume(speaker_name: str) -> tuple[Any, int]:
    """
    Set Speaker Volume
    Sets the volume level from 0 to 100 on the specified network speaker.
    ---
    parameters:
      - in: path
        name: speaker_name
        type: string
        required: true
        description: The broadcast name of the SoundTouch speaker
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            volume:
              type: integer
              example: 20
    responses:
      200:
        description: Volume level successfully sent.
      404:
        description: Speaker not found on the local network.
    """
    data = request.get_json(silent=True)
    if request.is_json and data is None and request.content_length not in (None, 0):
      return jsonify({"error": "Malformed JSON body."}), 400
    if data is not None and not isinstance(data, dict):
      return jsonify({"error": "Expected a JSON object."}), 400

    vol = _coerce_int((data or {}).get("volume", DEFAULT_VOLUME), "volume", {}, minimum=0, maximum=100)
    if vol is None:
      return jsonify({"error": "Volume must be between 0 and 100."}), 400

    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        jobs.cancel_operation(speaker_name)
        return jsonify({"error": "Speaker not found"}), 404
    if not jobs.manual_control(speaker_name, lambda current_ip: control.set_volume(current_ip, vol)):
        return _command_unconfirmed()
    return jsonify({"message": f"Sent volume {vol}% command to {speaker_name}"})

