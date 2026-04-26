# m365-owa-cli

`m365-owa-cli` is a personal, agent-first Python CLI for Microsoft 365 Outlook workflows through Outlook on the web / OWA internal service endpoints.

The implemented command surface is calendar/category-focused. Mail and Contacts currently have stable schema and placeholder command contracts so endpoint adapters can land behind a known machine interface. Microsoft Graph is intentionally out of scope.

## Examples

```bash
m365-owa-cli capabilities
m365-owa-cli schema event
m365-owa-cli auth set-token --connection work
m365-owa-cli auth bookmarklet --connection work --raw
m365-owa-cli auth extract-token --connection work --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth list-connections
m365-owa-cli categories list --connection work
m365-owa-cli categories details --connection work
m365-owa-cli categories upsert --connection work --name "Deep Work"
m365-owa-cli categories delete --connection work --name "Deep Work" --confirm-category-name "Deep Work"
m365-owa-cli events list --connection work --day 2026-04-24
m365-owa-cli events delete --connection work --id AAMk... --confirm-event-id AAMk...
m365-owa-cli schema mail-message
m365-owa-cli mail list --connection work
m365-owa-cli contacts list --connection work
```

Commands emit JSON by default. Use `--pretty` where supported for local human-readable output.
See [docs/schema.md](docs/schema.md) for the stable event and category JSON contracts.

## Configuration

Tokens are stored as plaintext files under:

```text
~/.config/m365-owa-cli/connections/<connection>.token
```

Tests and automation can override the config root with `M365_OWA_CONFIG_DIR`.

Connection names are the explicit account, tenant, or environment selector. Examples:

```bash
m365-owa-cli auth list-connections
m365-owa-cli events list --connection tenant-a --day 2026-04-24
m365-owa-cli events list --connection tenant-b --day 2026-04-24
m365-owa-cli events list --connection tenant-c --day 2026-04-24
m365-owa-cli events list --connection prod --day 2026-04-24
```

## Browser Token Capture

Preferred method: watch a DevTools-enabled Edge or Chrome tab and store OWA auth material from browser traffic. Open Outlook on the web in that browser first. On macOS, use a reusable debug profile so Chrome first-run and search-engine-choice prompts do not come back every session:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.config/m365-owa-cli/chrome-devtools-profile" --no-first-run --no-default-browser-check --disable-search-engine-choice-screen https://outlook.office.com/calendar/
```

Capture per connection:

```bash
m365-owa-cli auth extract-token --connection tenant-a --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection tenant-b --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection tenant-c --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

Each command stores separate local auth state:

```text
~/.config/m365-owa-cli/connections/tenant-a.token
~/.config/m365-owa-cli/connections/tenant-b.token
~/.config/m365-owa-cli/connections/tenant-c.token
~/.config/m365-owa-cli/connections/tenant-a.credential.json
```

The command only accepts bearer headers from known Outlook hosts on recognized OWA route families and Microsoft identity token responses from `login.microsoftonline.com`; it stores secrets locally and emits metadata only. If the capture times out, interact with the open Outlook tab and retry without `--reload`.

## Manual Token Capture Fallback

Use the bookmarklet helper only when DevTools capture is unavailable:

```bash
m365-owa-cli auth bookmarklet --connection tenant-a --raw
```

Create a browser bookmark with the generated value as the URL, open Outlook on the web, click the bookmarklet, then refresh or open Calendar. If OWA sends an `Authorization: Bearer ...` header to `/owa/service.svc`, the helper displays it for copying into `auth set-token`.

## Opsec

- Do not print, paste, commit, screenshot, or document bearer token values.
- Do not copy `~/.config/m365-owa-cli/connections/*.token` or `*.credential.json` into this repository.
- Use `--connection` names like `tenant-a`, `tenant-b`, `prod`, `dev`, or another explicit tenant/environment name so agents never depend on hidden account state.
- Keep remote debugging bound to the local machine, for example `http://127.0.0.1:9222`.
- Prefer JSON command output and rely on built-in redaction for errors; do not add ad hoc debug logging around auth headers.

## Releases

New versions are published to PyPI from GitHub Actions when a `v*` tag is pushed. The workflow uses PyPI trusted publishing against the `pypi` environment in this repository, so no long-lived PyPI API token is stored in GitHub.

Before the first release, configure a pending trusted publisher on PyPI:

- PyPI project name: `m365-owa-cli`
- Owner: `okms`
- Repository: `m365-owa-cli`
- Workflow: `publish.yml`
- Environment: `pypi`

Release flow:

```bash
# bump version in pyproject.toml, commit
git tag vX.Y.Z
git push origin main --tags
```

The `.github/workflows/publish.yml` workflow runs tests, builds the source and wheel distributions, checks them with Twine, and publishes them to PyPI. Tag-less runs can also be triggered manually from the Actions tab.

The sdist is intentionally minimal: package source, package metadata, `README.md`, and `docs/schema.md`. Operational agent guidance, research notes, tests, CI workflows, local locks, and generated artifacts are excluded. See [docs/release.md](docs/release.md) for artifact inspection and scanning commands.

## Live Tests

The default test suite is fixture-only. Live OWA tests are opt-in:

```bash
uv run pytest tests/live -rs
M365_OWA_LIVE_CONNECTION=work uv run pytest tests/live -m live -rs
M365_OWA_LIVE_CONNECTION=work M365_OWA_LIVE_ALLOW_MUTATION=1 uv run pytest tests/live -m "live and mutating" -rs
```

Mutating live tests create synthetic names with a `m365-owa-cli-live-test-` prefix and clean them up with exact confirmations.
