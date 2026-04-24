# m365-owa-cli

`m365-owa-cli` is a personal, agent-first Python CLI for Microsoft 365 Outlook workflows through Outlook on the web / OWA internal service endpoints.

The current command surface is calendar-focused, but the package name leaves room for mail and tasks if the same OWA-authenticated endpoint strategy proves useful there. Microsoft Graph is intentionally out of scope.

## Examples

```bash
m365-owa-cli capabilities
m365-owa-cli schema event
m365-owa-cli auth set-token --connection work
m365-owa-cli auth bookmarklet --connection work --raw
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

## Manual Token Capture

Generate a local-only bookmarklet helper:

```bash
m365-owa-cli auth bookmarklet --connection work --raw
```

Create a browser bookmark with the generated value as the URL, open Outlook on the web, click the bookmarklet, then refresh or open Calendar. If OWA sends an `Authorization: Bearer ...` header to `/owa/service.svc`, the helper displays it for copying into `auth set-token`.

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
