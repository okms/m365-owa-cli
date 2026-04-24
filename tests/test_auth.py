from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m365_owa_cli.auth import auth_test, bookmarklet_payload, extract_token
from m365_owa_cli.config import (
    CONFIG_DIR_ENV_VAR,
    CONFIG_ERROR,
    UNSUPPORTED_OPERATION,
    M365OwaError,
    connection_env_var_name,
    get_config_dir,
    list_connections,
    read_token_file,
    remove_token,
    resolve_token,
    set_token,
    validate_connection_name,
)


def test_get_config_dir_defaults_and_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv(CONFIG_DIR_ENV_VAR, raising=False)
    assert get_config_dir() == Path.home() / ".config" / "m365-owa-cli"

    override = tmp_path / "config"
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(override))
    assert get_config_dir() == override


def test_validate_connection_name_rejects_path_traversal():
    with pytest.raises(M365OwaError) as excinfo:
        validate_connection_name("../work")
    assert excinfo.value.code == CONFIG_ERROR

    with pytest.raises(M365OwaError):
        validate_connection_name("work/team")


def test_token_precedence_direct_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))

    set_token("work", "file-token")
    env_var = connection_env_var_name("work")
    monkeypatch.setenv(env_var, "env-token")

    assert resolve_token("work", token="direct-token") == "direct-token"
    assert resolve_token("work") == "env-token"

    monkeypatch.delenv(env_var)
    assert resolve_token("work") == "file-token"


def test_list_and_remove_connections_do_not_leak_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))

    set_token("work", "secret-file-token")
    set_token("personal", "another-secret")
    env_var = connection_env_var_name("alpha")
    monkeypatch.setenv(env_var, "env-secret-token")

    records = list_connections()
    dumped = json.dumps(records, sort_keys=True)

    assert any(record["name"] == "work" and record["sources"] == ["file"] for record in records)
    assert any(record["name"] == "alpha" and record["sources"] == ["env"] for record in records)
    assert "secret-file-token" not in dumped
    assert "another-secret" not in dumped
    assert "env-secret-token" not in dumped

    assert read_token_file("work") == "secret-file-token"
    assert remove_token("work") is True
    assert remove_token("work") is False
    assert read_token_file("work") is None

    records_after = list_connections()
    assert all(record["name"] != "work" for record in records_after)


def test_auth_test_probes_owa_when_token_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    set_token("work", "file-token")

    calls = []

    class FakeOWAClient:
        def __init__(self, *, connection, token):
            calls.append((connection, token))

        def probe(self):
            calls.append("probe")

    monkeypatch.setattr("m365_owa_cli.auth.OWAClient", FakeOWAClient)

    auth_test("work")

    assert calls == [("work", "file-token"), "probe"]


def test_extract_token_placeholder_raises_structured_error(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))

    with pytest.raises(M365OwaError) as excinfo:
        extract_token("work")
    assert excinfo.value.code == UNSUPPORTED_OPERATION
    assert excinfo.value.details["connection"] == "work"
    assert excinfo.value.details["env_var"] == connection_env_var_name("work")


def test_bookmarklet_payload_is_local_only_and_host_restricted():
    payload = bookmarklet_payload("work")
    bookmarklet = payload["bookmarklet"]

    assert payload["connection"] == "work"
    assert bookmarklet.startswith("javascript:")
    assert "outlook.cloud.microsoft" in bookmarklet
    assert "outlook.office.com" in bookmarklet
    assert "/owa/service.svc" in bookmarklet
    assert "fetch(" not in bookmarklet
    assert "XMLHttpRequest" in bookmarklet
    assert "navigator.clipboard.writeText" in bookmarklet
    assert "secret-token-value" not in json.dumps(payload)
