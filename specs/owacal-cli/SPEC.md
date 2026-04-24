# `owacal-cli` Specification Baseline

## Purpose

`owacal-cli` is a **personal, agent-first CLI** for CRUD operations against a Microsoft 365 Outlook calendar using the same backend used by **Outlook on the web / OWA**, not Microsoft Graph.

The tool is explicitly intended to use OWA internal service endpoints such as:

```text
https://outlook.cloud.microsoft/owa/service.svc?action=GetCalendarView&app=Calendar&n=102
```

Microsoft Graph is intentionally out of scope for v1.

The OWA API is treated as unstable and undocumented. Breakage is acceptable, and the CLI should expose enough debug/inspection tooling for agents to adapt it over time.

## Primary Design Principles

1. **Agent-first**

   - JSON output by default.
   - Stable command structure.
   - Stable machine-readable error model.
   - Stable exit codes.
   - Self-documenting command and schema interfaces.
   - Explicit non-interactive flags for destructive actions.

2. **Precision over convenience**

   - Verbose but unambiguous commands are preferred.
   - Mutating commands should be explicit.
   - Deleting or changing recurring instances must not accidentally affect the full series.

3. **OWA backend only**

   - No Microsoft Graph dependency in v1.
   - Endpoint discovery may be based on live instructions, browser traffic, manually pasted samples, or sanitized HAR files.

4. **Personal-use security model**

   - Bearer tokens may be handled as plaintext.
   - Tokens are not stored by default.
   - Optional plaintext token files are allowed.
   - Token values must still be redacted from logs and errors unless explicitly debugging token handling.

## CLI Name

```bash
owacal-cli
```

Recommended command namespace:

```bash
owacal-cli events <command>
owacal-cli auth <command>
owacal-cli schema <command>
owacal-cli capabilities
```

This is more precise for agentic use than short commands like `day`, `week`, `get`, and `delete`.

## Authentication

### Supported Auth Methods

#### 1. Environment Variable

Agents should be able to pass tokens explicitly:

```bash
OWACAL_TOKEN_WORK="..." owacal-cli events list --connection work --day 2026-04-24
```

#### 2. Plaintext Token Files

The CLI must support multiple named connections.

Example config:

```text
~/.config/owacal-cli/connections/work.token
~/.config/owacal-cli/connections/personal.token
```

Example command:

```bash
owacal-cli auth set-token --connection work
owacal-cli auth set-token --connection personal
```

The token may be stored in plaintext.

#### 3. Direct Token Argument

Useful for short-lived agent workflows:

```bash
owacal-cli events list --token "Bearer ey..." --day 2026-04-24
```

This should be supported but discouraged in help text because shell history may retain it.

#### 4. Edge Browser Token Extraction

Best-effort only.

```bash
owacal-cli auth extract-token --browser edge --connection work
```

Requirements:

```text
- Target Microsoft Edge first.
- Best-effort implementation only.
- Do not rely on this as the primary auth path.
- If extraction fails, return a structured error explaining what manual token input is required.
```

### Multiple Connections

The CLI must support juggling at least two connections.

Every command that talks to OWA should accept:

```bash
--connection <name>
```

Example:

```bash
owacal-cli events list --connection work --week 2026-W17
owacal-cli events list --connection personal --day 2026-04-24
```

There should be no hidden global account assumption for agent use.

Recommended auth commands:

```bash
owacal-cli auth list-connections
owacal-cli auth set-token --connection <name>
owacal-cli auth test --connection <name>
owacal-cli auth remove-token --connection <name>
owacal-cli auth extract-token --connection <name> --browser edge
```

## Calendar Scope

V1 scope:

```text
- Microsoft 365 accounts only.
- Default calendar only.
- No shared calendars.
- No delegated calendars.
- No calendar listing.
- No explicit calendar selector.
```

## Time Behavior

```text
Default timezone:
- Account timezone.

Day:
- Midnight to midnight in the account/user timezone.

Week:
- ISO week, Monday through Sunday.

Date input:
- ISO dates only.

Supported week inputs:
- ISO week, e.g. 2026-W17.
- Any ISO date inside the target week, e.g. 2026-04-24.

Timezone output:
- Preserve the event timezone returned by OWA.
```

Examples:

```bash
owacal-cli events list --connection work --day 2026-04-24
owacal-cli events list --connection work --week 2026-W17
owacal-cli events list --connection work --week 2026-04-24
```

## Event Model

Use the term **event** everywhere.

Supported fields:

```text
- id
- occurrence_id
- subject
- start
- end
- body
- body_type: text | html
- categories
- meeting_link
- timezone
- is_recurring
- is_occurrence
- is_private
- raw_owa
```

