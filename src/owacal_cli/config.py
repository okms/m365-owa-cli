from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from .errors import (  # type: ignore
        AUTH_REQUIRED,
        CONFIG_ERROR,
        OWA_ENDPOINT_NOT_IMPLEMENTED,
        UNSUPPORTED_OPERATION,
        OwacalError,
    )
except ImportError:  # pragma: no cover - fallback for partial scaffolds
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONFIG_ERROR = "CONFIG_ERROR"
    OWA_ENDPOINT_NOT_IMPLEMENTED = "OWA_ENDPOINT_NOT_IMPLEMENTED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"

    class OwacalError(Exception):
        def __init__(
            self,
            code: str,
            message: str,
            *,
            retryable: bool = False,
            details: dict | None = None,
        ) -> None:
            super().__init__(message)
            self.code = code
            self.message = message
            self.retryable = retryable
            self.details = details or {}

        def to_dict(self) -> dict:
            return {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "details": self.details,
            }

        def __str__(self) -> str:
            return self.message

CONFIG_DIR_ENV_VAR = "OWACAL_CONFIG_DIR"
TOKEN_ENV_PREFIX = "OWACAL_TOKEN_"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "owacal-cli"
CONNECTIONS_DIR_NAME = "connections"
TOKEN_FILE_SUFFIX = ".token"

_CONNECTION_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def get_config_dir() -> Path:
    configured = os.environ.get(CONFIG_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CONFIG_DIR


def validate_connection_name(name: str) -> str:
    if not isinstance(name, str) or not name or not _CONNECTION_NAME_RE.fullmatch(name):
        raise OwacalError(
            CONFIG_ERROR,
            "Connection names may only contain letters, digits, dot, underscore, and dash.",
            retryable=False,
            details={"connection": name},
        )
    return name


def connection_env_var_name(name: str) -> str:
    validate_connection_name(name)
    return TOKEN_ENV_PREFIX + _NON_ALNUM_RE.sub("_", name).upper()


def connection_token_path(name: str, config_dir: Path | None = None) -> Path:
    validate_connection_name(name)
    base_dir = Path(config_dir) if config_dir is not None else get_config_dir()
    return base_dir / CONNECTIONS_DIR_NAME / f"{name}{TOKEN_FILE_SUFFIX}"


def _normalize_token_value(token: str) -> str:
    if not isinstance(token, str):
        raise OwacalError(
            CONFIG_ERROR,
            "Token values must be strings.",
            retryable=False,
        )
    return token.rstrip("\r\n")


def set_token(name: str, token: str, config_dir: Path | None = None) -> Path:
    path = connection_token_path(name, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_normalize_token_value(token), encoding="utf-8")
    return path


def remove_token(name: str, config_dir: Path | None = None) -> bool:
    path = connection_token_path(name, config_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def read_token_file(name: str, config_dir: Path | None = None) -> str | None:
    path = connection_token_path(name, config_dir)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").rstrip("\r\n")


def _file_connection_names(config_dir: Path) -> list[str]:
    connections_dir = config_dir / CONNECTIONS_DIR_NAME
    if not connections_dir.exists():
        return []

    names: list[str] = []
    for path in sorted(connections_dir.glob(f"*{TOKEN_FILE_SUFFIX}")):
        if not path.is_file():
            continue
        name = path.name[: -len(TOKEN_FILE_SUFFIX)]
        if _CONNECTION_NAME_RE.fullmatch(name):
            names.append(name)
    return names


def _env_connection_names() -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for env_name in sorted(os.environ):
        if not env_name.startswith(TOKEN_ENV_PREFIX):
            continue
        suffix = env_name[len(TOKEN_ENV_PREFIX) :]
        if not suffix:
            continue
        connection_name = suffix.lower()
        if _CONNECTION_NAME_RE.fullmatch(connection_name):
            names.append((connection_name, env_name))
    return names


def list_connections(config_dir: Path | None = None) -> list[dict]:
    base_dir = Path(config_dir) if config_dir is not None else get_config_dir()
    records: dict[str, dict] = {}

    for name in _file_connection_names(base_dir):
        records.setdefault(
            name,
            {
                "name": name,
                "sources": [],
                "token_file": str(connection_token_path(name, base_dir)),
            },
        )["sources"].append("file")

    for name, env_name in _env_connection_names():
        record = records.setdefault(
            name,
            {
                "name": name,
                "sources": [],
                "token_file": None,
            },
        )
        record["sources"].append("env")
        record["env_var"] = env_name

    for record in records.values():
        sources = []
        for source in record["sources"]:
            if source not in sources:
                sources.append(source)
        record["sources"] = sources
        record["has_token"] = bool(record["sources"])

    return [records[name] for name in sorted(records)]


def resolve_token(
    name: str,
    token: str | None = None,
    config_dir: Path | None = None,
) -> str | None:
    validate_connection_name(name)

    if token is not None:
        return _normalize_token_value(token)

    env_name = connection_env_var_name(name)
    if env_name in os.environ:
        return os.environ[env_name].rstrip("\r\n")

    return read_token_file(name, config_dir=config_dir)


def missing_token_error(name: str) -> OwacalError:
    return OwacalError(
        AUTH_REQUIRED,
        f"No token found for connection {name!r}.",
        retryable=False,
        details={"connection": name},
    )
