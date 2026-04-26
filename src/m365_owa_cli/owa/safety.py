from __future__ import annotations

from typing import Any, Mapping

from m365_owa_cli.errors import (
    SERIES_OPERATION_REFUSED,
    UNSAFE_OPERATION_REJECTED,
    M365OwaError,
)


class SafetyError(M365OwaError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, retryable=False, details=dict(details or {}))


def _get_value(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


def _as_bool(value: Any) -> bool:
    return bool(value)


def is_likely_series_or_master(event: Any) -> bool:
    if _as_bool(_get_value(event, "is_occurrence")):
        return False
    if _as_bool(_get_value(event, "is_recurring")):
        return True
    if _get_value(event, "recurrence") is not None:
        return True
    if _get_value(event, "series_master_id") is not None:
        return True
    if _get_value(event, "seriesMasterId") is not None:
        return True
    return False


def refuse_likely_series_operation(event: Any, *, operation: str = "operation") -> None:
    if is_likely_series_or_master(event):
        raise SafetyError(
            code=SERIES_OPERATION_REFUSED,
            message=(
                "This command appears to target a recurring series. "
                "m365-owa-cli v1 only supports operations on individual occurrences."
            ),
            details={
                "operation": operation,
                "event_id": _get_value(event, "id"),
                "occurrence_id": _get_value(event, "occurrence_id"),
            },
        )


def require_occurrence_id(event: Any, *, operation: str = "operation") -> str:
    occurrence_id = _get_value(event, "occurrence_id")
    if _as_bool(_get_value(event, "is_recurring")) and not _as_bool(_get_value(event, "is_occurrence")):
        raise SafetyError(
            code=SERIES_OPERATION_REFUSED,
            message="Recurring events require an occurrence_id for mutation.",
            details={"operation": operation, "event_id": _get_value(event, "id")},
        )
    if not occurrence_id:
        raise SafetyError(
            code=UNSAFE_OPERATION_REJECTED,
            message="This recurring occurrence is missing an occurrence_id.",
            details={"operation": operation, "event_id": _get_value(event, "id")},
        )
    return str(occurrence_id)


def require_exact_confirmation(
    value: str,
    confirmation: str,
    *,
    label: str,
) -> None:
    if value != confirmation:
        raise SafetyError(
            code=UNSAFE_OPERATION_REJECTED,
            message=f"Confirmation must exactly match the {label}.",
            details={
                label.replace(" ", "_"): value,
                f"confirm_{label.replace(' ', '_')}": confirmation,
            },
        )


def require_delete_confirmation(event_id: str, confirm_event_id: str) -> None:
    require_exact_confirmation(event_id, confirm_event_id, label="event id")
