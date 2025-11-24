# Google Calendar MCP Server - Specification

## Executive Summary

A Model Context Protocol (MCP) server for accessing and analyzing Google Calendar events. Designed to work standalone or in conjunction with spark-mcp for cross-referencing meetings with transcripts and emails.

## Core Requirements

### 1. Authentication
- **OAuth2 authentication** with Google Calendar API
- Secure storage of refresh tokens
- Automatic token refresh handling
- Initial setup flow for user authorization

### 2. Core Functionality
- **Summarize meetings**: Get upcoming meetings, past meetings, daily/weekly summaries
- **Meeting preparation**: "What do I need to be prepared for?"
- **Relationship tracking**: "When was the last time I met with X?"
- **Follow-up tracking**: "Remind me about follow-ups from meetings over the past two weeks"
- **Calendar analysis**: Understand meeting patterns, time allocation

### 3. Blocked Time Intelligence
- Distinguish between different types of blocked time:
  - Deep work blocks (hard blocks)
  - Flexible blocks (available for last-minute requests)
- Allow querying "true" availability vs calendar availability
- Optional: tag or pattern-based block classification

### 4. Integration with spark-mcp
- Cross-reference calendar events with meeting transcripts
- Match meetings by time/date/participants
- Provide unified view of "meeting context" (calendar + transcript + related emails)

## Technical Architecture

### Authentication Flow

```
1. Initial Setup:
   ┌─────────────────────────────────────────────┐
   │ User runs: python -m calendar_mcp.auth      │
   └─────────────────┬───────────────────────────┘
                     │
   ┌─────────────────▼───────────────────────────┐
   │ Opens browser for Google OAuth consent      │
   │ User grants Calendar read permission        │
   └─────────────────┬───────────────────────────┘
                     │
   ┌─────────────────▼───────────────────────────┐
   │ Saves refresh token to:                     │
   │ ~/.config/calendar-mcp/credentials.json     │
   └─────────────────────────────────────────────┘

2. MCP Server Operation:
   ┌─────────────────────────────────────────────┐
   │ Server starts, loads refresh token          │
   └─────────────────┬───────────────────────────┘
                     │
   ┌─────────────────▼───────────────────────────┐
   │ On each API call:                           │
   │ - Check if access token valid               │
   │ - If expired, use refresh token for new one │
   │ - Make API call                             │
   └─────────────────────────────────────────────┘
```

### Data Model

**Calendar Event:**
```python
{
    "id": str,              # Google event ID
    "summary": str,         # Event title
    "description": str,     # Event description
    "start": datetime,      # Start time
    "end": datetime,        # End time
    "attendees": [          # List of attendees
        {
            "email": str,
            "displayName": str,
            "responseStatus": str  # accepted/declined/tentative/needsAction
        }
    ],
    "organizer": {
        "email": str,
        "displayName": str
    },
    "location": str,        # Meeting location/link
    "eventType": str,       # default/focusTime/outOfOffice/workingLocation
    "status": str,          # confirmed/tentative/cancelled
    "hangoutLink": str,     # Google Meet link if present
    "attachments": [],      # File attachments
    "reminders": {},        # Reminder settings
}
```

## MCP Tools

### 1. `list_calendar_events`
**Purpose:** List calendar events with filtering

**Parameters:**
```python
{
    "timeMin": str,          # ISO datetime (default: now)
    "timeMax": str,          # ISO datetime (default: +7 days)
    "maxResults": int,       # Max results (default: 20)
    "query": str,            # Search query (optional)
    "showDeclined": bool,    # Include declined events (default: false)
    "singleEvents": bool     # Expand recurring events (default: true)
}
```

**Returns:**
```python
{
    "events": [
        {
            "id": str,
            "summary": str,
            "start": str,
            "end": str,
            "attendees": [...],
            "location": str,
            "description": str,
            "status": str
        }
    ],
    "total": int
}
```

### 2. `get_upcoming_meetings`
**Purpose:** Get upcoming meetings for preparation

**Parameters:**
```python
{
    "hours": int,           # Look ahead N hours (default: 24)
    "includeAllDay": bool   # Include all-day events (default: false)
}
```

**Returns:**
```python
{
    "meetings": [
        {
            "id": str,
            "summary": str,
            "start": str,
            "timeUntil": str,      # "in 2 hours"
            "attendees": [...],
            "description": str,
            "preparationNotes": str  # Extracted from description
        }
    ],
    "summary": str  # "You have 3 meetings today..."
}
```

