from typing import NotRequired, Required, TypedDict


class Schedule(TypedDict):
    name: str
    days: list[str] | None
    on_time: str | None
    off_time: str | None
    preset: int | None
    source: str | None
    volume: int
    fade_in_duration: float
    fade_out_duration: float
    paused: bool


class SchedulePayload(TypedDict, total=False):
    name: str
    previous_name: str | None
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


class ConfigDocument(TypedDict):
    version: int
    schedules: dict[str, list[Schedule]]
