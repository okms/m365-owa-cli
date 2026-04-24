from owacal_cli.owa.client import OWAClient, OWAEndpointNotImplementedError
from owacal_cli.owa.safety import (
    SafetyError,
    refuse_likely_series_operation,
    require_delete_confirmation,
    require_occurrence_id,
)


def test_delete_confirmation_requires_exact_match():
    require_delete_confirmation("abc", "abc")
    try:
        require_delete_confirmation("abc", "abcd")
    except SafetyError as exc:
        assert exc.code == "UNSAFE_OPERATION_REJECTED"
    else:
        raise AssertionError("Expected SafetyError")


def test_likely_series_mutation_is_refused():
    event = {"id": "series-1", "is_recurring": True, "is_occurrence": False}
    try:
        refuse_likely_series_operation(event, operation="events.update")
    except SafetyError as exc:
        assert exc.code == "SERIES_OPERATION_REFUSED"
        assert "recurring series" in exc.message
    else:
        raise AssertionError("Expected SafetyError")


def test_occurrence_id_is_required_for_recurring_mutations():
    event = {"id": "occ-1", "is_recurring": True, "is_occurrence": True, "occurrence_id": "occ-1/1"}
    assert require_occurrence_id(event, operation="events.update") == "occ-1/1"


def test_client_raises_not_implemented_with_redacted_token_details():
    client = OWAClient(connection="work", token="Bearer eyJsecret.token.value")
    try:
        client.list_events(request={"authorization": "Bearer eyJsecret.token.value"})
    except OWAEndpointNotImplementedError as exc:
        assert exc.code == "OWA_ENDPOINT_NOT_IMPLEMENTED"
        details = exc.details
        assert "[REDACTED]" in str(details)
        assert "eyJsecret.token.value" not in str(details)
    else:
        raise AssertionError("Expected OWAEndpointNotImplementedError")
