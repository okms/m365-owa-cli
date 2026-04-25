"""Stable error types, exit codes, and redaction helpers for m365-owa-cli."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_EXPIRED = "AUTH_EXPIRED"
AUTH_REFRESH_FAILED = "AUTH_REFRESH_FAILED"
CONNECTION_NOT_FOUND = "CONNECTION_NOT_FOUND"
TOKEN_FILE_ERROR = "TOKEN_FILE_ERROR"
OWA_BACKEND_ERROR = "OWA_BACKEND_ERROR"
OWA_ENDPOINT_NOT_IMPLEMENTED = "OWA_ENDPOINT_NOT_IMPLEMENTED"
NOT_FOUND = "NOT_FOUND"
UNSAFE_OPERATION_REJECTED = "UNSAFE_OPERATION_REJECTED"
SERIES_OPERATION_REFUSED = "SERIES_OPERATION_REFUSED"
UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
CONFIG_ERROR = "CONFIG_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: str
    exit_code: int
    retryable: bool
    message: str


ERROR_SPECS: tuple[ErrorSpec, ...] = (
    ErrorSpec(INVALID_ARGUMENTS, 2, False, "Invalid arguments were provided."),
    ErrorSpec(AUTH_REQUIRED, 3, False, "OWA authentication is required."),
    ErrorSpec(AUTH_EXPIRED, 3, False, "OWA bearer token expired or was rejected."),
    ErrorSpec(AUTH_REFRESH_FAILED, 3, False, "OWA authentication refresh failed."),
    ErrorSpec(CONNECTION_NOT_FOUND, 9, False, "The requested connection was not found."),
    ErrorSpec(TOKEN_FILE_ERROR, 9, False, "The connection token file could not be read or written."),
    ErrorSpec(OWA_BACKEND_ERROR, 10, True, "OWA returned an error response."),
    ErrorSpec(OWA_ENDPOINT_NOT_IMPLEMENTED, 10, False, "That OWA endpoint is not implemented yet."),
    ErrorSpec(NOT_FOUND, 4, False, "The requested resource was not found."),
    ErrorSpec(UNSAFE_OPERATION_REJECTED, 6, False, "The requested operation was rejected for safety."),
    ErrorSpec(SERIES_OPERATION_REFUSED, 6, False, "Recurring series operations are not supported."),
    ErrorSpec(UNSUPPORTED_OPERATION, 10, False, "That operation is not supported."),
    ErrorSpec(NORMALIZATION_ERROR, 10, False, "The backend response could not be normalized."),
    ErrorSpec(CONFIG_ERROR, 9, False, "The connection configuration is invalid."),
    ErrorSpec(INTERNAL_ERROR, 1, True, "An internal error occurred."),
)


_ERROR_SPEC_BY_CODE = {spec.code: spec for spec in ERROR_SPECS}


_TOKEN_PATTERN = re.compile(
    r"(?i)\bBearer\s+([A-Za-z0-9._~+/=-]{8,})\b|\b(M365_OWA_TOKEN(?:_[A-Z0-9]+)?)\b\s*=\s*([^\s'\";]+)"
)
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "secret",
    "password",
    "cookie",
)
_SENSITIVE_TOKEN_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "token_value",
}


def stable_error_specs() -> list[dict[str, Any]]:
    return [
        {
            "code": spec.code,
            "exit_code": spec.exit_code,
            "retryable": spec.retryable,
            "message": spec.message,
        }
        for spec in ERROR_SPECS
    ]


def exit_code_for_error_code(code: str) -> int:
    spec = _ERROR_SPEC_BY_CODE.get(code)
    if spec is not None:
        return spec.exit_code
    return 10


class M365OwaError(Exception):
    """Stable structured error for m365-owa-cli."""

    __slots__ = ("code", "message", "retryable", "details")

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details

    def exit_code(self) -> int:
        return exit_code_for_error_code(self.code)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": redact_tokens(self.message),
            "retryable": self.retryable,
            "details": redact_tokens(_json_safe(self.details)),
        }
        return payload

    def __str__(self) -> str:
        return f"{self.code}: {redact_tokens(self.message)}"

    def __repr__(self) -> str:
        return (
            "M365OwaError("
            f"code={self.code!r}, "
            f"message={redact_tokens(self.message)!r}, "
            f"retryable={self.retryable!r}, "
            f"details={redact_tokens(_json_safe(self.details))!r}"
            ")"
        )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _is_sensitive_key(key: Any) -> bool:
    key_text = str(key).lower()
    if key_text in _SENSITIVE_TOKEN_KEYS:
        return True
    if key_text.endswith("_token") and not key_text.startswith("has_"):
        return True
    return any(part in key_text for part in _SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return "Bearer [REDACTED]"
        if match.group(2) is not None:
            return f"{match.group(2)}=[REDACTED]"
        return "[REDACTED]"

    return _TOKEN_PATTERN.sub(replace_match, value)


def redact_tokens(value: Any) -> Any:
    """Redact bearer tokens and M365_OWA_TOKEN-like values from nested data."""

    return _redact_any(value, seen=set())


def _redact_any(value: Any, *, seen: set[int]) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _redact_string(value)
    value_id = id(value)
    if value_id in seen:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        seen.add(value_id)
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[str(key)] = item if isinstance(item, bool) or item is None else "[REDACTED]"
            else:
                redacted[str(key)] = _redact_any(item, seen=seen)
        seen.remove(value_id)
        return redacted
    if isinstance(value, tuple):
        seen.add(value_id)
        items = [_redact_any(item, seen=seen) for item in value]
        seen.remove(value_id)
        return items
    if isinstance(value, list):
        seen.add(value_id)
        items = [_redact_any(item, seen=seen) for item in value]
        seen.remove(value_id)
        return items
    if isinstance(value, set):
        seen.add(value_id)
        items = [_redact_any(item, seen=seen) for item in value]
        seen.remove(value_id)
        return items
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _redact_any(value.model_dump(), seen=seen)
    if hasattr(value, "__dict__"):
        return _redact_any(vars(value), seen=seen)
    return _redact_string(str(value))
