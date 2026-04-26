from __future__ import annotations

import pytest

from .conftest import run_cli


pytestmark = pytest.mark.live


def test_live_auth_test_returns_success(live_connection: str) -> None:
    code, payload = run_cli("auth", "test", "--connection", live_connection)

    assert code == 0
    assert payload.get("ok") is True
    assert (payload.get("data") or {}).get("authenticated") is True
