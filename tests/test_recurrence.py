"""Tests for recurring-event support (RRULE building + create_event wiring)."""

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from calendar_mcp.calendar_client import (
    CalendarClient,
    _build_exdate_line,
    _build_rrule,
    _count_occurrences,
)


CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


# ---------- _build_rrule: spec examples ----------

def test_mwf_with_until_in_central():
    # Monday 2026-07-06 13:00 Central, MWF until end of 2026-07-24 (Central).
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    rule = _build_rrule(
        {"freq": "WEEKLY", "by_day": ["MO", "WE", "FR"], "until": "2026-07-24"},
        start,
    )
    # 23:59:59 Central on 2026-07-24 → 04:59:59 UTC next day.
    assert rule == "FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20260725T045959Z"


def test_every_weekday_for_a_month_count():
    start = datetime(2026, 7, 6, 9, 0, tzinfo=CENTRAL)  # Monday
    rule = _build_rrule(
        {"freq": "WEEKLY", "by_day": ["MO", "TU", "WE", "TH", "FR"], "count": 20},
        start,
    )
    assert rule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;COUNT=20"


def test_first_monday_each_month():
    start = datetime(2026, 1, 5, 9, 0, tzinfo=CENTRAL)  # First Monday of Jan
    rule = _build_rrule(
        {"freq": "MONTHLY", "by_day": ["MO"], "by_set_pos": [1], "count": 12},
        start,
    )
    assert rule == "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1;COUNT=12"


def test_every_other_tuesday_indefinitely():
    start = datetime(2026, 7, 7, 14, 0, tzinfo=CENTRAL)  # Tuesday
    rule = _build_rrule(
        {"freq": "WEEKLY", "interval": 2, "by_day": ["TU"]},
        start,
    )
    assert rule == "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"


def test_default_interval_is_omitted():
    start = datetime(2026, 7, 6, 9, 0, tzinfo=CENTRAL)
    rule = _build_rrule({"freq": "DAILY", "count": 5}, start)
    assert "INTERVAL" not in rule
    assert rule == "FREQ=DAILY;COUNT=5"


# ---------- _build_rrule: validation ----------

def test_count_and_until_mutually_exclusive():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="mutually exclusive"):
        _build_rrule(
            {"freq": "WEEKLY", "by_day": ["MO"], "count": 5, "until": "2026-08-01"},
            start,
        )


def test_by_day_weekday_mismatch_with_start_rejects():
    # Start is Monday (MO), but by_day says only Tuesday — Google would silently
    # add Monday as an extra. We reject.
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="does not include start"):
        _build_rrule({"freq": "WEEKLY", "by_day": ["TU"]}, start)


def test_by_day_on_daily_freq_rejected():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="only valid with freq=WEEKLY"):
        _build_rrule({"freq": "DAILY", "by_day": ["MO"]}, start)


def test_empty_by_day_with_weekly_rejected():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="non-empty list"):
        _build_rrule({"freq": "WEEKLY", "by_day": []}, start)


def test_count_zero_rejected():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="positive integer"):
        _build_rrule({"freq": "DAILY", "count": 0}, start)


def test_by_set_pos_without_by_day_rejected():
    start = datetime(2026, 1, 5, 9, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="requires by_day"):
        _build_rrule({"freq": "MONTHLY", "by_set_pos": [1], "count": 12}, start)


def test_until_before_or_equal_start_rejected():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="strictly after"):
        _build_rrule(
            {"freq": "WEEKLY", "by_day": ["MO"], "until": "2026-07-06T12:00:00-05:00"},
            start,
        )


def test_invalid_freq_rejected():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="freq must be one of"):
        _build_rrule({"freq": "HOURLY"}, start)


# ---------- _build_exdate_line ----------

def test_exdate_for_timed_event_includes_tzid_and_local_time():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    line = _build_exdate_line(["2026-07-13"], start, all_day=False)
    assert line == "EXDATE;TZID=America/Chicago:20260713T130000"


def test_exdate_for_all_day_uses_value_date():
    start = datetime(2026, 7, 6, 0, 0, tzinfo=CENTRAL)
    line = _build_exdate_line(["2026-07-13", "2026-07-20"], start, all_day=True)
    assert line == "EXDATE;VALUE=DATE:20260713,20260720"


# ---------- _count_occurrences ----------

def test_count_occurrences_mwf_three_weeks():
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    rule = _build_rrule(
        {"freq": "WEEKLY", "by_day": ["MO", "WE", "FR"], "until": "2026-07-24"},
        start,
    )
    count, first, last = _count_occurrences(rule, start)
    assert count == 9
    assert first == start
    # Last occurrence is Friday 2026-07-24 13:00 Central.
    assert last == datetime(2026, 7, 24, 13, 0, tzinfo=CENTRAL)


def test_count_occurrences_infinite_returns_none():
    start = datetime(2026, 7, 7, 14, 0, tzinfo=CENTRAL)
    rule = _build_rrule({"freq": "WEEKLY", "interval": 2, "by_day": ["TU"]}, start)
    count, _first, _last = _count_occurrences(rule, start)
    assert count is None


# ---------- create_event with mocked Google service ----------

def _make_client_with_mock_service():
    """Bypass __init__ and inject a mock Google service."""
    client = object.__new__(CalendarClient)
    mock_service = MagicMock()
    # events().insert(...).execute() returns whatever we tell it to.
    client._services = {}
    client._default_service = mock_service
    client.service = mock_service
    client._calendars_cache = []
    client._calendars_cache_by_account = {}
    client._config = {}
    return client, mock_service


