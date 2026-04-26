from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_verification_matrix_covers_mail_contacts_and_cleanup():
    text = (ROOT / "docs" / "live-verification.md").read_text(encoding="utf-8")

    required_sections = [
        "## Safety Rules",
        "## Route Families",
        "## Auth And Redaction",
        "## Mail Read",
        "## Mail Compose And Send",
        "## Mail State Mutations",
        "## Mail Reactions",
        "## Mail Attachments",
        "## Contacts Read",
        "## Contacts Write",
        "## Contacts Favorites And Linking",
        "## Cleanup Checklist",
        "## Fixture Refresh",
    ]
    for section in required_sections:
        assert section in text

    assert "m365-owa-cli auth extract-token" in text
    assert "Feature command under test" in text
    assert "/owa/service.svc" in text
    assert "PeopleGraphVx" in text
    assert "OWA_ENDPOINT_NOT_IMPLEMENTED" in text
