# owacal-cli

`owacal-cli` is a personal, agent-first Python CLI for Microsoft 365 Outlook calendar CRUD through Outlook on the web internal service endpoints.

The first implementation slice provides the stable command surface, JSON envelopes, schemas, token-file connection management, safety checks, and structured backend placeholders. Microsoft Graph is intentionally out of scope.

## Examples

```bash
owacal-cli capabilities
owacal-cli schema event
owacal-cli auth set-token --connection work
owacal-cli auth bookmarklet --connection work --raw
owacal-cli auth list-connections
owacal-cli events list --connection work --day 2026-04-24
owacal-cli events delete --connection work --id AAMk... --confirm-event-id AAMk...
```

Commands emit JSON by default. Use `--pretty` where supported for local human-readable output.

## Configuration

Tokens are stored as plaintext files under:

```text
~/.config/owacal-cli/connections/<connection>.token
```

Tests and automation can override the config root with `OWACAL_CONFIG_DIR`.

## Manual Token Capture

Generate a local-only bookmarklet helper:

```bash
owacal-cli auth bookmarklet --connection work --raw
```

Create a browser bookmark with the generated value as the URL, open Outlook on the web, click the bookmarklet, then refresh or open Calendar. If OWA sends an `Authorization: Bearer ...` header to `/owa/service.svc`, the helper displays it for copying into `auth set-token`.
