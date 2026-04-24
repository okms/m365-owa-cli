from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from owacal_cli.capabilities import capabilities_payload
from owacal_cli.models import Event
from owacal_cli.schemas import (
    commands_schema_payload,
    error_schema_payload,
    event_schema_payload,
    help_json_payload,
)


def test_event_schema_shape() -> None:
    schema = Event.model_json_schema()

    assert schema["title"] == "Event"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"subject", "start", "end"}

    properties = schema["properties"]
    assert properties["body_type"]["enum"] == ["text", "html", None]
    assert properties["categories"]["type"] == "array"
    assert properties["is_private"]["type"] == "boolean"
    assert "raw_owa" in properties


def test_capabilities_payload_shape() -> None:
    payload = capabilities_payload()

    assert payload["ok"] is True
    data = payload["data"]
    assert data["backend"] == "owa-service-svc"
    assert data["graph_supported"] is False
    assert data["default_calendar_only"] is True
    assert data["private_events_default"] == "excluded"
    assert data["recurring_series_update"] is False
    assert data["auth_methods"] == [
        "env",
        "token_file",
        "direct_token",
        "bookmarklet",
        "edge_best_effort",
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
    assert "events delete" in command_names

    assert event_payload["ok"] is True
    assert event_payload["data"]["name"] == "Event"
    assert event_payload["data"]["required_fields"] == ["subject", "start", "end"]
    assert event_payload["data"]["schema"]["properties"]["body_type"]["enum"][:2] == [
        "text",
        "html",
    ]

    assert error_payload["ok"] is True
    assert error_payload["data"]["count"] >= 10
    error_codes = {item["code"] for item in error_payload["data"]["errors"]}
    assert "INVALID_ARGUMENTS" in error_codes
    assert "SERIES_OPERATION_REFUSED" in error_codes

    assert help_payload["ok"] is True
    assert "commands" in help_payload["data"]
    assert "capabilities" in help_payload["data"]
    assert "schemas" in help_payload["data"]
