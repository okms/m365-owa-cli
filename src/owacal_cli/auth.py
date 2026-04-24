from __future__ import annotations

from pathlib import Path

try:
    from .errors import (  # type: ignore
        AUTH_REQUIRED,
        OWA_ENDPOINT_NOT_IMPLEMENTED,
        UNSUPPORTED_OPERATION,
        OwacalError,
    )
except ImportError:  # pragma: no cover - fallback for partial scaffolds
    from .config import (
        OWA_ENDPOINT_NOT_IMPLEMENTED,
        UNSUPPORTED_OPERATION,
        OwacalError,
    )
    AUTH_REQUIRED = "AUTH_REQUIRED"

from .config import (
    connection_env_var_name,
    list_connections,
    remove_token,
    resolve_token,
    set_token,
    validate_connection_name,
)

__all__ = [
    "auth_test",
    "extract_token",
    "list_connections",
    "remove_token",
    "resolve_token",
    "set_token",
]


def auth_test(
    connection: str,
    token: str | None = None,
    config_dir: Path | None = None,
) -> None:
    validate_connection_name(connection)
    if not resolve_token(connection, token=token, config_dir=config_dir):
        raise OwacalError(
            AUTH_REQUIRED,
            f"No token found for connection {connection!r}.",
            retryable=False,
            details={"connection": connection},
        )
    raise OwacalError(
        OWA_ENDPOINT_NOT_IMPLEMENTED,
        "auth test is not implemented until a supported OWA probe endpoint is identified.",
        retryable=False,
        details={"connection": connection},
    )


def extract_token(
    connection: str,
    browser: str = "edge",
    config_dir: Path | None = None,
) -> None:
    validate_connection_name(connection)
    if browser.lower() != "edge":
        raise OwacalError(
            UNSUPPORTED_OPERATION,
            "Only Edge token extraction is considered for v1.",
            retryable=False,
            details={"browser": browser},
        )
    raise OwacalError(
        UNSUPPORTED_OPERATION,
        "Browser token extraction is not implemented in this build.",
        retryable=False,
        details={
            "browser": browser,
            "connection": connection,
            "env_var": connection_env_var_name(connection),
        },
    )
