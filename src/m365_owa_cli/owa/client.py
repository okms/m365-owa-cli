from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, urlencode

import httpx

from m365_owa_cli.errors import (
    AUTH_EXPIRED,
    NORMALIZATION_ERROR,
    NOT_FOUND,
    OWA_BACKEND_ERROR,
    OWA_ENDPOINT_NOT_IMPLEMENTED,
    M365OwaError,
    redact_tokens,
)

from .endpoints import get_endpoint
from .normalize import normalize_category, normalize_category_detail, normalize_event
from .requests import (
    OwaRequest,
    build_category_details_request,
    build_category_delete_request,
    build_category_upsert_request,
    build_create_event_request,
    build_delete_event_request,
    build_contact_folders_request,
    build_contact_get_request,
    build_contacts_list_request as build_contacts_list_owa_request,
    build_contacts_search_request as build_contacts_search_owa_request,
    build_get_event_request,
    build_list_categories_request,
    build_list_events_request,
    build_mail_folders_request,
    build_mail_get_request,
    build_mail_list_request,
    build_mail_search_request,
    build_search_events_request,
    build_update_event_request,
)


def _redact_value(value: Any) -> Any:
    return redact_tokens(value)


def _ensure_bearer(token: str | None) -> str | None:
    if token is None:
        return None
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def _format_owa_range_boundary(value: Any, *, end: bool = False) -> str:
    if isinstance(value, datetime):
        base = value.replace(tzinfo=None).isoformat(timespec="seconds")
    elif isinstance(value, date):
        base = f"{value.isoformat()}T00:00:00"
    else:
        text = str(value)
        if "T" in text:
            base = text.split("+", 1)[0].replace("Z", "")
        else:
            base = f"{text}T00:00:00"
    suffix = ".000" if end else ".001"
    return base.split(".", 1)[0] + suffix


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                return None
            return datetime.combine(parsed_date, datetime.min.time())
    return None


def _format_create_datetime(value: Any) -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return str(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(timespec="seconds") + ".000"


def _is_all_day_range(start: Any, end: Any) -> bool:
    parsed_start = _coerce_datetime(start)
    parsed_end = _coerce_datetime(end)
    if parsed_start is None or parsed_end is None:
        return False
    if parsed_start.tzinfo is not None:
        parsed_start = parsed_start.astimezone(timezone.utc).replace(tzinfo=None)
    if parsed_end.tzinfo is not None:
        parsed_end = parsed_end.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        parsed_start.time() == datetime.min.time()
        and parsed_end.time() == datetime.min.time()
        and (parsed_end - parsed_start).days >= 1
        and (parsed_end - parsed_start).seconds == 0
    )


class OWAEndpointNotImplementedError(M365OwaError):
    def __init__(
        self,
        message: str = "This OWA endpoint is not implemented yet.",
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            OWA_ENDPOINT_NOT_IMPLEMENTED,
            message,
            retryable=False,
            details=dict(details or {}),
        )


