# Browser Token Extraction Research

Date: 2026-04-25

## Source Reviewed

- `https://github.com/steipete/sweetlink`, cloned locally to `/tmp/sweetlink`.

## SweetLink Patterns Worth Reusing

SweetLink uses a browser-control model instead of asking users to paste credentials into a CLI:

- It launches or reuses a Chromium-family browser with Chrome DevTools Protocol enabled.
- It discovers DevTools endpoints through explicit config, saved config, and local port scans.
- It selects the relevant tab, attaches over DevTools/Puppeteer, and evaluates browser-side state.
- It can copy cookies from a normal Chrome profile into a controlled profile using `@steipete/sweet-cookie`.
- It keeps secrets out of normal CLI output and primarily reports session/control metadata.

Relevant files in the cloned repo:

- `/tmp/sweetlink/src/runtime/chrome/launch.ts`
- `/tmp/sweetlink/src/runtime/chrome/reuse.ts`
- `/tmp/sweetlink/src/runtime/chrome/cookies.ts`
- `/tmp/sweetlink/src/runtime/cookies.ts`
- `/tmp/sweetlink/src/runtime/devtools/cdp.ts`

## Implications For OWA

OWA calendar calls use bearer authorization on requests to `/owa/service.svc`. A CLI cannot read past browser network history through CDP after the fact, so the useful browser integration is a live capture:

1. Attach to an already-open OWA tab in Edge or Chrome through a DevTools endpoint.
2. Enable CDP network events.
3. Watch future requests.
4. Accept only `Authorization: Bearer ...` headers on allowed OWA hosts and `/owa/service.svc`.
5. Store the captured value through the existing local token store.
6. Return only redacted metadata in JSON.

Cookie copying is less directly useful for this project because the CLI needs the OWA service bearer header, not a browser cookie jar. It may become useful later if a controlled OWA browser profile is launched automatically and needs to inherit sign-in state from the user profile.

## Current Implementation Direction

The first implementation is intentionally narrow and conservative:

- `m365-owa-cli auth extract-token --connection <name>` now attempts DevTools capture.
- `--browser edge` remains the default, with `chrome` also accepted because CDP semantics are shared.
- `--devtools-url` can point at a running endpoint such as `http://127.0.0.1:9222`.
- If no endpoint is provided, local ports `9222..9322` are scanned.
- `--reload` can reload the selected OWA tab after attaching to trigger fresh OWA requests.
- Captured tokens are stored locally and never emitted.
- DevTools capture is the preferred method for future agent use; bookmarklet/manual copy is the fallback.
- Use explicit company, tenant, account, or environment connection names such as `crayon`, `softwareone`, `swon`, `prod`, or `dev`.

See `docs/auth-capture.md` for the operational runbook.

## Manual Setup For Interactive Testing

Start a browser with remote debugging, then open Outlook on the web:

```bash
"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" --remote-debugging-port=9222
```

Then run:

```bash
m365-owa-cli auth extract-token --connection crayon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection softwareone --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth extract-token --connection swon --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

If capture times out, keep the command running without `--reload` and interact with Calendar, or use:

```bash
m365-owa-cli auth bookmarklet --connection work --raw
```

## Security Notes

- Token values should not be written to docs, tests, logs, or normal command output.
- Structured errors may include DevTools URLs, tab URLs, and launch hints, but not authorization values.
- The CDP capture accepts only bearer headers scoped to known OWA hosts and `/owa/service.svc`.
- Token files under `~/.config/m365-owa-cli/connections/*.token` are local machine state and must not be copied into the repository.