Required for create:

```text
- subject
- start
- end
```

Optional for create/update:

```text
- body
- body_type
- categories
- meeting_link preservation where applicable
```

Out of scope for v1:

```text
- attendees
- reminders
- location
- free/busy status
- sensitivity editing
- shared calendars
- delegated calendars
- recover/trash
```

## Recurring Events

Recurring events must be fetched as **individual expanded occurrences**.

Requirements:

```text
- Do not fetch or operate on the whole meeting series for normal list operations.
- Display occurrence_id for recurring event instances.
- Update/delete requires an occurrence_id.
- If the backend operation appears to target a series/master event, v1 must refuse.
- Updating/deleting a full series is out of scope.
- Updating/deleting "this and following" is out of scope.
```

Example refusal:

```json
{
  "ok": false,
  "error": {
    "code": "SERIES_OPERATION_REFUSED",
    "message": "This command appears to target a recurring series. owacal-cli v1 only supports operations on individual occurrences.",
    "retryable": false
  }
}
```

## Private Events

Default behavior:

```text
- Private events are excluded by default.
```

Selectable behavior:

```bash
owacal-cli events list --connection work --week 2026-W17 --include-private
```

If private events are included, the CLI should preserve whatever OWA returns. It should not invent hidden details.

## Categories

Category behavior:

```text
- Create any category that does not already exist.
- Assign categories by category name.
- If OWA requires IDs or color metadata internally, the CLI should resolve or create those behind the scenes.
```

Example:

```bash
owacal-cli events create \
  --connection work \
  --subject "Focus block" \
  --start "2026-04-24T10:00:00" \
  --end "2026-04-24T11:00:00" \
  --category "Deep Work"
```

## Meeting Link Behavior

Meeting links are **preserved**, not created.

V1 does not need to create Teams meetings.

For update operations:

```text
- If an existing event has a meeting link and the user does not explicitly alter it, preserve it.
- Do not delete or rewrite meeting-link metadata accidentally.
- If meeting-link editing is not safely understood from OWA responses, treat it as read-only.
```

## Command Design

### Read Commands

```bash
owacal-cli events list --connection <name> --day <YYYY-MM-DD>
owacal-cli events list --connection <name> --week <YYYY-Www|YYYY-MM-DD>
owacal-cli events get --connection <name> --id <event_id>
owacal-cli events search --connection <name> --query <text>
```

Search behavior:

```text
- Must call an OWA search endpoint, not only perform local search.
- Default search range: current ISO week.
- Search should allow explicit range override later.
```

Recommended search flags:

```bash
owacal-cli events search \
  --connection work \
  --query "dentist"

owacal-cli events search \
  --connection work \
  --query "dentist" \
  --from 2026-04-20 \
  --to 2026-04-26
```

### Create Command

```bash
owacal-cli events create \
  --connection <name> \
  --subject <subject> \
  --start <datetime> \
  --end <datetime> \
  [--body <body>] \
  [--body-type text|html] \
  [--category <name>] \
  [--category <name>] \
  [--dry-run]
```

### Update Command

```bash
owacal-cli events update \
  --connection <name> \
  --id <event_id_or_occurrence_id> \
  [--subject <subject>] \
  [--start <datetime>] \
  [--end <datetime>] \
  [--body <body>] \
  [--body-type text|html] \
  [--category <name>] \
  [--dry-run]
```

Update requirements:

```text
- Preserve meeting link unless explicitly and safely changed.
- For recurring events, require occurrence_id.
- Refuse likely series/master updates.
```

### Delete Command

Deletion must be explicit.

Recommended command:

```bash
owacal-cli events delete \
  --connection <name> \
  --id <event_id_or_occurrence_id> \
  --confirm-event-id <same_id>
```

Example:

```bash
owacal-cli events delete \
  --connection work \
  --id AAMkAG... \
  --confirm-event-id AAMkAG...
```

Requirements:

```text
- No delete without explicit confirmation.
- No recover/trash command in v1.
- Deletion means delete, not soft-archive, unless OWA itself implements delete as recoverable trash.
```

For agentic use, `--confirm-event-id` is better than `--yes` because it reduces accidental deletion from malformed plans.

## Output Format

Default output:

```text
JSON
```

Human-readable output:

```bash
--pretty
```

Raw OWA preservation:

```text
- Unknown OWA response fields should be preserved in raw JSON output.
- Event objects should include raw_owa or support --include-raw.
```

Recommended default response envelope:

```json
{
  "ok": true,
  "connection": "work",
  "operation": "events.list",
  "data": []
}
```

For list responses:

```json
{
  "ok": true,
  "connection": "work",
  "operation": "events.list",
  "range": {
    "type": "iso_week",
    "start": "2026-04-20",
    "end": "2026-04-26",
    "timezone": "Europe/Oslo"
  },
  "data": [
    {
      "id": "AAMk...",
      "occurrence_id": "AAMk.../occurrence...",
      "subject": "Example",
      "start": "2026-04-24T10:00:00+02:00",
      "end": "2026-04-24T10:30:00+02:00",
      "timezone": "Europe/Oslo",
      "categories": ["Deep Work"],
      "meeting_link": null,
      "is_recurring": false,
      "is_occurrence": false,
      "is_private": false
    }
  ]
}
```

## Self-Documenting Agent Interface

Required commands:

```bash
owacal-cli capabilities
owacal-cli schema commands
owacal-cli schema event
owacal-cli schema errors
owacal-cli help --json
```

### `capabilities`

Should return what this build supports.

Example:

```json
{
  "ok": true,
  "data": {
    "backend": "owa-service-svc",
    "graph_supported": false,
    "default_calendar_only": true,
    "shared_calendars": false,
    "recurring_occurrence_update": true,
    "recurring_series_update": false,
    "private_events_default": "excluded",
    "auth_methods": [
      "env",
      "token_file",
      "direct_token",
      "edge_best_effort"
    ]
  }
}
```

### `schema event`

Should return a JSON schema or schema-like description of normalized event objects.

### `schema errors`

Should return all stable error codes.

### `help --json`

Should expose commands, arguments, defaults, required fields, and examples in machine-readable form.

## Error Model

All errors must be stable and machine-readable.

Example:

```json
{
  "ok": false,
  "connection": "work",
  "operation": "events.list",
  "error": {
    "code": "AUTH_EXPIRED",
    "message": "OWA bearer token expired or was rejected.",
    "retryable": false,
    "details": {}
  }
}
```

Raw OWA error bodies should **not** be hidden by default, based on your answer.

Recommended behavior:

```text
- Include normalized error by default.
- Include OWA error details if available.
- Redact bearer tokens regardless.
```

## Exit Codes

Recommended stable exit codes:

```text
0  success
1  generic error
2  invalid arguments
3  auth error
4  not found
5  OWA backend error
6  unsafe operation rejected
7  unsupported operation
8  parse/normalization error
9  connection configuration error
```

## Endpoint Modeling

The implementation should use an endpoint registry internally, even if the exact endpoint shapes are discovered later.

Recommended internal shape:

```json
{
  "GetCalendarView": {
    "method": "POST",
    "path": "/owa/service.svc",
    "query": {
      "action": "GetCalendarView",
      "app": "Calendar"
    },
    "purpose": "Fetch expanded calendar events for a date range"
  }
}
```

Discovery inputs may include:

```text
- Live instructions
- Manually pasted request samples
- Manually pasted response samples
- Sanitized HAR files
- Existing observed endpoint:
  https://outlook.cloud.microsoft/owa/service.svc?action=GetCalendarView&app=Calendar&n=102
```

Testing should use mocked responses based on real OWA responses.

## Implementation Preferences

```text
Language:
- Python

Primary OS:
- macOS

Packaging:
- Single binary is not required.

Tests:
- Mocked tests based on real OWA responses.
- No live integration tests required for v1 unless added later.

Implementation agent:
- Codex or Claude Code will implement.
```

Recommended Python stack:

```text
- typer or click for CLI
- pydantic for schemas
- httpx for HTTP
- pytest for tests
- respx or pytest-httpx for HTTP mocks
- rich optional for --pretty output
```

For agent-first use, slightly favor **Typer + Pydantic + httpx**.

## Open Items Still Worth Deciding

Only a few meaningful choices remain:

1. Should the CLI support config files beyond token files, for example:

```text
~/.config/owacal-cli/config.toml
```

2. Should `--connection` be required on every OWA command, or should there be a default connection?

For agents, recommended: **required** unless exactly one connection exists.

3. Should search support explicit `--from` / `--to` in v1?

Recommended: yes, even though the default is current ISO week.

4. Should `--include-raw` be opt-in, or should raw OWA always be included?

Recommended: opt-in by default:

```bash
owacal-cli events get --connection work --id <id> --include-raw
```

5. Should body input support file input?

Recommended: yes:

```bash
owacal-cli events create \
  --connection work \
  --subject "Planning" \
  --start "2026-04-24T10:00:00" \
  --end "2026-04-24T11:00:00" \
  --body-file body.html \
  --body-type html
```

Recommended defaults:

```text
- Config file: yes.
- --connection: required unless only one connection exists.
- Search --from/--to: supported in v1.
- Raw OWA: opt-in.
- Body file input: supported.
```
