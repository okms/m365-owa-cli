from __future__ import annotations

from datetime import date

import pytest

from .conftest import run_cli


pytestmark = pytest.mark.live


def test_live_events_list_read_only_shape(live_connection: str) -> None:
    code, payload = run_cli(
        "events",
        "list",
        "--connection",
        live_connection,
        "--day",
        date.today().isoformat(),
    )

    assert code == 0
    assert payload.get("ok") is True
    assert isinstance(payload.get("data"), list)
