"""Explicit unsaved radio draft tests; reuse the current radio engine."""
from typing import Any

from flask import Blueprint, jsonify

from app.api.favorites import body
from app.core import station_drafts
from app.scheduler import jobs

station_drafts_bp = Blueprint('station_drafts', __name__)


@station_drafts_bp.errorhandler(ValueError)
def invalid_request(error: ValueError) -> tuple[Any, int]:
    return jsonify(error=str(error)), 400


@station_drafts_bp.errorhandler(jobs.StationRequestConflict)
def conflict(error: ValueError) -> tuple[Any, int]:
    return jsonify(error=str(error)), 409


@station_drafts_bp.errorhandler(jobs.StationWorkerUnavailable)
def unavailable(error: Exception) -> tuple[Any, int]:
    return jsonify(error=str(error) or 'Playback worker unavailable. No request was accepted.'), 503


@station_drafts_bp.post('/api/station-drafts')
def create() -> Any:
    data = body()
    return jsonify(draft=station_drafts.create(data.get('name'), data.get('url'))), 201


@station_drafts_bp.get('/api/station-drafts/<draft_id>')
def status(draft_id: str) -> Any:
    response = jsonify(station_drafts.status(draft_id))
    response.headers['Cache-Control'] = 'no-store'
    return response


@station_drafts_bp.post('/api/station-drafts/<draft_id>/test')
def test(draft_id: str) -> Any:
    return jsonify(station_drafts.test(draft_id, body())), 202


@station_drafts_bp.post('/api/station-drafts/<draft_id>/stop')
def stop(draft_id: str) -> Any:
    return jsonify(station_drafts.stop(draft_id, body())), 202


@station_drafts_bp.post('/api/station-drafts/<draft_id>/save')
def save(draft_id: str) -> Any:
    return jsonify(station=station_drafts.save(draft_id, body())), 201
