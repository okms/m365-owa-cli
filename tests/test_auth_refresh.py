from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from typer.testing import CliRunner

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m365_owa_cli import auth
from m365_owa_cli.cli import app
from m365_owa_cli.config import CONFIG_DIR_ENV_VAR, resolve_token, set_credential, set_token
from m365_owa_cli.errors import AUTH_EXPIRED, M365OwaError


runner = CliRunner()


ACCESS_TOKEN = "Bearer access-token-secret"
REFRESH_TOKEN = "refresh-token-secret"
ROTATED_REFRESH_TOKEN = "rotated-refresh-token-secret"


def _credential_path(config_dir: Path, connection: str) -> Path:
    return config_dir / "connections" / f"{connection}.credential.json"


def _write_credential(
    config_dir: Path,
    *,
    connection: str = "work",
    access_token: str = ACCESS_TOKEN,
    refresh_token: str = REFRESH_TOKEN,
    scope: str | None = "openid profile offline_access https://outlook.office.com/OWA.AccessAsUser.All",
    resource: str | None = None,
) -> Path:
    path = _credential_path(config_dir, connection)
    path.parent.mkdir(parents=True, exist_ok=True)
    credential = {
        "version": 1,
        "connection": connection,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": "2026-04-25T21:50:07Z",
        "authority": "https://login.microsoftonline.com/common",
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "client_id": "owa-public-client-id",
        "origin": "https://outlook.office.com",
        "redirect_uri": "https://outlook.office.com/mail/",
        "captured_source": "devtools_token_response",
        "captured_at": "2026-04-25T20:35:00Z",
    }
    if scope is not None:
        credential["scope"] = scope
    if resource is not None:
        credential["resource"] = resource
    path.write_text(json.dumps(credential), encoding="utf-8")
    return path


def _json(result):
    return json.loads(result.stdout)


def _require_auth_callable(name: str):
    value = getattr(auth, name, None)
    assert callable(value), f"m365_owa_cli.auth.{name} must be implemented"
    return value


def test_credential_file_is_inspectable_without_leaking_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    _write_credential(tmp_path)

    list_result = runner.invoke(app, ["auth", "list-connections"])
    assert list_result.exit_code == 0
    list_payload = _json(list_result)
    records_by_name = {item["name"]: item for item in list_payload["data"]}
    assert "work" in records_by_name, "credential files must appear in auth list-connections"
    record = records_by_name["work"]
    assert "credential_file" in record["sources"]
    assert record["has_token"] is True
    assert record["has_refresh_token"] is True
    assert record["access_token_expires_at"] == "2026-04-25T21:50:07Z"
    assert ACCESS_TOKEN not in list_result.stdout
    assert REFRESH_TOKEN not in list_result.stdout

    inspect_result = runner.invoke(app, ["auth", "inspect", "--connection", "work"])
    assert inspect_result.exit_code == 0
    inspect_payload = _json(inspect_result)
    assert inspect_payload["operation"] == "auth.inspect"
    assert inspect_payload["connection"] == "work"
    assert inspect_payload["data"]["has_access_token"] is True
    assert inspect_payload["data"]["has_refresh_token"] is True
    assert inspect_payload["data"]["expires_at"] == "2026-04-25T21:50:07Z"
    assert inspect_payload["data"]["token_endpoint_host"] == "login.microsoftonline.com"
    assert inspect_payload["data"]["client_id_present"] is True
    assert ACCESS_TOKEN not in inspect_result.stdout
    assert REFRESH_TOKEN not in inspect_result.stdout


def test_refresh_posts_stored_scope_metadata_and_rotates_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    _write_credential(tmp_path)
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        form = parse_qs(request.content.decode())
        assert str(request.url) == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        assert request.headers["Origin"] == "https://outlook.office.com"
        assert form["client_id"] == ["owa-public-client-id"]
        assert form["grant_type"] == ["refresh_token"]
        assert form["refresh_token"] == [REFRESH_TOKEN]
        assert form["scope"] == [
            "openid profile offline_access https://outlook.office.com/OWA.AccessAsUser.All"
        ]
        assert "resource" not in form
        return httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "Bearer refreshed-access-token-secret",
                "refresh_token": ROTATED_REFRESH_TOKEN,
                "expires_in": 3600,
            },
        )

    refresh_connection_token = _require_auth_callable("refresh_connection_token")
    now = datetime(2026, 4, 25, 20, 0, 0, tzinfo=UTC)
    result = refresh_connection_token(
        "work",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        now=now,
    )

    assert len(seen_requests) == 1
    assert result["name"] == "work"
    assert result["refreshed"] is True
    assert result["has_access_token"] is True
    assert result["has_refresh_token"] is True
    assert "refreshed-access-token-secret" not in json.dumps(result)
    assert ROTATED_REFRESH_TOKEN not in json.dumps(result)

    stored = json.loads(_credential_path(tmp_path, "work").read_text(encoding="utf-8"))
    assert stored["access_token"] == "Bearer refreshed-access-token-secret"
    assert stored["refresh_token"] == ROTATED_REFRESH_TOKEN
    assert stored["expires_at"] == (now + timedelta(seconds=3600)).isoformat().replace("+00:00", "Z")


