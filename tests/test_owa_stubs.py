import json
from urllib.parse import parse_qs, urlsplit

import httpx

from m365_owa_cli.errors import AUTH_EXPIRED, OWA_BACKEND_ERROR, M365OwaError
from m365_owa_cli.owa.client import (
    OWAClient,
    OWAEndpointNotImplementedError,
    build_category_upsert_request,
    build_category_details_request,
    build_category_delete_request,
    build_list_categories_request,
    build_create_request,
    build_delete_request,
    build_list_request,
)
from m365_owa_cli.owa.safety import (
    SafetyError,
    refuse_likely_series_operation,
    require_delete_confirmation,
    require_occurrence_id,
)
from m365_owa_cli.time_ranges import parse_day_range


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
    except M365OwaError as exc:
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
    except M365OwaError as exc:
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
    except M365OwaError as exc:
        assert exc.code == OWA_BACKEND_ERROR
        assert exc.details["delete_errors"][0]["ResponseCode"] == "ErrorInvalidIdMalformed"
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected delete backend error")


def test_client_lists_mailbox_categories_from_owa_shapes():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "ResponseClass": "Success",
                "ResponseCode": "NoError",
                "WasSuccessful": True,
                "MasterList": [
                    {"Name": "Deep Work", "Color": "Preset0", "Id": "cat-1"},
                    {"Name": "Travel", "Color": 15, "Id": "cat-2"},
                ],
            },
        )

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    categories = client.list_categories(request=build_list_categories_request().to_dict())

    assert categories == [
        {"name": "Deep Work", "color": "Preset0"},
        {"name": "Travel", "color": "15"},
    ]
    assert parse_qs(urlsplit(captured["url"]).query)["action"] == ["GetMasterCategoryList"]
    assert captured["headers"]["action"] == "GetMasterCategoryList"
    assert captured["payload"] == {"request": {}}


def test_client_lists_category_usage_details_from_owa_shapes():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        action = parse_qs(urlsplit(str(request.url)).query)["action"][0]
        if action == "GetMasterCategoryList":
            return httpx.Response(
                200,
                json={
                    "ResponseCode": "NoError",
                    "MasterList": [
                        {"Name": "Deep Work", "Color": "Preset0"},
                        {"Name": "Travel", "Color": "Preset1"},
                    ],
                },
            )
        if action == "FindCategoryDetails":
            return httpx.Response(
                200,
                json={
                    "Body": {
                        "ResponseCode": "NoError",
                        "CategoryDetails": [
                            {
                                "Name": "Deep Work",
                                "ItemCount": 3,
                                "UnreadCount": 1,
                                "IsSearchFolderReady": True,
                            }
                        ],
                    }
                },
            )
        raise AssertionError(f"Unexpected action {action}")

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    details = client.category_details(request=build_category_details_request().to_dict())

    assert details == [
        {
            "name": "Deep Work",
            "color": "Preset0",
            "item_count": 3,
            "unread_count": 1,
            "is_search_folder_ready": True,
        },
        {
            "name": "Travel",
            "color": "Preset1",
            "item_count": 0,
            "unread_count": 0,
            "is_search_folder_ready": False,
        },
    ]
    assert parse_qs(urlsplit(captured["url"]).query)["action"] == ["FindCategoryDetails"]
    assert captured["headers"]["action"] == "FindCategoryDetails"
    assert captured["payload"]["__type"] == "FindCategoryDetailsJsonRequest:#Exchange"
    assert captured["payload"]["Body"]["__type"] == "FindCategoryDetailsRequest:#Exchange"


