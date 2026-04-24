from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from owacal_cli.auth import auth_test, extract_token
from owacal_cli.config import (
    CONFIG_DIR_ENV_VAR,
    CONFIG_ERROR,
    OWA_ENDPOINT_NOT_IMPLEMENTED,
    UNSUPPORTED_OPERATION,
    OwacalError,
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
    assert get_config_dir() == Path.home() / ".config" / "owacal-cli"

    override = tmp_path / "config"
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(override))
    assert get_config_dir() == override


def test_validate_connection_name_rejects_path_traversal():
    with pytest.raises(OwacalError) as excinfo:
        validate_connection_name("../work")
    assert excinfo.value.code == CONFIG_ERROR

    with pytest.raises(OwacalError):
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


def test_auth_placeholders_raise_structured_errors(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    set_token("work", "file-token")

    with pytest.raises(OwacalError) as excinfo:
        auth_test("work")
    assert excinfo.value.code == OWA_ENDPOINT_NOT_IMPLEMENTED
    assert excinfo.value.details["connection"] == "work"

    with pytest.raises(OwacalError) as excinfo:
        extract_token("work")
    assert excinfo.value.code == UNSUPPORTED_OPERATION
    assert excinfo.value.details["connection"] == "work"
    assert excinfo.value.details["env_var"] == connection_env_var_name("work")
