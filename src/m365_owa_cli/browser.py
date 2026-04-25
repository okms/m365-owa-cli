from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
import secrets
import socket
import struct
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from .errors import AUTH_REQUIRED, CONFIG_ERROR, M365OwaError, UNSUPPORTED_OPERATION


DEVTOOLS_URL_ENV_VAR = "M365_OWA_BROWSER_DEVTOOLS_URL"
DEFAULT_DEVTOOLS_PORTS = range(9222, 9323)
SUPPORTED_BROWSERS = {"edge", "chrome"}
OWA_ALLOWED_HOSTS = {
    "outlook.cloud.microsoft",
    "outlook.office.com",
    "outlook.office365.com",
}


@dataclass(frozen=True, slots=True)
class BrowserBearerToken:
    token: str
    browser: str
    devtools_url: str
    page_url: str
    source: str
    captured_url: str


@dataclass(frozen=True, slots=True)
class BrowserTokenCredential:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None
    browser: str
    devtools_url: str
    page_url: str
    source: str
    captured_url: str
    token_endpoint: str
    client_id: str
    scope: str | None
    resource: str | None
    redirect_uri: str | None
    origin: str | None
    client_info: str | None
    claims: str | None
    authority: str | None


class _DevToolsWebSocket:
    def __init__(self, websocket_url: str, *, timeout: float) -> None:
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws" or not parsed.hostname:
            raise M365OwaError(
                UNSUPPORTED_OPERATION,
                "Only local ws:// DevTools endpoints are supported.",
                details={"websocket_scheme": parsed.scheme or None},
            )
        self._host = parsed.hostname
        self._port = parsed.port or 80
        self._path = parsed.path or "/"
        if parsed.query:
            self._path += f"?{parsed.query}"
        self._timeout = timeout
        self._sock: socket.socket | None = None

    def __enter__(self) -> "_DevToolsWebSocket":
        sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
        sock.settimeout(self._timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._read_http_response(sock)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise M365OwaError(
                CONFIG_ERROR,
                "DevTools endpoint did not accept a WebSocket upgrade.",
                details={"host": self._host, "port": self._port},
            )
        self._sock = sock
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._sock is not None:
            try:
                self._send_frame(b"", opcode=0x8)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def send_json(self, payload: dict[str, Any]) -> None:
        self._send_frame(json.dumps(payload, separators=(",", ":")).encode("utf-8"), opcode=0x1)

    def receive_json(self, *, timeout: float) -> dict[str, Any] | None:
        sock = self._require_socket()
        previous_timeout = sock.gettimeout()
        sock.settimeout(max(timeout, 0.001))
        try:
            while True:
                opcode, payload = self._receive_frame()
                if opcode == 0x8:
                    return None
                if opcode == 0x9:
                    self._send_frame(payload, opcode=0xA)
                    continue
                if opcode not in {0x1, 0x2}:
                    continue
                try:
                    decoded = payload.decode("utf-8")
                    parsed = json.loads(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return None
                return parsed if isinstance(parsed, dict) else None
        except socket.timeout:
            return None
        finally:
            sock.settimeout(previous_timeout)

    @staticmethod
    def _read_http_response(sock: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while b"\r\n\r\n" not in b"".join(chunks):
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise RuntimeError("DevTools WebSocket is not connected")
        return self._sock

    def _send_frame(self, payload: bytes, *, opcode: int) -> None:
        sock = self._require_socket()
        first = 0x80 | opcode
        mask_bit = 0x80
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", first, mask_bit | length)
        elif length <= 0xFFFF:
            header = struct.pack("!BBH", first, mask_bit | 126, length)
        else:
            header = struct.pack("!BBQ", first, mask_bit | 127, length)
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.sendall(header + mask + masked)

    def _receive_frame(self) -> tuple[int, bytes]:
        sock = self._require_socket()
        header = self._recv_exact(sock, 2)
        first, second = struct.unpack("!BB", header)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(sock, 8))[0]
        mask = self._recv_exact(sock, 4) if masked else b""
        payload = self._recv_exact(sock, length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    @staticmethod
    def _recv_exact(sock: socket.socket, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise M365OwaError(CONFIG_ERROR, "DevTools WebSocket closed unexpectedly.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def capture_browser_bearer_token(
    *,
    browser: str = "edge",
    devtools_url: str | None = None,
    timeout_seconds: float = 20.0,
    reload: bool = False,
) -> BrowserBearerToken | BrowserTokenCredential:
    normalized_browser = browser.lower()
    if normalized_browser not in SUPPORTED_BROWSERS:
        raise M365OwaError(
            UNSUPPORTED_OPERATION,
            "Browser token extraction currently supports Edge and Chrome DevTools endpoints.",
            details={"browser": browser, "supported_browsers": sorted(SUPPORTED_BROWSERS)},
        )
    if timeout_seconds <= 0:
        raise M365OwaError(
            CONFIG_ERROR,
            "Token extraction timeout must be greater than zero.",
            details={"timeout_seconds": timeout_seconds},
        )

    endpoints = discover_devtools_endpoints(devtools_url)
    if not endpoints:
        raise _capture_failed(
            "No browser DevTools endpoint was available.",
            browser=normalized_browser,
            devtools_url=devtools_url,
            endpoints=[],
        )

    candidates: list[dict[str, Any]] = []
    endpoint_errors: list[dict[str, Any]] = []
    for endpoint in endpoints:
        try:
            tabs = fetch_devtools_tabs(endpoint)
        except M365OwaError as exc:
            endpoint_errors.append({"devtools_url": endpoint, "error": exc.to_dict()})
            continue
        tab = choose_owa_tab(tabs)
        if tab is not None:
            candidates.append({"devtools_url": endpoint, "tab": tab})

    if not candidates:
        raise _capture_failed(
            "No open Outlook on the web tab was found in the available DevTools endpoints.",
            browser=normalized_browser,
            devtools_url=devtools_url,
            endpoints=endpoints,
            endpoint_errors=endpoint_errors,
        )

    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        endpoint = str(candidate["devtools_url"])
        tab = candidate["tab"]
        try:
            token = _capture_from_tab(
                browser=normalized_browser,
                devtools_url=endpoint,
                tab=tab,
                timeout_seconds=remaining,
                reload=reload,
            )
            if token is not None:
                return token
            attempts.append({"devtools_url": endpoint, "page_url": tab.get("url"), "captured": False})
        except M365OwaError as exc:
            attempts.append({"devtools_url": endpoint, "page_url": tab.get("url"), "error": exc.to_dict()})

    raise _capture_failed(
        "No OWA bearer authorization header was observed before the timeout.",
        browser=normalized_browser,
        devtools_url=devtools_url,
        endpoints=endpoints,
        attempts=attempts,
    )


def discover_devtools_endpoints(devtools_url: str | None = None) -> list[str]:
    explicit = devtools_url or os.environ.get(DEVTOOLS_URL_ENV_VAR)
    if explicit:
        return [_normalize_devtools_url(explicit)]

    endpoints: list[str] = []
    with httpx.Client(timeout=0.2) as client:
        for port in DEFAULT_DEVTOOLS_PORTS:
            endpoint = f"http://127.0.0.1:{port}"
            try:
                response = client.get(f"{endpoint}/json/version")
            except httpx.HTTPError:
                continue
            if response.status_code == 200:
                endpoints.append(endpoint)
    return endpoints


def fetch_devtools_tabs(devtools_url: str) -> list[dict[str, Any]]:
    normalized = _normalize_devtools_url(devtools_url)
    try:
        response = httpx.get(f"{normalized}/json/list", timeout=2.0)
    except httpx.HTTPError as exc:
        raise M365OwaError(
            CONFIG_ERROR,
            "Could not query the browser DevTools tab list.",
            details={"devtools_url": normalized, "error": str(exc)},
        ) from exc
    if response.status_code != 200:
        raise M365OwaError(
            CONFIG_ERROR,
            "Browser DevTools tab list returned a non-200 response.",
            details={"devtools_url": normalized, "status_code": response.status_code},
        )
    payload = response.json()
    if not isinstance(payload, list):
        raise M365OwaError(
            CONFIG_ERROR,
            "Browser DevTools tab list had an unexpected shape.",
            details={"devtools_url": normalized},
        )
    return [entry for entry in payload if isinstance(entry, dict)]


def choose_owa_tab(tabs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tab in tabs:
        if tab.get("type") not in {None, "page"}:
            continue
        url = tab.get("url")
        websocket_url = tab.get("webSocketDebuggerUrl")
        if isinstance(url, str) and isinstance(websocket_url, str) and _is_allowed_owa_url(url):
            return tab
    return None


def _capture_from_tab(
    *,
    browser: str,
    devtools_url: str,
    tab: dict[str, Any],
    timeout_seconds: float,
    reload: bool,
) -> BrowserBearerToken | BrowserTokenCredential | None:
    websocket_url = tab.get("webSocketDebuggerUrl")
    page_url = tab.get("url")
    if not isinstance(websocket_url, str) or not isinstance(page_url, str):
        return None

    next_id = 0
    request_urls: dict[str, str] = {}
    pending_authorizations: dict[str, str] = {}
    token_request_metadata: dict[str, dict[str, Any]] = {}

    def next_command_id() -> int:
        nonlocal next_id
        next_id += 1
        return next_id

    with _DevToolsWebSocket(websocket_url, timeout=min(timeout_seconds, 5.0)) as websocket:
        network_id = next_command_id()
        websocket.send_json({"id": network_id, "method": "Network.enable"})
        _wait_for_command_response(websocket, network_id, deadline=time.monotonic() + min(2.0, timeout_seconds))

        if reload:
            reload_id = next_command_id()
            websocket.send_json({"id": reload_id, "method": "Page.reload", "params": {"ignoreCache": False}})

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            message = websocket.receive_json(timeout=deadline - time.monotonic())
            if not message:
                continue
            captured = _capture_authorization_from_cdp_event(
                message,
                browser=browser,
                devtools_url=devtools_url,
                page_url=page_url,
                request_urls=request_urls,
                pending_authorizations=pending_authorizations,
            )
            if captured is not None:
                return captured
            credential = _capture_token_response_from_cdp_event(
                message,
                websocket=websocket,
                next_command_id=next_command_id,
                browser=browser,
                devtools_url=devtools_url,
                page_url=page_url,
                token_request_metadata=token_request_metadata,
                deadline=deadline,
            )
            if credential is not None:
                return credential
    return None


def _wait_for_command_response(
    websocket: _DevToolsWebSocket,
    command_id: int,
    *,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        message = websocket.receive_json(timeout=deadline - time.monotonic())
        if not message:
            continue
        if message.get("id") == command_id:
            error = message.get("error")
            if isinstance(error, dict):
                raise M365OwaError(
                    CONFIG_ERROR,
                    "Browser DevTools command failed.",
                    details={"command_id": command_id, "error": error.get("message")},
                )
            return


def _capture_authorization_from_cdp_event(
    message: dict[str, Any],
    *,
    browser: str,
    devtools_url: str,
    page_url: str,
    request_urls: dict[str, str],
    pending_authorizations: dict[str, str],
) -> BrowserBearerToken | None:
    method = message.get("method")
    params = message.get("params")
    if not isinstance(method, str) or not isinstance(params, dict):
        return None

    request_id = params.get("requestId")
    request_id_text = request_id if isinstance(request_id, str) else None

    if method == "Network.requestWillBeSent":
        request = params.get("request")
        if not isinstance(request, dict):
            return None
        url = request.get("url")
        if isinstance(url, str) and request_id_text:
            request_urls[request_id_text] = url
            pending = pending_authorizations.pop(request_id_text, None)
            if pending and _is_target_owa_service_url(url):
                return BrowserBearerToken(
                    token=pending,
                    browser=browser,
                    devtools_url=devtools_url,
                    page_url=page_url,
                    source="devtools_network",
                    captured_url=url,
                )
        headers = request.get("headers")
        authorization = find_authorization_header(headers)
        if authorization and isinstance(url, str) and _is_target_owa_service_url(url):
            return BrowserBearerToken(
                token=authorization,
                browser=browser,
                devtools_url=devtools_url,
                page_url=page_url,
                source="devtools_network",
                captured_url=url,
            )

    if method == "Network.requestWillBeSentExtraInfo":
        headers = params.get("headers")
        authorization = find_authorization_header(headers)
        if not authorization or not request_id_text:
            return None
        url = request_urls.get(request_id_text)
        if url and _is_target_owa_service_url(url):
            return BrowserBearerToken(
                token=authorization,
                browser=browser,
                devtools_url=devtools_url,
                page_url=page_url,
                source="devtools_network_extra_info",
                captured_url=url,
            )
        pending_authorizations[request_id_text] = authorization

    return None


def _capture_token_response_from_cdp_event(
    message: dict[str, Any],
    *,
    websocket: _DevToolsWebSocket,
    next_command_id: Any,
    browser: str,
    devtools_url: str,
    page_url: str,
    token_request_metadata: dict[str, dict[str, Any]],
    deadline: float,
) -> BrowserTokenCredential | None:
    method = message.get("method")
    params = message.get("params")
    if not isinstance(method, str) or not isinstance(params, dict):
        return None

    request_id = params.get("requestId")
    request_id_text = request_id if isinstance(request_id, str) else None
    if not request_id_text:
        return None

    if method == "Network.requestWillBeSent":
        request = params.get("request")
        if isinstance(request, dict):
            metadata = _parse_token_request_metadata(request)
            if metadata is not None:
                token_request_metadata[request_id_text] = metadata
        return None

    if method != "Network.loadingFinished" or request_id_text not in token_request_metadata:
        return None

    command_id = next_command_id()
    websocket.send_json(
        {
            "id": command_id,
            "method": "Network.getResponseBody",
            "params": {"requestId": request_id_text},
        }
    )
    while time.monotonic() < deadline:
        response = websocket.receive_json(timeout=deadline - time.monotonic())
        if not response:
            continue
        if response.get("id") != command_id:
            continue
        result = response.get("result")
        if not isinstance(result, dict):
            return None
        body = result.get("body")
        if not isinstance(body, str):
            return None
        if result.get("base64Encoded") is True:
            try:
                body = base64.b64decode(body).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        metadata = token_request_metadata[request_id_text]
        return _capture_credential_from_token_response(
            payload,
            request_metadata=metadata,
            browser=browser,
            devtools_url=devtools_url,
            page_url=page_url,
            captured_url=str(metadata["token_endpoint"]),
        )
    return None


def find_authorization_header(headers: Any) -> str | None:
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if str(key).lower() != "authorization":
            continue
        value_text = str(value)
        if value_text.lower().startswith("bearer ") and len(value_text.split(None, 1)) == 2:
            return value_text
    return None


def _header_value(headers: Any, name: str) -> str | None:
    if not isinstance(headers, dict):
        return None
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return None


def _first_form_value(form: dict[str, list[str]], name: str) -> str | None:
    values = form.get(name)
    if not values:
        return None
    return values[0]


def _is_microsoft_identity_token_endpoint(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.hostname != "login.microsoftonline.com":
        return False
    return parsed.path.endswith("/token") and "/oauth2/" in parsed.path


def _parse_token_request_metadata(request: dict[str, Any]) -> dict[str, Any] | None:
    url = request.get("url")
    if not isinstance(url, str) or not _is_microsoft_identity_token_endpoint(url):
        return None
    post_data = request.get("postData")
    form = parse_qs(post_data if isinstance(post_data, str) else "", keep_blank_values=True)
    headers = request.get("headers")
    parsed = urlparse(url)
    token_endpoint = parsed._replace(query="", fragment="").geturl()
    metadata = {
        "token_endpoint": token_endpoint,
        "client_id": _first_form_value(form, "client_id"),
        "grant_type": _first_form_value(form, "grant_type"),
        "scope": _first_form_value(form, "scope"),
        "resource": _first_form_value(form, "resource"),
        "redirect_uri": _first_form_value(form, "redirect_uri"),
        "origin": _header_value(headers, "origin"),
        "client_info": _first_form_value(form, "client_info"),
    }
    claims = _first_form_value(form, "claims")
    if claims is not None:
        metadata["claims"] = claims
    return metadata


def _capture_credential_from_token_response(
    response_json: dict[str, Any],
    *,
    request_metadata: dict[str, Any],
    browser: str,
    devtools_url: str,
    page_url: str,
    captured_url: str,
) -> BrowserTokenCredential | None:
    access_token = response_json.get("access_token")
    refresh_token = response_json.get("refresh_token")
    token_endpoint = request_metadata.get("token_endpoint")
    client_id = request_metadata.get("client_id")
    if not all(
        isinstance(value, str) and value
        for value in (access_token, refresh_token, token_endpoint, client_id)
    ):
        return None
    expires_in_value = response_json.get("expires_in")
    expires_in: int | None
    try:
        expires_in = int(float(str(expires_in_value))) if expires_in_value is not None else None
    except (TypeError, ValueError):
        expires_in = None
    parsed_endpoint = urlparse(token_endpoint)
    path_parts = [part for part in parsed_endpoint.path.split("/") if part]
    authority = None
    if path_parts:
        authority = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}/{path_parts[0]}"
    return BrowserTokenCredential(
        access_token=str(access_token),
        refresh_token=str(refresh_token),
        token_type=str(response_json.get("token_type") or "Bearer"),
        expires_in=expires_in,
        browser=browser,
        devtools_url=devtools_url,
        page_url=page_url,
        source="devtools_token_response",
        captured_url=captured_url,
        token_endpoint=str(token_endpoint),
        client_id=str(client_id),
        scope=request_metadata.get("scope"),
        resource=request_metadata.get("resource"),
        redirect_uri=request_metadata.get("redirect_uri"),
        origin=request_metadata.get("origin"),
        client_info=request_metadata.get("client_info"),
        claims=request_metadata.get("claims"),
        authority=authority,
    )


def _safe_captured_credential_metadata(credential: BrowserTokenCredential | None) -> dict[str, Any]:
    if credential is None:
        return {"stored_access_token": False, "stored_refresh_token": False}
    return {
        "stored_access_token": bool(credential.access_token),
        "stored_refresh_token": bool(credential.refresh_token),
        "token_endpoint_host": urlparse(credential.token_endpoint).hostname,
        "source": credential.source,
        "client_id": credential.client_id,
        "expires_in": credential.expires_in,
    }


def _is_allowed_owa_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in OWA_ALLOWED_HOSTS


def _is_target_owa_service_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in OWA_ALLOWED_HOSTS and "/owa/service.svc" in parsed.path


def _normalize_devtools_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise M365OwaError(
            CONFIG_ERROR,
            "DevTools URL must be an http(s) URL.",
            details={"devtools_url": value},
        )
    return value.rstrip("/")


def _capture_failed(
    message: str,
    *,
    browser: str,
    devtools_url: str | None,
    endpoints: list[str],
    **details: Any,
) -> M365OwaError:
    return M365OwaError(
        AUTH_REQUIRED,
        message,
        details={
            "browser": browser,
            "devtools_url": devtools_url,
            "discovered_devtools_urls": endpoints,
            "env_var": DEVTOOLS_URL_ENV_VAR,
            "manual_fallback": "m365-owa-cli auth bookmarklet --connection <name> --raw",
            "launch_hint": _browser_launch_hint(browser),
            **details,
        },
    )


def _browser_launch_hint(browser: str) -> str:
    if browser == "edge":
        return (
            "Start Microsoft Edge with remote debugging enabled, open Outlook on the web, then rerun with "
            "--devtools-url http://127.0.0.1:9222. On macOS the executable is commonly "
            "'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'."
        )
    return (
        "Start Chrome with --remote-debugging-port=9222, open Outlook on the web, then rerun with "
        "--devtools-url http://127.0.0.1:9222."
    )
