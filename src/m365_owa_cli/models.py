"""Normalized data models for m365-owa-cli."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    occurrence_id: str | None = None
    series_master_id: str | None = None
    subject: str | None = Field(default=...)
    title: str | None = None
    start: str | None = Field(default=...)
    start_iso_local: str | None = None
    end: str | None = Field(default=...)
    end_iso_local: str | None = None
    is_all_day: bool = False
    duration_minutes: int | None = None
    body: str | None = None
    body_type: str | None = None
    body_content_type: str | None = None
    body_preview: str | None = None
    categories: list[str] = Field(default_factory=list)
    location: str | None = None
    organizer: str | None = None
    sensitivity: str | None = None
    meeting_link: str | None = None
    timezone: str | None = None
    is_recurring: bool = False
    is_occurrence: bool = False
    is_series_master: bool = False
    is_private: bool = False
    raw_owa: Any = None

    BODY_TYPES: ClassVar[tuple[str, str]] = ("text", "html")

    @field_validator("categories", mode="before")
    @classmethod
    def _validate_categories(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)

    @field_validator("body_type", mode="before")
    @classmethod
    def _validate_body_type(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).lower()
        if text not in cls.BODY_TYPES:
            raise ValueError("body_type must be text or html")
        return text

    @field_validator("body_content_type", mode="before")
    @classmethod
    def _validate_body_content_type(cls, value: Any) -> str | None:
        return cls._validate_body_type(value)

    def model_dump(  # type: ignore[override]
        self,
        *,
        include_none: bool = False,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", not include_none)
        payload = super().model_dump(**kwargs)
        if include_raw:
            payload["raw_owa"] = _json_safe(self.raw_owa)
        else:
            payload.pop("raw_owa", None)
        return payload

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        return self.model_dump(include_none=False, include_raw=include_raw)

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        return {
            "title": "Event",
            "type": "object",
            "additionalProperties": False,
            "required": ["subject", "start", "end"],
            "properties": {
                "id": {"type": ["string", "null"]},
                "occurrence_id": {"type": ["string", "null"]},
                "series_master_id": {"type": ["string", "null"]},
                "subject": {"type": ["string", "null"]},
                "title": {"type": ["string", "null"]},
                "start": {"type": ["string", "null"], "format": "date-time"},
                "start_iso_local": {"type": ["string", "null"], "format": "date-time"},
                "end": {"type": ["string", "null"], "format": "date-time"},
                "end_iso_local": {"type": ["string", "null"], "format": "date-time"},
                "is_all_day": {"type": "boolean"},
                "duration_minutes": {"type": ["integer", "null"]},
                "body": {"type": ["string", "null"]},
                "body_type": {
                    "type": ["string", "null"],
                    "enum": ["text", "html", None],
                },
                "body_content_type": {
                    "type": ["string", "null"],
                    "enum": ["text", "html", None],
                },
                "body_preview": {"type": ["string", "null"]},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "location": {"type": ["string", "null"]},
                "organizer": {"type": ["string", "null"]},
                "sensitivity": {"type": ["string", "null"]},
                "meeting_link": {"type": ["string", "null"]},
                "timezone": {"type": ["string", "null"]},
                "is_recurring": {"type": "boolean"},
                "is_occurrence": {"type": "boolean"},
                "is_series_master": {"type": "boolean"},
                "is_private": {"type": "boolean"},
                "raw_owa": {},
            },
        }


class Category(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    color: str | None = None
    raw_owa: Any = None

    def model_dump(  # type: ignore[override]
        self,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = super().model_dump(**kwargs)
        if include_raw:
            payload["raw_owa"] = _json_safe(self.raw_owa)
        else:
            payload.pop("raw_owa", None)
        return payload

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        return self.model_dump(include_raw=include_raw)


@dataclass(slots=True)
class ResponseEnvelope:
    ok: bool = True
    data: Any = None
    connection: str | None = None
    operation: str | None = None
    range: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.connection is not None:
            payload["connection"] = self.connection
        if self.operation is not None:
            payload["operation"] = self.operation
        if self.range is not None:
            payload["range"] = _json_safe(self.range)
        payload["data"] = _json_safe(self.data)
        return payload


@dataclass(slots=True)
class ErrorEnvelope:
    ok: bool = False
    error: dict[str, Any] = field(default_factory=dict)
    connection: str | None = None
    operation: str | None = None
    range: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, "error": _json_safe(self.error)}
        if self.connection is not None:
            payload["connection"] = self.connection
        if self.operation is not None:
            payload["operation"] = self.operation
        if self.range is not None:
            payload["range"] = _json_safe(self.range)
        return payload


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
