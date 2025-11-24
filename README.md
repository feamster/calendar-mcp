# Google Calendar MCP Server

MCP server for accessing and analyzing Google Calendar events through the Model Context Protocol.

## Features

- 📅 **Access ALL your calendars** - Primary, work, shared calendars, everything!
- ➕ **Create calendar events** - Schedule meetings with attendees and send invitations
- ✅ **Accept/decline invitations** - Respond to calendar invites
- 🗑️ **Delete events** - Remove calendar entries
- 🔍 Find when you last met with someone
- 📊 Analyze meeting patterns and time blocks
- 🎯 Distinguish between deep work and flexible time blocks
- ⚡ Answer questions like "What do I need to be prepared for?"
- 🔗 Integrates with spark-mcp for unified meeting context
- 📋 List and search events across all your calendars at once

## Requirements

- Python 3.10+
- Google Cloud project with Calendar API enabled
- OAuth2 credentials (see setup below)

## Installation

```bash
# Install in development mode
pip install -e .
```

## Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project:
   - Click "Select a project" at the top
   - Click "New Project"
   - Name: `Calendar MCP` (or your choice)
   - Click "Create"
3. Enable the [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com):
   - In left sidebar: "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click on it, then click "Enable"

### 2. Configure OAuth Consent Screen

**Important: Do this BEFORE creating credentials**

1. In left sidebar: "APIs & Services" → "OAuth consent screen"
2. If you see "Overview" page with metrics, look for navigation in left sidebar
3. Click on **"Audience"**:
   - Click "ADD USERS"
   - Add your Google email address
   - Click "Add" then "Save"
4. Click on **"Data Access"** in left sidebar:
   - Click "Add or Remove Scopes"
   - Search for "Google Calendar API"
   - Check: `.../auth/calendar` (full access for read/write operations)
   - Click "Update"
   - Click "Save"

### 3. Create OAuth Client Credentials

1. In left sidebar: Click **"Clients"**
2. Click "CREATE CLIENT" or similar button
3. Choose:
   - Application type: **Desktop app**
   - Name: `calendar-mcp-client`
4. Click "Create"
5. You'll see the client created - click on it
6. In "Client secrets" section:
   - Click "+ Add secret"
   - Copy the new secret OR click download
7. Download the JSON file (should auto-download or look for download option)
8. Save as `client_secret.json` in `/Users/feamster/src/calendar-mcp/`

**Note:** The Google Cloud Console interface uses "OAuth Platform" with Audience/Data Access/Clients, not the old consent screen wizard.

### 4. Authenticate

Run the authentication setup:

```bash
python -m calendar_mcp.auth
```

This will:
- Open your browser for Google OAuth consent
- Ask you to grant Calendar read and write permissions
- Save the refresh token to `~/.config/calendar-mcp/credentials.json`

**Important:** Google will show a warning "Google hasn't verified this app" because this is your personal project. This is normal and safe:
- Click "Advanced"
- Click "Go to Calendar MCP (unsafe)"
- Grant the calendar read and write permissions

### 5. Configure Meeting Preferences (Optional)

Create `~/.config/calendar-mcp/config.json` to customize your scheduling preferences:

```json
{
  "preferences": {
    "timezone": "America/New_York",
    "meetingPreferences": {
      "preferAdjacentToMeetings": true,
      "preferredMeetingDuration": 30,
      "avoidDeepWorkBlocks": true,
      "deepWorkBlockUsage": "end",
      "neverAvailablePatterns": ["kids"],
      "preferredDays": {
        "Wednesday-PM": 100,
        "Thursday": 100,
        "Monday-PM": 70,
        "Tuesday": 40,
        "Friday": 40
      },
      "afternoonStartHour": 12,
      "notes": "SCHEDULING PRIORITY: 1. BEST (100): Wed PM & Thu. 2. GOOD (70): Mon PM. 3. LAST RESORT (40): Tue & Fri. Prefer 30-min slots adjacent to meetings. Avoid deep work blocks. Never schedule over 'kids' blocks."
    },
    "flexibleBlockPatterns": ["flexible", "optional", "buffer", "hold"],
    "deepWorkPatterns": ["deep work", "focus time", "writing", "research", "reading"]
  }
}
```

