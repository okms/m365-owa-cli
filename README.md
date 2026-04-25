# m365-owa-cli

`m365-owa-cli` is a personal, agent-first Python CLI for Microsoft 365 Outlook workflows through Outlook on the web / OWA internal service endpoints.

The current command surface is calendar-focused, but the package name leaves room for mail and tasks if the same OWA-authenticated endpoint strategy proves useful there. Microsoft Graph is intentionally out of scope.

## Examples

```bash
m365-owa-cli capabilities
m365-owa-cli schema event
m365-owa-cli auth set-token --connection work
m365-owa-cli auth bookmarklet --connection work --raw
m365-owa-cli auth extract-token --connection work --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth list-connections
m365-owa-cli events list --connection work --day 2026-04-24
m365-owa-cli events delete --connection work --id AAMk... --confirm-event-id AAMk...
```

Commands emit JSON by default. Use `--pretty` where supported for local human-readable output.

## Configuration

Tokens are stored as plaintext files under:

```text
~/.config/m365-owa-cli/connections/<connection>.token
```

Tests and automation can override the config root with `M365_OWA_CONFIG_DIR`.

Connection names are the explicit account, company, tenant, or environment selector. Examples:

```bash
m365-owa-cli auth list-connections
m365-owa-cli events list --connection crayon --day 2026-04-24
m365-owa-cli events list --connection softwareone --day 2026-04-24
m365-owa-cli events list --connection swon --day 2026-04-24
m365-owa-cli events list --connection prod --day 2026-04-24
```

## Browser Token Capture

Preferred method: watch a DevTools-enabled Edge or Chrome tab and store the first OWA service bearer header it observes. Open Outlook on the web in that browser first:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
```

Capture per connection:

```bash
m365-owa-cli auth extract-token --connection crayon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection softwareone --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection swon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

Each command stores a separate local token file:

```text
~/.config/m365-owa-cli/connections/crayon.token
~/.config/m365-owa-cli/connections/softwareone.token
~/.config/m365-owa-cli/connections/swon.token
```

The command only accepts bearer headers from known Outlook hosts on `/owa/service.svc`; it stores the token locally and emits metadata only. If the capture times out, interact with the open Calendar tab and retry without `--reload`.

## Manual Token Capture Fallback

Use the bookmarklet helper only when DevTools capture is unavailable:

```bash
m365-owa-cli auth bookmarklet --connection crayon --raw
```

Create a browser bookmark with the generated value as the URL, open Outlook on the web, click the bookmarklet, then refresh or open Calendar. If OWA sends an `Authorization: Bearer ...` header to `/owa/service.svc`, the helper displays it for copying into `auth set-token`.

## Opsec

- Do not print, paste, commit, screenshot, or document bearer token values.
- Do not copy `~/.config/m365-owa-cli/connections/*.token` into this repository.
- Use `--connection` names like `crayon`, `softwareone`, `swon`, `prod`, `dev`, or another explicit company/environment name so agents never depend on hidden account state.
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
