from __future__ import annotations

import os
import re
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from .errors import (  # type: ignore
        AUTH_REQUIRED,
        CONFIG_ERROR,
        OWA_ENDPOINT_NOT_IMPLEMENTED,
        UNSUPPORTED_OPERATION,
        M365OwaError,
    )
except ImportError:  # pragma: no cover - fallback for partial scaffolds
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONFIG_ERROR = "CONFIG_ERROR"
    OWA_ENDPOINT_NOT_IMPLEMENTED = "OWA_ENDPOINT_NOT_IMPLEMENTED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"

    class M365OwaError(Exception):
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

CONFIG_DIR_ENV_VAR = "M365_OWA_CONFIG_DIR"
TOKEN_ENV_PREFIX = "M365_OWA_TOKEN_"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "m365-owa-cli"
CONNECTIONS_DIR_NAME = "connections"
TOKEN_FILE_SUFFIX = ".token"
CREDENTIAL_FILE_SUFFIX = ".credential.json"

_CONNECTION_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def get_config_dir() -> Path:
    configured = os.environ.get(CONFIG_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CONFIG_DIR


def validate_connection_name(name: str) -> str:
    if not isinstance(name, str) or not name or not _CONNECTION_NAME_RE.fullmatch(name):
        raise M365OwaError(
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


def connection_credential_path(name: str, config_dir: Path | None = None) -> Path:
    validate_connection_name(name)
    base_dir = Path(config_dir) if config_dir is not None else get_config_dir()
    return base_dir / CONNECTIONS_DIR_NAME / f"{name}{CREDENTIAL_FILE_SUFFIX}"


def _normalize_token_value(token: str) -> str:
    if not isinstance(token, str):
        raise M365OwaError(
            CONFIG_ERROR,
            "Token values must be strings.",
            retryable=False,
        )
    return token.rstrip("\r\n")


def set_token(name: str, token: str, config_dir: Path | None = None) -> Path:
    path = connection_token_path(name, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_normalize_token_value(token), encoding="utf-8")
    _chmod_owner_only(path)
    return path


def remove_token(name: str, config_dir: Path | None = None) -> bool:
    removed = False
    for path in (
        connection_token_path(name, config_dir),
        connection_credential_path(name, config_dir),
    ):
        if path.exists():
            path.unlink()
            removed = True
    return removed


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


def _credential_connection_names(config_dir: Path) -> list[str]:
    connections_dir = config_dir / CONNECTIONS_DIR_NAME
    if not connections_dir.exists():
        return []

    names: list[str] = []
    for path in sorted(connections_dir.glob(f"*{CREDENTIAL_FILE_SUFFIX}")):
        if not path.is_file():
            continue
        name = path.name[: -len(CREDENTIAL_FILE_SUFFIX)]
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

    for name in _credential_connection_names(base_dir):
        credential = read_credential(name, base_dir)
        records.setdefault(
            name,
            {
                "name": name,
                "sources": [],
                "token_file": str(connection_token_path(name, base_dir)),
                "credential_file": str(connection_credential_path(name, base_dir)),
            },
        )["sources"].append("credential_file")
        records[name].update(credential_metadata(name, credential=credential, config_dir=base_dir))

    for name in _file_connection_names(base_dir):
        records.setdefault(
            name,
            {
                "name": name,
                "sources": [],
                "token_file": str(connection_token_path(name, base_dir)),
                "credential_file": str(connection_credential_path(name, base_dir)),
            },
        )["sources"].append("file")

    for name, env_name in _env_connection_names():
        record = records.setdefault(
            name,
            {
                "name": name,
                "sources": [],
                "token_file": None,
                "credential_file": str(connection_credential_path(name, base_dir)),
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
        if "has_refresh_token" not in record:
            record["has_refresh_token"] = False
        if "access_token_expires_at" not in record:
            record["access_token_expires_at"] = None

    return [records[name] for name in sorted(records)]


def resolve_token(
    name: str,
    token: str | None = None,
    config_dir: Path | None = None,
) -> str | None:
    validate_connection_name(name)

    if token is not None:
        return _normalize_token_value(token)

    credential = read_credential(name, config_dir=config_dir)
    if credential and credential.get("access_token"):
        return _normalize_token_value(str(credential["access_token"]))

    env_name = connection_env_var_name(name)
    if env_name in os.environ:
        return os.environ[env_name].rstrip("\r\n")

    return read_token_file(name, config_dir=config_dir)


def missing_token_error(name: str) -> M365OwaError:
    return M365OwaError(
        AUTH_REQUIRED,
        f"No token found for connection {name!r}.",
        retryable=False,
        details={"connection": name},
    )


def _chmod_owner_only(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_expires_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def set_credential(
    name: str,
    credential: dict[str, Any],
    config_dir: Path | None = None,
) -> Path:
    validate_connection_name(name)
    path = connection_credential_path(name, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(credential)
    payload["version"] = int(payload.get("version") or 1)
    payload["connection"] = name
    if "expires_at" in payload:
        payload["expires_at"] = _normalize_expires_at(payload.get("expires_at"))
    if "captured_at" not in payload:
        payload["captured_at"] = _utc_now().isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _chmod_owner_only(path)
    return path


def read_credential(name: str, config_dir: Path | None = None) -> dict[str, Any] | None:
    path = connection_credential_path(name, config_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise M365OwaError(
            CONFIG_ERROR,
            "Connection credential file could not be read.",
            retryable=False,
            details={"connection": name, "credential_file": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise M365OwaError(
            CONFIG_ERROR,
            "Connection credential file must contain a JSON object.",
            details={"connection": name, "credential_file": str(path)},
        )
    if payload.get("connection") not in {None, name}:
        raise M365OwaError(
            CONFIG_ERROR,
            "Connection credential file name does not match its connection field.",
            details={
                "connection": name,
                "credential_file": str(path),
                "credential_connection": payload.get("connection"),
            },
        )
    return payload


def credential_metadata(
    name: str,
    *,
    credential: dict[str, Any] | None = None,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    payload = credential if credential is not None else read_credential(name, config_dir=config_dir)
    path = connection_credential_path(name, config_dir)
    if not payload:
        return {
            "credential_file": str(path),
            "has_access_token": False,
            "has_refresh_token": False,
            "access_token_expires_at": None,
            "token_endpoint_host": None,
            "client_id_present": False,
        }
    token_endpoint = payload.get("token_endpoint")
    host = urlparse(str(token_endpoint)).hostname if token_endpoint else None
    return {
        "credential_file": str(path),
        "has_access_token": bool(payload.get("access_token")),
        "has_refresh_token": bool(payload.get("refresh_token")),
        "access_token_expires_at": payload.get("expires_at"),
        "token_endpoint_host": host,
        "client_id_present": bool(payload.get("client_id")),
        "captured_source": payload.get("captured_source"),
    }
