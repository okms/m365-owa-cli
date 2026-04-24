from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from m365_owa_cli.errors import redact_tokens


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
GUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "cookie",
    "password",
    "secret",
    "token",
)
_IDENTITY_KEY_NAMES = {
    "changekey",
    "conversationid",
    "eventid",
    "folderid",
    "icaluid",
    "id",
    "instancekey",
    "itemid",
    "occurrenceid",
    "seriesmasterid",
    "uid",
}
_IDENTITY_KEY_SUFFIXES = ("id", "key")


def _key_text(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_sensitive_key(key: Any) -> bool:
    text = _key_text(key)
    return any(part in text for part in _SENSITIVE_KEY_PARTS)


def _is_identity_key(key: Any) -> bool:
    text = _key_text(key)
    return text in _IDENTITY_KEY_NAMES or text.endswith(_IDENTITY_KEY_SUFFIXES)


def _is_identity_path(path: tuple[str, ...]) -> bool:
    return bool(path) and _is_identity_key(path[-1])


def _placeholder(mapping: dict[str, str], value: str, prefix: str) -> str:
    if value not in mapping:
        mapping[value] = f"<{prefix}_{len(mapping) + 1:04d}>"
    return mapping[value]


@dataclass
class OwaFixtureSanitizer:
    """Redact identity and token material from captured OWA request/response JSON."""

    emails: dict[str, str] = field(default_factory=dict)
    guids: dict[str, str] = field(default_factory=dict)
    owa_ids: dict[str, str] = field(default_factory=dict)

    def sanitize(self, value: Any, *, path: tuple[str, ...] = ()) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._sanitize_string(value, path=path)
        if isinstance(value, Mapping):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                key_string = str(key)
                if _is_sensitive_key(key_string):
                    redacted[key_string] = "[REDACTED]"
                else:
                    redacted[key_string] = self.sanitize(item, path=path + (key_string,))
            return redacted
        if isinstance(value, list):
            return [self.sanitize(item, path=path) for item in value]
        if isinstance(value, tuple):
            return [self.sanitize(item, path=path) for item in value]
        return self._sanitize_string(str(value), path=path)

    def _sanitize_string(self, value: str, *, path: tuple[str, ...]) -> str:
        parsed_json = self._sanitize_embedded_json(value, path=path)
        if parsed_json is not None:
            return parsed_json

        if GUID_RE.fullmatch(value):
            return _placeholder(self.guids, value.lower(), "GUID")
        if EMAIL_RE.fullmatch(value):
            return self._email_placeholder(value)
        if _is_identity_path(path) and value:
            return _placeholder(self.owa_ids, value, "OWA_ID")

        redacted = redact_tokens(value)
        redacted = self._redact_url_query_values(redacted)
        redacted = EMAIL_RE.sub(lambda match: self._email_placeholder(match.group(0)), redacted)
        redacted = GUID_RE.sub(lambda match: _placeholder(self.guids, match.group(0).lower(), "GUID"), redacted)
        return redacted

    def _sanitize_embedded_json(self, value: str, *, path: tuple[str, ...]) -> str | None:
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        sanitized = self.sanitize(parsed, path=path)
        return json.dumps(sanitized, ensure_ascii=False, sort_keys=False, separators=(",", ":"))

    def _email_placeholder(self, value: str) -> str:
        key = value.lower()
        if key not in self.emails:
            self.emails[key] = f"user{len(self.emails) + 1:03d}@example.invalid"
        return self.emails[key]

    def _redact_url_query_values(self, value: str) -> str:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc or not parts.query:
            return value
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        redacted_pairs = [
            (key, "[REDACTED]" if _is_sensitive_key(key) else item)
            for key, item in pairs
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted_pairs), parts.fragment))


def sanitize_owa_fixture(value: Any) -> Any:
    return OwaFixtureSanitizer().sanitize(value)


def extract_har_action_entries(har_payload: Mapping[str, Any], action: str) -> dict[str, Any]:
    entries = har_payload.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        return {"log": {"entries": []}}

    marker = f"action={action}".lower()
    selected = []
    for entry in entries:
        request = entry.get("request", {}) if isinstance(entry, Mapping) else {}
        url = str(request.get("url", "")).lower() if isinstance(request, Mapping) else ""
        if marker in url:
            selected.append(entry)
    return {"log": {"entries": selected}}
