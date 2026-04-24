from __future__ import annotations

import json
from pathlib import Path
import sys

from typer.testing import CliRunner


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from owacal_cli.cli import app
from owacal_cli.errors import OWA_BACKEND_ERROR, OwacalError


runner = CliRunner()


def _json(result):
    return json.loads(result.stdout)


def test_capabilities_and_schema_commands_emit_success_envelopes():
    result = runner.invoke(app, ["capabilities"])
    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert payload["data"]["backend"] == "owa-service-svc"
    assert payload["data"]["graph_supported"] is False

    result = runner.invoke(app, ["schema", "errors"])
    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert {item["code"] for item in payload["data"]["errors"]} >= {
        "INVALID_ARGUMENTS",
        "UNSAFE_OPERATION_REJECTED",
        "OWA_ENDPOINT_NOT_IMPLEMENTED",
    }


def test_auth_token_commands_do_not_leak_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("OWACAL_CONFIG_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["auth", "set-token", "--connection", "work", "--token", "Bearer secret-token-value"],
    )
    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert payload["connection"] == "work"
    assert "secret-token-value" not in result.stdout

    result = runner.invoke(app, ["auth", "list-connections"])
    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert payload["data"][0]["name"] == "work"
    assert payload["data"][0]["has_token"] is True
    assert "secret-token-value" not in result.stdout

    result = runner.invoke(app, ["auth", "remove-token", "--connection", "work"])
    assert result.exit_code == 0
    payload = _json(result)
    assert payload["data"]["removed"] is True


def test_auth_bookmarklet_generates_inspectable_helper():
    result = runner.invoke(app, ["auth", "bookmarklet", "--connection", "work"])

    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert payload["operation"] == "auth.bookmarklet"
    assert payload["connection"] == "work"
    assert payload["data"]["bookmarklet"].startswith("javascript:")
    assert "/owa/service.svc" in payload["data"]["bookmarklet"]
    assert "outlook.cloud.microsoft" in payload["data"]["allowed_hosts"]

    raw_result = runner.invoke(app, ["auth", "bookmarklet", "--connection", "work", "--raw"])
    assert raw_result.exit_code == 0
    assert raw_result.stdout.startswith("javascript:")
    assert '"ok"' not in raw_result.stdout


def test_delete_confirmation_failure_exits_before_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("OWACAL_CONFIG_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "events",
            "delete",
            "--connection",
            "work",
            "--id",
            "event-1",
            "--confirm-event-id",
            "event-2",
        ],
    )

    assert result.exit_code == 6
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNSAFE_OPERATION_REJECTED"


def test_events_list_with_direct_token_reaches_owa_client_without_leaking_token(monkeypatch):
    class FakeOWAClient:
        def __init__(self, *, connection, token):
            assert connection == "work"
            assert token == "Bearer should-not-leak"

        def list_events(self, *, request, include_raw):
            assert request["endpoint"] == "GetCalendarView"
            assert include_raw is False
            raise OwacalError(
                OWA_BACKEND_ERROR,
                "backend received Bearer should-not-leak",
                details={"authorization": "Bearer should-not-leak"},
            )

    monkeypatch.setattr("owacal_cli.cli.OWAClient", FakeOWAClient)

    result = runner.invoke(
        app,
        [
            "events",
            "list",
            "--connection",
            "work",
            "--day",
            "2026-04-24",
            "--token",
            "Bearer should-not-leak",
        ],
    )

    assert result.exit_code == 10
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["operation"] == "events.list"
    assert payload["error"]["code"] == "OWA_BACKEND_ERROR"
    assert "should-not-leak" not in result.stdout


def test_create_dry_run_does_not_require_token():
    result = runner.invoke(
        app,
        [
            "events",
            "create",
            "--connection",
            "work",
            "--subject",
            "Focus block",
            "--start",
            "2026-04-24T10:00:00",
            "--end",
            "2026-04-24T11:00:00",
            "--category",
            "Deep Work",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = _json(result)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["request"]["payload"]["subject"] == "Focus block"


def test_update_rejects_noop_with_stable_invalid_arguments():
    result = runner.invoke(
        app,
        ["events", "update", "--connection", "work", "--id", "event-1", "--dry-run"],
    )

    assert result.exit_code == 2
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"


def test_unknown_option_returns_stable_json_error():
    result = runner.invoke(app, ["events", "list", "--connection", "work", "--bogus"])

    assert result.exit_code == 2
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["operation"] == "events.list"
    assert payload["connection"] == "work"
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"]["click_error"] == "NoSuchOption"


def test_missing_option_value_returns_stable_json_error():
    result = runner.invoke(
        app,
        ["events", "list", "--connection", "work", "--day", "2026-04-24", "--token"],
    )

    assert result.exit_code == 2
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["operation"] == "events.list"
    assert payload["connection"] == "work"
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"]["click_error"] == "BadOptionUsage"


def test_typer_bad_parameter_returns_stable_json_error():
    result = runner.invoke(app, ["help"])

    assert result.exit_code == 2
    payload = _json(result)
    assert payload["ok"] is False
    assert payload["operation"] == "help"
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"]["click_error"] == "BadParameter"
