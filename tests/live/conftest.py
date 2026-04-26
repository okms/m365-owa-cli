from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    connection = os.environ.get("M365_OWA_LIVE_CONNECTION")
    allow_mutation = os.environ.get("M365_OWA_LIVE_ALLOW_MUTATION") == "1"
    skip_live = pytest.mark.skip(reason="set M365_OWA_LIVE_CONNECTION to run live OWA tests")
    skip_mutating = pytest.mark.skip(
        reason="set M365_OWA_LIVE_ALLOW_MUTATION=1 to run mutating live OWA tests"
    )
    for item in items:
        if "live" in item.keywords and not connection:
            item.add_marker(skip_live)
        if "mutating" in item.keywords and not allow_mutation:
            item.add_marker(skip_mutating)


@pytest.fixture(scope="session")
def live_connection() -> str:
    connection = os.environ.get("M365_OWA_LIVE_CONNECTION")
    if not connection:
        pytest.skip("set M365_OWA_LIVE_CONNECTION to run live OWA tests")
    return connection


def run_cli(*args: str) -> tuple[int, dict[str, Any]]:
    process = subprocess.run(
        ["uv", "run", "m365-owa-cli", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": {"code": "NON_JSON_OUTPUT"}}
    return process.returncode, payload
