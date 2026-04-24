"""Static capability payloads for owacal-cli."""

from __future__ import annotations

from typing import Any

from owacal_cli.output import success_envelope


def capabilities_data() -> dict[str, Any]:
    return {
        "backend": "owa-service-svc",
        "graph_supported": False,
        "default_calendar_only": True,
        "shared_calendars": False,
        "delegated_calendars": False,
        "private_events_default": "excluded",
        "recurring_occurrence_update": True,
        "recurring_series_update": False,
        "meeting_link_preserved": True,
        "auth_methods": [
            "env",
            "token_file",
            "direct_token",
            "edge_best_effort",
        ],
    }


def capabilities_payload() -> dict[str, Any]:
    return success_envelope(capabilities_data())
