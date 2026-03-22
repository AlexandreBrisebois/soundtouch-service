from flask import Blueprint, jsonify, request
from app.core import discovery, status, control
from app.scheduler.jobs import load_config

api_bp = Blueprint('api', __name__)

@api_bp.route("/", methods=["GET"])
def api_root():
    return jsonify({"service": "SoundTouch-Service", "config": load_config()})

@api_bp.route("/api/discover", methods=["GET"])
def api_discover():
    devices = discovery.discover_systems(timeout=3)
    return jsonify(devices)

@api_bp.route("/api/<speaker_name>/status", methods=["GET"])
def api_status(speaker_name):
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            curr_status = status.get_now_playing(d['ip'])
            return jsonify({"speaker": speaker_name, "status": curr_status, "ip": d['ip']})
    return jsonify({"error": "Speaker not found"}), 404

@api_bp.route("/api/<speaker_name>/power", methods=["POST"])
def api_power(speaker_name):
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.power_action(d['ip'])
            return jsonify({"message": f"Sent POWER toggle signal to {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404

@api_bp.route("/api/<speaker_name>/preset/<int:preset_id>", methods=["POST"])
def api_preset(speaker_name, preset_id):
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.play_preset(d['ip'], preset_num=preset_id)
            return jsonify({"message": f"Playing PRESET_{preset_id} on {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404

@api_bp.route("/api/<speaker_name>/volume", methods=["POST"])
def api_volume(speaker_name):
    data = request.json
    vol = data.get("volume", 20) if data else 20
    devices = discovery.discover_systems(timeout=3)
    for d in devices:
        if d['name'] == speaker_name:
            control.set_volume(d['ip'], vol)
            return jsonify({"message": f"Set volume to {vol}% on {speaker_name} at {d['ip']}"})
    return jsonify({"error": "Speaker not found"}), 404
