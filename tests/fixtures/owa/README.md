# OWA Fixture Collection

Only sanitized fixtures belong in this directory. Keep raw browser exports, HAR files, and copied request/response bodies outside git, or under `tests/fixtures/owa/raw/`, which is ignored.

## GetCalendarView Day And Week

Capture the OWA network request from Outlook on the web:

```text
/owa/service.svc?action=GetCalendarView&app=Calendar
```

Save the raw request/response pair or HAR as JSON, then sanitize it before committing:

```bash
python scripts/sanitize_owa_fixture.py \
  tests/fixtures/owa/raw/get_calendar_view_day.har \
  tests/fixtures/owa/get_calendar_view_day.json \
  --har-action GetCalendarView

python scripts/sanitize_owa_fixture.py \
  tests/fixtures/owa/raw/get_calendar_view_week.har \
  tests/fixtures/owa/get_calendar_view_week.json \
  --har-action GetCalendarView
```

If the source is not a HAR, wrap it as a request/response JSON object first:

```json
{
  "fixture": "get_calendar_view_day",
  "operation": "GetCalendarView",
  "scenario": "day",
  "request": {
    "method": "POST",
    "url": "https://outlook.cloud.microsoft/owa/service.svc?action=GetCalendarView&app=Calendar",
    "headers": {},
    "body": {}
  },
  "response": {
    "status": 200,
    "headers": {},
    "body": {}
  }
}
```

Before committing, inspect the sanitized output for:

- bearer tokens, cookies, or `M365_OWA_TOKEN` values
- real email addresses
- tenant IDs, user IDs, mailbox GUIDs, and event IDs
- private body text that is not needed to preserve payload shape

## Mail And People Captures

Mail and People endpoint discovery should use synthetic or disposable content whenever possible.
Raw HAR files stay under `tests/fixtures/owa/raw/` or outside the repository.

Useful route filters:

```bash
python scripts/sanitize_owa_fixture.py \
  tests/fixtures/owa/raw/mail.har \
  tests/fixtures/owa/mail_find_item.json \
  --har-action FindItem

python scripts/sanitize_owa_fixture.py \
  tests/fixtures/owa/raw/mail.har \
  tests/fixtures/owa/mail_get_item.json \
  --har-action GetItem

python scripts/sanitize_owa_fixture.py \
  tests/fixtures/owa/raw/people.har \
  tests/fixtures/owa/people_contacts.json \
  --url-contains PeopleGraphVx/v1.0/contacts
```

The sanitizer preserves action names, URLs, HTTP methods, statuses, object shape, and array
cardinality. It replaces tokens, cookies, item/contact/persona ids, subjects, message bodies,
notes, person names, SMTP addresses, phone numbers, postal addresses, attachment names, and
photo URLs with deterministic placeholders.

The first read-only fixtures needed are:

- `get_calendar_view_day.json`
- `get_calendar_view_week.json`
- normal event
- private event
- recurring occurrence
- Teams or meeting-link event
- auth failure
- not-found failure
- search request/response
- mail folder/list/get/search request/response
- contacts folder/list/get/search request/response
