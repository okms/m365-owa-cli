from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    from .errors import (  # type: ignore
        AUTH_REFRESH_FAILED,
        AUTH_REQUIRED,
        CONFIG_ERROR,
        M365OwaError,
        redact_tokens,
    )
except ImportError:  # pragma: no cover - fallback for partial scaffolds
    from .config import M365OwaError
    AUTH_REFRESH_FAILED = "AUTH_REFRESH_FAILED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONFIG_ERROR = "CONFIG_ERROR"

from .config import (
    connection_credential_path,
    credential_metadata,
    list_connections,
    read_credential,
    remove_token,
    resolve_token,
    set_credential,
    set_token,
    validate_connection_name,
)
from .browser import BrowserTokenCredential, capture_browser_bearer_token
from .owa.client import OWAClient

__all__ = [
    "auth_test",
    "bookmarklet_payload",
    "inspect_connection",
    "extract_token",
    "list_connections",
    "remove_token",
    "refresh_connection_token",
    "resolve_connection_access_token",
    "resolve_token",
    "set_token",
]


BOOKMARKLET_ALLOWED_HOSTS = (
    "outlook.cloud.microsoft",
    "outlook.office.com",
    "outlook.office365.com",
)
DEFAULT_REFRESH_ORIGIN = "https://outlook.office.com"
REFRESH_SKEW = timedelta(minutes=5)


def _compact_javascript(source: str) -> str:
    return " ".join(line.strip() for line in source.splitlines() if line.strip())


