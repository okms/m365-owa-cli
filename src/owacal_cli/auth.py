from __future__ import annotations

import json
from pathlib import Path

try:
    from .errors import (  # type: ignore
        AUTH_REQUIRED,
        UNSUPPORTED_OPERATION,
        OwacalError,
    )
except ImportError:  # pragma: no cover - fallback for partial scaffolds
    from .config import (
        UNSUPPORTED_OPERATION,
        OwacalError,
    )
    AUTH_REQUIRED = "AUTH_REQUIRED"

from .config import (
    connection_env_var_name,
    list_connections,
    remove_token,
    resolve_token,
    set_token,
    validate_connection_name,
)
from .owa.client import OWAClient

__all__ = [
    "auth_test",
    "bookmarklet_payload",
    "extract_token",
    "list_connections",
    "remove_token",
    "resolve_token",
    "set_token",
]


BOOKMARKLET_ALLOWED_HOSTS = (
    "outlook.cloud.microsoft",
    "outlook.office.com",
    "outlook.office365.com",
)


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
            alert("owacal-cli: open Outlook on the web first. Allowed hosts: " + allowedHosts.join(", "));
            return;
          }}
          if (window.__owacalTokenBookmarkletInstalled) {{
            if (window.__owacalTokenBookmarkletShow) {{
              window.__owacalTokenBookmarkletShow("Already watching OWA requests for connection " + connection + ".");
            }}
            return;
          }}
          window.__owacalTokenBookmarkletInstalled = true;
          const panel = document.createElement("div");
          panel.id = "owacal-token-helper";
          panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;width:min(520px,calc(100vw - 32px));background:#111827;color:#f9fafb;border:1px solid #374151;border-radius:6px;padding:12px;font:13px/1.35 system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 18px 40px rgba(0,0,0,.35)";
          function makeText(tag, text, styles) {{
            const node = document.createElement(tag);
            node.textContent = text;
            if (styles) Object.assign(node.style, styles);
            return node;
          }}
          const title = makeText("div", "owacal-cli token helper", {{fontWeight:"700", marginBottom:"6px"}});
          const status = makeText("div", "Watching future OWA calendar requests for connection " + connection + ". Refresh or open Calendar if nothing appears.");
          status.id = "owacal-status";
          const textarea = document.createElement("textarea");
          textarea.id = "owacal-token";
          textarea.readOnly = true;
          Object.assign(textarea.style, {{display:"none", marginTop:"8px", width:"100%", height:"82px", boxSizing:"border-box", background:"#030712", color:"#f9fafb", border:"1px solid #4b5563", borderRadius:"4px", padding:"6px", font:"12px ui-monospace,SFMono-Regular,Menlo,monospace"}});
          const actions = document.createElement("div");
          Object.assign(actions.style, {{display:"flex", gap:"8px", marginTop:"8px"}});
          const copy = document.createElement("button");
          copy.id = "owacal-copy";
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
          window.__owacalTokenBookmarkletShow = message => {{
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
            status.textContent = "Captured bearer header from " + new URL(url, location.href).pathname + ". Store it with: owacal-cli auth set-token --connection " + connection;
            copy.onclick = () => navigator.clipboard.writeText(auth).then(() => {{
              status.textContent = "Copied. Store it with: owacal-cli auth set-token --connection " + connection;
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
            this.__owacalUrl = url;
            return originalOpen.apply(this, arguments);
          }};
          XMLHttpRequest.prototype.setRequestHeader = function(name, value) {{
            if (String(name).toLowerCase() === "authorization") this.__owacalAuthorization = value;
            return originalSetRequestHeader.apply(this, arguments);
          }};
          const originalSend = XMLHttpRequest.prototype.send;
          XMLHttpRequest.prototype.send = function() {{
            try {{ capture(this.__owacalAuthorization, this.__owacalUrl || location.href); }} catch (error) {{}}
            return originalSend.apply(this, arguments);
          }};
          window.__owacalTokenBookmarkletShow("Watching future OWA requests for connection " + connection + ". Refresh or open Calendar if nothing appears.");
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
            "Copy the captured bearer value and run owacal-cli auth set-token --connection "
            + connection,
        ],
    }


def auth_test(
    connection: str,
    token: str | None = None,
    config_dir: Path | None = None,
) -> None:
    validate_connection_name(connection)
    resolved_token = resolve_token(connection, token=token, config_dir=config_dir)
    if not resolved_token:
        raise OwacalError(
            AUTH_REQUIRED,
            f"No token found for connection {connection!r}.",
            retryable=False,
            details={"connection": connection},
        )
    OWAClient(connection=connection, token=resolved_token).probe()


def extract_token(
    connection: str,
    browser: str = "edge",
    config_dir: Path | None = None,
) -> None:
    validate_connection_name(connection)
    if browser.lower() != "edge":
        raise OwacalError(
            UNSUPPORTED_OPERATION,
            "Only Edge token extraction is considered for v1.",
            retryable=False,
            details={"browser": browser},
        )
    raise OwacalError(
        UNSUPPORTED_OPERATION,
        "Browser token extraction is not implemented in this build.",
        retryable=False,
        details={
            "browser": browser,
            "connection": connection,
            "env_var": connection_env_var_name(connection),
        },
    )
