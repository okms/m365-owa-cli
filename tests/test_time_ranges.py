from datetime import date, datetime

import pytest

from owacal_cli.time_ranges import parse_day_range, parse_time_range, parse_week_range


def test_parse_day_range_returns_exclusive_next_midnight():
    result = parse_day_range("2026-04-24")
    assert result.range_type == "iso_day"
    assert result.start == date(2026, 4, 24)
    assert result.end == date(2026, 4, 25)
    assert result.to_dict() == {
        "type": "iso_day",
        "start": "2026-04-24",
        "end": "2026-04-25",
        "timezone": None,
        "source": "2026-04-24",
    }


def test_parse_week_range_from_iso_week_uses_monday_boundary():
    result = parse_week_range("2026-W17")
    assert result.range_type == "iso_week"
    assert result.start == date(2026, 4, 20)
    assert result.end == date(2026, 4, 27)


def test_parse_week_range_from_date_inside_week_uses_same_iso_week():
    result = parse_week_range("2026-04-24")
    assert result.start == date(2026, 4, 20)
    assert result.end == date(2026, 4, 27)
    assert result.source == "2026-04-24"


def test_parse_week_range_handles_year_boundary():
    result = parse_week_range("2020-12-31")
    assert result.start == date(2020, 12, 28)
    assert result.end == date(2021, 1, 4)


def test_parse_time_range_accepts_datetime_input_for_day():
    result = parse_time_range(day=datetime(2026, 4, 24, 15, 30))
    assert result.start == date(2026, 4, 24)
    assert result.end == date(2026, 4, 25)


def test_parse_time_range_rejects_missing_or_ambiguous_inputs():
    with pytest.raises(ValueError, match="Exactly one"):
        parse_time_range()
    with pytest.raises(ValueError, match="Exactly one"):
        parse_time_range(day="2026-04-24", week="2026-W17")