def bookmarklet_payload(connection: str) -> dict:
    validate_connection_name(connection)
    connection_js = json.dumps(connection)
    allowed_hosts_js = json.dumps(list(BOOKMARKLET_ALLOWED_HOSTS))
    script = _compact_javascript(
        f"""
        (() => {{
          const connection = {connection_js};
          const allowedHosts = {allowed_hosts_js};
          if (!allowedHosts.includes(location.hostname)) {{
            alert("m365-owa-cli: open Outlook on the web first. Allowed hosts: " + allowedHosts.join(", "));
            return;
          }}
          if (window.__m365OwaTokenBookmarkletInstalled) {{
            if (window.__m365OwaTokenBookmarkletShow) {{
              window.__m365OwaTokenBookmarkletShow("Already watching OWA requests for connection " + connection + ".");
            }}
            return;
          }}
          window.__m365OwaTokenBookmarkletInstalled = true;
          const panel = document.createElement("div");
          panel.id = "m365-owa-token-helper";
          panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;width:min(520px,calc(100vw - 32px));background:#111827;color:#f9fafb;border:1px solid #374151;border-radius:6px;padding:12px;font:13px/1.35 system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 18px 40px rgba(0,0,0,.35)";
          function makeText(tag, text, styles) {{
            const node = document.createElement(tag);
            node.textContent = text;
            if (styles) Object.assign(node.style, styles);
            return node;
          }}
          const title = makeText("div", "m365-owa-cli token helper", {{fontWeight:"700", marginBottom:"6px"}});
          const status = makeText("div", "Watching future OWA calendar requests for connection " + connection + ". Refresh or open Calendar if nothing appears.");
          status.id = "m365-owa-status";
          const textarea = document.createElement("textarea");
          textarea.id = "m365-owa-token";
          textarea.readOnly = true;
          Object.assign(textarea.style, {{display:"none", marginTop:"8px", width:"100%", height:"82px", boxSizing:"border-box", background:"#030712", color:"#f9fafb", border:"1px solid #4b5563", borderRadius:"4px", padding:"6px", font:"12px ui-monospace,SFMono-Regular,Menlo,monospace"}});
          const actions = document.createElement("div");
          Object.assign(actions.style, {{display:"flex", gap:"8px", marginTop:"8px"}});
          const copy = document.createElement("button");
          copy.id = "m365-owa-copy";
          copy.type = "button";
          copy.textContent = "Copy";
          copy.style.display = "none";
          const close = document.createElement("button");
          close.type = "button";
          close.textContent = "Close";
          actions.append(copy, close);
          panel.append(title, status, textarea, actions);
          document.body.appendChild(panel);
          close.onclick = () => panel.remove();
          window.__m365OwaTokenBookmarkletShow = message => {{
            if (!document.body.contains(panel)) document.body.appendChild(panel);
            status.textContent = message;
          }};
          function headerValue(headers, name) {{
            if (!headers) return null;
            const wanted = name.toLowerCase();
            try {{
              if (typeof Headers !== "undefined" && headers instanceof Headers) return headers.get(name);
              if (Array.isArray(headers)) {{
                for (const pair of headers) {{
                  if (String(pair[0]).toLowerCase() === wanted) return String(pair[1]);
                }}
                return null;
              }}
              if (typeof headers === "object") {{
                for (const key of Object.keys(headers)) {{
                  if (key.toLowerCase() === wanted) return String(headers[key]);
                }}
              }}
            }} catch (error) {{}}
            return null;
          }}
          function isTarget(url) {{
            try {{
              const parsed = new URL(url, location.href);
              return allowedHosts.includes(parsed.hostname) && parsed.pathname.includes("/owa/service.svc");
            }} catch (error) {{
              return false;
            }}
          }}
          function requestUrl(input) {{
            if (typeof input === "string") return input;
            if (input && input.url) return input.url;
            return "";
          }}
          function capture(auth, url) {{
            if (!auth || !/^Bearer\\s+\\S+/i.test(auth) || !isTarget(url)) return;
            textarea.style.display = "block";
            copy.style.display = "inline-block";
            textarea.value = auth;
            status.textContent = "Captured bearer header from " + new URL(url, location.href).pathname + ". Store it with: m365-owa-cli auth set-token --connection " + connection;
            copy.onclick = () => navigator.clipboard.writeText(auth).then(() => {{
              status.textContent = "Copied. Store it with: m365-owa-cli auth set-token --connection " + connection;
            }}).catch(() => {{
              textarea.focus();
              textarea.select();
            }});
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(auth).catch(() => {{}});
            }}
          }}
          const originalFetch = window.fetch;
          if (originalFetch) {{
            window.fetch = function(input, init) {{
              try {{
                const url = requestUrl(input);
                const auth = headerValue(init && init.headers, "authorization") || headerValue(input && input.headers, "authorization");
                capture(auth, url);
              }} catch (error) {{}}
              return originalFetch.apply(this, arguments);
            }};
          }}
          const originalOpen = XMLHttpRequest.prototype.open;
          const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
          XMLHttpRequest.prototype.open = function(method, url) {{
            this.__m365OwaUrl = url;
            return originalOpen.apply(this, arguments);
          }};
          XMLHttpRequest.prototype.setRequestHeader = function(name, value) {{
            if (String(name).toLowerCase() === "authorization") this.__m365OwaAuthorization = value;
            return originalSetRequestHeader.apply(this, arguments);
          }};
          const originalSend = XMLHttpRequest.prototype.send;
          XMLHttpRequest.prototype.send = function() {{
            try {{ capture(this.__m365OwaAuthorization, this.__m365OwaUrl || location.href); }} catch (error) {{}}
            return originalSend.apply(this, arguments);
          }};
          window.__m365OwaTokenBookmarkletShow("Watching future OWA requests for connection " + connection + ". Refresh or open Calendar if nothing appears.");
        }})();
        """
    )
    return {
        "connection": connection,
        "bookmarklet": "javascript:" + script,
        "allowed_hosts": list(BOOKMARKLET_ALLOWED_HOSTS),
        "captures": [
            "Authorization bearer headers from future fetch/XMLHttpRequest calls to /owa/service.svc",
        ],
        "does_not": [
            "read browser network history",
            "send captured values to a remote service",
            "write token files directly",
        ],
        "usage": [
            "Create a browser bookmark whose URL is the bookmarklet value.",
            "Open Outlook on the web on an allowed host.",
            "Click the bookmarklet, then refresh or open Calendar to trigger OWA service requests.",
            "Copy the captured bearer value and run m365-owa-cli auth set-token --connection "
            + connection,
        ],
    }


