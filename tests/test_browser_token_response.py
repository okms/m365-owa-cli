from __future__ import annotations

import json
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m365_owa_cli import browser


ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.secret-access-token"
REFRESH_TOKEN = "0.AXMAAA.secret-refresh-token"
AUTHORIZATION_CODE = "0.ARoAAA.secret-authorization-code"


def test_login_microsoftonline_v2_token_endpoint_is_recognized():
    assert browser._is_microsoft_identity_token_endpoint(  # pyright: ignore[reportPrivateUsage]
        "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    )
    assert browser._is_microsoft_identity_token_endpoint(  # pyright: ignore[reportPrivateUsage]
        "https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/oauth2/v2.0/token"
    )
    assert browser._is_microsoft_identity_token_endpoint(  # pyright: ignore[reportPrivateUsage]
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/token?client-request-id=abc"
    )

    assert not browser._is_microsoft_identity_token_endpoint(  # pyright: ignore[reportPrivateUsage]
        "https://login.microsoftonline.com/common/oauth2/authorize"
    )
    assert not browser._is_microsoft_identity_token_endpoint(  # pyright: ignore[reportPrivateUsage]
        "https://evil.example/common/oauth2/v2.0/token"
    )


def test_owa_route_family_classifier_recognizes_mail_and_people_routes():
    service = browser.classify_owa_route_family(
        "https://outlook.office.com/owa/service.svc?action=FindItem&app=Mail"
    )
    subroute = browser.classify_owa_route_family(
        "https://outlook.office.com/owa/service.svc/s/GetPersonaPhoto?id=abc"
    )
    people = browser.classify_owa_route_family(
        "https://outlook.office.com/PeopleGraphVx/v1.0/contacts"
    )
    graphql = browser.classify_owa_route_family(
        "https://outlook.office.com/ows/beta/graphql"
    )
    external = browser.classify_owa_route_family("https://example.com/owa/service.svc")

    assert service["route_family"] == "owa_service_svc"
    assert service["accepted_for_bearer_capture"] is True
    assert subroute["route_family"] == "owa_service_svc_s"
    assert people["route_family"] == "owa_people_routes"
    assert graphql["route_family"] == "owa_graphql_gateway"
    assert external["route_family"] == "external"
    assert external["accepted_for_bearer_capture"] is False


def test_token_request_metadata_parses_form_without_preserving_secrets():
    request = {
        "url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Origin": "https://outlook.office.com",
        },
        "postData": (
            "client_id=owa-public-client-id"
            "&grant_type=authorization_code"
            f"&code={AUTHORIZATION_CODE}"
            "&scope=openid%20profile%20offline_access%20https%3A%2F%2Foutlook.office.com%2F.default"
            "&redirect_uri=https%3A%2F%2Foutlook.office.com%2Fmail%2F"
            "&client_info=1"
        ),
    }

    metadata = browser._parse_token_request_metadata(request)  # pyright: ignore[reportPrivateUsage]
    dumped = json.dumps(metadata, sort_keys=True)

    assert metadata == {
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "client_id": "owa-public-client-id",
        "grant_type": "authorization_code",
        "scope": "openid profile offline_access https://outlook.office.com/.default",
        "resource": None,
        "redirect_uri": "https://outlook.office.com/mail/",
        "origin": "https://outlook.office.com",
        "client_info": "1",
    }
    assert AUTHORIZATION_CODE not in dumped
    assert "code=" not in dumped
    assert "postData" not in dumped


def test_token_response_json_becomes_captured_credential_with_context():
    request_metadata = {
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "client_id": "owa-public-client-id",
        "grant_type": "authorization_code",
        "scope": "openid profile offline_access https://outlook.office.com/.default",
        "resource": None,
        "redirect_uri": "https://outlook.office.com/mail/",
        "origin": "https://outlook.office.com",
        "client_info": "1",
    }
    response_json = {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3599,
    }

    credential = browser._capture_credential_from_token_response(  # pyright: ignore[reportPrivateUsage]
        response_json,
        request_metadata=request_metadata,
        browser="chrome",
        devtools_url="http://127.0.0.1:9222",
        page_url="https://outlook.office.com/mail/",
        captured_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    )

    assert credential is not None
    assert credential.access_token == ACCESS_TOKEN
    assert credential.refresh_token == REFRESH_TOKEN
    assert credential.token_type == "Bearer"
    assert credential.expires_in == 3599
    assert credential.token_endpoint == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert credential.client_id == "owa-public-client-id"
    assert credential.scope == "openid profile offline_access https://outlook.office.com/.default"
    assert credential.resource is None
    assert credential.redirect_uri == "https://outlook.office.com/mail/"
    assert credential.origin == "https://outlook.office.com"
    assert credential.source == "devtools_token_response"
    assert credential.browser == "chrome"
    assert credential.devtools_url == "http://127.0.0.1:9222"
    assert credential.page_url == "https://outlook.office.com/mail/"
    assert credential.captured_url == "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def test_token_response_capture_metadata_redacts_tokens():
    request_metadata = {
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "client_id": "owa-public-client-id",
        "grant_type": "authorization_code",
        "scope": "openid profile offline_access https://outlook.office.com/.default",
        "resource": None,
        "redirect_uri": "https://outlook.office.com/mail/",
        "origin": "https://outlook.office.com",
        "client_info": "1",
    }
    credential = browser._capture_credential_from_token_response(  # pyright: ignore[reportPrivateUsage]
        {
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "token_type": "Bearer",
            "expires_in": 3599,
        },
        request_metadata=request_metadata,
        browser="chrome",
        devtools_url="http://127.0.0.1:9222",
        page_url="https://outlook.office.com/mail/",
        captured_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    )

    metadata = browser._safe_captured_credential_metadata(credential)  # pyright: ignore[reportPrivateUsage]
    dumped = json.dumps(metadata, sort_keys=True)

    assert metadata["stored_access_token"] is True
    assert metadata["stored_refresh_token"] is True
    assert metadata["token_endpoint_host"] == "login.microsoftonline.com"
    assert metadata["source"] == "devtools_token_response"
    assert metadata["client_id"] == "owa-public-client-id"
    assert ACCESS_TOKEN not in dumped
    assert REFRESH_TOKEN not in dumped
    assert "secret-access-token" not in dumped
    assert "secret-refresh-token" not in dumped