def _captured_body(mock_service):
    """Pull the request body kwarg from the most recent insert() call."""
    return mock_service.events.return_value.insert.call_args.kwargs["body"]


def test_create_event_emits_recurrence_array_and_count():
    client, svc = _make_client_with_mock_service()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt123",
        "summary": "Censorship course",
        "start": {"dateTime": "2026-07-06T13:00:00-05:00", "timeZone": "America/Chicago"},
        "end": {"dateTime": "2026-07-06T14:30:00-05:00", "timeZone": "America/Chicago"},
        "htmlLink": "https://calendar.google.com/event?eid=xxx",
        "created": "2026-05-13T00:00:00Z",
    }

    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    end = datetime(2026, 7, 6, 14, 30, tzinfo=CENTRAL)
    result = client.create_event(
        summary="Censorship course",
        start=start,
        end=end,
        recurrence={
            "freq": "WEEKLY",
            "by_day": ["MO", "WE", "FR"],
            "until": "2026-07-24",
        },
    )

    body = _captured_body(svc)
    assert body["recurrence"] == [
        "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20260725T045959Z"
    ]
    # Timezone preserved (not stripped to UTC).
    assert body["start"]["dateTime"] == "2026-07-06T13:00:00-05:00"
    assert "America/Chicago" in body["start"]["timeZone"] or "UTC-05:00" in body["start"]["timeZone"]
    assert result["success"] is True
    assert result["recurrence"]["occurrence_count"] == 9
    assert result["recurrence"]["first_occurrence"] == start.isoformat()


def test_create_event_with_exceptions_emits_exdate_and_reduces_count():
    client, svc = _make_client_with_mock_service()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt124",
        "summary": "MWF",
        "start": {"dateTime": "2026-07-06T13:00:00-05:00"},
        "end": {"dateTime": "2026-07-06T14:00:00-05:00"},
    }

    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    end = datetime(2026, 7, 6, 14, 0, tzinfo=CENTRAL)
    result = client.create_event(
        summary="MWF",
        start=start,
        end=end,
        recurrence={
            "freq": "WEEKLY",
            "by_day": ["MO", "WE", "FR"],
            "until": "2026-07-24",
            "exceptions": ["2026-07-13"],
        },
    )

    body = _captured_body(svc)
    assert body["recurrence"][0] == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20260725T045959Z"
    assert body["recurrence"][1] == "EXDATE;TZID=America/Chicago:20260713T130000"
    # 9 base occurrences - 1 EXDATE = 8.
    assert result["recurrence"]["occurrence_count"] == 8


def test_create_event_with_raw_rrule_escape_hatch():
    client, svc = _make_client_with_mock_service()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt125",
        "summary": "Raw",
        "start": {"dateTime": "2026-07-06T13:00:00-05:00"},
        "end": {"dateTime": "2026-07-06T14:00:00-05:00"},
    }
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    end = datetime(2026, 7, 6, 14, 0, tzinfo=CENTRAL)
    client.create_event(
        summary="Raw",
        start=start,
        end=end,
        recurrence_rrule="RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=9",
    )
    body = _captured_body(svc)
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=9"]


def test_create_event_rejects_both_recurrence_and_rrule():
    client, _svc = _make_client_with_mock_service()
    start = datetime(2026, 7, 6, 13, 0, tzinfo=CENTRAL)
    end = datetime(2026, 7, 6, 14, 0, tzinfo=CENTRAL)
    with pytest.raises(ValueError, match="not both"):
        client.create_event(
            summary="x",
            start=start,
            end=end,
            recurrence={"freq": "DAILY", "count": 3},
            recurrence_rrule="FREQ=DAILY;COUNT=3",
        )


def test_create_event_all_day_recurring_uses_date_form_until():
    client, svc = _make_client_with_mock_service()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt126",
        "summary": "Daily holiday",
        "start": {"date": "2026-07-06"},
        "end": {"date": "2026-07-07"},
    }
    start = datetime(2026, 7, 6, tzinfo=CENTRAL)
    end = datetime(2026, 7, 7, tzinfo=CENTRAL)
    client.create_event(
        summary="Daily holiday",
        start=start,
        end=end,
        all_day=True,
        recurrence={"freq": "DAILY", "until": "2026-07-10"},
    )
    body = _captured_body(svc)
    assert body["recurrence"] == ["RRULE:FREQ=DAILY;UNTIL=20260710"]
    assert "date" in body["start"] and "dateTime" not in body["start"]


def test_create_event_dst_spanning_series_preserves_tz():
    # Start before DST ends (Nov 1 2026), recur weekly past it. We verify the
    # MCP doesn't drop the tz on serialization.
    client, svc = _make_client_with_mock_service()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt127",
        "summary": "DST",
        "start": {"dateTime": "2026-10-26T09:00:00-05:00"},
        "end": {"dateTime": "2026-10-26T10:00:00-05:00"},
    }
    start = datetime(2026, 10, 26, 9, 0, tzinfo=CENTRAL)  # Mon, still CDT
    end = datetime(2026, 10, 26, 10, 0, tzinfo=CENTRAL)
    client.create_event(
        summary="DST",
        start=start,
        end=end,
        recurrence={"freq": "WEEKLY", "by_day": ["MO"], "count": 6},
    )
    body = _captured_body(svc)
    # tz preserved on the wire.
    assert "America/Chicago" in body["start"]["timeZone"]
