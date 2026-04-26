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
    "GetCalendarFolders": EndpointSpec(
        action="GetCalendarFolders",
        method="POST",
        path="/owa/service.svc",
        purpose="Fetch calendar folders so the default calendar id can be resolved",
        query={"action": "GetCalendarFolders", "app": "Calendar"},
    ),
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
    "CreateItem": EndpointSpec(
        action="CreateItem",
        method="POST",
        path="/owa/service.svc",
        purpose="Create a calendar item in the default calendar",
        query={"action": "CreateItem", "app": "Calendar"},
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
    "DeleteItem": EndpointSpec(
        action="DeleteItem",
        method="POST",
        path="/owa/service.svc",
        purpose="Delete an item by id using OWA's generic item deletion action",
        query={"action": "DeleteItem", "app": "Calendar"},
    ),
    "GetMasterCategoryList": EndpointSpec(
        action="GetMasterCategoryList",
        method="POST",
        path="/owa/service.svc",
        purpose="Fetch mailbox master category names, colors, ids, and keyboard shortcuts",
        query={"action": "GetMasterCategoryList", "app": "Mail"},
    ),
    "FindCategoryDetails": EndpointSpec(
        action="FindCategoryDetails",
        method="POST",
        path="/owa/service.svc",
        purpose="Fetch category usage counts for mailbox items",
        query={"action": "FindCategoryDetails", "app": "Mail"},
    ),
    "UpdateMasterCategoryList": EndpointSpec(
        action="UpdateMasterCategoryList",
        method="POST",
        path="/owa/service.svc",
        purpose="Investigated OWA service action; returns success for some shapes without mutating the master list",
        query={"action": "UpdateMasterCategoryList", "app": "Mail"},
    ),
    "OutlookRestMasterCategories": EndpointSpec(
        action="OutlookRestMasterCategories",
        method="POST",
        path="/api/v2.0/me/MasterCategories",
        purpose="Create mailbox master categories through Outlook REST v2 when missing",
        query={},
    ),
}


def get_endpoint(action: str) -> EndpointSpec:
    try:
        return ENDPOINTS[action]
    except KeyError as exc:
        raise KeyError(f"Unknown OWA action {action!r}") from exc


def known_action_names() -> tuple[str, ...]:
    return tuple(ENDPOINTS.keys())
