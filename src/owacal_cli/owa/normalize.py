from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping

try:  # pragma: no cover - exercised when models.py exists
    from ..models import Event  # type: ignore
except Exception:  # pragma: no cover - fallback for this scaffold

    @dataclass(slots=True)
    class Event:  # type: ignore[no-redef]
        id: str | None
        occurrence_id: str | None = None
        subject: str | None = None
        start: str | None = None
        end: str | None = None
        body: str | None = None
        body_type: str | None = None
        categories: list[str] | None = None
        meeting_link: str | None = None
        timezone: str | None = None
        is_recurring: bool = False
        is_occurrence: bool = False
        is_private: bool = False
        raw_owa: dict[str, Any] | None = None


def _first_present(data: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _coerce_iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(text)
            except ValueError:
                return text
            return datetime.combine(parsed_date, datetime.min.time()).isoformat()
        return parsed.isoformat()
    return str(value)


def _extract_datetime_field(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, Mapping):
        tz = _first_present(value, ("timeZone", "timezone"))
        dt = _first_present(value, ("dateTime", "value", "datetime"))
        return _coerce_iso_datetime(dt), tz
    return _coerce_iso_datetime(value), None


def _extract_body(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, Mapping):
        body_type = _first_present(value, ("contentType", "bodyType", "type"))
        body = _first_present(value, ("content", "text", "body"))
        return (None if body is None else str(body)), (
            None if body_type is None else str(body_type).lower()
        )
    if value is None:
        return None, None
    return str(value), None


def _extract_categories(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _extract_meeting_link(data: Mapping[str, Any]) -> str | None:
    online_meeting = data.get("onlineMeeting")
    if isinstance(online_meeting, Mapping):
        for key in ("joinUrl", "join_url", "meetingLink"):
            if online_meeting.get(key):
                return str(online_meeting[key])
    for key in ("meeting_link", "meetingLink", "joinUrl", "onlineMeetingLink"):
        if data.get(key):
            return str(data[key])
    return None


def _is_private(data: Mapping[str, Any]) -> bool:
    if data.get("is_private") is not None:
        return bool(data["is_private"])
    sensitivity = data.get("sensitivity")
    if isinstance(sensitivity, str) and sensitivity.lower() == "private":
        return True
    if data.get("showAs") == "private":
        return True
    return False


def _is_recurring(data: Mapping[str, Any]) -> bool:
    if data.get("is_recurring") is not None:
        return bool(data["is_recurring"])
    if data.get("isRecurring") is not None:
        return bool(data["isRecurring"])
    if data.get("recurrence") is not None:
        return True
    if data.get("seriesMasterId") is not None:
        return True
    return False


def _is_occurrence(data: Mapping[str, Any]) -> bool:
    if data.get("is_occurrence") is not None:
        return bool(data["is_occurrence"])
    if data.get("isOccurrence") is not None:
        return bool(data["isOccurrence"])
    if data.get("occurrence_id") is not None:
        return True
    return False


def _construct_event(payload: dict[str, Any]) -> Event:
    try:
        return Event(**payload)  # type: ignore[misc]
    except TypeError:
        payload = dict(payload)
        payload.pop("raw_owa", None)
        return Event(**payload)  # type: ignore[misc]


def normalize_event(event: Mapping[str, Any], *, include_raw: bool = False) -> Event:
    start_value, timezone = _extract_datetime_field(
        _first_present(event, ("start", "Start"))
    )
    end_value, end_timezone = _extract_datetime_field(_first_present(event, ("end", "End")))
    body_value, body_type = _extract_body(_first_present(event, ("body", "Body")))
    categories = _extract_categories(_first_present(event, ("categories", "Categories")))
    meeting_link = _extract_meeting_link(event)
    normalized_timezone = _first_present(
        event,
        ("timezone", "timeZone", "TimeZone"),
    )
    if normalized_timezone is None:
        normalized_timezone = timezone or end_timezone
    payload: dict[str, Any] = {
        "id": _first_present(event, ("id", "Id", "itemId", "ItemId")),
        "occurrence_id": _first_present(
            event,
            ("occurrence_id", "occurrenceId", "OccurrenceId"),
        ),
        "subject": _first_present(event, ("subject", "Subject")),
        "start": start_value,
        "end": end_value,
        "body": body_value,
        "body_type": _first_present(event, ("body_type", "bodyType")) or body_type or "text",
        "categories": categories or [],
        "meeting_link": meeting_link,
        "timezone": normalized_timezone,
        "is_recurring": _is_recurring(event),
        "is_occurrence": _is_occurrence(event),
        "is_private": _is_private(event),
    }
    if include_raw:
        payload["raw_owa"] = dict(event)
    else:
        payload["raw_owa"] = None
    return _construct_event(payload)
