# Auth Capture For Agents

This project supports multiple named Microsoft 365 / OWA connections. Treat the connection name as the explicit company, tenant, account, or environment selector.

Good connection names:

- `crayon`
- `softwareone`
- `swon`
- `work`
- `personal`
- `prod`
- `dev`
- any other company or environment specific text that matches the connection-name rules

Connection names may contain letters, digits, dot, underscore, and dash.

## Preferred Method

Use DevTools browser capture first. It is the preferred auth workflow because it avoids manually copying bearer tokens through chats, shell history, notes, screenshots, and docs.

Start Chrome with a local DevTools port and open Outlook on the web. On macOS, prefer this reusable debug profile:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.config/m365-owa-cli/chrome-devtools-profile" --no-first-run --no-default-browser-check --disable-search-engine-choice-screen https://outlook.office.com/calendar/
```

The persistent `chrome-devtools-profile` keeps account selection and first-run state between sessions. `--disable-search-engine-choice-screen` suppresses Chrome's default search engine prompt. If Chrome is already running on `127.0.0.1:9222`, reuse it instead of launching another instance.

Then capture and store the token for the intended connection:

```bash
m365-owa-cli auth extract-token --connection crayon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection softwareone --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection swon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

The same pattern works for any company or environment specific connection name:

```bash
m365-owa-cli auth extract-token --connection <company-or-env> --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

If the browser is Edge:

```bash
m365-owa-cli auth extract-token --connection crayon --browser edge --devtools-url http://127.0.0.1:9222 --reload
```

## Verify

After capture, test the connection:

```bash
m365-owa-cli auth test --connection crayon
m365-owa-cli auth test --connection softwareone
m365-owa-cli auth test --connection swon
```

List configured connections without exposing token values:

```bash
m365-owa-cli auth list-connections
```

## Storage

Captured tokens and refresh credentials are stored outside the repository:

```text
~/.config/m365-owa-cli/connections/<connection>.token
~/.config/m365-owa-cli/connections/<connection>.credential.json
```

Examples:

```text
~/.config/m365-owa-cli/connections/crayon.token
~/.config/m365-owa-cli/connections/softwareone.token
~/.config/m365-owa-cli/connections/swon.token
~/.config/m365-owa-cli/connections/crayon.credential.json
```

These files are local machine state, not project files.

## Fallback

Use the bookmarklet only when DevTools capture is unavailable:

```bash
m365-owa-cli auth bookmarklet --connection crayon --raw
```

Then open Outlook on the web, run the bookmarklet, trigger Calendar traffic, and store the copied value with:

```bash
m365-owa-cli auth set-token --connection crayon
```

## Opsec Rules

- Never print, paste, commit, upload, screenshot, or document bearer token values.
- Never add real tokens to tests, fixtures, README examples, research notes, issues, PRs, commit messages, or chat transcripts.
- Never copy `~/.config/m365-owa-cli/connections/*.token` into this repository.
- Keep DevTools capture on local loopback, such as `http://127.0.0.1:9222`.
- Prefer `auth extract-token` over `auth set-token --token ...`; direct token arguments can land in shell history.
- Structured output may include connection names, token file paths, source names, hostnames, elapsed time, and success or failure state. It must not include bearer values.
- If adding new diagnostics, run tests that assert captured or backend bearer strings are redacted from stdout and exceptions.
