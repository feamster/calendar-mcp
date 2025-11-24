# Google Calendar MCP - Setup Guide

## Step-by-Step Installation

### Prerequisites

- Python 3.10 or higher
- Google account with Calendar access
- Claude Desktop app (for MCP integration)

---

## Step 1: Create Google Cloud Project

**1. Go to Google Cloud Console:**

- Visit [Google Cloud Console](https://console.cloud.google.com)
- Sign in with your Google account

**2. Create a new project:**

- Click "Select a project" at the top
- Click "New Project"
- Project name: `calendar-mcp` (or any name you prefer)
- Click "Create"
- Wait for the project to be created (a few seconds)

**3. Enable Google Calendar API:**

- Make sure your new project is selected
- Go to "APIs & Services" → "Library" (left sidebar)
- Search for "Google Calendar API"
- Click on "Google Calendar API"
- Click "Enable"
- Wait for API to be enabled ✓

---

## Step 2: Create OAuth2 Credentials

**1. Configure OAuth consent screen:**

- Go to "APIs & Services" → "OAuth consent screen" (left sidebar)
- User Type: Select "External" (unless you have a Google Workspace account)
- Click "Create"

**2. Fill in app information:**

- App name: `Calendar MCP`
- User support email: Your email
- Developer contact: Your email
- Click "Save and Continue"

**3. Add scopes:**

- Click "Add or Remove Scopes"
- Search for "Google Calendar API"
- Check the box for `.../auth/calendar.readonly`
- Click "Update"
- Click "Save and Continue"

**4. Add test users:**

- Click "Add Users"
- Add your Google email address
- Click "Add"
- Click "Save and Continue"
- Click "Back to Dashboard"

**5. Create OAuth client:**

- Go to "APIs & Services" → "Credentials" (left sidebar)
- Click "Create Credentials" at the top
- Select "OAuth client ID"
- Application type: **Desktop app**
- Name: `calendar-mcp-client`
- Click "Create"

**6. Download credentials:**

- A popup will appear with your client ID and secret
- Click "Download JSON"
- Save the file as `client_secret.json` in `/Users/feamster/src/calendar-mcp/`

---

## Step 3: Install the Package

```bash
cd /Users/feamster/src/calendar-mcp
pip install -e .
```

This will install:

- `google-auth-oauthlib` - OAuth2 authentication
- `google-auth-httplib2` - HTTP transport
- `google-api-python-client` - Calendar API client
- `mcp` - Model Context Protocol SDK

---

## Step 4: Authenticate with Google

Run the authentication setup:

```bash
python -m calendar_mcp.auth
```

**What will happen:**

1. Your default web browser will open
2. You'll see a Google sign-in page
3. Sign in with your Google account
4. Google will show a warning: "Google hasn't verified this app"
    - Click "Advanced"
    - Click "Go to Calendar MCP (unsafe)"
    - This is safe - it's your own app!
5. Review the permissions:
    - "View your calendars" - Click "Continue"
6. You'll see "Authentication successful! You can close this window."
7. Close the browser tab
8. Your terminal will show: "✓ Authentication successful!"

**Where credentials are stored:**

- `~/.config/calendar-mcp/credentials.json`
- This file contains your refresh token
- Keep it secure - don't share it
- It will be automatically refreshed when needed

---

## Step 5: Configure Claude Desktop

**1. Open Claude Desktop config file:**

```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**2. Add calendar-mcp to the config:**

If this is your first MCP server:

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

If you already have spark-mcp or other servers:

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

**Important:** Make sure the JSON is valid (no trailing commas, proper brackets)

**3. Save the file**

---

## Step 6: Restart Claude Desktop

1. Quit Claude Desktop completely (Cmd+Q)
2. Reopen Claude Desktop
3. Wait a few seconds for MCP servers to initialize

---

## Step 7: Test It!

In Claude Desktop, try these queries:

- "What meetings do I have today?"
- "Show me my calendar for the next week"
- "When was the last time I met with [someone's email]?"
- "Summarize my meetings from the past week"

If Claude can answer these questions, you're all set! 🎉

---

## Troubleshooting

### Authentication Failed

**Error:** `No valid credentials found`

**Solution:**

```bash
# Re-run authentication
python -m calendar_mcp.auth

# Test credentials
python -m calendar_mcp.auth --test
```

---

### Browser Doesn't Open

**Error:** OAuth flow doesn't start

**Solution:**

1. Check if you have `client_secret.json` in the project directory
2. Manually specify the path:
    ```bash
    python -m calendar_mcp.auth --credentials /path/to/client_secret.json
    ```

---

### "Google hasn't verified this app"

**This is normal!** Since this is your personal project, Google shows this warning.

**Solution:**

- Click "Advanced"
- Click "Go to Calendar MCP (unsafe)"
- This is safe because it's your own app running locally

---

### Claude Desktop Can't Connect

**Error:** Tools don't appear in Claude

**Solution:**

1. Check Claude Desktop logs:
    ```bash
    tail -f ~/Library/Logs/Claude/mcp-server-calendar.log
    ```

2. Verify config syntax:
    ```bash
    cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
    ```

3. Check Python path:
    ```bash
    which python
    # Make sure this matches the 'command' in your config
    ```

4. Try running server directly:
    ```bash
    cd /Users/feamster/src/calendar-mcp
    python -m calendar_mcp.server
    # Should start without errors (Ctrl+C to exit)
    ```

---

### API Not Enabled

**Error:** `Calendar API has not been used in project`

**Solution:**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select your project
3. Go to "APIs & Services" → "Library"
4. Search for [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
5. Click "Enable"

---

### Rate Limit Exceeded

**Error:** `Quota exceeded for quota metric`

**Solution:**

- Google Calendar API has limits
- Default: 1,000,000 queries per day
- If you hit this, wait a few minutes
- Most queries use 1-2 quota units

---

### Credentials Expired

**Error:** Token refresh failed

**Solution:**

```bash
# Delete old credentials
rm ~/.config/calendar-mcp/credentials.json

# Re-authenticate
python -m calendar_mcp.auth
```

---

## Testing Without Claude Desktop

You can test the calendar client directly:

```bash
# Test authentication
python -m calendar_mcp.auth --test

# Test calendar access
python test_calendar.py
```

---

## Security Notes

- ✅ **Read-only access**: Only requests `calendar.readonly` scope
- ✅ **Local storage**: Credentials stored in `~/.config/calendar-mcp/`
- ✅ **Automatic refresh**: Tokens refreshed automatically when expired
- ⚠️ **Protect credentials**: Don't commit `client_secret.json` or credentials
- ⚠️ **Test users**: In development mode, only test users can access the app

---

## Next Steps

Once setup is complete:

1. **Try basic queries** to verify it works
2. **Explore all tools** - see [README.md](README.md) for full list
3. **Configure block patterns** - customize in `~/.config/calendar-mcp/config.json`
4. **Use with spark-mcp** - cross-reference meetings with transcripts

---

## Uninstalling

To remove the calendar MCP:

1. Remove from Claude Desktop config
2. Delete credentials:
    ```bash
    rm -rf ~/.config/calendar-mcp
    ```
3. Uninstall package:
    ```bash
    pip uninstall calendar-mcp
    ```

---

## Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review the logs: `~/Library/Logs/Claude/mcp-server-calendar.log`
3. Test authentication: `python -m calendar_mcp.auth --test`
4. Check API status: [Google Cloud Status](https://status.cloud.google.com)

---

## Advanced Configuration

### Custom Timezone

Create `~/.config/calendar-mcp/config.json`:

```json
{
    "preferences": {
        "timezone": "America/New_York"
    }
}
```

### Custom Block Patterns

Customize how blocks are classified:

```json
{
    "preferences": {
        "flexibleBlockPatterns": ["flexible", "optional", "buffer", "hold"],
        "deepWorkPatterns": ["deep work", "focus", "writing", "research", "reading"]
    }
}
```

### Multiple Calendars

✅ **The server automatically reads ALL your calendars!**

This includes:
- Your primary Google Calendar
- Work calendars
- Shared calendars
- Any calendar you have access to

Each event will show which calendar it's from (calendarName field).
