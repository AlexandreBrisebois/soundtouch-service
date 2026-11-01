"""Explicit user-directed NAS library lifecycle API."""
from typing import Any

from flask import Blueprint, jsonify

from app.api.favorites import body
from app.core import music_libraries

music_libraries_bp = Blueprint('music_libraries', __name__)


def _public_library(record: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {key: record[key] for key in ('id', 'name', 'added', 'visible_to', 'reconciliation_pending') if key in record}
    value['observations'] = {device_id: {key: observation[key] for key in
        ('speaker', 'state', 'source_id', 'observed_at', 'stale', 'reason') if key in observation}
        for device_id, observation in record.get('observations', {}).items()}
    if record.get('pending'):
        value['pending'] = {key: record['pending'][key] for key in
            ('action', 'speaker_id', 'state', 'created_at') if key in record['pending']}
    return value


def _result(value: dict[str, Any]) -> Any:
    public = {key: item for key, item in value.items() if key not in ('account', 'previous_accounts')}
    if 'libraries' in public:
        public['libraries'] = [_public_library(record) for record in public['libraries']]
    if 'library' in public:
        public['library'] = _public_library(public['library'])
    return jsonify(public)


@music_libraries_bp.errorhandler(ValueError)
def invalid(error: ValueError) -> tuple[Any, int]:
    return jsonify(error=str(error)), 400


@music_libraries_bp.get('/api/music-libraries')
def listing() -> Any:
    return _result(music_libraries.listing())


@music_libraries_bp.post('/api/music-libraries/discover')
def discover() -> Any:
    body()
    return _result(music_libraries.discover())


@music_libraries_bp.post('/api/music-libraries/<library_id>/check')
def check(library_id: str) -> Any:
    body()
    return _result(music_libraries.check(library_id))


def _target_fields(data: dict[str, Any]) -> tuple[str, str]:
    speaker, speaker_id = data.get('speaker'), data.get('speaker_id')
    if not isinstance(speaker, str) or not speaker.strip() or not isinstance(speaker_id, str) or not speaker_id.strip():
        raise ValueError('Choose a speaker with a verified identity.')
    return speaker, speaker_id


@music_libraries_bp.post('/api/music-libraries/<library_id>/add')
def add(library_id: str) -> Any:
    data = body()
    speaker, speaker_id = _target_fields(data)
    return _result(music_libraries.add(library_id, speaker, speaker_id,
                                      confirmed=data.get('confirmed') is True, retry=data.get('retry') is True))


@music_libraries_bp.post('/api/music-libraries/<library_id>/removal-plan')
def removal_plan(library_id: str) -> Any:
    data = body()
    speaker, speaker_id = _target_fields(data)
    return _result(music_libraries.removal_plan(library_id, speaker, speaker_id))


@music_libraries_bp.post('/api/music-libraries/<library_id>/remove')
def remove(library_id: str) -> Any:
    data = body()
    return _result(music_libraries.remove(library_id, data.get('plan_id', ''),
                                         confirmed=data.get('confirmed') is True, retry=data.get('retry') is True))