def test_refresh_posts_resource_when_scope_was_not_captured(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    _write_credential(tmp_path, scope=None, resource="https://outlook.office.com")

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        assert form["client_id"] == ["owa-public-client-id"]
        assert form["grant_type"] == ["refresh_token"]
        assert form["refresh_token"] == [REFRESH_TOKEN]
        assert form["resource"] == ["https://outlook.office.com"]
        assert "scope" not in form
        assert request.headers["Origin"] == "https://outlook.office.com"
        return httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "Bearer refreshed-access-token-secret",
                "expires_in": 1800,
            },
        )

    refresh_connection_token = _require_auth_callable("refresh_connection_token")
    refresh_connection_token(
        "work",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        now=datetime(2026, 4, 25, 20, 0, 0, tzinfo=UTC),
    )

    stored = json.loads(_credential_path(tmp_path, "work").read_text(encoding="utf-8"))
    assert stored["refresh_token"] == REFRESH_TOKEN
    assert stored["access_token"] == "Bearer refreshed-access-token-secret"


def test_legacy_token_file_resolution_still_works(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    set_token("legacy", "Bearer legacy-access-token")

    assert resolve_token("legacy") == "Bearer legacy-access-token"


def test_events_refresh_before_expired_credential_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    _write_credential(tmp_path, access_token="Bearer stale-access-token")

    def fake_refresh(connection: str, **kwargs):
        assert connection == "work"
        set_credential(
            "work",
            {
                "access_token": "Bearer fresh-access-token",
                "refresh_token": ROTATED_REFRESH_TOKEN,
                "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "client_id": "owa-public-client-id",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        return {"name": "work", "refreshed": True}

    seen_tokens: list[str] = []

    class FakeOWAClient:
        def __init__(self, *, connection, token):
            assert connection == "work"
            seen_tokens.append(token)

        def list_events(self, *, request, include_raw):
            return []

    monkeypatch.setattr("m365_owa_cli.auth.refresh_connection_token", fake_refresh)
    monkeypatch.setattr("m365_owa_cli.cli.OWAClient", FakeOWAClient)

    result = runner.invoke(app, ["events", "list", "--connection", "work", "--day", "2026-04-24"])

    assert result.exit_code == 0
    assert seen_tokens == ["Bearer fresh-access-token"]


def test_events_retry_once_after_auth_expired_refreshes_credential(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV_VAR, str(tmp_path))
    _write_credential(
        tmp_path,
        access_token="Bearer rejected-access-token",
        refresh_token=REFRESH_TOKEN,
    )
    stored = json.loads(_credential_path(tmp_path, "work").read_text(encoding="utf-8"))
    stored["expires_at"] = "2099-01-01T00:00:00Z"
    _credential_path(tmp_path, "work").write_text(json.dumps(stored), encoding="utf-8")

    def fake_refresh(connection: str, **kwargs):
        assert connection == "work"
        stored = json.loads(_credential_path(tmp_path, "work").read_text(encoding="utf-8"))
        stored["access_token"] = "Bearer retry-access-token"
        stored["refresh_token"] = ROTATED_REFRESH_TOKEN
        _credential_path(tmp_path, "work").write_text(json.dumps(stored), encoding="utf-8")
        return {"name": "work", "refreshed": True}

    calls: list[str] = []

    class FakeOWAClient:
        def __init__(self, *, connection, token):
            calls.append(token)

        def list_events(self, *, request, include_raw):
            if len(calls) == 1:
                raise M365OwaError(AUTH_EXPIRED, "expired")
            return []

    monkeypatch.setattr("m365_owa_cli.cli.refresh_connection_token", fake_refresh)
    monkeypatch.setattr("m365_owa_cli.cli.OWAClient", FakeOWAClient)

    result = runner.invoke(app, ["events", "list", "--connection", "work", "--day", "2026-04-24"])

    assert result.exit_code == 0
    assert calls == ["Bearer rejected-access-token", "Bearer retry-access-token"]
