from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from m365_owa_cli.capabilities import capabilities_payload
from m365_owa_cli.models import Contact, ContactFolder, Event, MailAttachment, MailFolder, MailMessage
from m365_owa_cli.owa.normalize import normalize_event
from m365_owa_cli.schemas import (
    contact_folder_schema_payload,
    contact_schema_payload,
    commands_schema_payload,
    error_schema_payload,
    event_schema_payload,
    help_json_payload,
    mail_attachment_schema_payload,
    mail_folder_schema_payload,
    mail_message_schema_payload,
)


def test_event_schema_shape() -> None:
    schema = Event.model_json_schema()

    assert schema["title"] == "Event"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"subject", "start", "end"}

    properties = schema["properties"]
    expected_properties = {
        "id",
        "occurrence_id",
        "series_master_id",
        "subject",
        "title",
        "start",
        "start_iso_local",
        "end",
        "end_iso_local",
        "is_all_day",
        "duration_minutes",
        "body",
        "body_type",
        "body_content_type",
        "body_preview",
        "categories",
        "location",
        "organizer",
        "sensitivity",
        "meeting_link",
        "timezone",
        "is_recurring",
        "is_occurrence",
        "is_series_master",
        "is_private",
        "raw_owa",
    }
    assert expected_properties <= set(properties)
    assert properties["body_type"]["enum"] == ["text", "html", None]
    assert properties["body_content_type"]["enum"] == ["text", "html", None]
    assert properties["categories"]["type"] == "array"
    assert properties["is_private"]["type"] == "boolean"
    assert "raw_owa" in properties


def test_mail_and_contact_schema_shapes() -> None:
    for model in (MailMessage, MailFolder, MailAttachment, Contact, ContactFolder):
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert "raw_owa" in schema["properties"]


def test_capabilities_payload_shape() -> None:
    payload = capabilities_payload()

    assert payload["ok"] is True
    data = payload["data"]
    assert data["backend"] == "owa-service-svc"
    assert data["graph_supported"] is False
    assert data["default_calendar_only"] is True
    assert data["private_events_default"] == "excluded"
    assert data["recurring_series_update"] is False
    assert data["mail_read"] is False
    assert data["mail_write"] is False
    assert data["contacts_read"] is False
    assert data["contacts_write"] is False
    assert data["route_families"]["microsoft_graph"] is False
    assert data["auth_methods"] == [
        "env",
        "token_file",
        "direct_token",
        "bookmarklet",
        "browser_devtools_best_effort",
    ]


def test_schema_payload_shapes() -> None:
    commands_payload = commands_schema_payload()
    event_payload = event_schema_payload()
    error_payload = error_schema_payload()
    help_payload = help_json_payload()

    assert commands_payload["ok"] is True
    assert commands_payload["data"]["count"] >= 10
    command_names = {item["name"] for item in commands_payload["data"]["commands"]}
    assert "events list" in command_names
    assert "schema event" in command_names
    assert "auth bookmarklet" in command_names
    assert "auth extract-token" in command_names
    assert "events delete" in command_names
    assert "categories list" in command_names
    assert "categories details" in command_names
    assert "categories delete" in command_names
    assert "categories upsert" in command_names
    assert "schema mail-message" in command_names
    assert "schema contact" in command_names
    assert "mail list" in command_names
    assert "contacts list" in command_names
    upsert_command = next(
        item for item in commands_payload["data"]["commands"] if item["name"] == "categories upsert"
    )
    assert upsert_command["required_args"] == ["--connection", "--name"]

    assert event_payload["ok"] is True
    assert event_payload["data"]["name"] == "Event"
    assert event_payload["data"]["required_fields"] == ["subject", "start", "end"]
    assert event_payload["data"]["schema"]["properties"]["body_type"]["enum"][:2] == [
        "text",
        "html",
    ]
    for payload in (
        mail_message_schema_payload(),
        mail_folder_schema_payload(),
        mail_attachment_schema_payload(),
        contact_schema_payload(),
        contact_folder_schema_payload(),
    ):
        assert payload["ok"] is True
        assert payload["data"]["schema"]["additionalProperties"] is False

    assert error_payload["ok"] is True
    assert error_payload["data"]["count"] >= 10
    error_codes = {item["code"] for item in error_payload["data"]["errors"]}
    assert "INVALID_ARGUMENTS" in error_codes
    assert "SERIES_OPERATION_REFUSED" in error_codes

    assert help_payload["ok"] is True
    assert "commands" in help_payload["data"]
    assert "capabilities" in help_payload["data"]
    assert "schemas" in help_payload["data"]


def test_event_schema_covers_normalized_event_output() -> None:
    event = normalize_event(
        {
            "ItemId": {"Id": "event-1"},
            "Subject": "Planning",
            "Start": "2026-04-24T10:00:00",
            "End": "2026-04-24T11:30:00",
            "IsAllDayEvent": False,
            "Body": {"BodyType": "HTML", "Value": "<p>Agenda</p>"},
            "Preview": "Agenda",
            "Categories": ["Deep Work"],
            "Location": {"DisplayName": "Room 1"},
            "Organizer": {"Mailbox": {"Name": "Ada"}},
            "Sensitivity": "Normal",
        }
    ).to_dict()
    schema = event_schema_payload()["data"]["schema"]

    assert set(event) <= set(schema["properties"])
    assert set(schema["required"]) <= set(event)
    assert event["title"] == "Planning"
    assert event["start_iso_local"] == "2026-04-24T10:00:00"
    assert event["end_iso_local"] == "2026-04-24T11:30:00"
    assert event["duration_minutes"] == 90
