from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..time_ranges import TimeRange


@dataclass(frozen=True, slots=True)
class OwaRequest:
    operation: str
    endpoint: str
    method: str = "POST"
    query: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "endpoint": self.endpoint,
            "method": self.method,
            "query": dict(self.query),
            "headers": dict(self.headers),
            "payload": dict(self.payload),
        }


def build_list_events_request(
    time_range: TimeRange,
    *,
    include_private: bool = False,
) -> OwaRequest:
    return OwaRequest(
        operation="events.list",
        endpoint="GetCalendarView",
        query={"type": time_range.range_type},
        payload={
            "range": time_range.to_dict(),
            "include_private": include_private,
        },
    )


def build_get_event_request(event_id: str, *, include_raw: bool = False) -> OwaRequest:
    return OwaRequest(
        operation="events.get",
        endpoint="GetEvent",
        payload={"id": event_id, "include_raw": include_raw},
    )


def build_search_events_request(
    query: str,
    *,
    time_range: TimeRange | None = None,
    include_private: bool = False,
) -> OwaRequest:
    payload: dict[str, Any] = {"query": query, "include_private": include_private}
    if time_range is not None:
        payload["range"] = time_range.to_dict()
    return OwaRequest(
        operation="events.search",
        endpoint="SearchEvents",
        payload=payload,
    )


def build_create_event_request(
    *,
    subject: str,
    start: str,
    end: str,
    body: str | None = None,
    body_type: str = "text",
    categories: list[str] | None = None,
) -> OwaRequest:
    return OwaRequest(
        operation="events.create",
        endpoint="CreateEvent",
        payload={
            "subject": subject,
            "start": start,
            "end": end,
            "body": body,
            "body_type": body_type,
            "categories": list(categories or []),
        },
    )


def build_update_event_request(
    *,
    event_id: str,
    subject: str | None = None,
    start: str | None = None,
    end: str | None = None,
    body: str | None = None,
    body_type: str | None = None,
    categories: list[str] | None = None,
) -> OwaRequest:
    return OwaRequest(
        operation="events.update",
        endpoint="UpdateEvent",
        payload={
            "id": event_id,
            "subject": subject,
            "start": start,
            "end": end,
            "body": body,
            "body_type": body_type,
            "categories": None if categories is None else list(categories),
        },
    )


def build_delete_event_request(
    *,
    event_id: str,
    confirm_event_id: str,
) -> OwaRequest:
    return OwaRequest(
        operation="events.delete",
        endpoint="DeleteEvent",
        payload={
            "id": event_id,
            "confirm_event_id": confirm_event_id,
        },
    )


def build_list_categories_request() -> OwaRequest:
    return OwaRequest(
        operation="categories.list",
        endpoint="GetMasterCategoryList",
    )


def build_category_details_request() -> OwaRequest:
    return OwaRequest(
        operation="categories.details",
        endpoint="FindCategoryDetails",
    )


def build_category_upsert_request(*, name: str) -> OwaRequest:
    return OwaRequest(
        operation="categories.upsert",
        endpoint="UpdateMasterCategoryList",
        payload={"name": name},
    )
