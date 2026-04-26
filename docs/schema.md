# Stable JSON Schemas

`m365-owa-cli` emits JSON success and error envelopes by default. Machine consumers should inspect `m365-owa-cli schema commands`, `m365-owa-cli schema event`, and `m365-owa-cli schema errors` before relying on a command.

## Event Output

`events list` and `events search` return `data` as an array of `Event` objects. `events get` returns a single `Event` object once the OWA adapter is implemented.

```json
{
  "ok": true,
  "connection": "work",
  "operation": "events.list",
  "range": {},
  "data": []
}
```

The canonical machine schema is `schema event`. The current stable event object includes:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string or null | OWA item id when available. |
| `occurrence_id` | string or null | Expanded occurrence id or instance key when available. |
| `series_master_id` | string or null | Series/master identifier when OWA exposes it. |
| `subject` | string or null | Compatibility name for the event title. |
| `title` | string or null | Canonical export title; currently mirrors `subject` when no explicit title is present. |
| `start`, `end` | string or null | Compatibility ISO datetime fields. |
| `start_iso_local`, `end_iso_local` | string or null | Canonical export datetime fields. |
| `is_all_day` | boolean | Derived from OWA all-day metadata. |
| `duration_minutes` | integer or null | Derived when both start and end parse as datetimes. |
| `body` | string or null | Body content, falling back to preview when no body is available. |
| `body_type` | `text`, `html`, or null | Compatibility body content type. |
| `body_content_type` | `text`, `html`, or null | Canonical export body content type. |
| `body_preview` | string or null | OWA preview text when available. |
| `categories` | array of strings | Event category names. |
| `location` | string or null | Normalized OWA location text. |
| `organizer` | string or null | Normalized organizer display or email text. |
| `sensitivity` | string or null | OWA sensitivity value. |
| `meeting_link` | string or null | Preserved meeting link when exposed by OWA. |
| `timezone` | string or null | OWA timezone metadata when available. |
| `is_recurring` | boolean | True for recurring events or occurrences. |
| `is_occurrence` | boolean | True for expanded occurrences and exceptions. |
| `is_series_master` | boolean | True when OWA identifies the item as a series master. |
| `is_private` | boolean | Private events are excluded by default unless `--include-private` is used. |
| `raw_owa` | object | Present only when `--include-raw` is used. |

Recurring calendar reads are occurrence-oriented. Mutations of likely series masters remain refused by safety checks.

## Category Output

`categories list` returns mailbox master categories. `color` is retained only when OWA provides it; many OWA responses expose names without colors.

```json
{
  "ok": true,
  "connection": "work",
  "operation": "categories.list",
  "data": [
    {"name": "Deep Work", "color": "Preset0"}
  ]
}
```

`categories details` returns the master category names merged with usage details from OWA
`FindCategoryDetails`. Categories with no usage entry remain present with zero counts.

```json
{
  "ok": true,
  "connection": "work",
  "operation": "categories.details",
  "data": [
    {
      "name": "Deep Work",
      "color": "Preset0",
      "item_count": 3,
      "unread_count": 1,
      "is_search_folder_ready": true
    }
  ]
}
```

`categories upsert` is name-only. Existing names return a no-op result. Missing
names are created through Outlook REST v2 `POST /api/v2.0/me/MasterCategories`;
OWA `GetMasterCategoryList` remains the read-after-write verification source.
Category color is not user-configurable and defaults to Outlook's `Preset0`.

```json
{
  "ok": true,
  "connection": "work",
  "operation": "categories.upsert",
  "data": {
    "name": "Deep Work",
    "created": false,
    "updated": false,
    "noop": true,
    "changed": false
  }
}
```