def test_client_upserts_mailbox_category_noop_by_name_and_creates_missing_category():
    requests = []
    categories = [{"Name": "Deep Work"}]

    def handler(request: httpx.Request) -> httpx.Response:
        parsed_url = urlsplit(str(request.url))
        body = json.loads(request.content)
        if parsed_url.path == "/api/v2.0/me/MasterCategories":
            requests.append(("OutlookRestMasterCategories", body))
            categories.append(
                {
                    "Name": body["DisplayName"],
                    "DisplayName": body["DisplayName"],
                    "Color": body["Color"],
                    "Id": "rest-cat-1",
                }
            )
            return httpx.Response(
                201,
                json={
                    "DisplayName": body["DisplayName"],
                    "Color": body["Color"],
                    "Id": "rest-cat-1",
                },
            )

        action = parse_qs(parsed_url.query)["action"][0]
        requests.append((action, body))
        if action == "GetMasterCategoryList":
            return httpx.Response(
                200,
                json={
                    "ResponseCode": "NoError",
                    "ResponseClass": "Success",
                    "WasSuccessful": True,
                    "MasterList": list(categories),
                },
            )
        raise AssertionError(f"Unexpected action {action}")

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        rest_base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    noop = client.upsert_category(
        request=build_category_upsert_request(name="Deep Work").to_dict()
    )

    assert noop["changed"] is False
    assert noop["created"] is False
    assert noop["updated"] is False
    created = client.upsert_category(request=build_category_upsert_request(name="Planning").to_dict())

    assert created == {
        "name": "Planning",
        "id": "rest-cat-1",
        "created": True,
        "updated": False,
        "noop": False,
        "changed": True,
        "write_endpoint": "Outlook REST /api/v2.0/me/MasterCategories",
    }
    assert [action for action, _payload in requests] == [
        "GetMasterCategoryList",
        "GetMasterCategoryList",
        "OutlookRestMasterCategories",
    ]
    assert requests[-1][1] == {"DisplayName": "Planning", "Color": "Preset0"}


def test_client_deletes_mailbox_category_with_read_after_delete():
    requests = []
    categories = [
        {"Name": "Deep Work", "Color": "Preset0", "Id": "cat-1"},
        {"Name": "Travel", "Color": "Preset1", "Id": "cat-2"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        parsed_url = urlsplit(str(request.url))
        if request.method == "DELETE":
            requests.append(("DELETE", parsed_url.path))
            assert parsed_url.path == "/api/v2.0/me/MasterCategories('cat-1')"
            categories[:] = [category for category in categories if category["Id"] != "cat-1"]
            return httpx.Response(204)

        body = json.loads(request.content)
        action = parse_qs(parsed_url.query)["action"][0]
        requests.append((action, body))
        if action == "GetMasterCategoryList":
            return httpx.Response(
                200,
                json={
                    "ResponseCode": "NoError",
                    "ResponseClass": "Success",
                    "WasSuccessful": True,
                    "MasterList": list(categories),
                },
            )
        raise AssertionError(f"Unexpected action {action}")

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        rest_base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    deleted = client.delete_category(
        request=build_category_delete_request(
            name="Deep Work",
            confirm_category_name="Deep Work",
        ).to_dict()
    )

    assert deleted == {
        "name": "Deep Work",
        "id": "cat-1",
        "deleted": True,
        "changed": True,
        "write_endpoint": "Outlook REST /api/v2.0/me/MasterCategories",
    }
    assert [item[0] for item in requests] == ["GetMasterCategoryList", "DELETE", "GetMasterCategoryList"]


def test_client_delete_category_missing_name_raises_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ResponseCode": "NoError",
                "MasterList": [{"Name": "Travel", "Color": "Preset1", "Id": "cat-2"}],
            },
        )

    client = OWAClient(
        token="Bearer test-token",
        base_url="https://outlook.example.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    try:
        client.delete_category(
            request=build_category_delete_request(
                name="Deep Work",
                confirm_category_name="Deep Work",
            ).to_dict()
        )
    except M365OwaError as exc:
        assert exc.code == "NOT_FOUND"
        assert "Deep Work" in exc.message
    else:
        raise AssertionError("Expected missing category error")


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
    except M365OwaError as exc:
        assert exc.code == OWA_BACKEND_ERROR
        assert exc.details["create_error"]["ResponseCode"] == "ErrorCannotCreateCalendarItemInNonCalendarFolder"
        assert "secret-token-value" not in repr(exc)
    else:
        raise AssertionError("Expected create backend error")
