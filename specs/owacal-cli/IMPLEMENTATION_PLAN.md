# `owacal-cli` Implementation Plan

## Current Read

The baseline specification is implementation-ready for a first scaffold, but the OWA request and response shapes are intentionally incomplete. The plan should therefore separate the stable public CLI contract from the unstable backend adapter.

Primary constraints to preserve throughout implementation:

- OWA service endpoints only; Microsoft Graph is out of scope for v1.
- JSON output by default, with stable envelopes, error codes, and exit codes.
- Multiple named connections; OWA commands accept `--connection`.
- Default calendar only.
- Private events excluded by default.
- Recurring events handled as expanded occurrences; likely series/master mutations are refused.
- Meeting links are preserved, not created.
- Deletion requires `--confirm-event-id <same_id>`.
- Bearer tokens are always redacted from logs, errors, fixtures, and debug output.

## Recommended Decisions

Adopt the defaults recommended by the spec unless there is a later reason to revisit them:

- Use Python with Typer, Pydantic, httpx, pytest, and pytest-httpx or respx.
- Support `~/.config/owacal-cli/config.toml` plus per-connection plaintext token files.
- Require `--connection` on OWA commands, with a possible later convenience exception when exactly one connection exists.
- Support `events search --from/--to` in v1.
- Make raw OWA event payloads opt-in via `--include-raw`.
- Support `--body-file` alongside `--body`.
- Keep Edge token extraction best-effort and non-blocking for the rest of v1.

## Development Method

Use red/green TDD for each implementation slice:

1. Red: add or update a focused failing test that describes the public contract, safety rule, parser behavior, normalization behavior, or mocked OWA interaction.
2. Green: implement the smallest production change that makes the test pass.
3. Refactor: clean up structure only while the full relevant test set stays green.

Rules:

- Do not add live OWA behavior without first adding mocked tests or fixture-based tests.
- Start each command by testing the JSON envelope, exit code, and stable error behavior before filling in backend details.
- Add redaction tests before any code path can surface tokens.
- Add safety-rule tests before mutating commands can issue backend requests.
- When OWA samples are discovered, capture sanitized fixtures first, then write failing normalization/client tests from those fixtures before changing adapter code.
- Keep test failures narrow. A failing test should identify one missing behavior, not a broad phase of work.

## Proposed Package Shape

```text
pyproject.toml
README.md
src/owacal_cli/
  __init__.py
  __main__.py
  cli.py
  output.py
  errors.py
  capabilities.py
  config.py
  auth.py
  time_ranges.py
  models.py
  schemas.py
  owa/
    __init__.py
    client.py
    endpoints.py
    normalize.py
    requests.py
    safety.py
tests/
  fixtures/
    owa/
  test_cli_*.py
  test_auth.py
  test_errors.py
  test_normalize.py
  test_time_ranges.py
  test_owa_client.py
```

Boundaries:

- `cli.py`: Typer command tree and argument validation.
- `output.py`: JSON envelopes, pretty output, terminal rendering, and exception-to-exit handling.
- `errors.py`: stable error codes, exit code mapping, redaction helpers.
- `config.py`: config directory discovery, token-file reads/writes, connection listing.
- `auth.py`: token precedence and auth test/extraction entry points.
- `models.py`: normalized Pydantic models such as `Event`, `ResponseEnvelope`, `ErrorEnvelope`.
- `schemas.py`: schema command payloads and JSON help metadata.
- `owa/endpoints.py`: endpoint registry, independent of command code.
- `owa/client.py`: httpx transport, URL construction, headers, backend error capture.
- `owa/requests.py`: backend request builders for list/get/search/create/update/delete.
- `owa/normalize.py`: OWA payload-to-normalized-event mapping.
- `owa/safety.py`: recurring-event and destructive-operation safety checks.

## Implementation Phases

### Phase 1: CLI Contract Scaffold

Goal: Create an installable CLI with stable command structure, schema commands, output envelopes, error mapping, and tests that do not call OWA.

TDD sequence:

1. Red: CLI invocation tests for each command returning the expected JSON envelope or structured not-implemented error.
2. Green: Typer command scaffold and output helpers.
3. Red: schema and capabilities snapshot/shape tests.
4. Green: Pydantic models, schema emitters, and capabilities payload.
5. Red: invalid argument, missing token, and delete-confirmation exit-code tests.
6. Green: error classes, exit-code mapping, and safety validation.

Deliverables:

- `pyproject.toml` with console script `owacal-cli`.
- Typer command tree:
  - `capabilities`
  - `schema commands`
  - `schema event`
  - `schema errors`
  - `auth list-connections`
  - `auth set-token`
  - `auth remove-token`
  - `auth test`
  - `auth extract-token`
  - `events list`
  - `events get`
  - `events search`
  - `events create`
  - `events update`
  - `events delete`
