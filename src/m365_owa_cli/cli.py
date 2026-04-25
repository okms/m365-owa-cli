from __future__ import annotations

from collections.abc import Sequence
import json
import sys
from pathlib import Path
from typing import Any

import click
import typer
from typer.core import TyperGroup

from m365_owa_cli import __version__
from m365_owa_cli.auth import (
    auth_test,
    bookmarklet_payload,
    extract_token,
    inspect_connection,
    refresh_connection_token,
    resolve_connection_access_token,
)
from m365_owa_cli.capabilities import capabilities_payload
from m365_owa_cli.config import (
    list_connections as list_configured_connections,
    read_credential,
    read_token_file,
    remove_token as remove_connection_token,
    set_token as store_connection_token,
)
from m365_owa_cli.errors import (
    AUTH_EXPIRED,
    AUTH_REQUIRED,
    CONFIG_ERROR,
    CONNECTION_NOT_FOUND,
    INVALID_ARGUMENTS,
    M365OwaError,
)
from m365_owa_cli.output import error_envelope, success_envelope
from m365_owa_cli.owa.client import (
    OWAClient,
    build_create_request,
    build_delete_request,
    build_get_request,
    build_list_request,
    build_search_request,
    build_update_request,
)
from m365_owa_cli.owa.safety import require_delete_confirmation
from m365_owa_cli.schemas import (
    commands_schema_payload,
    error_schema_payload,
    event_schema_payload,
    help_json_payload,
)
from m365_owa_cli.time_ranges import TimeRange, parse_day_range, parse_time_range, parse_week_range


_GROUP_COMMANDS = {"auth", "events", "schema"}
_TOP_LEVEL_COMMANDS = {"capabilities", "help"}


def _print_payload(payload: dict[str, Any], *, pretty: bool = False) -> None:
    indent = 2 if pretty else None
    typer.echo(json.dumps(payload, indent=indent, sort_keys=False))


def _operation_from_args(args: Sequence[str]) -> str | None:
    if not args:
        return None
    command = args[0]
    if command.startswith("-"):
        return None
    if command in _GROUP_COMMANDS and len(args) > 1 and not args[1].startswith("-"):
        return f"{command}.{args[1]}"
    if command in _TOP_LEVEL_COMMANDS:
        return command
    return None


def _connection_from_args(args: Sequence[str]) -> str | None:
    try:
        index = args.index("--connection")
    except ValueError:
        return None
    if index + 1 >= len(args):
        return None
    value = args[index + 1]
    return value if not value.startswith("-") else None


def _emit_click_error(error: click.ClickException, *, args: Sequence[str]) -> None:
    m365_owa_error = M365OwaError(
        INVALID_ARGUMENTS,
        error.format_message(),
        details={"click_error": type(error).__name__},
    )
    _print_payload(
        error_envelope(
            m365_owa_error,
            operation=_operation_from_args(args),
            connection=_connection_from_args(args),
        )
    )