def auth_test(
    connection: str,
    token: str | None = None,
    config_dir: Path | None = None,
) -> None:
    validate_connection_name(connection)
    resolved_token = resolve_connection_access_token(connection, token=token, config_dir=config_dir)
    if not resolved_token:
        raise M365OwaError(
            AUTH_REQUIRED,
            f"No token found for connection {connection!r}.",
            retryable=False,
            details={"connection": connection},
        )
    OWAClient(connection=connection, token=resolved_token).probe()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _credential_expires_soon(credential: dict[str, Any], *, now: datetime | None = None) -> bool:
    expires_at = _parse_datetime(credential.get("expires_at"))
    if expires_at is None:
        return False
    return expires_at <= ((now or _utc_now()) + REFRESH_SKEW)


def _expires_at_from_token_response(payload: dict[str, Any], *, now: datetime | None = None) -> str | None:
    if payload.get("expires_at"):
        parsed = _parse_datetime(payload.get("expires_at"))
        return _format_datetime(parsed) if parsed else str(payload["expires_at"])
    if payload.get("expires_on"):
        expires_on = payload["expires_on"]
        try:
            parsed = datetime.fromtimestamp(int(str(expires_on)), tz=timezone.utc)
            return _format_datetime(parsed)
        except (TypeError, ValueError, OSError):
            parsed = _parse_datetime(expires_on)
            return _format_datetime(parsed) if parsed else str(expires_on)
    if payload.get("expires_in") is not None:
        try:
            seconds = int(float(str(payload["expires_in"])))
        except (TypeError, ValueError):
            return None
        return _format_datetime((now or _utc_now()) + timedelta(seconds=seconds))
    return None


def _refresh_form(credential: dict[str, Any]) -> dict[str, str]:
    refresh_token = credential.get("refresh_token")
    client_id = credential.get("client_id")
    if not refresh_token or not client_id:
        raise M365OwaError(
            AUTH_REQUIRED,
            "Connection does not have refresh-token metadata.",
            details={
                "connection": credential.get("connection"),
                "has_refresh_token": bool(refresh_token),
                "client_id_present": bool(client_id),
            },
        )
    form = {
        "client_id": str(client_id),
        "grant_type": "refresh_token",
        "refresh_token": str(refresh_token),
    }
    if credential.get("scope"):
        form["scope"] = str(credential["scope"])
    elif credential.get("resource"):
        form["resource"] = str(credential["resource"])
    for key in ("redirect_uri", "client_info", "claims"):
        value = credential.get(key)
        if value:
            form[key] = str(value)
    return form


def _credential_from_browser_capture(connection: str, captured: BrowserTokenCredential) -> dict[str, Any]:
    return {
        "version": 1,
        "connection": connection,
        "access_token": captured.access_token,
        "refresh_token": captured.refresh_token,
        "token_type": captured.token_type,
        "expires_at": _expires_at_from_token_response({"expires_in": captured.expires_in}),
        "authority": captured.authority,
        "token_endpoint": captured.token_endpoint,
        "client_id": captured.client_id,
        "origin": captured.origin or DEFAULT_REFRESH_ORIGIN,
        "resource": captured.resource,
        "scope": captured.scope,
        "redirect_uri": captured.redirect_uri,
        "client_info": captured.client_info,
        "claims": captured.claims,
        "captured_source": captured.source,
        "captured_at": _format_datetime(_utc_now()),
    }


def inspect_connection(connection: str, config_dir: Path | None = None) -> dict[str, Any]:
    validate_connection_name(connection)
    credential = read_credential(connection, config_dir=config_dir)
    metadata = credential_metadata(connection, credential=credential, config_dir=config_dir)
    metadata["name"] = connection
    metadata["has_credential"] = credential is not None
    metadata["expires_at"] = metadata.get("access_token_expires_at")
    return metadata


