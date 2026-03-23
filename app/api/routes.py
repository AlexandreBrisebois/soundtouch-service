from flask import Blueprint, jsonify, request, render_template, current_app
from app.core import discovery, status, control
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


@api_bp.route("/api/discover", methods=["GET"])
def api_discover():
    """
    Discover SoundTouch Speakers
    Perform a mDNS zero-configuration broadcast to find all local speakers on the network.
    ---
    responses:
      200:
        description: A list of discovered devices containing their names and IP addresses.
    """
    devices = discovery.discover_systems(timeout=3)
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
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            status_data = status.get_now_playing(d['ip'])
            return jsonify({"speaker": speaker_name, "ip": d['ip'], **status_data})
    return jsonify({"error": "Speaker not found"}), 404

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
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.power_action(d['ip'])
            return jsonify({"message": f"Sent POWER toggle signal to {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404

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
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.play_preset(d['ip'], preset_num=preset_id)
            return jsonify({"message": f"Playing PRESET_{preset_id} on {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404

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
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.set_volume(d['ip'], vol)
            return jsonify({"message": f"Set volume to {vol}% on {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404
