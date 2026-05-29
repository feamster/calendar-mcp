"""Tests for calendar name → id resolution and the enriched create_event response."""

from unittest.mock import MagicMock

import pytest

from calendar_mcp.calendar_client import CalendarClient, CalendarResolutionError


def _make_client(calendars):
    """Build a CalendarClient with a preseeded calendar cache."""
    client = object.__new__(CalendarClient)
    client._services = {}
    client._default_service = MagicMock()
    client.service = client._default_service
    client._calendars_cache = list(calendars)
    client._calendars_cache_by_account = {}
    client._config = {}
    return client


GMAIL_PERSONAL = {
    "id": "abc123@group.calendar.google.com",
    "summary": "Personal",
    "summaryOverride": None,
    "accessRole": "owner",
    "account": "feamster@gmail.com",
}
GMAIL_CHEMSTER = {
    "id": "chem456@group.calendar.google.com",
    "summary": "Chemster Events",
    "summaryOverride": None,
    "accessRole": "owner",
    "account": "feamster@gmail.com",
}
GMAIL_PRIMARY = {
    "id": "feamster@gmail.com",
    "summary": "feamster@gmail.com",
    "summaryOverride": "Work - Gmail",
    "accessRole": "owner",
    "account": "feamster@gmail.com",
}
UCHI_PERSONAL = {
    "id": "uchi-personal@group.calendar.google.com",
    "summary": "Personal",
    "summaryOverride": None,
    "accessRole": "writer",
    "account": "feamster@uchicago.edu",
}


# ---------- passthrough ----------

def test_resolve_passes_primary_through():
    c = _make_client([GMAIL_PERSONAL])
    assert c.resolve_calendar_id("primary") == "primary"


def test_resolve_passes_email_id_through():
    c = _make_client([GMAIL_PERSONAL])
    # Email-shaped id is treated as an id, not a name — no cache lookup needed.
    assert c.resolve_calendar_id("feamster@uchicago.edu") == "feamster@uchicago.edu"


def test_resolve_passes_group_id_through():
    c = _make_client([GMAIL_PERSONAL])
    raw = "anything@group.calendar.google.com"
    assert c.resolve_calendar_id(raw) == raw


# ---------- name match ----------

def test_resolve_matches_display_name_case_insensitively():
    c = _make_client([GMAIL_CHEMSTER])
    assert c.resolve_calendar_id("chemster events") == GMAIL_CHEMSTER["id"]
    assert c.resolve_calendar_id("  Chemster Events  ") == GMAIL_CHEMSTER["id"]


def test_resolve_matches_summary_override():
    c = _make_client([GMAIL_PRIMARY])
    # Stored under summary "feamster@gmail.com" but renamed to "Work - Gmail".
    assert c.resolve_calendar_id("Work - Gmail") == GMAIL_PRIMARY["id"]


# ---------- ambiguous ----------

def test_resolve_ambiguous_raises_with_candidates():
    c = _make_client([GMAIL_PERSONAL, UCHI_PERSONAL])
    with pytest.raises(CalendarResolutionError) as excinfo:
        c.resolve_calendar_id("Personal")
    payload = excinfo.value.to_dict()
    assert payload["kind"] == "ambiguous"
    assert payload["query"] == "Personal"
    candidate_accounts = {ent["account"] for ent in payload["candidates"]}
    assert candidate_accounts == {"feamster@gmail.com", "feamster@uchicago.edu"}


def test_resolve_account_scope_disambiguates():
    c = _make_client([GMAIL_PERSONAL, UCHI_PERSONAL])
    # Same name, but scoping to one account picks the right one without error.
    assert c.resolve_calendar_id("Personal", account="feamster@gmail.com") == GMAIL_PERSONAL["id"]
    assert c.resolve_calendar_id("Personal", account="feamster@uchicago.edu") == UCHI_PERSONAL["id"]


# ---------- not found ----------

def test_resolve_missing_lists_available_names():
    c = _make_client([GMAIL_PERSONAL, GMAIL_CHEMSTER])
    with pytest.raises(CalendarResolutionError) as excinfo:
        c.resolve_calendar_id("Not A Real Calendar")
    payload = excinfo.value.to_dict()
    assert payload["kind"] == "not_found"
    names = {ent["name"] for ent in payload["candidates"]}
    assert names == {"Personal", "Chemster Events"}


def test_resolve_missing_with_account_scope_lists_only_that_account():
    c = _make_client([GMAIL_PERSONAL, UCHI_PERSONAL])
    with pytest.raises(CalendarResolutionError) as excinfo:
        c.resolve_calendar_id("Nope", account="feamster@gmail.com")
    payload = excinfo.value.to_dict()
    assert payload["kind"] == "not_found"
    accounts = {ent["account"] for ent in payload["candidates"]}
    assert accounts == {"feamster@gmail.com"}


# ---------- tool registration ----------

def test_all_advertised_tools_registered():
    """Both list_all_calendars and list_calendar_events must be in TOOLS."""
    from calendar_mcp.server import TOOLS
    names = {t.name for t in TOOLS}
    # The two the spec called out specifically.
    assert "list_all_calendars" in names
    assert "list_calendar_events" in names
    # Sanity floor — current count is 15; if it drops below that, something
    # unregistered a tool inadvertently.
    assert len(names) >= 15


# ---------- enriched create_event response ----------

def test_create_event_response_includes_resolved_name_and_stored_times():
    c = _make_client([GMAIL_CHEMSTER])
    svc = c._default_service
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt300",
        "summary": "Coffee",
        "htmlLink": "https://calendar.google.com/event?eid=xxx",
        "created": "2026-06-01T10:00:00Z",
        "start": {"dateTime": "2026-06-01T17:10:00-05:00", "timeZone": "America/Chicago"},
        "end":   {"dateTime": "2026-06-01T18:00:00-05:00", "timeZone": "America/Chicago"},
    }

    from datetime import datetime
    from zoneinfo import ZoneInfo
    central = ZoneInfo("America/Chicago")
    res = c.create_event(
        summary="Coffee",
        start=datetime(2026, 6, 1, 17, 10, tzinfo=central),
        end=datetime(2026, 6, 1, 18, 0, tzinfo=central),
        calendar_id="Chemster Events",  # resolved by name
    )

    assert res["resolved_calendar_id"] == GMAIL_CHEMSTER["id"]
    assert res["resolved_calendar_name"] == "Chemster Events"
    # Stored start/end keep the timeZone field so callers can render in CT.
    assert res["start"]["timeZone"] == "America/Chicago"
    assert res["start"]["dateTime"] == "2026-06-01T17:10:00-05:00"
    assert res["end"]["timeZone"] == "America/Chicago"
    # Success message names the calendar, not just the id.
    assert "Chemster Events" in res["message"]
