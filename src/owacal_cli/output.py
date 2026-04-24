"""JSON envelope helpers for owacal-cli."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from owacal_cli.errors import OwacalError, redact_tokens


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if is_dataclass(value):
        return {field.name: json_safe(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return json_safe(value.model_dump())
    if hasattr(value, "__dict__"):
        return json_safe(vars(value))
    return str(value)


def success_envelope(
    data: Any = None,
    *,
    connection: str | None = None,
    operation: str | None = None,
    range: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": json_safe(data)}
    if connection is not None:
        payload["connection"] = connection
    if operation is not None:
        payload["operation"] = operation
    if range is not None:
        payload["range"] = json_safe(range)
    if extra:
        payload.update(json_safe(extra))
    return redact_tokens(payload)


def error_envelope(
    error: OwacalError | Exception | str,
    *,
    connection: str | None = None,
    operation: str | None = None,
    range: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if isinstance(error, OwacalError):
        error_payload = error.to_dict()
    else:
        wrapped = OwacalError(
            "INTERNAL_ERROR",
            str(error),
            retryable=True,
            details={"exception_type": type(error).__name__},
        )
        error_payload = wrapped.to_dict()
    payload: dict[str, Any] = {"ok": False, "error": error_payload}
    if connection is not None:
        payload["connection"] = connection
    if operation is not None:
        payload["operation"] = operation
    if range is not None:
        payload["range"] = json_safe(range)
    if extra:
        payload.update(json_safe(extra))
    return redact_tokens(payload)
