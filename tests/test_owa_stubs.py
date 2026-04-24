import json
from urllib.parse import parse_qs, urlsplit

import httpx

from owacal_cli.errors import AUTH_EXPIRED, OWA_BACKEND_ERROR, OwacalError
from owacal_cli.owa.client import (
    OWAClient,
    OWAEndpointNotImplementedError,
    build_create_request,
    build_delete_request,
    build_list_request,
)
from owacal_cli.owa.safety import (
    SafetyError,
    refuse_likely_series_operation,
    require_delete_confirmation,
    require_occurrence_id,
)
from owacal_cli.time_ranges import parse_day_range


def test_delete_confirmation_requires_exact_match():
    require_delete_confirmation("abc", "abc")
    try:
        require_delete_confirmation("abc", "abcd")
    except SafetyError as exc:
        assert exc.code == "UNSAFE_OPERATION_REJECTED"
    else:
        raise AssertionError("Expected SafetyError")


def test_likely_series_mutation_is_refused():
    event = {"id": "series-1", "is_recurring": True, "is_occurrence": False}
    try:
        refuse_likely_series_operation(event, operation="events.update")
    except SafetyError as exc:
        assert exc.code == "SERIES_OPERATION_REFUSED"
        assert "recurring series" in exc.message
    else:
        raise AssertionError("Expected SafetyError")


def test_occurrence_id_is_required_for_recurring_mutations():
    event = {"id": "occ-1", "is_recurring": True, "is_occurrence": True, "occurrence_id": "occ-1/1"}
    assert require_occurrence_id(event, operation="events.update") == "occ-1/1"


def test_unimplemented_client_operations_redact_token_details():
    client = OWAClient(connection="work", token="Bearer eyJsecret.token.value")
    try:
        client.get_event(request={"authorization": "Bearer eyJsecret.token.value"})
    except OWAEndpointNotImplementedError as exc:
        assert exc.code == "OWA_ENDPOINT_NOT_IMPLEMENTED"
        details = exc.details
        assert "[REDACTED]" in str(details)
        assert "eyJsecret.token.value" not in str(details)
    else:
        raise AssertionError("Expected OWAEndpointNotImplementedError")


def test_client_lists_events_from_live_owa_shapes():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        action = parse_qs(urlsplit(str(request.url)).query)["action"][0]
        if action == "GetCalendarFolders":
            return httpx.Response(
                200,
                json={
                    "CalendarGroups": [
                        {
                            "Calendars": [
                                {
                                    "IsDefaultCalendar": True,
                                    "CalendarFolderId": {
                                        "__type": "FolderId:#Exchange",
                                        "Id": "folder-1",
                                        "ChangeKey": "ck-1",
                                    },
                                }
                            ]
                        }
                    ]
                },
            )
        if action == "GetCalendarView":
            payload = json.loads(request.content)
            body = payload["Body"]
            assert body["CalendarId"]["BaseFolderId"]["Id"] == "folder-1"
            assert body["RangeStart"] == "2026-04-24T00:00:00.001"
            assert body["RangeEnd"] == "2026-04-25T00:00:00.000"
            return httpx.Response(
                200,
                json={
                    "Header": {},
                    "Body": {
                        "ResponseClass": "Success",
                        "ResponseCode": "NoError",
                        "Items": [
                            {
                                "ItemId": {"Id": "event-1", "ChangeKey": "ck-event"},
                                "Subject": "Planning",
                                "Start": "2026-04-24T10:00:00",
                                "End": "2026-04-24T11:00:00",
                                "StartTimeZoneId": "W. Europe Standard Time",
                                "Categories": ["Deep Work"],
                                "Sensitivity": "Normal",
                                "IsRecurring": False,
                                "Preview": "Agenda",
                            },
                            {
                                "ItemId": {"Id": "private-1"},
                                "Subject": "Hidden",
                                "Start": "2026-04-24T12:00:00",
                                "End": "2026-04-24T13:00:00",
                                "Sensitivity": "Private",
                            },
                        ],
                    },
                },
            )
        raise AssertionError(f"Unexpected action {action}")

    client = OWAClient(
        connection="work",
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_list_request(parse_day_range("2026-04-24"))

    events = client.list_events(request=request.to_dict())

    assert len(events) == 1
    assert events[0]["id"] == "event-1"
    assert events[0]["subject"] == "Planning"
    assert events[0]["body"] == "Agenda"
    assert events[0]["categories"] == ["Deep Work"]
    assert [parse_qs(urlsplit(str(item.url)).query)["action"][0] for item in requests] == [
        "GetCalendarFolders",
        "GetCalendarView",
    ]
    assert requests[0].headers["authorization"] == "Bearer test-token"
    assert requests[1].headers["action"] == "GetCalendarView"


def test_client_can_include_private_and_raw_owa_payloads():
    def handler(request: httpx.Request) -> httpx.Response:
        action = parse_qs(urlsplit(str(request.url)).query)["action"][0]
        if action == "GetCalendarFolders":
            return httpx.Response(
                200,
                json={"CalendarGroups": [{"Calendars": [{"CalendarFolderId": {"Id": "folder-1"}}]}]},
            )
        return httpx.Response(
            200,
            json={
                "Body": {
                    "ResponseCode": "NoError",
                    "Items": [
                        {
                            "ItemId": {"Id": "private-1"},
                            "Subject": "Private",
                            "Start": "2026-04-24T12:00:00",
                            "End": "2026-04-24T13:00:00",
                            "Sensitivity": "Private",
                        }
                    ],
                }
            },
        )

    client = OWAClient(
        token="test-token-without-prefix",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_list_request(parse_day_range("2026-04-24"), include_private=True)

    events = client.list_events(request=request.to_dict(), include_raw=True)

    assert events[0]["id"] == "private-1"
    assert events[0]["is_private"] is True
    assert events[0]["raw_owa"]["Sensitivity"] == "Private"


def test_client_maps_rejected_token_to_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "expired"})

    client = OWAClient(
        token="Bearer secret-token-value",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    try:
        client.probe()
    except OwacalError as exc:
        assert exc.code == AUTH_EXPIRED
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected auth error")


def test_client_maps_owa_error_bodies_without_leaking_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        action = parse_qs(urlsplit(str(request.url)).query)["action"][0]
        if action == "GetCalendarFolders":
            return httpx.Response(
                200,
                json={"CalendarGroups": [{"Calendars": [{"CalendarFolderId": {"Id": "folder-1"}}]}]},
            )
        return httpx.Response(
            500,
            json={
                "Body": {
                    "ResponseCode": "ErrorInternalServerError",
                    "ExceptionName": "InvalidCalendarGuidException",
                }
            },
        )

    client = OWAClient(
        token="Bearer secret-token-value",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_list_request(parse_day_range("2026-04-24"))

    try:
        client.list_events(request=request.to_dict())
    except OwacalError as exc:
        assert exc.code == OWA_BACKEND_ERROR
        assert exc.details["status_code"] == 500
        assert exc.details["owa_response"]["Body"]["ExceptionName"] == "InvalidCalendarGuidException"
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected backend error")


def test_client_deletes_event_with_delete_item_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "Body": {
                    "ResponseMessages": {
                        "Items": [
                            {
                                "ResponseClass": "Success",
                                "ResponseCode": "NoError",
                            }
                        ]
                    }
                }
            },
        )

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_delete_request(event_id="event-1", confirm_event_id="event-1")

    client.delete_event(request=request.to_dict())

    assert parse_qs(urlsplit(captured["url"]).query)["action"] == ["DeleteItem"]
    assert captured["headers"]["action"] == "DeleteItem"
    body = captured["payload"]["Body"]
    assert body["ItemIds"][0]["Id"] == "event-1"
    assert body["DeleteType"] == "MoveToDeletedItems"
    assert body["SendMeetingCancellations"] == "SendToNone"
    assert body["AffectedTaskOccurrences"] == "SpecifiedOccurrenceOnly"


