"""Machine-readable schema payloads for owacal-cli."""

from __future__ import annotations

from typing import Any

from owacal_cli.capabilities import capabilities_data
from owacal_cli.errors import stable_error_specs
from owacal_cli.models import Event
from owacal_cli.output import success_envelope


COMMAND_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "capabilities",
        "summary": "Return build capability metadata.",
        "required_args": [],
        "optional_args": [],
    },
    {
        "name": "schema commands",
        "summary": "Return the command inventory.",
        "required_args": [],
        "optional_args": [],
    },
    {
        "name": "schema event",
        "summary": "Return the normalized event schema.",
        "required_args": [],
        "optional_args": [],
    },
    {
        "name": "schema errors",
        "summary": "Return stable error codes and exit codes.",
        "required_args": [],
        "optional_args": [],
    },
    {
        "name": "auth list-connections",
        "summary": "List configured connections.",
        "required_args": [],
        "optional_args": ["--connection"],
    },
    {
        "name": "auth set-token",
        "summary": "Store a connection token.",
        "required_args": ["--connection"],
        "optional_args": ["--token"],
    },
    {
        "name": "auth bookmarklet",
        "summary": "Generate a browser bookmarklet for manual OWA bearer capture.",
        "required_args": ["--connection"],
        "optional_args": ["--raw"],
    },
    {
        "name": "auth remove-token",
        "summary": "Remove a connection token.",
        "required_args": ["--connection"],
        "optional_args": [],
    },
    {
        "name": "auth test",
        "summary": "Test authentication for a connection.",
        "required_args": ["--connection"],
        "optional_args": [],
    },
    {
        "name": "auth extract-token",
        "summary": "Best-effort browser token extraction.",
        "required_args": ["--connection"],
        "optional_args": ["--browser"],
    },
    {
        "name": "events list",
        "summary": "List expanded events for a date range.",
        "required_args": ["--connection", "--day|--week"],
        "optional_args": ["--include-private", "--include-raw"],
    },
    {
        "name": "events get",
        "summary": "Fetch a single event or occurrence.",
        "required_args": ["--connection", "--id"],
        "optional_args": ["--include-raw"],
    },
    {
        "name": "events search",
        "summary": "Search events by text.",
        "required_args": ["--connection", "--query"],
        "optional_args": ["--from", "--to", "--include-private", "--include-raw"],
    },
    {
        "name": "events create",
        "summary": "Create a new event.",
        "required_args": ["--connection", "--subject", "--start", "--end"],
        "optional_args": ["--body", "--body-file", "--body-type", "--category", "--dry-run"],
    },
    {
        "name": "events update",
        "summary": "Update an existing event or occurrence.",
        "required_args": ["--connection", "--id"],
        "optional_args": ["--subject", "--start", "--end", "--body", "--body-file", "--body-type", "--category", "--dry-run"],
    },
    {
        "name": "events delete",
        "summary": "Delete an event or occurrence.",
        "required_args": ["--connection", "--id", "--confirm-event-id"],
        "optional_args": [],
    },
]


def commands_schema_data() -> dict[str, Any]:
    return {
        "commands": COMMAND_SCHEMA,
        "count": len(COMMAND_SCHEMA),
    }


def event_schema_data() -> dict[str, Any]:
    return {
        "name": "Event",
        "required_fields": ["subject", "start", "end"],
        "schema": Event.model_json_schema(),
    }


def error_schema_data() -> dict[str, Any]:
    return {
        "errors": stable_error_specs(),
        "count": len(stable_error_specs()),
    }


def commands_schema_payload() -> dict[str, Any]:
    return success_envelope(commands_schema_data())


def event_schema_payload() -> dict[str, Any]:
    return success_envelope(event_schema_data())


def error_schema_payload() -> dict[str, Any]:
    return success_envelope(error_schema_data())


def help_json_payload() -> dict[str, Any]:
    return success_envelope(
        {
            "commands": COMMAND_SCHEMA,
            "capabilities": capabilities_data(),
            "schemas": {
                "commands": commands_schema_data(),
                "event": event_schema_data(),
                "errors": error_schema_data(),
            },
        }
    )
