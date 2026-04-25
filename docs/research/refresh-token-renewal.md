# Refresh Token Renewal Research

Date: 2026-04-25

## Question

Can `m365-owa-cli` use refresh tokens to obtain new OWA bearer access tokens, and what CLI changes would be needed?

## Summary

Yes, refresh-token based renewal is technically feasible if the CLI can obtain and store a Microsoft identity platform refresh token issued to the same public client/resource context that Outlook on the web uses.

The current CLI cannot refresh tokens yet because it stores only a bearer access token in:

```text
~/.config/m365-owa-cli/connections/<connection>.token
```

An access token is not enough to mint a replacement access token. The CLI needs either:

- a refresh token captured from the browser token acquisition flow, or
- a first-party interactive auth flow that obtains an access token and refresh token pair.

For v1 of this project, the least invasive path is to extend the existing DevTools browser capture workflow so it can capture the token endpoint response and store the refresh token locally. The CLI should continue to talk to OWA service endpoints only for calendar operations; using Microsoft identity platform token endpoints for auth renewal does not require Microsoft Graph.

Live testing found one important detail: OWA's refresh token is treated as a Single Page Application token. A normal server-style POST from `httpx` fails, but the same refresh request succeeds when the CLI includes:

```text
Origin: https://outlook.office.com
```

The refreshed access token was accepted by OWA `/owa/service.svc`.

## Sources Reviewed

- Existing implementation:
  - `src/m365_owa_cli/auth.py`
  - `src/m365_owa_cli/browser.py`
  - `src/m365_owa_cli/config.py`
  - `src/m365_owa_cli/owa/client.py`
  - `docs/auth-capture.md`
  - `docs/research/browser-token-extraction.md`