class OWAClient:
    def __init__(
        self,
        *,
        connection: str | None = None,
        token: str | None = None,
        base_url: str = "https://outlook.cloud.microsoft",
        rest_base_url: str = "https://outlook.office.com",
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.connection = connection
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.rest_base_url = rest_base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        token = "***REDACTED***" if self.token else None
        return f"OWAClient(connection={self.connection!r}, token={token!r}, base_url={self.base_url!r})"

    def _not_implemented(self, operation: str, endpoint_name: str, **details: Any) -> None:
        endpoint = get_endpoint(endpoint_name)
        payload = {
            "operation": operation,
            "endpoint": {
                "action": endpoint.action,
                "method": endpoint.method,
                "path": endpoint.path,
                "query": dict(endpoint.query),
            },
            "connection": self.connection,
            "auth": {
                "has_token": self.token is not None,
                "token": "[REDACTED]" if self.token else None,
            },
        }
        payload.update(details)
        raise OWAEndpointNotImplementedError(details=_redact_value(payload))

    def _headers(self, action: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Action": action,
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        authorization = _ensure_bearer(self.token)
        if authorization:
            headers["Authorization"] = authorization
        return headers

    def _url(self, endpoint_name: str) -> str:
        endpoint = get_endpoint(endpoint_name)
        query = urlencode(dict(endpoint.query))
        return f"{self.base_url}{endpoint.path}?{query}"

    def _post_json(self, endpoint_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        endpoint = get_endpoint(endpoint_name)
        url = self._url(endpoint_name)
        try:
            response = self.http_client.post(
                url,
                headers=self._headers(endpoint.action),
                json=dict(payload),
            )
        except httpx.HTTPError as exc:
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                f"OWA request failed for {endpoint.action}.",
                retryable=True,
                details={
                    "action": endpoint.action,
                    "url": url,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                },
            ) from exc

        details: dict[str, Any] = {
            "action": endpoint.action,
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
        }
        if response.status_code in {401, 403}:
            raise M365OwaError(
                AUTH_EXPIRED,
                "OWA bearer token expired or was rejected.",
                retryable=False,
                details=details,
            )

        try:
            data = response.json()
        except ValueError as exc:
            details["response_preview"] = response.text[:500]
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "OWA returned a non-JSON response.",
                retryable=response.status_code >= 500,
                details=details,
            ) from exc

        body = data.get("Body") if isinstance(data, Mapping) else None
        response_code = body.get("ResponseCode") if isinstance(body, Mapping) else None
        response_class = body.get("ResponseClass") if isinstance(body, Mapping) else None
        if response.status_code >= 400 or (
            isinstance(response_code, str) and response_code.lower() != "noerror"
        ):
            details["owa_response"] = data
            message = "OWA returned an error response."
            if response_code:
                message = f"OWA returned {response_code}."
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                message,
                retryable=response.status_code >= 500 or response_class == "Error",
                details=details,
            )
        return dict(data)

    def _rest_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }
        authorization = _ensure_bearer(self.token)
        if authorization:
            headers["Authorization"] = authorization
        return headers

    def _post_rest_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        url = f"{self.rest_base_url}{path}"
        try:
            response = self.http_client.post(url, headers=self._rest_headers(), json=dict(payload))
        except httpx.HTTPError as exc:
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST request failed.",
                retryable=True,
                details={
                    "url": url,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                },
            ) from exc

        details: dict[str, Any] = {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
        }
        if response.status_code in {401, 403}:
            raise M365OwaError(
                AUTH_EXPIRED,
                "Outlook bearer token expired or was rejected.",
                retryable=False,
                details=details,
            )

        try:
            data = response.json()
        except ValueError as exc:
            details["response_preview"] = response.text[:500]
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST returned a non-JSON response.",
                retryable=response.status_code >= 500,
                details=details,
            ) from exc

        if response.status_code >= 400:
            details["outlook_response"] = data
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST returned an error response.",
                retryable=response.status_code >= 500,
                details=details,
            )
        return dict(data)

    def _delete_rest(self, path: str) -> None:
        url = f"{self.rest_base_url}{path}"
        try:
            response = self.http_client.delete(url, headers=self._rest_headers())
        except httpx.HTTPError as exc:
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST delete request failed.",
                retryable=True,
                details={
                    "url": url,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                },
            ) from exc

        details: dict[str, Any] = {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
        }
        if response.status_code in {401, 403}:
            raise M365OwaError(
                AUTH_EXPIRED,
                "Outlook bearer token expired or was rejected.",
                retryable=False,
                details=details,
            )
        if response.status_code == 404:
            raise M365OwaError(
                NOT_FOUND,
                "Outlook REST category delete target was not found.",
                retryable=False,
                details=details,
            )
        if response.status_code >= 400:
            try:
                details["outlook_response"] = response.json()
            except ValueError:
                details["response_preview"] = response.text[:500]
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST returned an error response.",
                retryable=response.status_code >= 500,
                details=details,
            )

    def get_default_calendar_folder_id(self) -> dict[str, Any]:
        data = self._post_json("GetCalendarFolders", {})
        groups = data.get("CalendarGroups")
        if not isinstance(groups, list):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA calendar folder response did not include CalendarGroups.",
                details={"response_keys": sorted(data.keys())},
            )
        fallback: dict[str, Any] | None = None
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            calendars = group.get("Calendars")
            if not isinstance(calendars, list):
                continue
            for calendar in calendars:
                if not isinstance(calendar, Mapping):
                    continue
                folder_id = calendar.get("CalendarFolderId")
                if isinstance(folder_id, Mapping) and folder_id.get("Id"):
                    if fallback is None:
                        fallback = dict(folder_id)
                    if calendar.get("IsDefaultCalendar"):
                        return dict(folder_id)
        if fallback is not None:
            return fallback
        raise M365OwaError(
            NORMALIZATION_ERROR,
            "OWA calendar folder response did not include a usable calendar folder id.",
            details={"calendar_group_count": len(groups)},
        )

    def probe(self) -> None:
        self.get_default_calendar_folder_id()

    def _calendar_view_payload(self, request: Mapping[str, Any]) -> dict[str, Any]:
        payload = request.get("payload", {})
        range_payload = payload.get("range", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(range_payload, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.list request did not include a usable range payload.",
                details={"request": request},
            )
        folder_id = self.get_default_calendar_folder_id()
        return {
            "__type": "GetCalendarViewJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
            },
            "Body": {
                "__type": "GetCalendarViewRequest:#Exchange",
                "CalendarId": {
                    "__type": "TargetFolderId:#Exchange",
                    "BaseFolderId": folder_id,
                },
                "RangeStart": _format_owa_range_boundary(range_payload.get("start")),
                "RangeEnd": _format_owa_range_boundary(range_payload.get("end"), end=True),
            },
        }

    def _extract_calendar_items(self, data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        body = data.get("Body")
        if not isinstance(body, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA calendar view response did not include a Body object.",
                details={"response_keys": sorted(data.keys())},
            )
        items = body.get("Items")
        if not isinstance(items, list):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA calendar view response did not include an Items list.",
                details={"body_keys": sorted(str(key) for key in body.keys())},
            )
        return [item for item in items if isinstance(item, Mapping)]

    def list_events(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.list requires a structured OWA request.",
                details={"request": request},
            )
        include_raw = bool(kwargs.get("include_raw", False))
        request_payload = request.get("payload", {})
        include_private = (
            bool(request_payload.get("include_private", False))
            if isinstance(request_payload, Mapping)
            else False
        )
        payload = self._calendar_view_payload(request)
        data = self._post_json("GetCalendarView", payload)
        events = []
        for item in self._extract_calendar_items(data):
            event = normalize_event(item, include_raw=include_raw)
            if event.is_private and not include_private:
                continue
            events.append(event.to_dict(include_raw=include_raw))
        return events

    def get_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.get requires a structured OWA request.",
                details={"request": request},
            )
        include_raw = bool(kwargs.get("include_raw", False))
        payload = request.get("payload", {})
        event_id = payload.get("id") if isinstance(payload, Mapping) else None
        if not event_id:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.get request did not include an event id.",
                details={"request": request},
            )
        data = self._post_json("GetCalendarItem", self._get_item_payload(str(event_id)))
        event = normalize_event(self._extract_get_item(data), include_raw=include_raw)
        return event.to_dict(include_raw=include_raw)

    def search_events(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("events.search", "SearchEvents", request=kwargs.get("request"))
        return []

    def _get_item_payload(self, event_id: str) -> dict[str, Any]:
        return {
            "__type": "GetItemJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
            },
            "Body": {
                "__type": "GetItemRequest:#Exchange",
                "ItemShape": {
                    "__type": "ItemResponseShape:#Exchange",
                    "BaseShape": "AllProperties",
                },
                "ItemIds": [
                    {
                        "__type": "ItemId:#Exchange",
                        "Id": event_id,
                    }
                ],
            },
        }

    def _extract_get_item(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        body = data.get("Body")
        messages = body.get("ResponseMessages") if isinstance(body, Mapping) else None
        items = messages.get("Items") if isinstance(messages, Mapping) else None
        if not isinstance(items, list) or not items:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA get response did not include response messages.",
                details={"response_keys": sorted(data.keys())},
            )
        message = items[0]
        if not isinstance(message, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA get response message had an unexpected shape.",
                details={"message": message},
            )
        if str(message.get("ResponseClass", "")).lower() != "success" and str(
            message.get("ResponseCode", "")
        ).lower() != "noerror":
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "OWA returned an error while fetching an event.",
                retryable=False,
                details={"get_error": message},
            )
        found_items = message.get("Items")
        if not isinstance(found_items, list) or not found_items:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA get response did not include an event item.",
                details={"message_keys": sorted(str(key) for key in message.keys())},
            )
        item = found_items[0]
        if not isinstance(item, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA get event item had an unexpected shape.",
                details={"item": item},
            )
        return item

    def _create_item_payload(self, request: Mapping[str, Any]) -> dict[str, Any]:
        payload = request.get("payload", {})
        if not isinstance(payload, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.create request did not include a usable payload.",
                details={"request": request},
            )
        subject = payload.get("subject")
        start = payload.get("start")
        end = payload.get("end")
        if not subject or not start or not end:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.create request requires subject, start, and end.",
                details={"payload": payload},
            )

        item: dict[str, Any] = {
            "__type": "CalendarItem:#Exchange",
            "Subject": str(subject),
            "Start": _format_create_datetime(start),
            "End": _format_create_datetime(end),
            "IsAllDayEvent": _is_all_day_range(start, end),
            "ReminderIsSet": False,
        }
        body = payload.get("body")
        if body:
            body_type = str(payload.get("body_type") or "text")
            item["Body"] = {
                "__type": "BodyContentType:#Exchange",
                "BodyType": "HTML" if body_type.lower() == "html" else "Text",
                "Value": str(body),
            }
        categories = payload.get("categories")
        if isinstance(categories, list) and categories:
            item["Categories"] = [str(category) for category in categories]

        return {
            "__type": "CreateItemJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
            },
            "Body": {
                "__type": "CreateItemRequest:#Exchange",
                "Items": [item],
                "SendMeetingInvitations": "SendToNone",
            },
        }

    def _extract_created_item(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        body = data.get("Body")
        messages = body.get("ResponseMessages") if isinstance(body, Mapping) else None
        items = messages.get("Items") if isinstance(messages, Mapping) else None
        if not isinstance(items, list) or not items:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA create response did not include response messages.",
                details={"response_keys": sorted(data.keys())},
            )
        message = items[0]
        if not isinstance(message, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA create response message had an unexpected shape.",
                details={"message": message},
            )
        if str(message.get("ResponseClass", "")).lower() != "success" and str(
            message.get("ResponseCode", "")
        ).lower() != "noerror":
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "OWA returned an error while creating an event.",
                retryable=False,
                details={"create_error": message},
            )
        created_items = message.get("Items")
        if not isinstance(created_items, list) or not created_items:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA create response did not include a created item.",
                details={"message_keys": sorted(str(key) for key in message.keys())},
            )
        created_item = created_items[0]
        if not isinstance(created_item, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA created item had an unexpected shape.",
                details={"created_item": created_item},
            )
        return created_item

    def create_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.create requires a structured OWA request.",
                details={"request": request},
            )
        request_payload = request.get("payload", {})
        data = self._post_json("CreateItem", self._create_item_payload(request))
        created_item = dict(self._extract_created_item(data))
        if isinstance(request_payload, Mapping):
            created_item.setdefault("Subject", request_payload.get("subject"))
            created_item.setdefault("Start", request_payload.get("start"))
            created_item.setdefault("End", request_payload.get("end"))
            if request_payload.get("categories"):
                created_item.setdefault("Categories", request_payload.get("categories"))
        return normalize_event(created_item).to_dict()

    def update_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("events.update", "UpdateEvent", request=kwargs.get("request"))
        return {}

    def _delete_item_payload(self, event_id: str) -> dict[str, Any]:
        return {
            "__type": "DeleteItemJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
            },
            "Body": {
                "__type": "DeleteItemRequest:#Exchange",
                "ItemIds": [
                    {
                        "__type": "ItemId:#Exchange",
                        "Id": event_id,
                    }
                ],
                "DeleteType": "MoveToDeletedItems",
                "SendMeetingCancellations": "SendToNone",
                "AffectedTaskOccurrences": "SpecifiedOccurrenceOnly",
            },
        }

    def _raise_delete_response_errors(self, data: Mapping[str, Any]) -> None:
        body = data.get("Body")
        messages = body.get("ResponseMessages") if isinstance(body, Mapping) else None
        items = messages.get("Items") if isinstance(messages, Mapping) else None
        if not isinstance(items, list) or not items:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA delete response did not include response messages.",
                details={"response_keys": sorted(data.keys())},
            )
        errors = [
            item
            for item in items
            if isinstance(item, Mapping)
            and str(item.get("ResponseClass", "")).lower() != "success"
            and str(item.get("ResponseCode", "")).lower() != "noerror"
        ]
        if errors:
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "OWA returned an error while deleting an event.",
                retryable=False,
                details={"delete_errors": errors},
            )

    def delete_event(self, *_, **kwargs: Any) -> None:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.delete requires a structured OWA request.",
                details={"request": request},
            )
        payload = request.get("payload", {})
        event_id = payload.get("id") if isinstance(payload, Mapping) else None
        if not event_id:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "events.delete request did not include an event id.",
                details={"request": request},
            )
        data = self._post_json("DeleteItem", self._delete_item_payload(str(event_id)))
        self._raise_delete_response_errors(data)

    def _list_categories_payload(self) -> dict[str, Any]:
        return {
            "request": {},
        }

    def _category_details_payload(self) -> dict[str, Any]:
        return {
            "__type": "FindCategoryDetailsJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
            },
            "Body": {
                "__type": "FindCategoryDetailsRequest:#Exchange",
            },
        }

    def _extract_category_items(self, data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        body = data.get("Body") if isinstance(data.get("Body"), Mapping) else data
        if not isinstance(body, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA category response did not include a usable object.",
                details={"response_type": type(data).__name__},
            )
        for key in ("CategoryDetails", "CategoryDetailsList", "MasterList", "Categories", "Items"):
            items = body.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, Mapping)]
        raise M365OwaError(
            NORMALIZATION_ERROR,
            "OWA category response did not include a category list.",
            details={"body_keys": sorted(str(key) for key in body.keys())},
        )

    def list_categories(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.list requires a structured OWA request.",
                details={"request": request},
            )
        data = self._post_json("GetMasterCategoryList", self._list_categories_payload())
        categories = []
        for item in self._extract_category_items(data):
            category = normalize_category(item).to_dict()
            if not category.get("name"):
                raise M365OwaError(
                    NORMALIZATION_ERROR,
                    "OWA category response included a category without a usable name.",
                    details={"category": item},
                )
            categories.append(category)
        return categories

    def category_details(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.details requires a structured OWA request.",
                details={"request": request},
            )
        categories = self.list_categories(request=build_list_categories_request().to_dict())
        data = self._post_json("FindCategoryDetails", self._category_details_payload())
        detail_by_name = {
            detail.name: detail
            for detail in (
                normalize_category_detail(item)
                for item in self._extract_category_items(data)
            )
            if detail.name
        }
        merged = []
        seen_names: set[str] = set()
        for category in categories:
            name = str(category.get("name") or "")
            if not name:
                continue
            seen_names.add(name)
            detail = detail_by_name.get(name)
            merged.append(
                {
                    "name": name,
                    "color": category.get("color"),
                    "item_count": 0 if detail is None else detail.item_count,
                    "unread_count": 0 if detail is None else detail.unread_count,
                    "is_search_folder_ready": False
                    if detail is None
                    else detail.is_search_folder_ready,
                }
            )
        for name, detail in detail_by_name.items():
            if name in seen_names:
                continue
            merged.append(detail.to_dict())
        return merged

    def upsert_category(self, *_, **kwargs: Any) -> dict[str, Any]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.upsert requires a structured OWA request.",
                details={"request": request},
            )
        payload = request.get("payload", {})
        name = payload.get("name") if isinstance(payload, Mapping) else None
        if not name:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.upsert request requires name.",
                details={"payload": payload},
            )

        categories = self.list_categories(request=build_list_categories_request().to_dict())
        category_name = str(name)
        existing_index = next(
            (index for index, category in enumerate(categories) if category.get("name") == category_name),
            None,
        )
        if existing_index is not None:
            return {
                "name": category_name,
                "created": False,
                "updated": False,
                "noop": True,
                "changed": False,
            }

        created = self._post_rest_json(
            "/api/v2.0/me/MasterCategories",
            {
                "DisplayName": category_name,
                "Color": "Preset0",
            },
        )
        category = normalize_category(created).to_dict()
        return {
            "name": category.get("name") or category_name,
            "id": created.get("Id") or created.get("id"),
            "created": True,
            "updated": False,
            "noop": False,
            "changed": True,
            "write_endpoint": "Outlook REST /api/v2.0/me/MasterCategories",
        }

    def _master_category_items(self) -> list[Mapping[str, Any]]:
        data = self._post_json("GetMasterCategoryList", self._list_categories_payload())
        return self._extract_category_items(data)

    def delete_category(self, *_, **kwargs: Any) -> dict[str, Any]:
        request = kwargs.get("request")
        if not isinstance(request, Mapping):
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.delete requires a structured OWA request.",
                details={"request": request},
            )
        payload = request.get("payload", {})
        name = payload.get("name") if isinstance(payload, Mapping) else None
        if not name:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "categories.delete request requires name.",
                details={"payload": payload},
            )
        category_name = str(name)

        matching = [
            item
            for item in self._master_category_items()
            if str(item.get("Name") or item.get("DisplayName") or item.get("name") or "") == category_name
        ]
        if not matching:
            raise M365OwaError(
                NOT_FOUND,
                f"Category {category_name!r} was not found.",
                retryable=False,
                details={"name": category_name},
            )
        category = matching[0]
        category_id = category.get("Id") or category.get("id")
        if not category_id:
            raise M365OwaError(
                NORMALIZATION_ERROR,
                "OWA category response did not include an id for deletion.",
                details={"name": category_name, "category_keys": sorted(str(key) for key in category.keys())},
            )

        quoted_id = quote(str(category_id).replace("'", "''"), safe="")
        self._delete_rest(f"/api/v2.0/me/MasterCategories('{quoted_id}')")
        remaining = [
            item
            for item in self._master_category_items()
            if str(item.get("Name") or item.get("DisplayName") or item.get("name") or "") == category_name
        ]
        if remaining:
            raise M365OwaError(
                OWA_BACKEND_ERROR,
                "Outlook REST reported category deletion, but OWA still returns the category.",
                retryable=True,
                details={"name": category_name, "id": str(category_id)},
            )
        return {
            "name": category_name,
            "id": str(category_id),
            "deleted": True,
            "changed": True,
            "write_endpoint": "Outlook REST /api/v2.0/me/MasterCategories",
        }

    def list_mail_folders(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("mail.folders.list", "FindFolder", request=kwargs.get("request"))
        return []

    def list_mail_messages(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("mail.list", "FindItem", request=kwargs.get("request"))
        return []

    def get_mail_message(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("mail.get", "GetItem", request=kwargs.get("request"))
        return {}

    def search_mail_messages(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("mail.search", "FindItem", request=kwargs.get("request"))
        return []

    def list_contact_folders(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("contacts.folders.list", "GetPeopleFilters", request=kwargs.get("request"))
        return []

    def list_contacts(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("contacts.list", "FindPeople", request=kwargs.get("request"))
        return []

    def get_contact(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("contacts.get", "GetPersona", request=kwargs.get("request"))
        return {}

    def search_contacts(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("contacts.search", "FindPeople", request=kwargs.get("request"))
        return []


def build_list_request(time_range, *, include_private: bool = False) -> OwaRequest:
    return build_list_events_request(time_range, include_private=include_private)


def build_get_request(event_id: str, *, include_raw: bool = False) -> OwaRequest:
    return build_get_event_request(event_id, include_raw=include_raw)


def build_search_request(
    query: str,
    *,
    time_range=None,
    include_private: bool = False,
) -> OwaRequest:
    return build_search_events_request(
        query,
        time_range=time_range,
        include_private=include_private,
    )


def build_create_request(**kwargs: Any) -> OwaRequest:
    return build_create_event_request(**kwargs)


def build_update_request(**kwargs: Any) -> OwaRequest:
    return build_update_event_request(**kwargs)


def build_delete_request(**kwargs: Any) -> OwaRequest:
    return build_delete_event_request(**kwargs)


def build_mail_folders_list_request() -> OwaRequest:
    return build_mail_folders_request()


def build_mail_messages_list_request(**kwargs: Any) -> OwaRequest:
    return build_mail_list_request(**kwargs)


def build_mail_message_get_request(message_id: str) -> OwaRequest:
    return build_mail_get_request(message_id)


def build_mail_messages_search_request(**kwargs: Any) -> OwaRequest:
    return build_mail_search_request(**kwargs)


def build_contacts_folders_list_request() -> OwaRequest:
    return build_contact_folders_request()


def build_contacts_list_request(**kwargs: Any) -> OwaRequest:
    return build_contacts_list_owa_request(**kwargs)


def build_contact_request(contact_id: str) -> OwaRequest:
    return build_contact_get_request(contact_id)


def build_contacts_query_request(**kwargs: Any) -> OwaRequest:
    return build_contacts_search_owa_request(**kwargs)
