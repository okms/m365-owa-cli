from __future__ import annotations

import json
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from owacal_cli.owa.fixture_sanitize import extract_har_action_entries, sanitize_owa_fixture


def test_sanitize_owa_fixture_redacts_tokens_and_identity_consistently():
    event_id = "AAMkAGVmMDEzREAL_EVENT_ID"
    tenant_id = "11111111-2222-3333-4444-555555555555"
    payload = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token-value",
                "Cookie": "X-OWA-CANARY=secret-cookie",
                "Content-Type": "application/json",
            },
            "postData": {
                "text": json.dumps(
                    {
                        "ItemId": {"Id": event_id, "ChangeKey": "CQAAABYAAAD"},
                        "Organizer": {"EmailAddress": "alex@example.com"},
                    }
                )
            },
        },
        "response": {
            "status": 200,
            "content": {
                "text": json.dumps(
                    {
                        "Events": [
                            {
                                "ItemId": {"Id": event_id},
                                "TenantId": tenant_id,
                                "Location": {"DisplayName": "Room 1"},
                                "JoinUrl": (
                                    "https://teams.microsoft.com/l/meetup-join/"
                                    "?tenantId=11111111-2222-3333-4444-555555555555"
                                    "&login_hint=alex@example.com"
                                    "&access_token=raw-url-token"
                                ),
                            }
                        ]
                    }
                )
            },
        },
    }

    sanitized = sanitize_owa_fixture(payload)
    dumped = json.dumps(sanitized, sort_keys=True)

    assert "secret-token-value" not in dumped
    assert "secret-cookie" not in dumped
    assert "alex@example.com" not in dumped
    assert event_id not in dumped
    assert tenant_id not in dumped
    assert dumped.count("<OWA_ID_0001>") == 2
    assert "user001@example.invalid" in dumped
    assert "<GUID_0001>" in dumped
    assert "Room 1" in dumped
    assert sanitized["request"]["headers"]["Content-Type"] == "application/json"
    assert sanitized["response"]["status"] == 200


def test_extract_har_action_entries_keeps_only_matching_owa_action():
    har_payload = {
        "log": {
            "entries": [
                {"request": {"url": "https://outlook.cloud.microsoft/owa/service.svc?action=GetCalendarView&app=Calendar"}},
                {"request": {"url": "https://outlook.cloud.microsoft/owa/service.svc?action=FindPeople&app=People"}},
            ]
        }
    }

    extracted = extract_har_action_entries(har_payload, "GetCalendarView")

    assert len(extracted["log"]["entries"]) == 1
    assert "GetCalendarView" in extracted["log"]["entries"][0]["request"]["url"]
