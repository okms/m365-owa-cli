"""Normalized data models for owacal-cli."""

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
    subject: str | None = Field(default=...)
    start: str | None = Field(default=...)
    end: str | None = Field(default=...)
    body: str | None = None
    body_type: str | None = None
    categories: list[str] = Field(default_factory=list)
    meeting_link: str | None = None
    timezone: str | None = None
    is_recurring: bool = False
    is_occurrence: bool = False
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
                "subject": {"type": ["string", "null"]},
                "start": {"type": ["string", "null"], "format": "date-time"},
                "end": {"type": ["string", "null"], "format": "date-time"},
                "body": {"type": ["string", "null"]},
                "body_type": {
                    "type": ["string", "null"],
                    "enum": ["text", "html", None],
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "meeting_link": {"type": ["string", "null"]},
                "timezone": {"type": ["string", "null"]},
                "is_recurring": {"type": "boolean"},
                "is_occurrence": {"type": "boolean"},
                "is_private": {"type": "boolean"},
                "raw_owa": {},
            },
        }


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