### 3. `find_meetings_with_person`
**Purpose:** Find when you last met with someone

**Parameters:**
```python
{
    "email": str,           # Person's email (required)
    "name": str,            # OR person's name
    "maxResults": int,      # Max results (default: 10)
    "timeMin": str,         # Start date (default: -90 days)
    "timeMax": str          # End date (default: now)
}
```

**Returns:**
```python
{
    "meetings": [
        {
            "id": str,
            "summary": str,
            "start": str,
            "attendees": [...],
            "daysAgo": int
        }
    ],
    "lastMeeting": {
        "date": str,
        "daysAgo": int,
        "summary": str
    }
}
```

### 4. `get_meeting_by_id`
**Purpose:** Get full details of a specific meeting

**Parameters:**
```python
{
    "eventId": str  # Google Calendar event ID
}
```

**Returns:**
```python
{
    "event": {...},  # Full event details
    "relatedTranscript": {...} | null  # If spark-mcp available
}
```

### 5. `analyze_time_blocks`
**Purpose:** Analyze calendar blocks and availability

**Parameters:**
```python
{
    "date": str,            # Date to analyze (default: today)
    "includePatterns": bool # Include block pattern analysis (default: true)
}
```

**Returns:**
```python
{
    "date": str,
    "totalBlocked": int,     # Minutes blocked
    "blocks": [
        {
            "start": str,
            "end": str,
            "duration": int,
            "type": "deep-work" | "flexible" | "meeting" | "unknown",
            "summary": str
        }
    ],
    "trueAvailability": [    # Times genuinely available
        {"start": str, "end": str}
    ],
    "flexibleBlocks": [      # Blocks that can be moved
        {"start": str, "end": str, "summary": str}
    ]
}
```

### 6. `summarize_meetings`
**Purpose:** Get a summary of meetings for a time period

**Parameters:**
```python
{
    "timeMin": str,         # Start date
    "timeMax": str,         # End date
    "groupBy": "day" | "week" | "person"
}
```

**Returns:**
```python
{
    "period": str,
    "totalMeetings": int,
    "totalHours": float,
    "summary": str,         # Natural language summary
    "breakdown": {...},     # Grouped data
    "topAttendees": [...]   # Most frequent meeting partners
}
```

### 7. `find_action_items_from_meetings`
**Purpose:** Extract follow-ups from recent meetings

**Parameters:**
```python
{
    "days": int,            # Look back N days (default: 14)
    "keywords": [str]       # Keywords like "TODO", "ACTION", "FOLLOW-UP"
}
```

**Returns:**
```python
{
    "actionItems": [
        {
            "meeting": {...},
            "extractedItems": [str],
            "source": "description" | "transcript"
        }
    ]
}
```

### 8. `check_availability`
**Purpose:** Check if user is available at a given time

**Parameters:**
```python
{
    "start": str,           # Proposed start time
    "end": str,             # Proposed end time
    "respectFlexible": bool # Treat flexible blocks as busy (default: false)
}
```

**Returns:**
```python
{
    "available": bool,
    "conflicts": [...],
    "suggestion": str       # Alternative time if not available
}
```

## Implementation Details

### Dependencies
```json
{
  "google-auth-oauthlib": "^1.0.0",
  "google-auth-httplib2": "^0.2.0",
  "google-api-python-client": "^2.100.0",
  "mcp": "^0.9.0"
}
```

### OAuth2 Setup

**Required Scopes:**
- `https://www.googleapis.com/auth/calendar.readonly`

**Optional Scopes (for future features):**
- `https://www.googleapis.com/auth/calendar.events` (if we add write operations)

### Configuration

**Config File Location:** `~/.config/calendar-mcp/config.json`

```json
{
  "credentials": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "YOUR_REFRESH_TOKEN"
  },
  "preferences": {
    "primaryCalendar": "primary",
    "timezone": "America/New_York",
    "flexibleBlockPatterns": [
      "flexible",
      "optional",
      "buffer"
    ],
    "deepWorkPatterns": [
      "deep work",
      "focus time",
      "writing",
      "research"
    ]
  }
}
```

### Block Type Detection

**Strategy:**
1. Check event `eventType` field
   - `focusTime` → deep work
   - `outOfOffice` → hard block
   - `workingLocation` → informational

