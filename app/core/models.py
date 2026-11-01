from typing import Any, TypedDict
from typing_extensions import NotRequired, Required


class Schedule(TypedDict):
    speaker_id: NotRequired[str]
    favorite_id: NotRequired[str]
    station_id: NotRequired[str]
    collection: NotRequired[dict[str, Any]]
    source_kind: NotRequired[str]
    source_error: NotRequired[str]
    review_reason: NotRequired[str]
    review_token: NotRequired[str]
    name: str
    days: list[str] | None
    on_time: str | None
    off_time: str | None
    preset: NotRequired[int | None]
    source: NotRequired[str | None]
    volume: int
    fade_in_duration: float
    fade_out_duration: float
    paused: bool


class SchedulePayload(TypedDict, total=False):
    speaker_id: str
    favorite_id: str
    station_id: str
    collection: dict[str, Any]
    source_kind: str
    source_error: str
    review_reason: str
    review_token: str
    name: str
    previous_name: str | None
    previous_speaker: str | None
    days: list[str] | None
    on_time: str | None
    off_time: str | None
    preset: int | None
    source: str | None
    volume: int
    fade_in_duration: float
    fade_out_duration: float
    paused: bool


class ConfigMutation(TypedDict):
    action: Required[str]
    speaker: Required[str]
    schedule_name: Required[str]
    data: NotRequired[Schedule]
    previous_name: NotRequired[str | None]
    review_confirmed: NotRequired[bool]
    expected_review_token: NotRequired[str | None]
    previous_speaker: NotRequired[str | None]
    expected_origin_revision: NotRequired[str]


class ConfigDocument(TypedDict):
    version: int
    schedules: dict[str, list[Schedule]]

