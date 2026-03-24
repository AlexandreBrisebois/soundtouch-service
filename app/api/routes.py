from flask import Blueprint, jsonify, request, render_template, current_app
from app.core import discovery, status, control, speaker_cache
from app.scheduler import jobs

api_bp = Blueprint('api', __name__)

@api_bp.route("/", methods=["GET"])
def ui_root():
    """Serve the Web UI single-page application."""
    return render_template("index.html")

@api_bp.route("/sw.js")
def serve_sw():
    return current_app.send_static_file('sw.js')

@api_bp.route("/api/info", methods=["GET"])
def api_root():
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
def api_get_schedules():
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
def api_add_schedule(speaker_name):
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
    data = request.json
    if not data or "name" not in data:
        return jsonify({"error": "Missing schedule 'name' in request body."}), 400
        
    jobs.config_queue.put({
        "action": "add_update",
        "speaker": speaker_name,
        "schedule_name": data["name"],
        "data": data
    })
    
    return jsonify({"message": f"Schedule '{data['name']}' queued for processing on '{speaker_name}'"}), 202

@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>", methods=["DELETE"])
def api_delete_schedule(speaker_name, schedule_name):
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
    jobs.config_queue.put({
        "action": "delete",
        "speaker": speaker_name,
        "schedule_name": schedule_name
    })
    
    return jsonify({"message": f"Delete request for schedule '{schedule_name}' queued for processing on '{speaker_name}'"}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/pause", methods=["PATCH"])
def api_pause_schedule(speaker_name, schedule_name):
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

    updated = dict(target)
    updated["paused"] = True
    jobs.config_queue.put({
        "action": "add_update",
        "speaker": speaker_name,
        "schedule_name": schedule_name,
        "data": updated
    })
    return jsonify({"message": f"Schedule '{schedule_name}' on '{speaker_name}' is now paused."}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/resume", methods=["PATCH"])
def api_resume_schedule(speaker_name, schedule_name):
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

    updated = dict(target)
    updated["paused"] = False
    jobs.config_queue.put({
        "action": "add_update",
        "speaker": speaker_name,
        "schedule_name": schedule_name,
        "data": updated
    })
    return jsonify({"message": f"Schedule '{schedule_name}' on '{speaker_name}' has been resumed."}), 202


@api_bp.route("/api/<speaker_name>/schedules/<schedule_name>/trigger", methods=["POST"])
def api_trigger_schedule(speaker_name, schedule_name):
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
    """
    config = jobs.get_current_config()
    schedules = config.get(speaker_name, [])
    target = next((s for s in schedules if s.get("name") == schedule_name), None)
    if target is None:
        return jsonify({"error": f"Schedule '{schedule_name}' not found for speaker '{speaker_name}'"}), 404

    import threading
    threading.Thread(
        target=jobs.auto_on_job,
        args=(
            speaker_name,
            target.get("preset", 1),
            target.get("volume", 20),
            target.get("source"),
            target.get("fade_in_duration", 300)
        ),
        daemon=True
    ).start()

    return jsonify({"message": f"Manually triggering schedule '{schedule_name}' on '{speaker_name}'"}), 202


@api_bp.route("/api/discover", methods=["GET"])
def api_discover():
    """
    Discover SoundTouch Speakers
    Return all cached speakers from the background mDNS discovery. Force a cache refresh with ?refresh=true.
    ---
    responses:
      200:
        description: A list of discovered devices containing their names and IP addresses.
    """
    if request.args.get("refresh", "").lower() == "true":
        discovery.refresh_cache()
    devices = discovery.get_all_cached_devices()
    return jsonify(devices)

@api_bp.route("/api/<speaker_name>/status", methods=["GET"])
def api_status(speaker_name):
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
        return jsonify({"speaker": speaker_name, "ip": ip, **cached})
        
    # Fallback status check if cache not ready
    status_data = status.get_now_playing(ip)
    volume      = status.get_volume(ip)
    return jsonify({"speaker": speaker_name, "ip": ip, "volume": volume, **status_data})

@api_bp.route("/api/<speaker_name>/power", methods=["POST"])
def api_power(speaker_name):
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
        return jsonify({"error": "Speaker not found"}), 404
    control.power_action(ip)
    return jsonify({"message": f"Sent POWER toggle signal to {speaker_name} at {ip}"})

@api_bp.route("/api/<speaker_name>/preset/<int:preset_id>", methods=["POST"])
def api_preset(speaker_name, preset_id):
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
    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        return jsonify({"error": "Speaker not found"}), 404
    control.play_preset(ip, preset_num=preset_id)
    return jsonify({"message": f"Playing PRESET_{preset_id} on {speaker_name} at {ip}"})

@api_bp.route("/api/<speaker_name>/volume", methods=["POST"])
def api_volume(speaker_name):
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
    data = request.json
    vol = data.get("volume", 20) if data else 20
    ip = discovery.get_device_ip(speaker_name)
    if not ip:
        return jsonify({"error": "Speaker not found"}), 404
    control.set_volume(ip, vol)
    return jsonify({"message": f"Set volume to {vol}% on {speaker_name} at {ip}"})
