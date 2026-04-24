from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

RangeType = Literal["iso_day", "iso_week"]


@dataclass(frozen=True, slots=True)
class TimeRange:
    range_type: RangeType
    start: date
    end: date
    timezone: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.range_type,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone": self.timezone,
            "source": self.source,
        }


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Expected ISO date or datetime, got {value!r}") from exc
    raise TypeError(f"Unsupported date value: {type(value).__name__}")


def _week_start(value: Any) -> date:
    parsed = _coerce_date(value)
    return parsed - timedelta(days=parsed.isoweekday() - 1)


def parse_day_range(value: Any, *, timezone: str | None = None) -> TimeRange:
    day = _coerce_date(value)
    return TimeRange(
        range_type="iso_day",
        start=day,
        end=day + timedelta(days=1),
        timezone=timezone,
        source=day.isoformat(),
    )


def parse_week_range(value: Any, *, timezone: str | None = None) -> TimeRange:
    if isinstance(value, str) and "-W" in value:
        try:
            year_text, week_text = value.split("-W", 1)
            start = date.fromisocalendar(int(year_text), int(week_text), 1)
        except ValueError as exc:
            raise ValueError(f"Expected ISO week or ISO date, got {value!r}") from exc
        source = value
    else:
        start = _week_start(value)
        source = _coerce_date(value).isoformat()
    return TimeRange(
        range_type="iso_week",
        start=start,
        end=start + timedelta(days=7),
        timezone=timezone,
        source=source,
    )


def parse_time_range(
    *,
    day: Any | None = None,
    week: Any | None = None,
    timezone: str | None = None,
) -> TimeRange:
    if (day is None and week is None) or (day is not None and week is not None):
        raise ValueError("Exactly one of day or week must be provided")
    if day is not None:
        return parse_day_range(day, timezone=timezone)
    return parse_week_range(week, timezone=timezone)
