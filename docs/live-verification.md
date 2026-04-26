# Live Verification Matrix

This checklist is for maintainer-run OWA verification. The normal test suite remains mocked and deterministic. Live checks must be explicit, use synthetic content for mutations, and clean up before completion.

## Safety Rules

- Use `M365_OWA_LIVE_CONNECTION=<name>` only for intentional live checks.
- Use synthetic names with a `m365-owa-cli-live-` prefix and a random suffix.
- Do not print bearer tokens, cookies, mailbox addresses, tenant ids, real subjects, message bodies, contact notes, phone numbers, addresses, or attachment bytes.
- Read-only inspection of real data is allowed locally, but notes, fixtures, screenshots, issues, and PRs must use synthetic or sanitized data.
- Destructive operations require exact id/name confirmation. Do not add generic `--yes` flags.
- Commands that still return `OWA_ENDPOINT_NOT_IMPLEMENTED` are contract checks only; capture endpoint fixtures before implementing adapters.

## Route Families

Verify OWA-owned routes only:

- `/owa/service.svc`
- `/owa/service.svc/s/...`
- `/PeopleGraphVx/v1.0/...`
- OWA GraphQL/local resolver routes observed under Outlook-owned hosts

Microsoft Graph v1 remains out of scope.

## Auth And Redaction

```bash
m365-owa-cli auth extract-token --connection <name> --browser chrome --devtools-url http://127.0.0.1:9222 --reload
m365-owa-cli auth inspect --connection <name> --pretty
m365-owa-cli auth test --connection <name> --pretty
```

Run capture once from Mail and once from People when those adapters are under active development. Output may include connection name, source, route family, host, token file path, credential file path, and elapsed time. It must not include bearer values, cookies, refresh tokens, account names, tenant ids, company names, email addresses, or request bodies.

## Mail Read

Feature command under test:

```bash
m365-owa-cli mail folders list --connection <name>
m365-owa-cli mail list --connection <name> --limit 5
m365-owa-cli mail get --connection <name> --id <synthetic-message-id>
m365-owa-cli mail search --connection <name> --query <synthetic-subject> --limit 5
```

Verify folders, list, get, and backend search against a synthetic message. Default output must avoid full bodies and raw payloads. `--include-raw` is for local debugging only and must remain redacted before fixture use.

## Mail Compose And Send

Feature command under test:

```bash
m365-owa-cli mail draft create --connection <name> --to <test-recipient> --subject <synthetic-subject> --dry-run
m365-owa-cli mail send --connection <name> --draft-id <draft-id> --confirm-send-to <test-recipient>
```

Create drafts before sending. Sending must require exact recipient confirmation. Verify sent items and recipient arrival only with a test mailbox. Delete synthetic drafts and sent/received messages afterwards.

## Mail State Mutations

Feature command under test:

```bash
m365-owa-cli mail mark-read --connection <name> --id <synthetic-message-id>
m365-owa-cli mail flag --connection <name> --id <synthetic-message-id> --state flagged
m365-owa-cli mail move --connection <name> --id <synthetic-message-id> --folder <folder-id>
m365-owa-cli mail delete --connection <name> --id <synthetic-message-id> --confirm-message-id <synthetic-message-id>
```

Use one synthetic message. Verify read/unread, flag states, category add/remove, copy/move/archive/delete, and destination folders. Do not default to conversation-wide mutations.

## Mail Reactions

Feature command under test:

```bash
m365-owa-cli mail reactions list --connection <name> --id <synthetic-message-id>
m365-owa-cli mail reactions set --connection <name> --id <synthetic-message-id> --reaction like
m365-owa-cli mail reactions clear --connection <name> --id <synthetic-message-id>
```

Run only on synthetic content. If the write route remains undiscovered, leave mutation commands unimplemented and document the exact endpoint blocker.

## Mail Attachments

Feature command under test:

```bash
m365-owa-cli mail attachments list --connection <name> --message-id <synthetic-message-id>
m365-owa-cli mail attachments download --connection <name> --message-id <synthetic-message-id> --attachment-id <attachment-id> --output /tmp/m365-owa-cli-attachment.bin --confirm-filename <filename>
```

Use one small synthetic attachment. No bulk downloads. Do not print bytes. Refuse overwrite unless an explicit future flag exists. Remove downloaded files after verification.

## Contacts Read

Feature command under test:

```bash
m365-owa-cli contacts folders list --connection <name>
m365-owa-cli contacts list --connection <name> --limit 5
m365-owa-cli contacts get --connection <name> --id <synthetic-contact-id>
m365-owa-cli contacts search --connection <name> --query <synthetic-contact-name>
```

Create or identify a controlled synthetic contact. Verify personal contacts and directory/persona suggestions are clearly distinguished. Notes and raw payloads must be opt-in.

## Contacts Write

Feature command under test:

```bash
m365-owa-cli contacts create --connection <name> --display-name <synthetic-name> --dry-run
m365-owa-cli contacts update --connection <name> --id <synthetic-contact-id> --dry-run
m365-owa-cli contacts delete --connection <name> --id <synthetic-contact-id> --confirm-contact-id <synthetic-contact-id>
```

Use only synthetic names, emails, phones, company, and notes. Verify create, scalar update, collection update, folder create/rename/delete, tags, and photos only where endpoints are confirmed.

## Contacts Favorites And Linking

Feature command under test:

```bash
m365-owa-cli contacts favorites list --connection <name>
m365-owa-cli contacts favorites add --connection <name> --id <synthetic-contact-id>
m365-owa-cli contacts unlink --connection <name> --persona-id <synthetic-persona-id> --contact-id <synthetic-contact-id> --confirm-persona-id <synthetic-persona-id> --confirm-contact-id <synthetic-contact-id>
```

Run favorites, link suggestions, link, and unlink only on disposable synthetic contacts. Never probe aggregation-changing routes on real contacts.

## Cleanup Checklist

- Synthetic messages, drafts, sent items, copied/moved/archive remnants, and deleted-item remnants.
- Synthetic folders and categories.
- Synthetic contacts, contact folders, favorites, tags, photos, and links.
- Downloaded attachment files under `/tmp` or another explicit output path.
- Raw HAR captures under `tests/fixtures/owa/raw/` or outside the repo.
- Final search/list check for the unique synthetic prefix.

## Fixture Refresh

When OWA payloads drift:

1. Capture raw HAR/body data locally.
2. Keep raw files out of git.
3. Run `scripts/sanitize_owa_fixture.py` with `--har-action` or `--url-contains`.
4. Inspect sanitized output for leaked tokens, cookies, tenant ids, names, emails, bodies, notes, phone numbers, addresses, attachment names, and photo URLs.
5. Update request-builder and normalizer tests before changing adapters.
