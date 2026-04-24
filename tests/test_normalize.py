from m365_owa_cli.owa.normalize import Event, normalize_event


def test_normalize_event_maps_representative_owa_fields():
    event = normalize_event(
        {
            "id": "AAMk-1",
            "subject": "Planning",
            "start": {"dateTime": "2026-04-24T10:00:00+02:00", "timeZone": "Europe/Oslo"},
            "end": {"dateTime": "2026-04-24T11:00:00+02:00", "timeZone": "Europe/Oslo"},
            "body": {"contentType": "html", "content": "<p>Hello</p>"},
            "categories": ["Deep Work"],
            "onlineMeeting": {"joinUrl": "https://teams.example/join"},
            "sensitivity": "normal",
            "recurrence": None,
        }
    )

    assert isinstance(event, Event)
    assert event.id == "AAMk-1"
    assert event.subject == "Planning"
    assert event.start == "2026-04-24T10:00:00+02:00"
    assert event.end == "2026-04-24T11:00:00+02:00"
    assert event.body == "<p>Hello</p>"
    assert event.body_type == "html"
    assert event.categories == ["Deep Work"]
    assert event.meeting_link == "https://teams.example/join"
    assert event.timezone == "Europe/Oslo"
    assert event.is_recurring is False
    assert event.is_occurrence is False
    assert event.is_private is False
    assert event.raw_owa is None


def test_normalize_event_marks_private_and_preserves_raw_when_requested():
    payload = {
        "id": "AAMk-2",
        "subject": "Private note",
        "start": "2026-04-24T12:00:00+02:00",
        "end": "2026-04-24T12:30:00+02:00",
        "sensitivity": "private",
        "occurrence_id": "AAMk-2/occurrence",
        "isRecurring": True,
        "isOccurrence": True,
    }
    event = normalize_event(payload, include_raw=True)

    assert event.is_private is True
    assert event.is_recurring is True
    assert event.is_occurrence is True
    assert event.occurrence_id == "AAMk-2/occurrence"
    assert event.raw_owa == payload


def test_normalize_event_treats_owa_exception_as_occurrence():
    event = normalize_event(
        {
            "ItemId": {"Id": "event-1"},
            "Subject": "Changed recurring event",
            "Start": "2026-04-24T10:00:00",
            "End": "2026-04-24T11:00:00",
            "IsRecurring": True,
            "CalendarItemType": "Exception",
        }
    )

    assert event.is_recurring is True
    assert event.is_occurrence is True
