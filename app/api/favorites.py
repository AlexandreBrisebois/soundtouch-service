"""Explicit user-driven native preset management; never changes source registration."""
from typing import Any
from urllib.parse import urlsplit
from flask import Blueprint, jsonify, request
from app.core import favorites
from app.scheduler import jobs

favorites_bp = Blueprint('favorites', __name__)


@favorites_bp.errorhandler(ValueError)
def invalid_request(error: ValueError) -> tuple[Any, int]:
    # Only our deliberately public validation errors reach this handler.
    return jsonify({'error': str(error)}), 400


def body() -> dict[str, Any]:
    if request.content_length is not None and request.content_length > 8192:
        raise favorites.FavoriteError('Request too large.')
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.host):
        raise favorites.FavoriteError('Open Wisp directly before changing presets.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise favorites.FavoriteError('Expected a JSON object.')
    return data


@favorites_bp.get('/api/<speaker_name>/favorites')
def overview(speaker_name: str) -> Any:
    return jsonify(favorites.overview(speaker_name))


@favorites_bp.post('/api/<speaker_name>/library/browse')
def browse(speaker_name: str) -> Any:
    return jsonify(favorites.browse(speaker_name, body()))


@favorites_bp.post('/api/<speaker_name>/preset-plans')
def plan(speaker_name: str) -> Any:
    return jsonify(favorites.plan(speaker_name, body()))


@favorites_bp.post('/api/<speaker_name>/preset-plans/<plan_id>/confirm')
def confirm(speaker_name: str, plan_id: str) -> Any:
    if body().get('confirmed') is not True:
        raise favorites.FavoriteError('Confirm the displayed physical button assignment first.')
    result = favorites.confirm(speaker_name, plan_id)
    return jsonify(result), 200 if result['state'] == 'readback_matched' else 409


@favorites_bp.post('/api/<speaker_name>/favorites/<favorite_id>/test')
def test(speaker_name: str, favorite_id: str) -> Any:
    if body().get('confirmed') is not True:
        raise favorites.FavoriteError('Confirm that a quiet test will start audio on this speaker.')
    value = favorites.schedule_binding(favorite_id, speaker_name)
    operation = jobs.queue_on(speaker_name, {
        'name': 'Test favorite', 'speaker_id': value['speaker_id'], 'favorite_id': value['id'],
        'preset': value['slot'], 'source': None, 'volume': 5, 'fade_in_duration': 2,
        'fade_out_duration': 0, 'days': None, 'on_time': None, 'off_time': None, 'paused': False,
    }, force=True)
    if operation is None:
        return jsonify({'error': 'Playback worker unavailable. No test was started.'}), 503
    return jsonify({'operation': operation, 'state': 'accepted',
                    'message': 'Quiet test requested. Speaker playback and audible sound are separate checks.'}), 202


@favorites_bp.get('/api/radio/<favorite_id>')
def radio(favorite_id: str) -> Any:
    # No network fetch/redirect, no arbitrary URL parameter, no credential support.
    response = jsonify(favorites.descriptor(favorite_id))
    response.headers['Cache-Control'] = 'no-store'
    return response
