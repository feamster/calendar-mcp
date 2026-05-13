"""Google Calendar API client wrapper with multi-account support."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import (
    get_credentials,
    get_credentials_for_account,
    get_configured_accounts,
    get_default_account,
    load_accounts_config
)
import json
from pathlib import Path


_WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_VALID_WEEKDAYS = set(_WEEKDAY_CODES)
_VALID_FREQS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


def _weekday_code(dt: datetime) -> str:
    return _WEEKDAY_CODES[dt.weekday()]


def _parse_until(until: str, start_dt: datetime, all_day: bool) -> datetime:
    """Parse ``until`` value (ISO datetime or bare date) into a datetime.

    Bare dates are interpreted as end-of-day (23:59:59) in ``start_dt``'s tz for
    timed events, and as the literal date for all-day events.
    """
    # Detect bare-date form explicitly first — datetime.fromisoformat accepts
    # "YYYY-MM-DD" (Py 3.11+) and would otherwise silently produce midnight,
    # dropping the final instance of a series.
    bare_date_re = (len(until) == 10 and until[4] == "-" and until[7] == "-")
    if bare_date_re:
        try:
            d = datetime.strptime(until, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"recurrence.until invalid format: {until!r}") from e
        if all_day:
            return d.replace(tzinfo=start_dt.tzinfo) if start_dt.tzinfo else d
        if start_dt.tzinfo:
            return d.replace(hour=23, minute=59, second=59, tzinfo=start_dt.tzinfo)
        return d.replace(hour=23, minute=59, second=59)

    try:
        dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"recurrence.until invalid format: {until!r}") from e
    if dt.tzinfo is None and start_dt.tzinfo is not None:
        dt = dt.replace(tzinfo=start_dt.tzinfo)
    return dt


def _format_until(until_dt: datetime, all_day: bool) -> str:
    """Serialize UNTIL per RFC 5545: UTC Z form for timed, date form for all-day."""
    if all_day:
        return until_dt.strftime("%Y%m%d")
    if until_dt.tzinfo is None:
        return until_dt.strftime("%Y%m%dT%H%M%SZ")
    return until_dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def _build_rrule(
    spec: Dict[str, Any],
    start_dt: datetime,
    all_day: bool = False,
) -> str:
    """Build an RFC 5545 RRULE body (without the ``RRULE:`` prefix) from a
    structured recurrence spec, validating the spec along the way.

    Pure function — does no API calls. Designed for direct unit testing.
    """
    if not isinstance(spec, dict):
        raise ValueError("recurrence must be a dict")

    freq = spec.get("freq")
    if not freq:
        raise ValueError("recurrence.freq is required")
    freq = freq.upper()
    if freq not in _VALID_FREQS:
        raise ValueError(
            f"recurrence.freq must be one of {sorted(_VALID_FREQS)}, got {freq!r}"
        )

    if spec.get("count") is not None and spec.get("until") is not None:
        raise ValueError("recurrence: 'count' and 'until' are mutually exclusive")

    by_day = spec.get("by_day")
    if by_day is not None:
        if not isinstance(by_day, list) or not by_day:
            raise ValueError("recurrence.by_day must be a non-empty list")
        by_day = [d.upper() for d in by_day]
        bad = [d for d in by_day if d not in _VALID_WEEKDAYS]
        if bad:
            raise ValueError(
                f"recurrence.by_day has invalid weekday codes: {bad}. "
                f"Use {_WEEKDAY_CODES}."
            )
        if freq not in ("WEEKLY", "MONTHLY"):
            raise ValueError(
                "recurrence.by_day is only valid with freq=WEEKLY or MONTHLY"
            )
        if freq == "WEEKLY":
            wk = _weekday_code(start_dt)
            if wk not in by_day:
                raise ValueError(
                    f"recurrence.by_day={by_day} does not include start's weekday "
                    f"({wk}). Google would silently include start as an extra "
                    f"occurrence. Either change start to a day in by_day, or add "
                    f"{wk!r} to by_day."
                )

    by_set_pos = spec.get("by_set_pos")
    if by_set_pos is not None:
        if not by_day:
            raise ValueError("recurrence.by_set_pos requires by_day to be set")
        if freq not in ("MONTHLY", "YEARLY"):
            raise ValueError(
                "recurrence.by_set_pos is typically only used with freq=MONTHLY or YEARLY"
            )

    count = spec.get("count")
    if count is not None:
        if not isinstance(count, int) or count <= 0:
            raise ValueError("recurrence.count must be a positive integer")

    interval = spec.get("interval", 1)
    if not isinstance(interval, int) or interval < 1:
        raise ValueError("recurrence.interval must be a positive integer")

    until_str = None
    if spec.get("until") is not None:
        until_dt = _parse_until(spec["until"], start_dt, all_day)
        if until_dt <= start_dt:
            raise ValueError(
                f"recurrence.until ({spec['until']!r}) must be strictly after "
                f"start ({start_dt.isoformat()})"
            )
        until_str = _format_until(until_dt, all_day)

    parts = [f"FREQ={freq}"]
    if interval != 1:
        parts.append(f"INTERVAL={interval}")
    if by_day:
        parts.append(f"BYDAY={','.join(by_day)}")
    if spec.get("by_month_day"):
        parts.append(f"BYMONTHDAY={','.join(str(d) for d in spec['by_month_day'])}")
    if spec.get("by_month"):
        parts.append(f"BYMONTH={','.join(str(m) for m in spec['by_month'])}")
    if by_set_pos:
        parts.append(f"BYSETPOS={','.join(str(p) for p in by_set_pos)}")
    if count is not None:
        parts.append(f"COUNT={count}")
    if until_str:
        parts.append(f"UNTIL={until_str}")

    return ";".join(parts)


def _build_exdate_line(
    exceptions: List[str],
    start_dt: datetime,
    all_day: bool,
) -> str:
    """Build an EXDATE line excluding occurrences. Each entry must match the
    instance's DTSTART representation — local time + TZID for timed events,
    date-only for all-day events.
    """
    if not exceptions:
        raise ValueError("exceptions list must not be empty")
    if all_day:
        formatted = []
        for d in exceptions:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(
                    f"recurrence.exceptions entry {d!r} must be YYYY-MM-DD for all-day"
                ) from e
            formatted.append(dt.strftime("%Y%m%d"))
        return f"EXDATE;VALUE=DATE:{','.join(formatted)}"

    tz_name = _tz_name_for(start_dt)
    formatted = []
    start_time = start_dt.strftime("%H%M%S")
    for d in exceptions:
        is_bare_date = len(d) == 10 and d[4] == "-" and d[7] == "-"
        if is_bare_date:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(
                    f"recurrence.exceptions entry {d!r} must be ISO datetime or YYYY-MM-DD"
                ) from e
            local = f"{dt.strftime('%Y%m%d')}T{start_time}"
        else:
            try:
                dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(
                    f"recurrence.exceptions entry {d!r} must be ISO datetime or YYYY-MM-DD"
                ) from e
            local = dt.strftime("%Y%m%dT%H%M%S")
        formatted.append(local)
    return f"EXDATE;TZID={tz_name}:{','.join(formatted)}"


def _tz_name_for(dt: datetime) -> str:
    """Return a TZ name suitable for Google Calendar / RFC 5545 TZID."""
    tz = dt.tzinfo
    if tz is None:
        return "UTC"
    if isinstance(tz, ZoneInfo):
        return tz.key
    # Fixed offset (e.g. parsed from ISO with -05:00) — fall back to UTC for TZID.
    name = getattr(tz, "key", None) or str(tz)
    return name


def _count_occurrences(rrule_body: str, start_dt: datetime) -> Tuple[Optional[int], Optional[datetime], Optional[datetime]]:
    """Expand RRULE locally and return (count, first, last). Returns (None, ...)
    if the rule has no UNTIL/COUNT (infinite) or exceeds a sane cap.
    """
    cap = 10000
    try:
        rule = rrulestr(f"RRULE:{rrule_body}", dtstart=start_dt)
    except Exception:
        return (None, None, None)

    occurrences: List[datetime] = []
    for i, occ in enumerate(rule):
        if i >= cap:
            return (None, occurrences[0] if occurrences else None, None)
        occurrences.append(occ)
    if not occurrences:
        return (0, None, None)
    return (len(occurrences), occurrences[0], occurrences[-1])


class CalendarClient:
    """Client for Google Calendar API operations with multi-account support."""

    def __init__(self):
        """Initialize Calendar API client."""
        import sys

        # Multi-account support: store services per account
        self._services: Dict[str, Any] = {}
        self._default_service = None

        # Try to initialize with configured accounts
        accounts = get_configured_accounts()
        default_account = get_default_account()

        failed_accounts = []
        if accounts:
            # Initialize services for all configured accounts
            for email in accounts:
                try:
                    creds = get_credentials_for_account(email)
                    if creds:
                        self._services[email] = build('calendar', 'v3', credentials=creds)
                    else:
                        failed_accounts.append(f"{email} (no valid credentials)")
                except Exception as e:
                    failed_accounts.append(f"{email} ({str(e)})")
                    print(f"Warning: Failed to initialize account {email}: {e}", file=sys.stderr, flush=True)

            # Set default service
            if default_account and default_account in self._services:
                self._default_service = self._services[default_account]
            elif self._services:
                # Use first available service as default
                self._default_service = next(iter(self._services.values()))

        # Fall back to legacy single-account if no multi-account setup
        if not self._default_service:
            creds = get_credentials()
            if not creds:
                error_msg = "No valid credentials found. Please run: python -m calendar_mcp.auth"
                if failed_accounts:
                    error_msg += f"\n\nFailed accounts: {', '.join(failed_accounts)}"
                raise ValueError(error_msg)
            self._default_service = build('calendar', 'v3', credentials=creds)

        # For backwards compatibility
        self.service = self._default_service

        self._calendars_cache = None
        self._calendars_cache_by_account: Dict[str, List[Dict]] = {}
        self._config = self._load_config()

        # Log successful initialization
        if self._services:
            print(f"Calendar MCP initialized with {len(self._services)} account(s): {', '.join(self._services.keys())}", file=sys.stderr, flush=True)
            if failed_accounts:
                print(f"Warning: Some accounts failed to initialize: {', '.join(failed_accounts)}", file=sys.stderr, flush=True)

    def _get_service_for_account(self, account: Optional[str] = None) -> Any:
        """Get the Google Calendar service for a specific account.

        Args:
            account: Account email. If None, uses default account.

        Returns:
            Google Calendar API service object
        """
        if account and account in self._services:
            return self._services[account]
        return self._default_service

    def _infer_account_from_calendar_id(self, calendar_id: str) -> Optional[str]:
        """Infer which account to use based on calendar ID.

        If the calendar_id looks like an email and matches a configured account,
        use that account's credentials.

        Args:
            calendar_id: The calendar ID (could be 'primary', an email, or other ID)

        Returns:
            Account email if inferred, None otherwise
        """
        if not calendar_id or calendar_id == 'primary':
            return None

        # Check if calendar_id is an email that matches a configured account
        calendar_id_lower = calendar_id.lower()
        for account in self._services.keys():
            if account.lower() == calendar_id_lower:
                return account

        return None

    def _get_service_for_calendar(self, calendar_id: str, account: Optional[str] = None) -> Any:
        """Get the appropriate service for a calendar operation.

        Priority:
        1. Explicit account parameter
        2. Inferred from calendar_id
        3. Default account

        Args:
            calendar_id: The calendar ID
            account: Explicit account override

        Returns:
            Google Calendar API service object
        """
        # Explicit account takes priority
        if account:
            return self._get_service_for_account(account)

        # Try to infer from calendar_id
        inferred = self._infer_account_from_calendar_id(calendar_id)
        if inferred:
            return self._get_service_for_account(inferred)

        # Fall back to default
        return self._default_service

    def get_configured_accounts(self) -> List[str]:
        """Get list of configured accounts."""
        return list(self._services.keys())

    def get_default_account(self) -> Optional[str]:
        """Get the default account email."""
        return get_default_account()

    def _load_config(self) -> Dict[str, Any]:
        """Load user preferences from config file."""
        config_path = Path.home() / ".mcp-config" / "calendar" / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _get_ignored_calendars_for_availability(self) -> List[str]:
        """Get list of calendar IDs to ignore when checking availability."""
        return self._config.get('ignore_calendars_for_availability', [])

    def get_all_calendars(self) -> List[Dict[str, Any]]:
        """Get list of all calendars user has access to.

        Returns:
            List of calendar dictionaries with id, summary, description, etc.
        """
        if self._calendars_cache is not None:
            return self._calendars_cache

        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            # Cache the results
            self._calendars_cache = calendars
            return calendars
        except HttpError as e:
            return []

    def list_events(
        self,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 20,
        query: Optional[str] = None,
        show_declined: bool = False,
        single_events: bool = True,
        calendar_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """List calendar events from all accessible calendars.

        Args:
            time_min: Start of time range (default: now)
            time_max: End of time range (default: +7 days)
            max_results: Maximum results to return (total across all calendars)
            query: Search query
            show_declined: Include declined events
            single_events: Expand recurring events
            calendar_ids: Specific calendar IDs to query (default: all calendars)

        Returns:
            Dictionary with 'events' list and 'total' count
        """
        if time_min is None:
            time_min = datetime.now(ZoneInfo("UTC"))
        if time_max is None:
            time_max = time_min + timedelta(days=7)

        # Get all calendars if not specified
        if calendar_ids is None:
            calendars = self.get_all_calendars()
            calendar_ids = [cal['id'] for cal in calendars]

        all_events = []

        # Query each calendar
        errors = []
        for calendar_id in calendar_ids:
            try:
                events_result = self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    maxResults=max_results,  # Per calendar limit
                    singleEvents=single_events,
                    orderBy='startTime' if single_events else None,
                    q=query,
                    showDeleted=False
                ).execute()

                events = events_result.get('items', [])

                # Add calendar info to each event
                for event in events:
                    event['_calendar_id'] = calendar_id
                    event['_calendar_name'] = self._get_calendar_name(calendar_id)

                all_events.extend(events)

            except HttpError as e:
                # Log the error but continue with other calendars
                error_details = {
                    'calendar_id': calendar_id,
                    'calendar_name': self._get_calendar_name(calendar_id),
                    'error': str(e),
                    'reason': e.resp.reason if hasattr(e, 'resp') else 'Unknown'
                }
                errors.append(error_details)
                continue

        # Filter out declined events if requested
        if not show_declined:
            all_events = [
                e for e in all_events
                if self._is_not_declined(e)
            ]

        # Sort by start time
        all_events.sort(key=lambda e: e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '')))

        # Limit total results
        all_events = all_events[:max_results]

        result = {
            'events': [self._format_event(e) for e in all_events],
            'total': len(all_events),
            'calendars_queried': len(calendar_ids)
        }

        # Include errors if any occurred
        if errors:
            result['errors'] = errors
            result['calendars_with_errors'] = len(errors)

        return result

    def _get_calendar_name(self, calendar_id: str) -> str:
        """Get calendar name from ID."""
        calendars = self.get_all_calendars()
        for cal in calendars:
            if cal['id'] == calendar_id:
                return cal.get('summary', calendar_id)
        return calendar_id

    def get_upcoming_meetings(
        self,
        hours: int = 24,
        include_all_day: bool = False
    ) -> Dict[str, Any]:
        """Get upcoming meetings for preparation.

        Args:
            hours: Look ahead N hours
            include_all_day: Include all-day events

        Returns:
            Dictionary with 'meetings' list and 'summary' text
        """
        now = datetime.now(ZoneInfo("UTC"))
        time_max = now + timedelta(hours=hours)

        result = self.list_events(
            time_min=now,
            time_max=time_max,
            max_results=50
        )

        if 'error' in result:
            return result

        meetings = result['events']

        # Filter out all-day events if requested
        if not include_all_day:
            meetings = [
                m for m in meetings
                if not m.get('isAllDay', False)
            ]

        # Add time until meeting
        for meeting in meetings:
            start = datetime.fromisoformat(meeting['start'].replace('Z', '+00:00'))
            delta = start - now
            hours_until = delta.total_seconds() / 3600

            if hours_until < 1:
                meeting['timeUntil'] = f"in {int(delta.total_seconds() / 60)} minutes"
            elif hours_until < 24:
                meeting['timeUntil'] = f"in {int(hours_until)} hours"
            else:
                days = int(hours_until / 24)
                meeting['timeUntil'] = f"in {days} days"

        # Generate summary
        if not meetings:
            summary = f"No meetings in the next {hours} hours"
        elif len(meetings) == 1:
            summary = f"You have 1 meeting in the next {hours} hours"
        else:
            summary = f"You have {len(meetings)} meetings in the next {hours} hours"

        return {
            'meetings': meetings,
            'summary': summary
        }

    def find_meetings_with_person(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None,
        max_results: int = 10,
        days_back: int = 90
    ) -> Dict[str, Any]:
        """Find meetings with a specific person.

        Args:
            email: Person's email address
            name: Person's name
            max_results: Maximum results
            days_back: How many days to look back

        Returns:
            Dictionary with 'meetings' list and 'lastMeeting' info
        """
        if not email and not name:
            return {'error': 'Must provide email or name'}

        now = datetime.now(ZoneInfo("UTC"))
        time_min = now - timedelta(days=days_back)

        # Search query
        query = email if email else name

        result = self.list_events(
            time_min=time_min,
            time_max=now,
            max_results=max_results,
            query=query
        )

        if 'error' in result:
            return result

        meetings = result['events']

        # Filter to meetings with the person
        if email:
            meetings = [
                m for m in meetings
                if self._has_attendee_email(m, email)
            ]

        # Add days ago
        for meeting in meetings:
            start = datetime.fromisoformat(meeting['start'].replace('Z', '+00:00'))
            days_ago = (now - start).days
            meeting['daysAgo'] = days_ago

        # Sort by date (most recent first)
        meetings.sort(key=lambda m: m['start'], reverse=True)

        # Get last meeting info
        last_meeting = None
        if meetings:
            last = meetings[0]
            last_meeting = {
                'date': last['start'],
                'daysAgo': last['daysAgo'],
                'summary': last['summary']
            }

        return {
            'meetings': meetings[:max_results],
            'lastMeeting': last_meeting
        }

    def get_event_by_id(self, event_id: str, calendar_id: Optional[str] = None) -> Dict[str, Any]:
        """Get full details of a specific event.

        Args:
            event_id: Google Calendar event ID
            calendar_id: Optional calendar ID (searches all if not provided)

        Returns:
            Dictionary with event details
        """
        # If calendar_id provided, query that calendar
        if calendar_id:
            try:
                event = self.service.events().get(
                    calendarId=calendar_id,
                    eventId=event_id
                ).execute()

                event['_calendar_id'] = calendar_id
                event['_calendar_name'] = self._get_calendar_name(calendar_id)
                return self._format_event(event, full=True)
            except HttpError as e:
                return {'error': f'Event not found: {e}'}

        # Otherwise, search all calendars
        calendars = self.get_all_calendars()
        for cal in calendars:
            try:
                event = self.service.events().get(
                    calendarId=cal['id'],
                    eventId=event_id
                ).execute()

                event['_calendar_id'] = cal['id']
                event['_calendar_name'] = cal.get('summary', cal['id'])
                return self._format_event(event, full=True)
            except HttpError:
                continue

        return {'error': 'Event not found in any calendar'}

    def analyze_time_blocks(
        self,
        date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Analyze calendar blocks for a given day.

        Args:
            date: Date to analyze (default: today)

        Returns:
            Dictionary with block analysis
        """
        if date is None:
            date = datetime.now(ZoneInfo("UTC"))

        # Get start and end of day
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=23, minute=59, second=59)

        result = self.list_events(
            time_min=start_of_day,
            time_max=end_of_day,
            max_results=100
        )

        if 'error' in result:
            return result

        events = result['events']

        # Analyze blocks
        blocks = []
        total_blocked = 0

        for event in events:
            start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
            duration = int((end - start).total_seconds() / 60)

            block_type = self._classify_block(event)

            blocks.append({
                'start': event['start'],
                'end': event['end'],
                'duration': duration,
                'type': block_type,
                'summary': event['summary']
            })

            total_blocked += duration

        # Find flexible blocks
        flexible_blocks = [
            b for b in blocks
            if b['type'] == 'flexible'
        ]

        return {
            'date': date.date().isoformat(),
            'totalBlocked': total_blocked,
            'blocks': blocks,
            'flexibleBlocks': flexible_blocks
        }

    def summarize_meetings(
        self,
        time_min: datetime,
        time_max: datetime,
        group_by: str = 'day'
    ) -> Dict[str, Any]:
        """Summarize meetings for a time period.

        Args:
            time_min: Start date
            time_max: End date
            group_by: How to group ('day', 'week', 'person')

        Returns:
            Dictionary with meeting summary
        """
        result = self.list_events(
            time_min=time_min,
            time_max=time_max,
            max_results=500
        )

        if 'error' in result:
            return result

        meetings = result['events']

        total_meetings = len(meetings)
        total_hours = sum(
            self._get_duration_hours(m)
            for m in meetings
        )

        # Count attendees
        attendee_counts = {}
        for meeting in meetings:
            for attendee in meeting.get('attendees', []):
                email = attendee.get('email', '')
                attendee_counts[email] = attendee_counts.get(email, 0) + 1

        top_attendees = sorted(
            attendee_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        summary = (
            f"{total_meetings} meetings totaling {total_hours:.1f} hours "
            f"from {time_min.date()} to {time_max.date()}"
        )

        return {
            'period': f"{time_min.date()} to {time_max.date()}",
            'totalMeetings': total_meetings,
            'totalHours': total_hours,
            'summary': summary,
            'topAttendees': [
                {'email': email, 'count': count}
                for email, count in top_attendees
            ]
        }

    def check_availability(
        self,
        start: datetime,
        end: datetime,
        respect_flexible: bool = False
    ) -> Dict[str, Any]:
        """Check if user is available at a given time.

        Args:
            start: Proposed start time
            end: Proposed end time
            respect_flexible: Treat flexible blocks as busy

        Returns:
            Dictionary with availability info
        """
        result = self.list_events(
            time_min=start,
            time_max=end,
            max_results=100
        )

        if 'error' in result:
            return result

        conflicts = result['events']

        # Filter out events from ignored calendars (e.g., seminars, holidays)
        ignored_calendars = self._get_ignored_calendars_for_availability()
        if ignored_calendars:
            conflicts = [
                c for c in conflicts
                if c.get('calendarId') not in ignored_calendars
            ]

        # Filter out flexible blocks if requested
        if not respect_flexible:
            conflicts = [
                c for c in conflicts
                if self._classify_block(c) != 'flexible'
            ]

        available = len(conflicts) == 0

        return {
            'available': available,
            'conflicts': conflicts,
            'suggestion': None if available else 'Time slot has conflicts'
        }

    # Helper methods

    def _format_event(self, event: Dict, full: bool = False) -> Dict[str, Any]:
        """Format event data for response."""
        # Get start/end times
        start = event.get('start', {})
        end = event.get('end', {})

        # Check if all-day event
        is_all_day = 'date' in start

        formatted = {
            'id': event.get('id'),
            'summary': event.get('summary', '(No title)'),
            'start': start.get('dateTime') or start.get('date'),
            'end': end.get('dateTime') or end.get('date'),
            'isAllDay': is_all_day,
            'status': event.get('status'),
            'attendees': self._format_attendees(event.get('attendees', [])),
            'location': event.get('location'),
            'description': event.get('description', ''),
            'calendarId': event.get('_calendar_id'),
            'calendarName': event.get('_calendar_name')
        }

        if full:
            formatted.update({
                'organizer': event.get('organizer'),
                'hangoutLink': event.get('hangoutLink'),
                'eventType': event.get('eventType', 'default')
            })

        return formatted

    def _format_attendees(self, attendees: List[Dict]) -> List[Dict[str, str]]:
        """Format attendee list."""
        return [
            {
                'email': a.get('email', ''),
                'displayName': a.get('displayName', a.get('email', '')),
                'responseStatus': a.get('responseStatus', 'needsAction')
            }
            for a in attendees
        ]

    def _is_not_declined(self, event: Dict) -> bool:
        """Check if user has not declined the event."""
        attendees = event.get('attendees', [])

        # Get user's email from organizer or attendees
        for attendee in attendees:
            if attendee.get('self', False):
                return attendee.get('responseStatus') != 'declined'

        # If no self attendee found, assume not declined
        return True

    def _has_attendee_email(self, event: Dict, email: str) -> bool:
        """Check if event has attendee with given email."""
        attendees = event.get('attendees', [])
        email_lower = email.lower()

        for attendee in attendees:
            if attendee.get('email', '').lower() == email_lower:
                return True

        # Also check organizer
        organizer = event.get('organizer', {})
        if organizer.get('email', '').lower() == email_lower:
            return True

        return False

    def _classify_block(self, event: Dict) -> str:
        """Classify calendar block type.

        Returns: 'deep-work', 'flexible', 'meeting', 'out-of-office', 'unknown'
        """
        summary = event.get('summary', '').lower()
        event_type = event.get('eventType', 'default')

        # Check event type
        if event_type == 'focusTime':
            return 'deep-work'
        elif event_type == 'outOfOffice':
            return 'out-of-office'

        # Get patterns from config
        prefs = self._config.get('preferences', {})
        flexible_patterns = prefs.get('flexibleBlockPatterns', ['flexible', 'optional', 'buffer', 'hold'])
        deep_work_patterns = prefs.get('deepWorkPatterns', ['deep work', 'focus', 'blocked', 'writing', 'research', 'reading'])

        # Check summary patterns
        for pattern in flexible_patterns:
            if pattern.lower() in summary:
                return 'flexible'

        for pattern in deep_work_patterns:
            if pattern.lower() in summary:
                return 'deep-work'

        # Check if it has attendees (likely a meeting)
        attendees = event.get('attendees', [])
        if len(attendees) > 0:
            return 'meeting'

        return 'unknown'

    def find_meeting_times(
        self,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int = 30,
        max_suggestions: int = 5
    ) -> Dict[str, Any]:
        """Find available meeting times based on user preferences from config.

        Uses preferences from config.json including:
        - Day-of-week ranking (preferredDays): Higher scores = more preferred
          e.g., Wed-PM: 100, Thu: 100, Mon-PM: 70, Tue: 40, Fri: 40
        - Adjacent to meetings (preferAdjacentToMeetings): Prefer slots next to existing meetings
        - Avoid deep work (avoidDeepWorkBlocks): Try to preserve focus time
        - Never-available patterns (neverAvailablePatterns): Never suggest over these blocks

        Two-tier approach:
        1. First finds completely free slots and scores by day preference
        2. Only if needed, considers deep work blocks (end times)

        Args:
            start_date: Start of search range
            end_date: End of search range
            duration_minutes: Desired meeting length
            max_suggestions: Maximum suggestions to return

        Returns:
            Dictionary with suggested times (sorted by score) and metadata
        """
        # Get preferences from config
        prefs = self._config.get('preferences', {}).get('meetingPreferences', {})
        prefer_adjacent = prefs.get('preferAdjacentToMeetings', True)
        avoid_deep_work = prefs.get('avoidDeepWorkBlocks', True)
        deep_work_usage = prefs.get('deepWorkBlockUsage', 'end')
        never_available = prefs.get('neverAvailablePatterns', [])

        # Get all events in range
        result = self.list_events(
            time_min=start_date,
            time_max=end_date,
            max_results=500
        )

        if 'error' in result:
            return result

        events = result['events']

        # Filter out events from ignored calendars (e.g., seminars, holidays)
        ignored_calendars = self._get_ignored_calendars_for_availability()
        if ignored_calendars:
            events = [
                e for e in events
                if e.get('calendarId') not in ignored_calendars
            ]

        # Filter out "never available" blocks
        def is_never_available(event):
            summary = event.get('summary', '').lower()
            return any(pattern.lower() in summary for pattern in never_available)

        # Separate events by type
        meeting_events = []
        deep_work_events = []
        never_avail_events = []

        for event in events:
            if is_never_available(event):
                never_avail_events.append(event)
            else:
                block_type = self._classify_block(event)
                if block_type == 'deep-work':
                    deep_work_events.append(event)
                else:
                    meeting_events.append(event)

        # TIER 1: Find completely free slots
        free_slots = self._find_free_slots(
            meeting_events + never_avail_events,
            start_date,
            end_date,
            duration_minutes
        )

        # Score and rank free slots
        suggestions = []
        for slot in free_slots[:max_suggestions * 2]:  # Get extra to filter
            score = self._score_slot(slot, meeting_events, prefer_adjacent)
            suggestions.append({
                'start': slot['start'].isoformat(),
                'end': slot['end'].isoformat(),
                'duration': duration_minutes,
                'type': 'free',
                'score': score,
                'reason': 'Completely free' + (' (adjacent to meetings)' if score > 50 else '')
            })

        # Sort by score
        suggestions.sort(key=lambda x: x['score'], reverse=True)

        # If we have enough good suggestions, return them
        if len(suggestions) >= max_suggestions:
            return {
                'suggestions': suggestions[:max_suggestions],
                'totalFound': len(free_slots),
                'usedDeepWork': False
            }

        # TIER 2: Consider deep work blocks if needed
        if avoid_deep_work and len(suggestions) < max_suggestions and len(deep_work_events) > 0:
            deep_work_slots = self._find_deep_work_slots(
                deep_work_events,
                duration_minutes,
                deep_work_usage,
                never_avail_events
            )

            for slot in deep_work_slots:
                suggestions.append({
                    'start': slot['start'].isoformat(),
                    'end': slot['end'].isoformat(),
                    'duration': duration_minutes,
                    'type': 'deep-work',
                    'score': 25,  # Lower score than free time
                    'reason': f"Deep work block ({deep_work_usage} of block)"
                })

        return {
            'suggestions': suggestions[:max_suggestions],
            'totalFound': len(free_slots) + len(deep_work_slots) if 'deep_work_slots' in locals() else len(free_slots),
            'usedDeepWork': len(suggestions) > len(free_slots) if 'deep_work_slots' in locals() else False
        }

    def _find_free_slots(
        self,
        busy_events: List[Dict],
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int
    ) -> List[Dict[str, datetime]]:
        """Find gaps between events."""
        # Sort events by start time
        sorted_events = sorted(
            busy_events,
            key=lambda e: e.get('start', '')
        )

        free_slots = []
        current_time = start_date

        # Only consider working hours (9 AM - 6 PM)
        for event in sorted_events:
            event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
            event_end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))

            # Check gap before this event
            gap_minutes = (event_start - current_time).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                # Found a gap!
                free_slots.append({
                    'start': current_time,
                    'end': current_time + timedelta(minutes=duration_minutes)
                })

            # Move current time to end of this event
            if event_end > current_time:
                current_time = event_end

        # Check gap after last event
        gap_minutes = (end_date - current_time).total_seconds() / 60
        if gap_minutes >= duration_minutes:
            free_slots.append({
                'start': current_time,
                'end': current_time + timedelta(minutes=duration_minutes)
            })

        return free_slots

    def _score_slot(self, slot: Dict, meeting_events: List[Dict], prefer_adjacent: bool) -> int:
        """Score a time slot based on preferences."""
        score = 50  # Base score

        slot_start = slot['start']
        slot_end = slot['end']

        # Get day preferences from config
        prefs = self._config.get('preferences', {}).get('meetingPreferences', {})
        preferred_days = prefs.get('preferredDays', {})
        afternoon_start = prefs.get('afternoonStartHour', 12)

        # Score based on day of week
        day_name = slot_start.strftime('%A')  # Monday, Tuesday, etc.
        hour = slot_start.hour
        is_afternoon = hour >= afternoon_start

        # Check day preferences
        if is_afternoon:
            day_key = f"{day_name}-PM"
            if day_key in preferred_days:
                score += preferred_days[day_key]
            elif day_name in preferred_days:
                score += preferred_days[day_name]
        else:
            if day_name in preferred_days:
                score += preferred_days[day_name]

        # Score for adjacent to meetings
        if prefer_adjacent:
            for event in meeting_events:
                event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                event_end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))

                # Adjacent before
                if abs((slot_start - event_end).total_seconds()) < 300:  # Within 5 min
                    score += 30
                    break
                # Adjacent after
                if abs((event_start - slot_end).total_seconds()) < 300:
                    score += 30
                    break

        return score

    def _find_deep_work_slots(
        self,
        deep_work_events: List[Dict],
        duration_minutes: int,
        usage: str,
        never_avail_events: List[Dict]
    ) -> List[Dict[str, datetime]]:
        """Find slots within deep work blocks."""
        slots = []

        for event in deep_work_events:
            event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
            event_end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))

            event_duration = (event_end - event_start).total_seconds() / 60

            # Only use if block is long enough
            if event_duration < duration_minutes:
                continue

            if usage == 'end':
                # Offer end of block
                slot_start = event_end - timedelta(minutes=duration_minutes)
                slots.append({
                    'start': slot_start,
                    'end': event_end
                })
            elif usage == 'start':
                # Offer start of block
                slots.append({
                    'start': event_start,
                    'end': event_start + timedelta(minutes=duration_minutes)
                })

        return slots

    def _get_duration_hours(self, event: Dict) -> float:
        """Get event duration in hours."""
        start_str = event.get('start', '')
        end_str = event.get('end', '')

        if not start_str or not end_str:
            return 0.0

        try:
            start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            duration = (end - start).total_seconds() / 3600
            return duration
        except Exception:
            return 0.0

    # ===== Write Operations =====

    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        send_notifications: bool = True,
        calendar_id: str = 'primary',
        all_day: bool = False,
        account: Optional[str] = None,
        recurrence: Optional[Dict[str, Any]] = None,
        recurrence_rrule: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new calendar event, optionally recurring.

        Args:
            summary: Event title
            start: Event start time (for all-day events, time portion is ignored)
            end: Event end time (for all-day events, this is exclusive - event runs until start of this day)
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            send_notifications: Whether to send email invitations to attendees
            calendar_id: Calendar to create event in (default: 'primary')
            all_day: If True, creates an all-day event using date field (default: False)
            account: Google account to use (auto-inferred from calendar_id if not specified)
            recurrence: Structured recurrence spec — see ``_build_rrule``. Mutually
                exclusive with ``recurrence_rrule``.
            recurrence_rrule: Raw RRULE escape hatch, with or without the
                ``RRULE:`` prefix (e.g. ``FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10``).

        Returns:
            Dictionary with created event details including event ID. When the
            event is recurring, includes a ``recurrence`` block with the
            generated RRULE and locally-computed occurrence stats.
        """
        if recurrence is not None and recurrence_rrule is not None:
            raise ValueError(
                "Provide either 'recurrence' or 'recurrence_rrule', not both"
            )

        # Get the appropriate service (auto-infers account from calendar_id)
        service = self._get_service_for_calendar(calendar_id, account)

        # Build event object
        event = {
            'summary': summary
        }

        # Handle all-day vs timed events
        if all_day:
            # For all-day events, use date field (YYYY-MM-DD format)
            # Note: end date is exclusive in Google Calendar
            event['start'] = {
                'date': start.date().isoformat()
            }
            event['end'] = {
                'date': end.date().isoformat()
            }
        else:
            # For timed events, use dateTime field
            event['start'] = {
                'dateTime': start.isoformat(),
                'timeZone': str(start.tzinfo) if start.tzinfo else 'UTC'
            }
            event['end'] = {
                'dateTime': end.isoformat(),
                'timeZone': str(end.tzinfo) if end.tzinfo else 'UTC'
            }

        if description:
            event['description'] = description

        if location:
            event['location'] = location

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        # Build recurrence array if requested
        rrule_body: Optional[str] = None
        exceptions: Optional[List[str]] = None
        if recurrence is not None:
            exceptions = recurrence.get("exceptions")
            rrule_body = _build_rrule(recurrence, start, all_day=all_day)
        elif recurrence_rrule is not None:
            raw = recurrence_rrule.strip()
            rrule_body = raw[6:] if raw.upper().startswith("RRULE:") else raw

        if rrule_body:
            recurrence_lines = [f"RRULE:{rrule_body}"]
            if exceptions:
                recurrence_lines.append(_build_exdate_line(exceptions, start, all_day))
            event['recurrence'] = recurrence_lines

        # Create the event
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='all' if send_notifications else 'none'
        ).execute()

        # Determine which account was used
        used_account = account or self._infer_account_from_calendar_id(calendar_id) or get_default_account()

        response: Dict[str, Any] = {
            'success': True,
            'event_id': created_event['id'],
            'event_link': created_event.get('htmlLink'),
            'summary': created_event['summary'],
            'start': created_event['start'].get('dateTime', created_event['start'].get('date')),
            'end': created_event['end'].get('dateTime', created_event['end'].get('date')),
            'attendees': [
                {
                    'email': att['email'],
                    'responseStatus': att.get('responseStatus', 'needsAction')
                }
                for att in created_event.get('attendees', [])
            ] if attendees else [],
            'created': created_event.get('created'),
            'organizer_account': used_account,
            'message': f"Event '{summary}' created successfully" + (f" (organizer: {used_account})" if used_account else "")
        }

        if rrule_body:
            occ_count, first_occ, last_occ = _count_occurrences(rrule_body, start)
            if exceptions:
                # Exclude EXDATE entries from the count.
                excluded = set()
                for d in exceptions:
                    try:
                        excluded.add(datetime.fromisoformat(d.replace("Z", "+00:00")).date())
                    except ValueError:
                        try:
                            excluded.add(datetime.strptime(d, "%Y-%m-%d").date())
                        except ValueError:
                            pass
                if occ_count is not None and excluded:
                    occ_count = max(0, occ_count - len(excluded))
            response['recurrence'] = {
                'rrule': rrule_body,
                'occurrence_count': occ_count,
                'first_occurrence': first_occ.isoformat() if first_occ else None,
                'last_occurrence': last_occ.isoformat() if last_occ else None,
            }

        return response

    def delete_event(
        self,
        event_id: str,
        calendar_id: str = 'primary',
        send_notifications: bool = True,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a calendar event.

        Args:
            event_id: ID of the event to delete
            calendar_id: Calendar containing the event (default: 'primary')
            send_notifications: Whether to send cancellation emails to attendees
            account: Google account to use (auto-inferred from calendar_id if not specified)

        Returns:
            Dictionary with success status
        """
        # Get the appropriate service
        service = self._get_service_for_calendar(calendar_id, account)

        try:
            # Get event details before deleting (for response message)
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            event_summary = event.get('summary', 'Untitled Event')

            # Delete the event
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates='all' if send_notifications else 'none'
            ).execute()

            return {
                'success': True,
                'event_id': event_id,
                'message': f"Event '{event_summary}' deleted successfully"
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to delete event: {str(e)}"
            }

    def update_event_recurrence(
        self,
        event_id: str,
        calendar_id: str = 'primary',
        account: Optional[str] = None,
        recurrence: Optional[Dict[str, Any]] = None,
        recurrence_rrule: Optional[str] = None,
        scope: str = 'series',
        split_at: Optional[str] = None,
        send_notifications: bool = True,
    ) -> Dict[str, Any]:
        """Modify the recurrence rule of an existing event.

        Args:
            event_id: ID of the master recurring event (or instance for scope='single')
            calendar_id: Calendar containing the event
            account: Google account override
            recurrence: Structured recurrence spec (or None to clear recurrence
                entirely when scope='series')
            recurrence_rrule: Raw RRULE escape hatch
            scope: 'series' replaces the master's RRULE.
                   'this_and_following' shortens the original's UNTIL to just
                   before ``split_at`` and inserts a new event with the new rule
                   starting at ``split_at``.
                   'single' overrides a single instance — pass the instance
                   event_id (NOT the master id).
            split_at: ISO datetime where the series should split; required for
                scope='this_and_following'.
            send_notifications: Send update emails to attendees.
        """
        if recurrence is not None and recurrence_rrule is not None:
            return {
                'success': False,
                'error': "Provide either 'recurrence' or 'recurrence_rrule', not both",
            }
        if scope not in ('series', 'this_and_following', 'single'):
            return {
                'success': False,
                'error': f"scope must be one of series|this_and_following|single, got {scope!r}",
            }
        if scope == 'this_and_following' and not split_at:
            return {
                'success': False,
                'error': "scope='this_and_following' requires split_at",
            }

        service = self._get_service_for_calendar(calendar_id, account)
        send_updates = 'all' if send_notifications else 'none'

        try:
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
        except HttpError as e:
            return {'success': False, 'error': f"Event not found: {e}"}

        start_info = event.get('start', {})
        all_day = 'date' in start_info
        if all_day:
            start_dt = datetime.strptime(start_info['date'], '%Y-%m-%d').replace(
                tzinfo=ZoneInfo(start_info.get('timeZone', 'UTC'))
            )
        else:
            start_dt = datetime.fromisoformat(start_info['dateTime'].replace('Z', '+00:00'))

        def _build_recurrence_array(start_for_rule: datetime) -> Optional[List[str]]:
            if recurrence is None and recurrence_rrule is None:
                return None
            if recurrence is not None:
                body = _build_rrule(recurrence, start_for_rule, all_day=all_day)
                lines = [f"RRULE:{body}"]
                if recurrence.get('exceptions'):
                    lines.append(_build_exdate_line(
                        recurrence['exceptions'], start_for_rule, all_day
                    ))
                return lines
            raw = recurrence_rrule.strip()
            body = raw[6:] if raw.upper().startswith('RRULE:') else raw
            return [f"RRULE:{body}"]

        if scope == 'series':
            new_lines = _build_recurrence_array(start_dt)
            patch_body = {'recurrence': new_lines if new_lines is not None else []}
            updated = service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=patch_body,
                sendUpdates=send_updates,
            ).execute()
            return {
                'success': True,
                'scope': 'series',
                'event_id': updated['id'],
                'recurrence': updated.get('recurrence'),
                'message': f"Updated recurrence on series '{updated.get('summary')}'",
            }

        if scope == 'single':
            new_lines = _build_recurrence_array(start_dt)
            patch_body = {'recurrence': new_lines if new_lines is not None else []}
            updated = service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=patch_body,
                sendUpdates=send_updates,
            ).execute()
            return {
                'success': True,
                'scope': 'single',
                'event_id': updated['id'],
                'message': (
                    "Applied recurrence patch to single event. Note: single-instance "
                    "overrides are usually handled via dedicated instance ids."
                ),
            }

        # scope == 'this_and_following'
        split_dt = datetime.fromisoformat(split_at.replace('Z', '+00:00'))
        if split_dt.tzinfo is None and start_dt.tzinfo is not None:
            split_dt = split_dt.replace(tzinfo=start_dt.tzinfo)
        if split_dt <= start_dt:
            return {
                'success': False,
                'error': f"split_at ({split_at}) must be after the series start ({start_dt.isoformat()})",
            }

        # 1. Truncate the original series so its last occurrence is < split_at.
        existing_rec = event.get('recurrence') or []
        rrule_line = next((l for l in existing_rec if l.upper().startswith('RRULE:')), None)
        if not rrule_line:
            return {'success': False, 'error': 'Original event has no RRULE to split'}
        existing_body = rrule_line[6:]
        # Strip any existing UNTIL/COUNT, then set UNTIL = split_dt - 1 second (UTC Z).
        existing_parts = [
            p for p in existing_body.split(';')
            if not p.upper().startswith('UNTIL=') and not p.upper().startswith('COUNT=')
        ]
        until_cutoff = split_dt - timedelta(seconds=1)
        existing_parts.append(f"UNTIL={_format_until(until_cutoff, all_day)}")
        truncated_body = ';'.join(existing_parts)
        new_existing = [f"RRULE:{truncated_body}"] + [
            l for l in existing_rec if not l.upper().startswith('RRULE:')
        ]
        service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={'recurrence': new_existing},
            sendUpdates=send_updates,
        ).execute()

        # 2. Insert a new event starting at split_at with the new rule.
        # Preserve duration from the master.
        end_info = event.get('end', {})
        if all_day:
            old_end = datetime.strptime(end_info['date'], '%Y-%m-%d').replace(
                tzinfo=start_dt.tzinfo
            )
        else:
            old_end = datetime.fromisoformat(end_info['dateTime'].replace('Z', '+00:00'))
        duration = old_end - start_dt
        new_start = split_dt
        new_end = new_start + duration

        new_body: Dict[str, Any] = {
            'summary': event.get('summary'),
            'description': event.get('description'),
            'location': event.get('location'),
            'attendees': event.get('attendees'),
        }
        if all_day:
            new_body['start'] = {'date': new_start.date().isoformat()}
            new_body['end'] = {'date': new_end.date().isoformat()}
        else:
            tz = start_info.get('timeZone', 'UTC')
            new_body['start'] = {'dateTime': new_start.isoformat(), 'timeZone': tz}
            new_body['end'] = {'dateTime': new_end.isoformat(), 'timeZone': tz}

        new_lines = _build_recurrence_array(new_start)
        if new_lines:
            new_body['recurrence'] = new_lines

        # Drop None entries.
        new_body = {k: v for k, v in new_body.items() if v is not None}

        inserted = service.events().insert(
            calendarId=calendar_id,
            body=new_body,
            sendUpdates=send_updates,
        ).execute()

        return {
            'success': True,
            'scope': 'this_and_following',
            'original_event_id': event_id,
            'new_event_id': inserted['id'],
            'split_at': split_dt.isoformat(),
            'message': (
                f"Split series at {split_dt.isoformat()}: truncated original and "
                f"inserted new event {inserted['id']}"
            ),
        }

    def respond_to_event(
        self,
        event_id: str,
        response: str,
        calendar_id: str = 'primary',
        comment: Optional[str] = None,
        respond_to_series: bool = False,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Respond to a calendar event invitation (accept/decline/tentative).

        Args:
            event_id: ID of the event to respond to
            response: Response status - 'accepted', 'declined', or 'tentative'
            calendar_id: Calendar containing the event (default: 'primary')
            comment: Optional comment to include with response
            respond_to_series: If True and event is recurring, respond to all instances (default: False)
            account: Google account to use (auto-inferred from calendar_id if not specified)

        Returns:
            Dictionary with success status and updated event details
        """
        # Get the appropriate service
        service = self._get_service_for_calendar(calendar_id, account)

        valid_responses = ['accepted', 'declined', 'tentative']
        if response.lower() not in valid_responses:
            return {
                'success': False,
                'error': f"Invalid response. Must be one of: {', '.join(valid_responses)}"
            }

        try:
            # Get the event
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            # Check if this is a recurring event instance
            recurring_event_id = event.get('recurringEventId')
            is_recurring = recurring_event_id is not None

            # If user wants to respond to series and this is recurring, use the series ID
            target_event_id = event_id
            if respond_to_series and is_recurring:
                target_event_id = recurring_event_id
                # Get the recurring event (master)
                event = service.events().get(
                    calendarId=calendar_id,
                    eventId=target_event_id
                ).execute()

            # Get current user's email from credentials
            # We'll look for the attendee matching our calendar
            attendees = event.get('attendees', [])

            # Find ourselves in the attendee list and update response
            updated = False
            for attendee in attendees:
                if attendee.get('self', False):
                    attendee['responseStatus'] = response.lower()
                    if comment:
                        attendee['comment'] = comment
                    updated = True
                    break

            if not updated:
                return {
                    'success': False,
                    'error': 'Could not find your attendance in this event. You may not be invited.'
                }

            # Update the event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=target_event_id,
                body=event
            ).execute()

            message = f"Responded '{response}' to event '{updated_event.get('summary')}'"
            if respond_to_series and is_recurring:
                message += " (all instances)"

            return {
                'success': True,
                'event_id': target_event_id,
                'event_summary': updated_event.get('summary'),
                'response': response.lower(),
                'is_recurring': is_recurring,
                'responded_to_series': respond_to_series and is_recurring,
                'message': message
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to respond to event: {str(e)}"
            }

    def respond_to_pending_invitations(
        self,
        response: str,
        days_ahead: int = 90,
        calendar_id: str = 'primary',
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """Respond to all pending calendar invitations at once.

        Args:
            response: Response status - 'accepted', 'declined', or 'tentative'
            days_ahead: How many days ahead to look for pending invitations (default: 90)
            calendar_id: Calendar to check (default: 'primary')
            account: Google account to use (auto-inferred from calendar_id if not specified)

        Returns:
            Dictionary with list of updated events and summary
        """
        # Get the appropriate service
        service = self._get_service_for_calendar(calendar_id, account)

        valid_responses = ['accepted', 'declined', 'tentative']
        if response.lower() not in valid_responses:
            return {
                'success': False,
                'error': f"Invalid response. Must be one of: {', '.join(valid_responses)}"
            }

        try:
            # Get events for the next N days
            now = datetime.now(ZoneInfo("UTC"))
            time_max = now + timedelta(days=days_ahead)

            result = self.list_events(
                time_min=now,
                time_max=time_max,
                max_results=500,
                calendar_ids=[calendar_id]
            )

            events = result.get('events', [])

            # Filter for events where user hasn't responded yet
            pending_events = []
            for event in events:
                attendees = event.get('attendees', [])
                for attendee in attendees:
                    if attendee.get('self', False) and attendee.get('responseStatus') == 'needsAction':
                        pending_events.append(event)
                        break

            if not pending_events:
                return {
                    'success': True,
                    'updated_count': 0,
                    'events': [],
                    'message': 'No pending invitations found'
                }

            # Respond to each pending invitation
            updated_events = []
            failed_events = []

            for event in pending_events:
                event_id = event.get('id')
                event_summary = event.get('summary', 'Untitled Event')

                try:
                    # Get full event details and update
                    full_event = service.events().get(
                        calendarId=calendar_id,
                        eventId=event_id
                    ).execute()

                    # Update response status
                    attendees = full_event.get('attendees', [])
                    for attendee in attendees:
                        if attendee.get('self', False):
                            attendee['responseStatus'] = response.lower()
                            break

                    # Update the event
                    updated_event = service.events().update(
                        calendarId=calendar_id,
                        eventId=event_id,
                        body=full_event
                    ).execute()

                    updated_events.append({
                        'event_id': event_id,
                        'summary': event_summary,
                        'start': event.get('start'),
                        'response': response.lower()
                    })

                except Exception as e:
                    failed_events.append({
                        'event_id': event_id,
                        'summary': event_summary,
                        'error': str(e)
                    })

            return {
                'success': True,
                'updated_count': len(updated_events),
                'failed_count': len(failed_events),
                'events': updated_events,
                'failed': failed_events if failed_events else None,
                'message': f"Responded '{response}' to {len(updated_events)} invitation(s)"
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to process pending invitations: {str(e)}"
            }
