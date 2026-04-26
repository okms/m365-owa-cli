from __future__ import annotations

import json
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m365_owa_cli.owa.fixture_sanitize import (
    extract_har_action_entries,
    extract_har_url_entries,
    sanitize_owa_fixture,
)


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


def test_sanitize_mail_payload_redacts_mail_pii_but_keeps_shape():
    message_id = "AAMkAGVmMDEzMAIL_ITEM_ID"
    conversation_id = "AAQkAGVmMDEzCONVERSATION_ID"
    payload = {
        "request": {
            "method": "POST",
            "url": "https://outlook.cloud.microsoft/owa/service.svc?action=FindItem&app=Mail",
            "headers": {
                "Authorization": "Bearer eyJmail.token.value",
                "Cookie": "X-OWA-CANARY=secret-cookie",
            },
        },
        "response": {
            "status": 200,
            "content": {
                "text": json.dumps(
                    {
                        "Body": {
                            "Items": [
                                {
                                    "ItemId": {"Id": message_id, "ChangeKey": "CQAAABYMAIL"},
                                    "ConversationId": {"Id": conversation_id},
                                    "Subject": "Quarterly acquisition planning",
                                    "From": {
                                        "Mailbox": {
                                            "Name": "Alex Example",
                                            "EmailAddress": "alex@example.com",
                                        }
                                    },
                                    "ToRecipients": [
                                        {
                                            "Mailbox": {
                                                "Name": "Sam Recipient",
                                                "EmailAddress": "sam@example.com",
                                            }
                                        }
                                    ],
                                    "Body": {
                                        "BodyType": "HTML",
                                        "Value": "<p>Confidential body text</p>",
                                    },
                                    "Attachments": [
                                        {
                                            "AttachmentId": {"Id": "AAMkATTACHMENT_ID"},
                                            "Name": "board-plan.pdf",
                                            "ContentType": "application/pdf",
                                            "Size": 1234,
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                )
            },
        },
    }

    sanitized = sanitize_owa_fixture(payload)
    dumped = json.dumps(sanitized, sort_keys=True)

    assert "eyJmail.token.value" not in dumped
    assert "secret-cookie" not in dumped
    assert message_id not in dumped
    assert conversation_id not in dumped
    assert "Quarterly acquisition" not in dumped
    assert "Alex Example" not in dumped
    assert "Sam Recipient" not in dumped
    assert "alex@example.com" not in dumped
    assert "sam@example.com" not in dumped
    assert "Confidential body text" not in dumped
    assert "board-plan.pdf" not in dumped
    assert "<SUBJECT_0001>" in dumped
    assert "<PERSON_0001>" in dumped
    assert "user001@example.invalid" in dumped
    assert "<BODY_0001>" in dumped
    assert "<ATTACHMENT_0001>" in dumped
    assert "FindItem" in dumped
    assert "application/pdf" in dumped


def test_sanitize_people_payload_redacts_contact_pii_and_photo_urls():
    contact_id = "AAMkAGVmMDEzCONTACT_ID"
    payload = {
        "request": {
            "method": "GET",
            "url": "https://outlook.office.com/PeopleGraphVx/v1.0/contacts?$select=displayName,emailAddresses",
            "headers": {"Authorization": "Bearer eyJpeople.token.value"},
        },
        "response": {
            "status": 200,
            "content": {
                "text": json.dumps(
                    {
                        "value": [
                            {
                                "id": contact_id,
                                "displayName": "Morgan Contact",
                                "givenName": "Morgan",
                                "surname": "Contact",
                                "emailAddresses": [{"address": "morgan@example.com"}],
                                "businessPhones": ["+47 22 33 44 55"],
                                "homeAddress": {
                                    "street": "Main Street 1",
                                    "city": "Oslo",
                                    "postalCode": "0123",
                                },
                                "notes": "Met at private customer meeting",
                                "photoUrl": "https://outlook.office.com/owa/service.svc/s/GetPersonaPhoto?id=AAMkPHOTO_ID",
                            }
                        ]
                    }
                )
            },
        },
    }

    sanitized = sanitize_owa_fixture(payload)
    dumped = json.dumps(sanitized, sort_keys=True)

    assert "eyJpeople.token.value" not in dumped
    assert contact_id not in dumped
    assert "Morgan" not in dumped
    assert "morgan@example.com" not in dumped
    assert "+47 22 33 44 55" not in dumped
    assert "Main Street" not in dumped
    assert "private customer" not in dumped
    assert "AAMkPHOTO_ID" not in dumped
    assert "<PERSON_0001>" in dumped
    assert "user001@example.invalid" in dumped
    assert "<PHONE_0001>" in dumped
    assert "<ADDRESS_0001>" in dumped
    assert "<BODY_0001>" in dumped
    assert "<PHOTO_0001>" in dumped
    assert "PeopleGraphVx" in dumped


def test_extract_har_url_entries_keeps_matching_route_family():
    har_payload = {
        "log": {
            "entries": [
                {"request": {"url": "https://outlook.office.com/PeopleGraphVx/v1.0/contacts"}},
                {"request": {"url": "https://outlook.office.com/owa/service.svc?action=FindItem&app=Mail"}},
            ]
        }
    }

    extracted = extract_har_url_entries(har_payload, "PeopleGraphVx/v1.0/contacts")

    assert len(extracted["log"]["entries"]) == 1
    assert "PeopleGraphVx" in extracted["log"]["entries"][0]["request"]["url"]
