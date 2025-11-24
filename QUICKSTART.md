# Quick Start Guide

Get your Google Calendar MCP running in 10 minutes!

## Prerequisites

- Python 3.10+
- Google account
- Claude Desktop

## Installation Steps

### 1. Install Package

```bash
cd /Users/feamster/src/calendar-mcp
pip install -e .
```

### 2. Set Up Google Cloud Project

**Go to:** [Google Cloud Console](https://console.cloud.google.com)

1. Create new project: `calendar-mcp`
2. Enable [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) (APIs & Services → Library)
3. Configure OAuth consent screen (External, add your email as test user)
4. Create OAuth client (Desktop app)
5. Download `client_secret.json` to this directory

**Detailed steps:** See [SETUP.md](SETUP.md)

### 3. Authenticate

```bash
python -m calendar_mcp.auth
```

- Browser will open
- Sign in with Google
- Click "Advanced" → "Go to Calendar MCP (unsafe)"
- Grant calendar read permission
- Done! Credentials saved to `~/.config/calendar-mcp/`

### 4. Test It

```bash
python test_calendar.py
```

Should show:
- ✓ Credentials loaded
- ✓ Calendar client initialized
- ✓ Found X events
- ✓ All tests completed

### 5. Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

**If you have spark-mcp too:**

```json
{
  "mcpServers": {
    "spark": {
      "command": "python",
      "args": ["-m", "spark_mcp.server"],
      "cwd": "/Users/feamster/src/spark-mcp"
    },
    "calendar": {
      "command": "python",
      "args": ["-m", "calendar_mcp.server"],
      "cwd": "/Users/feamster/src/calendar-mcp"
    }
  }
}
```

### 6. Restart Claude Desktop

Quit and reopen Claude Desktop (Cmd+Q, then reopen)

### 7. Try It!

Ask Claude:
- "What meetings do I have today?"
- "When was the last time I met with john@example.com?"
- "Summarize my meetings from the past week"
- "What do I need to be prepared for?"

## Troubleshooting

### "No credentials found"

```bash
python -m calendar_mcp.auth
```

### "API not enabled"

Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Library → Enable [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)

### Claude can't connect

Check logs:
```bash
tail -f ~/Library/Logs/Claude/mcp-server-calendar.log
```

### Need help?

See [SETUP.md](SETUP.md) for detailed troubleshooting

## What You Can Do

### Query Your Calendar

- List events: "Show my calendar for next week"
- Find meetings: "When did I last meet with X?"
- Check availability: "Am I free tomorrow at 2pm?"

### Analyze Your Time

- Summarize: "How many hours of meetings this week?"
- Block analysis: "What's my calendar like today?"
- Patterns: "Who do I meet with most often?"

### Prepare for Meetings

- Upcoming: "What meetings do I have today?"
- Details: "Tell me about my 2pm meeting"
- Action items: "Find follow-ups from meetings this week"

### Integration with spark-mcp

If you have both installed:
- "Show me the transcript from my meeting with X last Tuesday"
- "Summarize all my meetings and their transcripts from last week"
- "Find action items from meetings over the past two weeks"

## Files Created

```
calendar-mcp/
├── calendar_mcp/          # Python package
│   ├── __init__.py
│   ├── auth.py           # OAuth2 authentication
│   ├── calendar_client.py # Google Calendar API wrapper
│   └── server.py         # MCP server
├── setup.py              # Package setup
├── test_calendar.py      # Test script
├── README.md            # Full documentation
├── SETUP.md             # Detailed setup guide
├── SPEC.md              # Technical specification
└── QUICKSTART.md        # This file

~/.config/calendar-mcp/
└── credentials.json      # Your OAuth tokens (auto-created)
```

## Security Notes

- ✅ Read-only access (calendar.readonly scope)
- ✅ Credentials stored locally
- ⚠️ Don't commit `client_secret.json`
- ⚠️ Keep `~/.config/calendar-mcp/credentials.json` secure

## Next Steps

1. ✅ Get it working with basic queries
2. Configure custom block patterns (see [SPEC.md](SPEC.md))
3. Use with spark-mcp for unified meeting context
4. Try all the available tools (see [README.md](README.md))

Enjoy your Calendar MCP! 📅
