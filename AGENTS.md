# Agent Guidance

## Intent

This repository is for `m365-owa-cli`, a personal, agent-first Python CLI for Microsoft 365 Outlook workflows through Outlook on the web / OWA internal service endpoints. Microsoft Graph is out of scope for v1.

The current implementation is calendar-focused, but the naming intentionally leaves room for mail and tasks if future OWA endpoint work extends beyond calendar CRUD.

The CLI should favor stable machine interfaces over convenience: JSON by default, stable commands, stable errors, stable exit codes, explicit destructive-operation confirmation, and schema/capability commands agents can inspect.

## What Is What

- `specs/` contains project specifications and is the source of product intent until implementation begins.
- `specs/m365-owa-cli/SPEC.md` is the current baseline product specification.
- `AGENTS.md` is the condensed working guidance for coding agents.
- `CLAUDE.md` delegates to this file for Claude Code.

## Core Constraints

- Backend is OWA service endpoints only, especially `/owa/service.svc`; do not add Microsoft Graph for v1.
- Treat OWA as unstable and undocumented. Preserve enough raw response/error detail for later inspection, while redacting bearer tokens.
- Support multiple named connections. Commands that talk to OWA should accept `--connection <name>`.
- Use tenant, account, or environment specific connection names such as `tenant-a`, `tenant-b`, `work`, `personal`, `prod`, or `dev` instead of hidden global account state.
- Default calendar only for v1. Shared, delegated, and explicit calendar selection are out of scope.
- Private events are excluded by default unless explicitly included.
- Recurring events must be handled as expanded occurrences. Refuse likely series/master mutation.
- Meeting links are preserved, not created.
- Deletion must require explicit confirmation with the event id, not a generic yes flag.

## Preferred Implementation Shape

- Python.
- Typer or Click for CLI.
- Pydantic for normalized schemas.
- httpx for HTTP.
- pytest with mocked OWA responses for tests.
- Rich is optional for human-readable `--pretty` output.

## Security Posture

This is a personal-use tool. Plaintext bearer tokens and plaintext token files are acceptable, but tokens must not leak through logs, errors, test fixtures, or normal debug output.

## Preferred Auth Capture Workflow

Prefer browser DevTools capture over manual copy/paste:

When a DevTools browser is not already running, launch a dedicated reusable Chrome profile on macOS with:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.config/m365-owa-cli/chrome-devtools-profile" --no-first-run --no-default-browser-check --disable-search-engine-choice-screen https://outlook.office.com/calendar/
```

Use the persistent `chrome-devtools-profile` path above instead of temporary profiles so account selection, browser first-run state, and search-engine-choice state are retained across sessions. The `--disable-search-engine-choice-screen` flag avoids Chrome's default search engine prompt. Keep DevTools bound to loopback and close the debug Chrome when done if no further capture is needed.

```bash
m365-owa-cli auth extract-token --connection tenant-a --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection tenant-b --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection tenant-c --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

Use `auth bookmarklet` only as a fallback when DevTools capture is unavailable. Never print, paste, commit, or document captured bearer values. Command output should contain only metadata such as connection name, source, host, token file path, and success/failure state.

Connection tokens and refresh credentials are local machine state under `~/.config/m365-owa-cli/connections/`; they are not repo artifacts. Do not copy `.token` or `.credential.json` files into the repository, test fixtures, issues, PRs, screenshots, docs, or logs.

## Current Status

The implementation scaffold exists and is pre-release. Preserve the stable machine interface while the OWA endpoint adapter is iterated.