**Meeting Preference Options:**
- `preferAdjacentToMeetings`: Suggest times next to existing meetings
- `preferredMeetingDuration`: Default meeting length in minutes
- `avoidDeepWorkBlocks`: Try not to suggest deep work time
- `deepWorkBlockUsage`: `"end"` = use end of block if needed, `"start"` = use start, `"avoid"` = never use
- `neverAvailablePatterns`: Keywords for completely unavailable blocks
- **`preferredDays`**: **Day-of-week ranking system (0-100 scale)**
  - **Higher scores = stronger preference** (100 = most preferred, 40 = least preferred, 0 = avoid)
  - Use full day names: `"Monday"`, `"Tuesday"`, `"Wednesday"`, `"Thursday"`, `"Friday"`
  - For **afternoon-only** preferences: `"Monday-PM"`, `"Wednesday-PM"`, etc.
  - **Example ranking:**
    - `"Wednesday-PM": 100` and `"Thursday": 100` = BEST days (strongly prefer)
    - `"Monday-PM": 70` = GOOD day (acceptable)
    - `"Tuesday": 40` and `"Friday": 40` = LAST RESORT (avoid if better options exist)
  - The MCP will **prioritize suggesting times on higher-scored days**
- `afternoonStartHour`: Hour when afternoon starts (default: 12 = noon)
- `notes`: Human-readable description explaining your preferences for Claude to understand

### 6. Configure Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

If you have other MCP servers (like spark-mcp), add the `"calendar"` section to your existing `"mcpServers"` object.

### 7. Test the Installation (Optional but Recommended)

Before configuring Claude Desktop, verify everything works:

```bash
python test_calendar.py
```

You should see:
- ✓ Credentials loaded successfully
- ✓ Calendar client initialized
- ✓ Found X events
- ✓ All tests completed

### 8. Restart Claude Desktop

Restart Claude Desktop to load the new MCP server.

## Usage

Once configured, ask Claude questions like:

**Meeting Queries:**
- "What meetings do I have today?"
- "Show me my calendar for the next week"
- "What do I need to be prepared for?"
- "Tell me about my 2pm meeting"

**Relationship Tracking:**
- "When was the last time I met with john@example.com?"
- "Show me all my meetings with the engineering team"
- "Who do I meet with most often?"

**Time Analysis:**
- "How many hours of meetings did I have this week?"
- "Analyze my calendar blocks for today"
- "Summarize my meetings from the past week"
- "Am I free tomorrow at 2pm?"

**Finding Meeting Times (with preferences):**
- "Find me times for a 30-minute meeting this week"
- "When should I schedule a call with John?"
- "What are my best meeting times next week?"
- "Suggest times for a 1-hour meeting"

When finding meeting times, the MCP will:
- **Prioritize your preferred days** (e.g., Wed PM & Thu over Tue & Fri)
- **Look for slots adjacent to existing meetings** (if enabled)
- **Avoid deep work blocks** (but use them as last resort if needed)
- **Never suggest times with "kids" or other never-available patterns**

**Managing Calendar Events:**
- "Create a meeting titled 'Project Review' tomorrow at 2pm for 1 hour"
- "Schedule a 30-minute call with john@example.com on Thursday at 3pm"
- "Add a meeting on Friday at 10am with sarah@example.com and bob@example.com"
- "Delete the meeting about quarterly planning"
- "Accept the invitation for tomorrow's standup"
- "Decline the Friday afternoon meeting"
- "Mark the project kickoff as tentative"

**Integration with spark-mcp:**
If you have both calendar-mcp and spark-mcp installed:
- "Show me the transcript from my meeting with X last Tuesday"
- "Summarize all my meetings and their transcripts from last week"
- "What were the action items from recent meetings?"

## Available Tools

### 1. `list_all_calendars`
List all calendars you have access to (primary, work, shared, etc.)

### 2. `list_calendar_events`
List calendar events **from ALL your calendars** with filtering by time range, search query, etc. Each event shows which calendar it's from.

### 3. `get_upcoming_meetings`
Get upcoming meetings for preparation, includes time until meeting and attendee info.

### 4. `find_meetings_with_person`
Find when you last met with someone (by email or name).

### 5. `get_meeting_by_id`
Get full details of a specific calendar event.

### 6. `analyze_time_blocks`
Analyze calendar blocks and distinguish between deep work and flexible time.

### 7. `summarize_meetings`
Get summaries of meetings grouped by day, week, or person.

