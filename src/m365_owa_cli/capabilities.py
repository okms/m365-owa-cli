"""Static capability payloads for m365-owa-cli."""

from __future__ import annotations

from typing import Any

from m365_owa_cli.output import success_envelope


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
        "mailbox_categories_read": True,
        "mailbox_categories_details": True,
        "mailbox_categories_write": True,
        "mailbox_categories_write_backend": "outlook-rest-v2",
        "category_color_preservation": False,
        "mail_read": False,
        "mail_write": False,
        "mail_reactions": False,
        "mail_attachments": False,
        "mail_backend": "not_implemented",
        "contacts_read": False,
        "contacts_write": False,
        "contacts_favorites": False,
        "contacts_backend": "not_implemented",
        "route_families": {
            "owa_service_svc": True,
            "owa_service_svc_s": "recognized",
            "owa_graphql_gateway": "recognized",
            "owa_people_routes": "recognized",
            "microsoft_graph": False,
        },
        "auth_methods": [
            "env",
            "token_file",
            "direct_token",
            "bookmarklet",
            "browser_devtools_best_effort",
        ],
    }


def capabilities_payload() -> dict[str, Any]:
    return success_envelope(capabilities_data())