class JsonErrorTyperGroup(TyperGroup):
    """Emit stable JSON for Typer/Click parse-time validation failures."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        effective_args = list(sys.argv[1:] if args is None else args)
        try:
            result = super().main(
                args=effective_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except click.ClickException as exc:
            if not standalone_mode:
                raise
            _emit_click_error(exc, args=effective_args)
            sys.exit(exc.exit_code)
        if standalone_mode and isinstance(result, int):
            sys.exit(result)
        return result


app = typer.Typer(
    name="m365-owa-cli",
    cls=JsonErrorTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    help="Agent-first CLI for Microsoft 365 Outlook on the web endpoints.",
)
schema_app = typer.Typer(cls=JsonErrorTyperGroup, help="Emit machine-readable schemas.")
auth_app = typer.Typer(cls=JsonErrorTyperGroup, help="Manage named OWA bearer-token connections.")
events_app = typer.Typer(cls=JsonErrorTyperGroup, help="Operate on default-calendar events.")

app.add_typer(schema_app, name="schema")
app.add_typer(auth_app, name="auth")
app.add_typer(events_app, name="events")


def _exit_with_error(
    error: M365OwaError | Exception,
    *,
    operation: str | None = None,
    connection: str | None = None,
    pretty: bool = False,
) -> None:
    if not isinstance(error, M365OwaError):
        error = M365OwaError("INTERNAL_ERROR", str(error), retryable=True)
    _print_payload(
        error_envelope(error, operation=operation, connection=connection),
        pretty=pretty,
    )
    raise typer.Exit(error.exit_code())


def _emit(
    payload: dict[str, Any],
    *,
    pretty: bool = False,
) -> None:
    _print_payload(payload, pretty=pretty)


def _invalid(message: str, *, details: dict[str, Any] | None = None) -> M365OwaError:
    return M365OwaError(INVALID_ARGUMENTS, message, details=details or {})


def _resolve_required_token(connection: str, token: str | None) -> str:
    resolved = resolve_connection_access_token(connection, token=token)
    if resolved:
        return resolved

    if read_token_file(connection) is None and read_credential(connection) is None:
        raise M365OwaError(
            CONNECTION_NOT_FOUND,
            f"No token source found for connection {connection!r}.",
            details={"connection": connection},
        )
    raise M365OwaError(
        AUTH_REQUIRED,
        f"Token for connection {connection!r} is empty.",
        details={"connection": connection},
    )


def _run_with_owa_client(
    connection: str,
    token: str | None,
    operation: Any,
) -> Any:
    resolved_token = _resolve_required_token(connection, token)
    client = OWAClient(connection=connection, token=resolved_token)
    try:
        return operation(client)
    except M365OwaError as exc:
        if exc.code != AUTH_EXPIRED or token is not None:
            raise
        credential = read_credential(connection)
        if not credential or not credential.get("refresh_token"):
            raise
        refresh_connection_token(connection)
        refreshed_token = _resolve_required_token(connection, token=None)
        refreshed_client = OWAClient(connection=connection, token=refreshed_token)
        return operation(refreshed_client)


def _read_body(body: str | None, body_file: Path | None) -> str | None:
    if body is not None and body_file is not None:
        raise _invalid("Use either --body or --body-file, not both.")
    if body_file is None:
        return body
    try:
        return body_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise M365OwaError(
            CONFIG_ERROR,
            f"Could not read body file {body_file}.",
            details={"path": str(body_file), "error": str(exc)},
        ) from exc


def _range_for_list(day: str | None, week: str | None) -> TimeRange:
    try:
        return parse_time_range(day=day, week=week)
    except (TypeError, ValueError) as exc:
        raise _invalid(str(exc), details={"day": day, "week": week}) from exc


def _range_for_search(from_date: str | None, to_date: str | None) -> dict[str, Any] | TimeRange:
    if from_date is None and to_date is None:
        return parse_week_range(__import__("datetime").date.today())
    if from_date is None or to_date is None:
        raise _invalid("Both --from and --to are required when overriding search range.")
    try:
        start = __import__("datetime").date.fromisoformat(from_date)
        end = __import__("datetime").date.fromisoformat(to_date)
    except ValueError as exc:
        raise _invalid("Search range dates must be ISO dates.", details={"from": from_date, "to": to_date}) from exc
    if end < start:
        raise _invalid("--to must be on or after --from.", details={"from": from_date, "to": to_date})
    return {
        "type": "custom",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": None,
        "source": "explicit",
    }


def _as_request_range(value: TimeRange | dict[str, Any]) -> TimeRange | None:
    return value if isinstance(value, TimeRange) else None


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        raise typer.Exit(0)


@app.command("capabilities")
def capabilities(pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON.")) -> None:
    _emit(capabilities_payload(), pretty=pretty)


@app.command("help")
def help_json(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable help."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    if not json_output:
        raise typer.BadParameter("Only --json help is supported by this command.")
    _emit(help_json_payload(), pretty=pretty)


@schema_app.command("commands")
def schema_commands(pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON.")) -> None:
    _emit(commands_schema_payload(), pretty=pretty)


@schema_app.command("event")
def schema_event(pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON.")) -> None:
    _emit(event_schema_payload(), pretty=pretty)


@schema_app.command("errors")
def schema_errors(pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON.")) -> None:
    _emit(error_schema_payload(), pretty=pretty)


@auth_app.command("list-connections")
def auth_list_connections(
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        data = list_configured_connections()
        _emit(success_envelope(data, operation="auth.list-connections"), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.list-connections", pretty=pretty)


@auth_app.command("set-token")
def auth_set_token(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Bearer token. Prefer stdin or prompt to avoid shell history.",
    ),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        token_value = token
        if token_value is None:
            if sys.stdin.isatty():
                token_value = typer.prompt("Token", hide_input=True)
            else:
                token_value = sys.stdin.read()
        if not token_value or not token_value.strip():
            raise M365OwaError(AUTH_REQUIRED, "Token input was empty.", details={"connection": connection})
        path = store_connection_token(connection, token_value.strip())
        data = {"name": connection, "stored": True, "token_file": str(path)}
        _emit(success_envelope(data, operation="auth.set-token", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.set-token", connection=connection, pretty=pretty)


@auth_app.command("bookmarklet")
def auth_bookmarklet(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    raw: bool = typer.Option(False, "--raw", help="Print only the bookmarklet URL."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        data = bookmarklet_payload(connection)
        if raw:
            typer.echo(data["bookmarklet"])
            return
        _emit(success_envelope(data, operation="auth.bookmarklet", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.bookmarklet", connection=connection, pretty=pretty)


@auth_app.command("remove-token")
def auth_remove_token(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        removed = remove_connection_token(connection)
        data = {"name": connection, "removed": removed}
        _emit(success_envelope(data, operation="auth.remove-token", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.remove-token", connection=connection, pretty=pretty)


@auth_app.command("inspect")
def auth_inspect(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        data = inspect_connection(connection)
        _emit(success_envelope(data, operation="auth.inspect", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.inspect", connection=connection, pretty=pretty)


@auth_app.command("refresh")
def auth_refresh(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        data = refresh_connection_token(connection)
        _emit(success_envelope(data, operation="auth.refresh", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.refresh", connection=connection, pretty=pretty)


@auth_app.command("test")
def auth_test_command(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        auth_test(connection, token=token)
        _emit(success_envelope({"authenticated": True}, operation="auth.test", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.test", connection=connection, pretty=pretty)


@auth_app.command("extract-token")
def auth_extract_token(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    browser: str = typer.Option("edge", "--browser", help="Browser to inspect."),
    devtools_url: str | None = typer.Option(
        None,
        "--devtools-url",
        help="Chrome DevTools HTTP URL, for example http://127.0.0.1:9222.",
    ),
    timeout_seconds: float = typer.Option(20.0, "--timeout", min=0.1, help="Seconds to watch OWA traffic."),
    reload: bool = typer.Option(False, "--reload", help="Reload the selected OWA tab after attaching."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    try:
        data = extract_token(
            connection,
            browser=browser,
            devtools_url=devtools_url,
            timeout_seconds=timeout_seconds,
            reload=reload,
        )
        _emit(success_envelope(data, operation="auth.extract-token", connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation="auth.extract-token", connection=connection, pretty=pretty)


@events_app.command("list")
def events_list(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    day: str | None = typer.Option(None, "--day", help="ISO date."),
    week: str | None = typer.Option(None, "--week", help="ISO week or date inside week."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    include_private: bool = typer.Option(False, "--include-private", help="Include private events."),
    include_raw: bool = typer.Option(False, "--include-raw", help="Include raw OWA payloads."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.list"
    try:
        time_range = _range_for_list(day, week)
        request = build_list_request(time_range, include_private=include_private)
        events = _run_with_owa_client(
            connection,
            token,
            lambda client: client.list_events(request=request.to_dict(), include_raw=include_raw),
        )
        _emit(
            success_envelope(events, operation=operation, connection=connection, range=time_range.to_dict()),
            pretty=pretty,
        )
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)


@events_app.command("get")
def events_get(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    event_id: str = typer.Option(..., "--id", help="Event or occurrence id."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    include_raw: bool = typer.Option(False, "--include-raw", help="Include raw OWA payload."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.get"
    try:
        request = build_get_request(event_id, include_raw=include_raw)
        event = _run_with_owa_client(
            connection,
            token,
            lambda client: client.get_event(request=request.to_dict(), include_raw=include_raw),
        )
        _emit(success_envelope(event, operation=operation, connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)


@events_app.command("search")
def events_search(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    query: str = typer.Option(..., "--query", help="Search query."),
    from_date: str | None = typer.Option(None, "--from", help="Search range start ISO date."),
    to_date: str | None = typer.Option(None, "--to", help="Search range end ISO date."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    include_private: bool = typer.Option(False, "--include-private", help="Include private events."),
    include_raw: bool = typer.Option(False, "--include-raw", help="Include raw OWA payloads."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.search"
    try:
        search_range = _range_for_search(from_date, to_date)
        request = build_search_request(
            query,
            time_range=_as_request_range(search_range),
            include_private=include_private,
        )
        request_dict = request.to_dict()
        if isinstance(search_range, dict):
            request_dict["payload"]["range"] = search_range
        events = _run_with_owa_client(
            connection,
            token,
            lambda client: client.search_events(request=request_dict, include_raw=include_raw),
        )
        range_payload = search_range.to_dict() if isinstance(search_range, TimeRange) else search_range
        _emit(
            success_envelope(events, operation=operation, connection=connection, range=range_payload),
            pretty=pretty,
        )
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)


@events_app.command("create")
def events_create(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    subject: str = typer.Option(..., "--subject", help="Event subject."),
    start: str = typer.Option(..., "--start", help="Event start datetime."),
    end: str = typer.Option(..., "--end", help="Event end datetime."),
    body: str | None = typer.Option(None, "--body", help="Event body."),
    body_file: Path | None = typer.Option(None, "--body-file", help="Read event body from file."),
    body_type: str = typer.Option("text", "--body-type", help="text or html."),
    category: list[str] | None = typer.Option(None, "--category", help="Category name."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show intended mutation without calling OWA."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.create"
    try:
        if body_type not in {"text", "html"}:
            raise _invalid("--body-type must be text or html.", details={"body_type": body_type})
        body_value = _read_body(body, body_file)
        request = build_create_request(
            subject=subject,
            start=start,
            end=end,
            body=body_value,
            body_type=body_type,
            categories=category or [],
        )
        if dry_run:
            _emit(
                success_envelope(
                    {"dry_run": True, "request": request.to_dict()},
                    operation=operation,
                    connection=connection,
                ),
                pretty=pretty,
            )
            return
        event = _run_with_owa_client(
            connection,
            token,
            lambda client: client.create_event(request=request.to_dict()),
        )
        _emit(success_envelope(event, operation=operation, connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)


@events_app.command("update")
def events_update(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    event_id: str = typer.Option(..., "--id", help="Event or occurrence id."),
    subject: str | None = typer.Option(None, "--subject", help="Event subject."),
    start: str | None = typer.Option(None, "--start", help="Event start datetime."),
    end: str | None = typer.Option(None, "--end", help="Event end datetime."),
    body: str | None = typer.Option(None, "--body", help="Event body."),
    body_file: Path | None = typer.Option(None, "--body-file", help="Read event body from file."),
    body_type: str | None = typer.Option(None, "--body-type", help="text or html."),
    category: list[str] | None = typer.Option(None, "--category", help="Category name."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show intended mutation without calling OWA."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.update"
    try:
        if body_type is not None and body_type not in {"text", "html"}:
            raise _invalid("--body-type must be text or html.", details={"body_type": body_type})
        body_value = _read_body(body, body_file)
        if all(
            value is None
            for value in (subject, start, end, body_value, body_type, category)
        ):
            raise _invalid("At least one update field must be provided.")
        request = build_update_request(
            event_id=event_id,
            subject=subject,
            start=start,
            end=end,
            body=body_value,
            body_type=body_type,
            categories=category,
        )
        if dry_run:
            _emit(
                success_envelope(
                    {"dry_run": True, "request": request.to_dict()},
                    operation=operation,
                    connection=connection,
                ),
                pretty=pretty,
            )
            return
        event = _run_with_owa_client(
            connection,
            token,
            lambda client: client.update_event(request=request.to_dict()),
        )
        _emit(success_envelope(event, operation=operation, connection=connection), pretty=pretty)
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)


@events_app.command("delete")
def events_delete(
    connection: str = typer.Option(..., "--connection", help="Connection name."),
    event_id: str = typer.Option(..., "--id", help="Event or occurrence id."),
    confirm_event_id: str = typer.Option(..., "--confirm-event-id", help="Must match --id exactly."),
    token: str | None = typer.Option(None, "--token", help="Direct bearer token."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON."),
) -> None:
    operation = "events.delete"
    try:
        require_delete_confirmation(event_id, confirm_event_id)
        request = build_delete_request(event_id=event_id, confirm_event_id=confirm_event_id)
        _run_with_owa_client(
            connection,
            token,
            lambda client: client.delete_event(request=request.to_dict()),
        )
        _emit(
            success_envelope({"deleted": True, "id": event_id}, operation=operation, connection=connection),
            pretty=pretty,
        )
    except M365OwaError as exc:
        _exit_with_error(exc, operation=operation, connection=connection, pretty=pretty)