### 8. `check_availability`
Check if you're available at a proposed time.

### 9. `find_meeting_times`
Find best available meeting times based on your preferences (day ranking, adjacent to meetings, avoid deep work).

### 10. `create_event`
Create a new calendar event with optional attendees and automatic invitation emails.

### 11. `delete_event`
Delete a calendar event with optional cancellation notifications to attendees.

### 12. `respond_to_event`
Accept, decline, or tentatively accept a calendar invitation.

## Block Type Detection

The server can distinguish between different types of calendar blocks:

- **Deep Work**: Focus time, writing, research (hard blocks)
- **Flexible**: Buffer time, optional blocks (can accommodate last-minute requests)
- **Meetings**: Scheduled meetings
- **Out of Office**: Hard blocks

Configure patterns in `~/.config/calendar-mcp/config.json`:

```json
{
  "preferences": {
    "flexibleBlockPatterns": ["flexible", "optional", "buffer"],
    "deepWorkPatterns": ["deep work", "focus time", "writing", "research"]
  }
}
```

## Integration with spark-mcp

If you have spark-mcp installed, the calendar MCP can cross-reference calendar events with meeting transcripts to provide unified context.

## Troubleshooting

### Authentication errors

1. Check credentials file exists:
   ```bash
   ls ~/.config/calendar-mcp/credentials.json
   ```

2. Re-run authentication:
   ```bash
   python -m calendar_mcp.auth
   ```

3. Verify API is enabled in [Google Cloud Console](https://console.cloud.google.com)

### No events returned

1. Check date range in your query
2. Verify you have events in your Google Calendar
3. Check token has proper scopes

### Server not connecting

1. Check Claude Desktop logs:
   ```bash
   tail -f ~/Library/Logs/Claude/mcp-server-calendar.log
   ```

2. Verify config syntax in `claude_desktop_config.json`

3. Make sure Python path is correct in config

4. Try running server directly to check for errors:
   ```bash
   cd /Users/feamster/src/calendar-mcp
   python -m calendar_mcp.server
   # Should start without errors (Ctrl+C to exit)
   ```

### "Google hasn't verified this app" warning

This is **normal** for personal projects. Your app is safe because you created it.

**Solution:**
- Click "Advanced" on the warning page
- Click "Go to Calendar MCP (unsafe)"
- Grant the permissions

### API quota exceeded

Google Calendar API has rate limits (1M queries/day). If you hit limits:
- Wait a few minutes
- Most queries use only 1-2 quota units
- Normal usage won't hit limits

## Testing & Development

### Test Installation

```bash
# Test authentication status
python -m calendar_mcp.auth --test

# Run full test suite
python test_calendar.py
```

### Development Mode

```bash
# Install in development mode
pip install -e .

# Make changes to calendar_mcp/*.py files
# Restart Claude Desktop to reload changes
```

### Project Structure

```
calendar-mcp/
├── calendar_mcp/
│   ├── __init__.py
│   ├── auth.py              # OAuth2 authentication
│   ├── calendar_client.py   # Google Calendar API wrapper
│   └── server.py            # MCP server implementation
├── test_calendar.py         # Test script
├── setup.py                 # Package installer
├── README.md               # This file
├── SETUP.md                # Detailed setup instructions
├── QUICKSTART.md           # Quick start guide
└── SPEC.md                 # Technical specification

~/.config/calendar-mcp/
└── credentials.json         # OAuth tokens (auto-created)
```

## Privacy & Security

- **Full calendar access**: Requests `calendar` scope for read and write operations
- **Local credentials**: Tokens stored locally in `~/.config/calendar-mcp/`
- **No data caching**: Doesn't cache calendar data
- **Secure token handling**: Automatic refresh token management
- **Notification control**: You can disable email notifications when creating/deleting events

## Documentation

- **[README.md](README.md)** (this file) - Overview and usage
- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 10 minutes
- **[SETUP.md](SETUP.md)** - Detailed setup instructions with troubleshooting
- **[SPEC.md](SPEC.md)** - Complete technical specification

## Future Enhancements

See [SPEC.md](SPEC.md) for detailed roadmap, including:
- Action item extraction from meeting descriptions
- Update existing events (modify time, location, description)
- Smart scheduling suggestions
- Advanced meeting analytics
- Recurring meeting tracking
- Cross-referencing with spark-mcp transcripts

## License

MIT