- JSON success/error envelopes.
- Stable exit code mapping.
- Token redaction helpers with focused tests.
- Time range parsing for ISO day and ISO week inputs.
- Stub OWA adapter methods returning `UNSUPPORTED_OPERATION` or `OWA_ENDPOINT_NOT_IMPLEMENTED` where endpoint details are not known yet.

Acceptance checks:

- `owacal-cli capabilities` returns JSON matching the spec intent.
- `owacal-cli schema event` returns Pydantic-derived JSON schema.
- `owacal-cli schema errors` lists every stable error code and exit code.
- Invalid arguments exit with code `2`.
- Missing connection/token exits with code `9` or `3` as appropriate.
- Delete without matching confirmation exits with code `6`.

### Phase 2: Auth and Connection Management

Goal: Make token discovery and connection state usable without live OWA endpoint certainty.

TDD sequence:

1. Red: token precedence tests for direct token, environment variable, and token file.
2. Green: auth resolver and config-path override support.
3. Red: token redaction tests against errors, connection listings, and representative logs.
4. Green: redaction helper integration.
5. Red: `auth set-token`, `auth list-connections`, and `auth remove-token` CLI tests.
6. Green: token file management.

Deliverables:

- Token precedence:
  1. `--token`
  2. `OWACAL_TOKEN_<CONNECTION>`
  3. token file under config directory
- `auth set-token --connection <name>` reading from stdin or prompt without echo when interactive.
- `auth list-connections` showing configured connection names and token source metadata, never token values.
- `auth remove-token`.
- `auth test` wired through the OWA client once a low-risk test endpoint is known; until then, return a clear structured unsupported/backend-not-implemented error.
- Best-effort `auth extract-token --browser edge` placeholder with structured failure until extraction mechanics are implemented.

Acceptance checks:

- Tests prove tokens do not appear in JSON errors, reprs, captured logs, or fixture snapshots.
- Environment variable and direct token paths work without writing files.
- Token files are read from a deterministic config path override in tests.

### Phase 3: Read-Only OWA Integration

Goal: Implement list/get/search using mocked real OWA payloads before enabling mutation.

TDD sequence:

1. Red: fixture-based normalization tests for normal, private, recurring, category, and meeting-link events.
2. Green: OWA-to-`Event` normalization.
3. Red: mocked HTTP tests for endpoint registry, request construction, auth failures, backend errors, and malformed payloads.
4. Green: read-only OWA client methods.
5. Red: CLI tests for `events list`, `events get`, and `events search` using mocked backend responses.
6. Green: command integration and output filtering.

Discovery inputs needed:

- Sanitized request/response pair for `GetCalendarView`.
- Sanitized request/response pair for fetching a single event, if OWA exposes a separate operation.
- Sanitized request/response pair for OWA-backed search.
- Examples covering normal event, private event, recurring occurrence, meeting link, category, and backend error.

Deliverables:

- Endpoint registry entries for discovered read endpoints.
- HTTP request builders for list/search/get.
- Normalization from OWA payloads to `Event`.
- `--include-private` filter behavior.
- `--include-raw` behavior.
- Raw backend errors included in normalized error details with token redaction.
- OWA search calls a backend search endpoint, not local filtering.

Acceptance checks:

- List day/week returns expanded event objects in stable JSON.
- Private events are excluded by default and included only with `--include-private`.
- Recurring occurrences expose `occurrence_id`.
- Unknown OWA fields survive in `raw_owa` only when requested.
- HTTP 401/403 maps to auth errors; malformed backend payload maps to parse/normalization error.

### Phase 4: Create and Update

Goal: Add event creation and single-event/occurrence updates after read normalization is reliable.

TDD sequence:

1. Red: CLI validation tests for required fields, `--body`/`--body-file` conflicts, dry-run output, and no-op updates.
2. Green: command validation and dry-run payloads.
3. Red: mocked request-builder tests for create, update, categories, and meeting-link preservation.
4. Green: mutation request builders.
5. Red: recurrence safety tests for occurrence update and likely series/master refusal.
6. Green: safety integration before backend request execution.

Discovery inputs needed:

- Sanitized create-event request/response.
- Sanitized update-event request/response.
- OWA category list/create/assign behavior.
- OWA response showing meeting-link metadata before and after update.
- Recurring occurrence update sample.
- Series/master update sample or detectable marker, if available.

Deliverables:

- `events create` with `--subject`, `--start`, `--end`, `--body`, `--body-file`, `--body-type`, repeated `--category`, and `--dry-run`.
- Category resolution/creation behind the command.
- `events update` preserving existing meeting link metadata unless safe editing support is explicitly implemented later.
- Recurring safety checks that require occurrence identifiers for recurring changes and refuse likely series/master mutations.
- Dry-run output that shows normalized intended operation without issuing mutation requests.

Acceptance checks:

- Create validates required fields and body input conflicts.
- Update refuses no-op updates unless dry-run semantics justify returning the current payload.
- Update preserves meeting-link metadata in mocked OWA payloads.
- Series/master mutation attempts exit with code `6` and `SERIES_OPERATION_REFUSED`.

### Phase 5: Delete

