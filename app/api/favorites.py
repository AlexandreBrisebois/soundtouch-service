"""Explicit user-driven native preset management; never changes source registration."""
from typing import Any
from urllib.parse import urlsplit
from flask import Blueprint, Response, jsonify, request
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


@favorites_bp.get('/api/stations')
def list_stations() -> Any:
    warnings: list[str] = []
    stations = favorites.stations(seed_warnings=warnings)
    return jsonify(stations=stations, removal_notice=favorites.REMOVAL_NOTICE, seed_warning=' '.join(warnings))


@favorites_bp.post('/api/stations')
def add_station() -> Any:
    data = body()
    return jsonify(station=favorites.add_station(data.get('name'), data.get('url'))), 201


@favorites_bp.delete('/api/stations/<station_id>')
def remove_station(station_id: str) -> Any:
    if body().get('confirmed') is not True:
        raise favorites.FavoriteError(favorites.REMOVAL_NOTICE)
    favorites.remove_station(station_id)
    return jsonify(removed=True, message=favorites.REMOVAL_NOTICE)


@favorites_bp.get('/api/stations/<station_id>/stream')
def station_stream(station_id: str) -> Any:
    response = jsonify(favorites.station_descriptor(station_id))
    response.headers['Cache-Control'] = 'no-store'
    return response


@favorites_bp.post('/api/<speaker_name>/stations/<station_id>/play')
def play_station(speaker_name: str, station_id: str) -> Any:
    if body().get('confirmed') is not True:
        raise favorites.FavoriteError('Confirm station playback at volume 5. For relay playback, stop current audio first.')
    from app.core import radio_relay
    item = favorites.station(station_id)
    found = favorites.device(speaker_name)
    ready = radio_relay.readiness(item['url'], found['ip'])
    if not ready['available']:
        raise favorites.FavoriteError(ready['reason'])
    operation = jobs.queue_station(speaker_name, found['device_id'], station_id)
    if operation is None:
        return jsonify(error='Playback worker unavailable. No station was started.'), 503
    return jsonify(operation=operation, state='accepted', message='Station playback requested. No speaker button was changed.'), 202


@favorites_bp.get('/api/<speaker_name>/stations/<station_id>/direct-test')
def direct_test_info(speaker_name: str, station_id: str) -> Any:
    from app.core import direct_radio, radio_stream
    item = favorites.station(station_id)
    favorites.device(speaker_name)
    try:
        radio_stream.candidate(item['url'])
        supported = True
    except radio_stream.StreamError:
        supported = False
    return jsonify(available=supported, experimental=True, warning=direct_radio.WARNING,
                   duration_seconds=10, target_volume=5, quiet_start_guaranteed=False,
                   physical_presets_supported=False, automatic_schedules_supported=False)


@favorites_bp.post('/api/<speaker_name>/stations/<station_id>/direct-test')
def direct_test(speaker_name: str, station_id: str) -> Any:
    from app.core import direct_radio, radio_stream
    data = body()
    if data.get('confirmed') is not True or data.get('accept_startup_volume_risk') is not True:
        raise favorites.FavoriteError(direct_radio.WARNING)
    item = favorites.station(station_id)
    radio_stream.candidate(item['url'])  # Validate before creating/canceling any operation.
    found = favorites.device(speaker_name)
    operation = jobs.queue_direct_radio_test(speaker_name, found['device_id'], station_id, item['url'])
    if operation is None:
        return jsonify(error='Playback worker unavailable. No test was started.'), 503
    return jsonify(operation=operation, state='accepted', warning=direct_radio.WARNING), 202


@favorites_bp.get('/api/radio-sessions/<token>/stream.mp3')
def radio_session_stream(token: str) -> Any:
    from app.core import radio_relay
    if request.method != 'GET':
        return jsonify(error='Only GET is supported.'), 405
    # Current container uses Werkzeug's threaded server. Refuse servers where
    # lifecycle cancellation cannot interrupt a blocked downstream socket.
    try:
        chunks, cleanup = radio_relay.consumer(token, request.remote_addr,
                                               request.environ.get('werkzeug.socket'))
    except radio_relay.RelayError:
        return jsonify(error='Radio stream unavailable.'), 410
    response = Response(chunks, content_type='audio/mpeg')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.call_on_close(cleanup)
    return response


@favorites_bp.get('/api/<speaker_name>/stations/<station_id>/readiness')
def station_readiness(speaker_name: str, station_id: str) -> Any:
    from app.core import radio_relay
    item = favorites.station(station_id)
    found = favorites.device(speaker_name)
    response = jsonify(radio_relay.readiness(item['url'], found['ip']))
    response.headers['Cache-Control'] = 'no-store'
    return response