def test_client_surfaces_delete_item_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Body": {
                    "ResponseMessages": {
                        "Items": [
                            {
                                "ResponseClass": "Error",
                                "ResponseCode": "ErrorInvalidIdMalformed",
                                "MessageText": "Id is malformed.",
                            }
                        ]
                    }
                }
            },
        )

    client = OWAClient(
        token="Bearer secret-token-value",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_delete_request(event_id="event-1", confirm_event_id="event-1")

    try:
        client.delete_event(request=request.to_dict())
    except OwacalError as exc:
        assert exc.code == OWA_BACKEND_ERROR
        assert exc.details["delete_errors"][0]["ResponseCode"] == "ErrorInvalidIdMalformed"
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected delete backend error")


def test_client_creates_event_with_create_item_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "Body": {
                    "ResponseMessages": {
                        "Items": [
                            {
                                "ResponseClass": "Success",
                                "ResponseCode": "NoError",
                                "Items": [
                                    {
                                        "__type": "CalendarItem:#Exchange",
                                        "ItemId": {"Id": "created-1"},
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
        )

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_create_request(
        subject="Copied event",
        start="2026-04-23T00:00:00+00:00",
        end="2026-04-24T00:00:00+00:00",
        body="Body text",
        categories=["CC HR"],
    )

    created = client.create_event(request=request.to_dict())

    assert created["id"] == "created-1"
    assert created["subject"] == "Copied event"
    assert created["start"] == "2026-04-23T00:00:00+00:00"
    assert created["end"] == "2026-04-24T00:00:00+00:00"
    assert parse_qs(urlsplit(captured["url"]).query)["action"] == ["CreateItem"]
    assert captured["headers"]["action"] == "CreateItem"
    item = captured["payload"]["Body"]["Items"][0]
    assert item["Subject"] == "Copied event"
    assert item["Start"] == "2026-04-23T00:00:00.000"
    assert item["End"] == "2026-04-24T00:00:00.000"
    assert item["IsAllDayEvent"] is True
    assert item["Body"]["BodyType"] == "Text"
    assert item["Body"]["Value"] == "Body text"
    assert item["Categories"] == ["CC HR"]
    assert captured["payload"]["Body"]["SendMeetingInvitations"] == "SendToNone"


def test_client_surfaces_create_item_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Body": {
                    "ResponseMessages": {
                        "Items": [
                            {
                                "ResponseClass": "Error",
                                "ResponseCode": "ErrorCannotCreateCalendarItemInNonCalendarFolder",
                                "MessageText": "Cannot create calendar item.",
                            }
                        ]
                    }
                }
            },
        )

    client = OWAClient(
        token="Bearer secret-token-value",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = build_create_request(
        subject="Copied event",
        start="2026-04-23T10:00:00+00:00",
        end="2026-04-23T11:00:00+00:00",
    )

    try:
        client.create_event(request=request.to_dict())
    except OwacalError as exc:
        assert exc.code == OWA_BACKEND_ERROR
        assert exc.details["create_error"]["ResponseCode"] == "ErrorCannotCreateCalendarItemInNonCalendarFolder"
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected create backend error")
