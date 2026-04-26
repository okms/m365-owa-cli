from __future__ import annotations

import uuid

import pytest

from .conftest import run_cli


pytestmark = pytest.mark.live


def test_live_categories_read_shapes(live_connection: str) -> None:
    list_code, list_payload = run_cli("categories", "list", "--connection", live_connection)
    details_code, details_payload = run_cli("categories", "details", "--connection", live_connection)

    assert list_code == 0
    assert list_payload.get("ok") is True
    assert isinstance(list_payload.get("data"), list)

    assert details_code == 0
    assert details_payload.get("ok") is True
    details = details_payload.get("data") or []
    assert isinstance(details, list)
    assert all(
        {"name", "item_count", "unread_count", "is_search_folder_ready"} <= set(row)
        for row in details
    )


@pytest.mark.mutating
def test_live_category_upsert_and_delete_synthetic(live_connection: str) -> None:
    name = f"m365-owa-cli-live-test-{uuid.uuid4().hex[:12]}"
    created = False
    try:
        upsert_code, upsert_payload = run_cli(
            "categories",
            "upsert",
            "--connection",
            live_connection,
            "--name",
            name,
        )
        assert upsert_code == 0
        assert upsert_payload.get("ok") is True
        created = True

        noop_code, noop_payload = run_cli(
            "categories",
            "upsert",
            "--connection",
            live_connection,
            "--name",
            name,
        )
        assert noop_code == 0
        assert noop_payload.get("ok") is True
        assert (noop_payload.get("data") or {}).get("noop") is True
    finally:
        if created:
            delete_code, delete_payload = run_cli(
                "categories",
                "delete",
                "--connection",
                live_connection,
                "--name",
                name,
                "--confirm-category-name",
                name,
            )
            assert delete_code == 0
            assert delete_payload.get("ok") is True

    list_code, list_payload = run_cli("categories", "list", "--connection", live_connection)
    assert list_code == 0
    assert list_payload.get("ok") is True
    assert not any(row.get("name") == name for row in (list_payload.get("data") or []))
