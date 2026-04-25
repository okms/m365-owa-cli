from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from m365_owa_cli.errors import (
    AUTH_EXPIRED,
    AUTH_REQUIRED,
    CONFIG_ERROR,
    CONNECTION_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_ARGUMENTS,
    NOT_FOUND,
    NORMALIZATION_ERROR,
    OWA_BACKEND_ERROR,
    OWA_ENDPOINT_NOT_IMPLEMENTED,
    M365OwaError,
    SERIES_OPERATION_REFUSED,
    TOKEN_FILE_ERROR,
    UNSAFE_OPERATION_REJECTED,
    UNSUPPORTED_OPERATION,
    exit_code_for_error_code,
    redact_tokens,
)
from m365_owa_cli.output import error_envelope


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        (INTERNAL_ERROR, 1),
        (INVALID_ARGUMENTS, 2),
        (AUTH_REQUIRED, 3),
        (AUTH_EXPIRED, 3),
        (NOT_FOUND, 4),
        (UNSAFE_OPERATION_REJECTED, 6),
        (SERIES_OPERATION_REFUSED, 6),
        (CONNECTION_NOT_FOUND, 9),
        (TOKEN_FILE_ERROR, 9),
        (CONFIG_ERROR, 9),
        (OWA_BACKEND_ERROR, 10),
        (OWA_ENDPOINT_NOT_IMPLEMENTED, 10),
        (NORMALIZATION_ERROR, 10),
        (UNSUPPORTED_OPERATION, 10),
    ],
)
def test_exit_code_mapping(code: str, exit_code: int) -> None:
    assert exit_code_for_error_code(code) == exit_code


def test_redact_tokens_nested_structures() -> None:
    payload = {
        "authorization": "Bearer abcdefghijk12345",
        "nested": {
            "message": "use Bearer zyxwvutsrqpon",
            "token_value": "keep-out",
            "stored_refresh_token": True,
            "rotated_refresh_token": False,
            "extra": [
                "M365_OWA_TOKEN_WORK=supersecretvalue",
                {"access_token": "plainsecret"},
            ],
        },
        "other": "visible",
    }

    redacted = redact_tokens(payload)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["message"] == "use Bearer [REDACTED]"
    assert redacted["nested"]["token_value"] == "[REDACTED]"
    assert redacted["nested"]["stored_refresh_token"] is True
    assert redacted["nested"]["rotated_refresh_token"] is False
    assert redacted["nested"]["extra"][0] == "M365_OWA_TOKEN_WORK=[REDACTED]"
    assert redacted["nested"]["extra"][1]["access_token"] == "[REDACTED]"
    assert redacted["other"] == "visible"


def test_error_envelope_redacts_details() -> None:
    error = M365OwaError(
        AUTH_EXPIRED,
        "Bearer sensitive-token was rejected",
        details={
            "authorization": "Bearer another-secret-token",
            "raw": "M365_OWA_TOKEN_WORK=token-value",
        },
    )

    envelope = error_envelope(error, connection="work", operation="events.list")

    assert envelope["ok"] is False
    assert envelope["connection"] == "work"
    assert envelope["operation"] == "events.list"
    assert envelope["error"]["code"] == AUTH_EXPIRED
    assert envelope["error"]["message"] == "Bearer [REDACTED] was rejected"
    assert envelope["error"]["details"]["authorization"] == "[REDACTED]"
    assert envelope["error"]["details"]["raw"] == "M365_OWA_TOKEN_WORK=[REDACTED]"