- Microsoft docs:
  - [Refresh tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens)
  - [Microsoft identity platform and OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
  - [Acquiring and using an access token with MSAL Browser](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/acquire-token)
  - [Caching in MSAL.js](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/caching)
  - [Access tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)

## Local Findings

The configured `work` connection is present and the existing access token authenticated successfully with:

```bash
uv run m365-owa-cli auth test --connection work --pretty
```

The stored value is a JWT bearer access token, not a refresh token. Decoding was done locally without printing the token. Relevant non-secret observations:

- Token version: v1.0.
- Audience: `https://outlook.office.com`.
- Client is a public client (`appidacr=0`).
- The access token lifetime was short, roughly in the expected access-token range.
- The token includes OWA/Outlook calendar-related delegated scopes.

Initial discovery found no active Chrome/Edge DevTools endpoint on local ports `9222..9322`. A separate Chrome debug profile was launched with a temporary user data directory and Outlook on the web was opened there.

Live DevTools findings:

- OWA requested tokens from `login.microsoftonline.com`.
- The token path was `/common/oauth2/v2.0/token`.
- The initial token grant was `authorization_code`.
- The request included `offline_access` and OWA/Outlook scopes.
- The token response included both `access_token` and `refresh_token`.
- The access token was a v1.0 JWT for audience `https://outlook.office.com`.
- The client was a public client (`appidacr=0`).
- The access token was accepted by the current OWA probe.

Refresh redemption tests:

- Plain CLI POST to `/common/oauth2/v2.0/token`: failed with `invalid_request`.
- Failure reason: `AADSTS9002327`, meaning SPA client-type tokens may only be redeemed via cross-origin requests.
- CLI POST with `Origin: https://outlook.office.com`: succeeded.
- CLI POST with `Origin` plus `Referer`: succeeded.
- Browser-context `fetch` from the OWA tab: succeeded.
- Refreshed access tokens from the successful variants all probed OWA successfully.

## Microsoft Identity Behavior That Matters

Microsoft identity platform refresh tokens are opaque secrets intended for the authorization server. They are bound to a user/client combination, not to one specific resource or tenant. They can be exchanged at the token endpoint for new access/refresh token pairs when the client has the needed permissions.

Refresh tokens rotate: a successful refresh response can include a new refresh token, and the client should store the new value and discard the previous one.

Refresh-token lifetime depends on client type. Microsoft documents 24 hours for SPA redirect URI refresh tokens and 90 days for other scenarios. OWA browser behavior is likely SPA-like or first-party-web-app-specific, so the implementation must treat refresh failure as normal and fall back to browser recapture.

MSAL Browser stores durable auth artifacts including access tokens, ID tokens, refresh tokens, and accounts in browser storage, depending on app cache configuration. MSAL Browser v4 may encrypt localStorage artifacts using a session cookie-backed key. Directly scraping browser storage is therefore more brittle than observing token endpoint responses via DevTools.

## Feasibility

### Feasible

If DevTools observes an OWA/Microsoft identity token response containing:

- `access_token`
- `refresh_token`
- `expires_in` or equivalent expiry metadata
- `token_type`

then the CLI can store the refresh token and later exchange it for a fresh access token.

The refresh request shape is standard OAuth:

```text
POST https://login.microsoftonline.com/<tenant-or-authority>/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded
Origin: https://outlook.office.com

client_id=<client-id>
grant_type=refresh_token
refresh_token=<stored-refresh-token>
scope=<same-resource-scope-shape-observed-from-browser>
```

For v1 token endpoint traffic, the equivalent request usually uses `resource=https://outlook.office.com` instead of `scope`. The observed OWA flow used v2 `scope`, not v1 `resource`. The implementation should still persist the captured request shape instead of guessing.

### Not Feasible With Current Storage Alone

The current `<connection>.token` access-token file cannot be used as a refresh token. A bearer access token authenticates to OWA; it is not a credential that the token endpoint can redeem for another delegated OWA access token.

## Recommended Implementation Plan

1. Add a credential record alongside the legacy token file.

   Suggested path:

   ```text
   ~/.config/m365-owa-cli/connections/<connection>.credential.json
   ```

   Suggested schema:

   ```json
   {
     "version": 1,
     "connection": "work",
     "access_token": "Bearer ...",
     "refresh_token": "...",
     "token_type": "Bearer",
     "expires_at": "2026-04-25T21:50:07Z",
     "authority": "https://login.microsoftonline.com/<tenant-or-common>",
     "token_endpoint": "https://login.microsoftonline.com/<tenant-or-common>/oauth2/v2.0/token",
     "client_id": "...",
     "origin": "https://outlook.office.com",
     "resource": "https://outlook.office.com",
     "scope": "openid profile offline_access https://outlook.office.com/...",
     "redirect_uri": "https://outlook.office.com/mail/",
     "client_info": "1",
     "claims": "{\"access_token\":{\"xms_cc\":{\"values\":[\"CP1\"]}}}",
     "captured_source": "devtools_token_response",
     "captured_at": "2026-04-25T20:35:00Z"
   }
   ```

   The file is plaintext like the existing token file, but should be written with owner-only permissions where the platform supports it.

2. Preserve backwards compatibility.

   Keep reading `<connection>.token` as access-token-only legacy storage. New commands should prefer the credential JSON when present, then fall back to env/direct token/file access token.

3. Extend DevTools capture.

   Current capture watches request headers to `/owa/service.svc`. Add a second capture path for token endpoint responses:

   - Watch `Network.requestWillBeSent` for `login.microsoftonline.com/.../oauth2/.../token`.
   - Record safe request metadata: token endpoint, client ID, grant type, scope/resource, redirect URI type if visible.
   - Never store or print authorization codes, access tokens, refresh tokens, cookies, or raw request bodies in diagnostics.
   - On `Network.responseReceived` or `Network.loadingFinished`, call `Network.getResponseBody` for that request ID.
   - Parse JSON responses and store token fields if `refresh_token` is present.
   - Return only metadata: `stored_access_token`, `stored_refresh_token`, `expires_at`, `token_endpoint_host`, `source`.

4. Add refresh execution code.

   Add an auth module function such as `refresh_connection_token(connection)`.

   It should:

   - load credential JSON,
   - POST form data to the stored token endpoint,
   - include stored `client_id`, `grant_type=refresh_token`, `refresh_token`, captured `scope` or `resource`, and captured OWA request context where needed,
   - send `Origin: https://outlook.office.com` for SPA refresh-token redemption,
   - store returned `access_token`,
   - rotate `refresh_token` if a new one is returned,
   - update `expires_at` from `expires_in` or `expires_on`,
   - redact token endpoint errors.

5. Add CLI commands.

   Suggested commands:

   ```bash
   m365-owa-cli auth refresh --connection work
   m365-owa-cli auth inspect --connection work
   ```

   `auth refresh` should emit JSON metadata only. `auth inspect` should show non-secret credential state such as `has_access_token`, `has_refresh_token`, `expires_at`, `token_endpoint_host`, `client_id_present`, and storage paths.

6. Integrate refresh into OWA calls.

   For `events list/get/search/create/update/delete`:

   - resolve credential,
   - if `expires_at` is near expiry, refresh before calling OWA,
   - if OWA returns `AUTH_EXPIRED` and a refresh token exists, refresh once and retry the OWA operation,
   - if refresh fails with `invalid_grant`, surface `AUTH_EXPIRED` or a new stable `AUTH_REFRESH_FAILED` error with recapture instructions.

7. Update auth listing and removal.

   `auth list-connections` should include non-secret refresh metadata:

   ```json
   {
     "name": "work",
     "sources": ["credential_file", "file"],
     "has_token": true,
     "has_refresh_token": true,
     "access_token_expires_at": "..."
   }
   ```

   `auth remove-token` should remove both legacy token and credential files, or grow a precise name such as `auth remove-connection-secret`.

8. Add tests.

   Required test coverage:

   - credential JSON read/write never leaks `access_token` or `refresh_token` in command output,
   - refresh request uses stored metadata and rotates refresh tokens,
   - legacy token file behavior still works,
   - automatic refresh before expiry,
   - one retry after OWA 401/403 when refresh succeeds,
   - refresh failure returns stable redacted errors,
   - DevTools token response capture stores secrets but reports only metadata.

## Open Verification Tasks

These were the original verification tasks and their current status:

1. Confirm which token endpoint OWA currently calls: done, observed `/common/oauth2/v2.0/token`.
2. Confirm whether the token response includes `refresh_token` in normal OWA browser traffic: done, yes.
3. Confirm whether OWA uses `scope` or `resource` for the Outlook service token request: done, observed `scope`.
4. Confirm the exact client ID from the token request rather than relying only on the observed access-token `appid` claim: partially done. The request contained `client_id`; the research notes intentionally store only a hash. Implementation may store the exact client ID because it is not a secret.
5. Confirm whether the refresh-token lifetime behaves like a SPA 24-hour token or another first-party public client flow: not completed. The SPA redemption error strongly indicates SPA behavior, so assume a 24-hour refresh-token lifetime until measured otherwise.

Recommended verification command after starting Chrome/Edge with remote debugging:

```bash
uv run m365-owa-cli auth extract-token --connection work --browser chrome --devtools-url http://127.0.0.1:9222 --reload
```

After implementation, the same command should report whether a refresh token was captured without printing it.

## Risks

- OWA and its auth flow are undocumented internal behavior and can change without notice.
- Direct browser storage scraping is brittle and may fail because MSAL Browser v4 can encrypt localStorage artifacts.
- Refresh tokens are more sensitive than short-lived access tokens because they can mint replacement tokens.
- Capturing token endpoint responses raises the blast radius of DevTools capture; diagnostics must stay aggressively redacted.
- If the refresh token is SPA-lifetime-bound, the CLI may still need daily browser recapture.
- Refresh redemption currently depends on sending a browser-style `Origin` header. This is not a normal confidential-client server flow; treat it as OWA browser-flow compatibility, not a general Microsoft identity integration.
- Using a Microsoft first-party public client ID outside its intended application is unsupported. Treat this as personal-use automation only.

## Conclusion

The CLI should add refresh support, but not by trying to transform the current access token into a refresh token. The practical design is:

1. Continue using DevTools as the preferred auth capture path.
2. Capture both OWA bearer request headers and Microsoft identity token responses.
3. Store a credential JSON with access token, refresh token, expiry, token endpoint metadata, and the minimal browser-origin context needed for refresh.
4. Refresh automatically before OWA calls using `Origin: https://outlook.office.com`, rotate refresh tokens, and retry once after `AUTH_EXPIRED`.
5. Fall back to DevTools recapture when refresh fails or no refresh token exists.
