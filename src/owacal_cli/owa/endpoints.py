from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    action: str
    method: str
    path: str
    purpose: str
    query: Mapping[str, str]


ENDPOINTS: dict[str, EndpointSpec] = {
    "GetCalendarView": EndpointSpec(
        action="GetCalendarView",
        method="POST",
        path="/owa/service.svc",
        purpose="Fetch expanded calendar events for a date range",
        query={"action": "GetCalendarView", "app": "Calendar"},
    ),
    "GetEvent": EndpointSpec(
        action="GetEvent",
        method="POST",
        path="/owa/service.svc",
        purpose="Fetch a single calendar event",
        query={"action": "GetEvent", "app": "Calendar"},
    ),
    "SearchEvents": EndpointSpec(
        action="SearchEvents",
        method="POST",
        path="/owa/service.svc",
        purpose="Search calendar events with backend support",
        query={"action": "SearchEvents", "app": "Calendar"},
    ),
    "CreateEvent": EndpointSpec(
        action="CreateEvent",
        method="POST",
        path="/owa/service.svc",
        purpose="Create a calendar event",
        query={"action": "CreateEvent", "app": "Calendar"},
    ),
    "UpdateEvent": EndpointSpec(
        action="UpdateEvent",
        method="POST",
        path="/owa/service.svc",
        purpose="Update a calendar event or occurrence",
        query={"action": "UpdateEvent", "app": "Calendar"},
    ),
    "DeleteEvent": EndpointSpec(
        action="DeleteEvent",
        method="POST",
        path="/owa/service.svc",
        purpose="Delete a calendar event or occurrence",
        query={"action": "DeleteEvent", "app": "Calendar"},
    ),
}


def get_endpoint(action: str) -> EndpointSpec:
    try:
        return ENDPOINTS[action]
    except KeyError as exc:
        raise KeyError(f"Unknown OWA action {action!r}") from exc


def known_action_names() -> tuple[str, ...]:
    return tuple(ENDPOINTS.keys())
