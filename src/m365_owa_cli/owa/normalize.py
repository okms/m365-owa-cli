from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping

try:  # pragma: no cover - exercised when models.py exists
    from ..models import Category, CategoryDetail, Event  # type: ignore
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
        body_type = _first_present(value, ("contentType", "bodyType", "BodyType", "type"))
        body = _first_present(value, ("content", "text", "body", "Value"))
        return (None if body is None else str(body)), (
            None if body_type is None else str(body_type).lower()
        )
    if value is None:
        return None, None
    return str(value), None


def _extract_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("DisplayName", "displayName", "Name", "name", "EmailAddress", "emailAddress"):
            if value.get(key):
                return str(value[key])
        mailbox = value.get("Mailbox") or value.get("mailbox")
        if isinstance(mailbox, Mapping):
            return _extract_text(mailbox)
    return str(value)


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


def _extract_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("Id", "id"):
            if value.get(key):
                return str(value[key])
        return None
    if value is None:
        return None
    return str(value)


def _is_private(data: Mapping[str, Any]) -> bool:
    if data.get("is_private") is not None:
        return bool(data["is_private"])
    sensitivity = _first_present(data, ("sensitivity", "Sensitivity"))
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
    if data.get("IsRecurring") is not None:
        return bool(data["IsRecurring"])
    if data.get("recurrence") is not None:
        return True
    if _first_present(data, ("seriesMasterId", "SeriesMasterItemId", "SeriesId")) is not None:
        return True
    return False


def _is_occurrence(data: Mapping[str, Any]) -> bool:
    if data.get("is_occurrence") is not None:
        return bool(data["is_occurrence"])
    if data.get("isOccurrence") is not None:
        return bool(data["isOccurrence"])
    if data.get("IsOccurrence") is not None:
        return bool(data["IsOccurrence"])
    if data.get("occurrence_id") is not None:
        return True
    calendar_item_type = data.get("CalendarItemType")
    if isinstance(calendar_item_type, str) and calendar_item_type.lower() in {
        "exception",
        "occurrence",
    }:
        return True
    return False


def _is_series_master(data: Mapping[str, Any]) -> bool:
    if data.get("is_series_master") is not None:
        return bool(data["is_series_master"])
    if data.get("isSeriesMaster") is not None:
        return bool(data["isSeriesMaster"])
    calendar_item_type = data.get("CalendarItemType")
    return isinstance(calendar_item_type, str) and calendar_item_type.lower() == "recurringmaster"


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    if start is None or end is None:
        return None
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((end_dt - start_dt).total_seconds() // 60)


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
    body_preview = _first_present(event, ("body_preview", "bodyPreview", "BodyPreview", "Preview", "preview"))
    categories = _extract_categories(_first_present(event, ("categories", "Categories")))
    meeting_link = _extract_meeting_link(event)
    normalized_timezone = _first_present(
        event,
        ("timezone", "timeZone", "TimeZone"),
    )
    if normalized_timezone is None:
        normalized_timezone = timezone or end_timezone
    subject = _first_present(event, ("subject", "Subject", "title", "Title"))
    sensitivity = _first_present(event, ("sensitivity", "Sensitivity"))
    payload: dict[str, Any] = {
        "id": _extract_id(_first_present(event, ("id", "Id", "itemId", "ItemId"))),
        "occurrence_id": _extract_id(
            _first_present(
                event,
                ("occurrence_id", "occurrenceId", "OccurrenceId", "InstanceKey"),
            )
        ),
        "series_master_id": _extract_id(
            _first_present(event, ("series_master_id", "seriesMasterId", "SeriesMasterItemId", "SeriesId"))
        ),
        "subject": subject,
        "title": _first_present(event, ("title", "Title")) or subject,
        "start": start_value,
        "start_iso_local": _first_present(event, ("start_iso_local", "startIsoLocal")) or start_value,
        "end": end_value,
        "end_iso_local": _first_present(event, ("end_iso_local", "endIsoLocal")) or end_value,
        "is_all_day": bool(_first_present(event, ("is_all_day", "isAllDay", "IsAllDayEvent")) or False),
        "duration_minutes": _first_present(event, ("duration_minutes", "durationMinutes"))
        or _duration_minutes(start_value, end_value),
        "body": body_value or body_preview,
        "body_type": _first_present(event, ("body_type", "bodyType")) or body_type or "text",
        "body_content_type": _first_present(event, ("body_content_type", "bodyContentType"))
        or _first_present(event, ("body_type", "bodyType"))
        or body_type
        or "text",
        "body_preview": None if body_preview is None else str(body_preview),
        "categories": categories or [],
        "location": _extract_text(_first_present(event, ("location", "Location"))),
        "organizer": _extract_text(_first_present(event, ("organizer", "Organizer"))),
        "sensitivity": None if sensitivity is None else str(sensitivity),
        "meeting_link": meeting_link,
        "timezone": normalized_timezone,
        "is_recurring": _is_recurring(event),
        "is_occurrence": _is_occurrence(event),
        "is_series_master": _is_series_master(event),
        "is_private": _is_private(event),
    }
    if include_raw:
        payload["raw_owa"] = dict(event)
    else:
        payload["raw_owa"] = None
    return _construct_event(payload)


def normalize_category(category: Mapping[str, Any], *, include_raw: bool = False) -> Category:
    name = _first_present(category, ("name", "Name", "Category", "displayName", "DisplayName"))
    color = _first_present(category, ("color", "Color", "categoryColor", "CategoryColor"))
    payload: dict[str, Any] = {
        "name": "" if name is None else str(name),
        "color": None if color is None else str(color),
        "raw_owa": dict(category) if include_raw else None,
    }
    return Category(**payload)


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def normalize_category_detail(category: Mapping[str, Any], *, include_raw: bool = False) -> CategoryDetail:
    name = _first_present(category, ("name", "Name", "Category", "displayName", "DisplayName"))
    color = _first_present(category, ("color", "Color", "categoryColor", "CategoryColor"))
    item_count = _first_present(
        category,
        ("item_count", "itemCount", "ItemCount", "TotalCount", "Count"),
    )
    unread_count = _first_present(category, ("unread_count", "unreadCount", "UnreadCount"))
    is_search_folder_ready = _first_present(
        category,
        (
            "is_search_folder_ready",
            "isSearchFolderReady",
            "IsSearchFolderReady",
            "SearchFolderReady",
        ),
    )
    payload: dict[str, Any] = {
        "name": "" if name is None else str(name),
        "color": None if color is None else str(color),
        "item_count": _coerce_int(item_count),
        "unread_count": _coerce_int(unread_count),
        "is_search_folder_ready": bool(is_search_folder_ready),
        "raw_owa": dict(category) if include_raw else None,
    }
    return CategoryDetail(**payload)
