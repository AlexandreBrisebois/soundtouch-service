"""Collection actions compose existing guarded playback and preset APIs."""
from typing import Any
from flask import Blueprint, jsonify
from app.api.favorites import body
from app.core import collections, favorites, playback
from app.scheduler import jobs

collections_bp = Blueprint('collections', __name__)


@collections_bp.errorhandler(ValueError)
def invalid(error: ValueError) -> Any:
    return jsonify(error=str(error)), 400


@collections_bp.post('/api/collections/browse')
def browse() -> Any:
    return jsonify(collections.browse(body()))


@collections_bp.post('/api/collections/resolve')
def resolve() -> Any:
    return jsonify(collections.choose(body()))


@collections_bp.post('/api/<speaker>/collections/play')
def play(speaker: str) -> Any:
    data = body()
    volume = data.get('volume')
    if data.get('confirmed') is not True:
        raise favorites.FavoriteError('Confirm replacement of current playback on the selected speaker.')
    if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
        raise favorites.FavoriteError('Choose a listening volume from 0 through 100.')
    value = collections.validate_binding(data.get('collection'))
    if data.get('speaker_id') != value['speaker_id']:
        raise favorites.FavoriteError('Select and verify the speaker again.')
    collections.resolve(value, speaker)
    try:
        operation = jobs.queue_on(speaker, {
            'name': value['content']['name'], 'speaker_id': value['speaker_id'],
            'collection': value, 'source_kind': 'collection', 'volume': volume,
            'fade_in_duration': 2, 'fade_out_duration': 0, 'days': None,
            'on_time': None, 'off_time': None, 'paused': False,
        }, force=True)
    except jobs.StationRequestConflict as exc:
        return jsonify(error=str(exc)), 409
    if operation is None:
        return jsonify(error='Playback worker unavailable. No audio was started.'), 503
    return jsonify(operation=operation, state='accepted'), 202


@collections_bp.get('/api/<speaker>/collections/status')
def status(speaker: str) -> Any:
    operation = jobs.get_last_outcome(speaker)
    if operation and operation.get('collection_session') and operation.get('state') == 'unknown':
        playback.reconcile_collection_session(speaker, operation.get('speaker_id', ''),
                                             operation.get('operation_id', ''))
        operation = jobs.get_last_outcome(speaker)
    return jsonify(operation=operation)


@collections_bp.post('/api/<speaker>/collections/stop')
def stop(speaker: str) -> Any:
    data = body()
    if any(not isinstance(data.get(key), str) or not data[key] for key in ('speaker_id', 'operation_id')):
        raise favorites.FavoriteError('Select the current listening session before stopping.')
    try:
        operation = jobs.queue_collection_stop(speaker, data['speaker_id'], data['operation_id'])
    except jobs.StationWorkerUnavailable:
        return jsonify(error='Playback worker unavailable. No Stop was accepted.'), 503
    if operation is None:
        return jsonify(error='This session is no longer current. Refresh its status.'), 409
    return jsonify(operation=operation, state='accepted'), 202