Goal: Implement explicit destructive deletion with recurrence safety.

TDD sequence:

1. Red: delete confirmation tests proving missing or mismatched `--confirm-event-id` exits before any backend call.
2. Green: confirmation guard.
3. Red: recurrence safety tests for occurrence deletion and series/master refusal.
4. Green: delete safety integration.
5. Red: mocked backend success and not-found tests.
6. Green: delete client method and success envelope.

Discovery inputs needed:

- Sanitized delete-event request/response.
- Delete recurring occurrence sample.
- Series/master delete sample or detectable marker, if available.

Deliverables:

- `events delete --id <id> --confirm-event-id <same_id>`.
- Confirmation validation before any backend request.
- Recurring safety checks before deletion when event metadata can be resolved.
- Structured success payload describing the deleted id.

Acceptance checks:

- Missing or mismatched confirmation exits with `UNSAFE_OPERATION_REJECTED`.
- Likely series/master deletion exits with `SERIES_OPERATION_REFUSED`.
- Backend not-found maps to exit code `4`.

### Phase 6: Pretty Output and Hardening

Goal: Improve local usability without weakening the machine interface.

TDD sequence:

1. Red: pretty-output smoke tests proving commands still default to JSON.
2. Green: Rich rendering behind `--pretty`.
3. Red: fixture sanitization and help metadata tests.
4. Green: docs, metadata completion, and CI test command.

Deliverables:

- Optional Rich-based `--pretty` output for list/get/search/auth commands.
- README usage examples.
- Fixture sanitization notes.
- More complete `help --json` metadata.
- CI-ready pytest setup.

Acceptance checks:

- JSON remains the default everywhere.
- Pretty output has no token leakage.
- Tests cover command envelopes, major error codes, redaction, and mocked OWA flows.

## Stable Error Codes

Initial codes to implement:

- `INVALID_ARGUMENTS`
- `AUTH_REQUIRED`
- `AUTH_EXPIRED`
- `CONNECTION_NOT_FOUND`
- `TOKEN_FILE_ERROR`
- `OWA_BACKEND_ERROR`
- `OWA_ENDPOINT_NOT_IMPLEMENTED`
- `NOT_FOUND`
- `UNSAFE_OPERATION_REJECTED`
- `SERIES_OPERATION_REFUSED`
- `UNSUPPORTED_OPERATION`
- `NORMALIZATION_ERROR`
- `CONFIG_ERROR`
- `INTERNAL_ERROR`

These should map onto the spec's exit code table, with `INTERNAL_ERROR` using exit code `1`.

## OWA Discovery Checklist

Before implementing real backend behavior, collect sanitized samples for:

- Calendar view list by day.
- Calendar view list by week.
- Normal event with body and categories.
- Private event.
- Recurring event occurrence.
- Meeting with an existing online meeting link.
- Backend auth failure.
- Backend not-found failure.
- Create event.
- Update event.
- Delete event.
- Search query.
- Category lookup/create if categories require separate calls.

Sanitization requirements:

- Replace bearer tokens.
- Replace event ids consistently but preserve shape.
- Replace email addresses and tenant/user identifiers.
- Preserve unknown OWA fields and nesting so normalization can be tested realistically.

## Near-Term First Build Slice

The first implementation PR should be limited to Phase 1 plus enough Phase 2 to support local token configuration. That gives agents a stable interface to inspect before any live OWA behavior exists.

Suggested first commands to make fully functional:

```bash
owacal-cli capabilities
owacal-cli schema event
owacal-cli schema errors
owacal-cli schema commands
owacal-cli auth list-connections
owacal-cli auth set-token --connection work
owacal-cli auth remove-token --connection work
```

Suggested first commands to scaffold with structured not-implemented errors:

```bash
owacal-cli auth test --connection work
owacal-cli auth extract-token --connection work --browser edge
owacal-cli events list --connection work --day 2026-04-24
owacal-cli events get --connection work --id <id>
owacal-cli events search --connection work --query dentist
owacal-cli events create --connection work --subject X --start ... --end ...
owacal-cli events update --connection work --id <id> --subject X
owacal-cli events delete --connection work --id <id> --confirm-event-id <id>
```

## Main Risks

- OWA endpoint contracts may vary by tenant, region, account type, or frontend version.
- OWA may require headers, cookies, canary values, or request metadata beyond bearer auth.
- Recurring series detection may be incomplete until several real samples are available.
- Meeting-link preservation may require retaining opaque OWA fields during update payload construction.
- Category creation may require separate endpoints and metadata not visible in event payloads.
- Browser token extraction may be brittle and should not block core CLI usability.

## Review Gates

Use these gates before expanding scope:

1. Public command names, output envelopes, error codes, and exit codes are covered by tests.
2. Token redaction tests fail closed.
3. Read-only OWA normalization works against sanitized fixtures.
4. Mutating commands have dry-run output and safety checks before live write support.
5. Recurring event behavior is tested with occurrence and series/master fixtures.
