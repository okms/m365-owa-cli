from __future__ import annotations

from typing import Any, Mapping

from owacal_cli.errors import OWA_ENDPOINT_NOT_IMPLEMENTED, OwacalError, redact_tokens

from .endpoints import get_endpoint
from .requests import (
    OwaRequest,
    build_create_event_request,
    build_delete_event_request,
    build_get_event_request,
    build_list_events_request,
    build_search_events_request,
    build_update_event_request,
)


def _redact_value(value: Any) -> Any:
    return redact_tokens(value)


class OWAEndpointNotImplementedError(OwacalError):
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
    ) -> None:
        self.connection = connection
        self.token = token
        self.base_url = base_url.rstrip("/")

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

    def list_events(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("events.list", "GetCalendarView", request=kwargs.get("request"))
        return []

    def get_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("events.get", "GetEvent", request=kwargs.get("request"))
        return {}

    def search_events(self, *_, **kwargs: Any) -> list[dict[str, Any]]:
        self._not_implemented("events.search", "SearchEvents", request=kwargs.get("request"))
        return []

    def create_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("events.create", "CreateEvent", request=kwargs.get("request"))
        return {}

    def update_event(self, *_, **kwargs: Any) -> dict[str, Any]:
        self._not_implemented("events.update", "UpdateEvent", request=kwargs.get("request"))
        return {}

    def delete_event(self, *_, **kwargs: Any) -> None:
        self._not_implemented("events.delete", "DeleteEvent", request=kwargs.get("request"))


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