2. Check event title patterns
   - Contains "deep work", "focus", "writing" → deep work
   - Contains "flexible", "optional", "buffer" → flexible
   - Default: unknown

3. Check event description for keywords

4. Allow user to configure custom patterns

## Integration with spark-mcp

### Cross-Referencing Strategy

**Match calendar events with transcripts:**

```python
def find_related_transcript(calendar_event):
    """Find transcript for a calendar event."""
    # Query spark-mcp for transcripts around meeting time
    transcripts = spark_mcp.search_meeting_transcripts(
        startDate=event.start - 30min,
        endDate=event.end + 30min
    )

    # Match by:
    # 1. Time overlap (within 30 min)
    # 2. Attendee email match
    # 3. Subject similarity

    return best_match
```

**Unified Meeting Context:**

```python
{
    "calendar": {
        "title": "Product Review Meeting",
        "attendees": [...],
        "start": "2025-11-21T10:00:00Z"
    },
    "transcript": {
        "messagePk": 12345,
        "fullText": "...",
        "duration": "45 min"
    },
    "emails": [
        # Related emails from spark-mcp
    ]
}
```

## Safety and Privacy

### Security Measures
- ✅ **Credential storage**: Encrypted storage using keyring library
- ✅ **Read-only by default**: Only calendar.readonly scope
- ✅ **Token refresh**: Automatic refresh token handling
- ✅ **No data persistence**: Don't cache calendar data locally
- ✅ **Minimal scopes**: Only request necessary permissions

### Privacy Considerations
- User's calendar data is sensitive
- Never log event details to console/files
- Handle attendee information carefully
- Clear error messages without exposing data

## Development Best Practices

### Following spark-mcp Lessons

1. **Silent operation**: No stdout/stderr output
2. **Small limits**: Default to 10-20 results
3. **Minimal descriptions**: Keep tool descriptions under 10 words
4. **Simple parameters**: Minimize optional parameters
5. **Fast responses**: Add timeouts, keep queries efficient
6. **Graceful errors**: Return errors as tool results

### Testing Strategy

1. **Unit tests**: Test API wrapper methods
2. **Integration tests**: Test OAuth flow
3. **Mock responses**: Test tools with mock calendar data
4. **Real data test**: Verify with actual Google Calendar

## Setup Process

### Initial Setup Steps (User Actions Required)

1. **Create Google Cloud Project:**
   - Go to https://console.cloud.google.com
   - Create new project
   - Enable Google Calendar API

2. **Create OAuth2 Credentials:**
   - Go to Credentials section
   - Create OAuth 2.0 Client ID
   - Application type: Desktop app
   - Download credentials JSON

3. **Run Authentication:**
   ```bash
   cd /Users/feamster/src/calendar-mcp
   pip install -e .
   python -m calendar_mcp.auth --credentials /path/to/client_secret.json
   ```

4. **Configure Claude Desktop:**
   ```json
   {
     "mcpServers": {
       "calendar": {
         "command": "python",
         "args": ["-m", "calendar_mcp.server"],
         "cwd": "/Users/feamster/src/calendar-mcp"
       }
     }
   }
   ```

5. **Restart Claude Desktop**

## Future Enhancements

- **Write operations**: Create/update events (requires additional scope)
- **Multiple calendars**: Support for multiple calendar accounts
- **Smart scheduling**: Suggest meeting times based on availability
- **Meeting analytics**: Deep insights into meeting patterns
- **Recurring meeting analysis**: Track recurring 1:1s, team meetings
- **Travel time**: Account for travel time between locations
- **Time zone handling**: Better support for multi-timezone meetings

## Success Metrics

- ✅ Successfully authenticate with Google Calendar API
- ✅ Retrieve events from user's calendar
- ✅ Answer "when did I last meet with X" queries
- ✅ Provide daily meeting summaries
- ✅ Distinguish between block types
- ✅ Sub-second response times
- ✅ No authentication errors after setup
- ✅ Integration with spark-mcp for unified context

## Error Handling

### Common Errors

1. **Authentication Failed**
   - Check credentials file exists
   - Re-run auth setup
   - Verify API is enabled

2. **API Quota Exceeded**
   - Google Calendar API has rate limits
   - Implement exponential backoff
   - Cache recent queries

3. **Invalid Time Range**
   - Validate date parameters
   - Provide clear error messages

4. **Network Errors**
   - Implement retries with backoff
   - Return user-friendly error messages