def refresh_connection_token(
    connection: str,
    *,
    config_dir: Path | None = None,
    http_client: httpx.Client | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_connection_name(connection)
    credential = read_credential(connection, config_dir=config_dir)
    if not credential:
        raise M365OwaError(
            AUTH_REQUIRED,
            f"No refresh credential found for connection {connection!r}.",
            details={
                "connection": connection,
                "credential_file": str(connection_credential_path(connection, config_dir)),
            },
        )
    token_endpoint = credential.get("token_endpoint")
    if not token_endpoint:
        raise M365OwaError(
            CONFIG_ERROR,
            "Connection credential is missing token endpoint metadata.",
            details={"connection": connection},
        )

    form = _refresh_form(credential)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": str(credential.get("origin") or DEFAULT_REFRESH_ORIGIN),
    }
    close_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        response = client.post(str(token_endpoint), data=form, headers=headers)
    except httpx.HTTPError as exc:
        raise M365OwaError(
            AUTH_REFRESH_FAILED,
            "Token refresh request failed.",
            retryable=True,
            details=redact_tokens(
                {
                    "connection": connection,
                    "token_endpoint_host": urlparse(str(token_endpoint)).hostname,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                }
            ),
        ) from exc
    finally:
        if close_client:
            client.close()

    details = {
        "connection": connection,
        "token_endpoint_host": urlparse(str(token_endpoint)).hostname,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
    }
    try:
        payload = response.json()
    except ValueError as exc:
        details["response_preview"] = response.text[:500]
        raise M365OwaError(
            AUTH_REFRESH_FAILED,
            "Token refresh returned a non-JSON response.",
            retryable=response.status_code >= 500,
            details=redact_tokens(details),
        ) from exc

    if response.status_code >= 400 or not isinstance(payload, dict) or not payload.get("access_token"):
        if isinstance(payload, dict):
            details["token_error"] = {
                "error": payload.get("error"),
                "error_description": payload.get("error_description"),
                "error_codes": payload.get("error_codes"),
            }
        raise M365OwaError(
            AUTH_REFRESH_FAILED,
            "Token refresh was rejected. Recapture the connection token from Outlook on the web.",
            retryable=False,
            details=redact_tokens(details),
        )

    updated = dict(credential)
    updated["access_token"] = str(payload["access_token"])
    if payload.get("refresh_token"):
        updated["refresh_token"] = str(payload["refresh_token"])
    if payload.get("token_type"):
        updated["token_type"] = str(payload["token_type"])
    expires_at = _expires_at_from_token_response(payload, now=now)
    if expires_at:
        updated["expires_at"] = expires_at
    set_credential(connection, updated, config_dir=config_dir)

    metadata = credential_metadata(connection, credential=updated, config_dir=config_dir)
    metadata.update(
        {
            "name": connection,
            "refreshed": True,
            "rotated_refresh_token": bool(payload.get("refresh_token")),
        }
    )
    return metadata


def resolve_connection_access_token(
    connection: str,
    *,
    token: str | None = None,
    config_dir: Path | None = None,
    refresh_if_needed: bool = True,
) -> str | None:
    validate_connection_name(connection)
    if token is not None:
        return resolve_token(connection, token=token, config_dir=config_dir)

    credential = read_credential(connection, config_dir=config_dir)
    if credential is not None:
        if refresh_if_needed and credential.get("refresh_token") and _credential_expires_soon(credential):
            refresh_connection_token(connection, config_dir=config_dir)
            credential = read_credential(connection, config_dir=config_dir)
        if credential and credential.get("access_token"):
            return str(credential["access_token"]).rstrip("\r\n")

    return resolve_token(connection, config_dir=config_dir)


def extract_token(
    connection: str,
    browser: str = "edge",
    devtools_url: str | None = None,
    timeout_seconds: float = 20.0,
    reload: bool = False,
    config_dir: Path | None = None,
) -> dict:
    validate_connection_name(connection)
    started_at = time.monotonic()
    captured = capture_browser_bearer_token(
        browser=browser,
        devtools_url=devtools_url,
        timeout_seconds=timeout_seconds,
        reload=reload,
    )
    if isinstance(captured, BrowserTokenCredential):
        credential = _credential_from_browser_capture(connection, captured)
        path = set_credential(connection, credential, config_dir=config_dir)
        return {
            "name": connection,
            "browser": captured.browser,
            "stored": True,
            "stored_access_token": True,
            "stored_refresh_token": True,
            "credential_file": str(path),
            "source": captured.source,
            "devtools_url": captured.devtools_url,
            "page_url": captured.page_url,
            "token_endpoint_host": urlparse(captured.token_endpoint).hostname,
            "expires_at": credential.get("expires_at"),
            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
        }
    path = set_token(connection, captured.token, config_dir=config_dir)
    return {
        "name": connection,
        "browser": captured.browser,
        "stored": True,
        "token_file": str(path),
        "source": captured.source,
        "devtools_url": captured.devtools_url,
        "page_url": captured.page_url,
        "captured_host": urlparse(captured.captured_url).hostname,
        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
    }
