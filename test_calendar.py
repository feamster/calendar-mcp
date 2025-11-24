#!/usr/bin/env python3
"""Test script for calendar MCP client."""

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from calendar_mcp.auth import get_credentials
from calendar_mcp.calendar_client import CalendarClient


def main():
    """Test calendar client functionality."""
    print("=" * 60)
    print("Google Calendar MCP - Test Script")
    print("=" * 60)
    print()

    # Test 1: Check credentials
    print("1. Checking credentials...")
    creds = get_credentials()

    if not creds:
        print("✗ No credentials found")
        print()
        print("Please run: python -m calendar_mcp.auth")
        print()
        sys.exit(1)

    print("✓ Credentials loaded successfully")
    print(f"  Scopes: {', '.join(creds.scopes)}")
    print(f"  Token valid: {not creds.expired}")
    print()

    # Test 2: Initialize client
    print("2. Initializing Calendar API client...")
    try:
        calendar = CalendarClient()
        print("✓ Calendar client initialized")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        print()
        sys.exit(1)

    # Test 3: List upcoming events
    print("3. Testing: List upcoming events (next 7 days)...")
    try:
        now = datetime.now(ZoneInfo("UTC"))
        time_max = now + timedelta(days=7)

        result = calendar.list_events(
            time_min=now,
            time_max=time_max,
            max_results=10
        )

        if 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            events = result['events']
            print(f"✓ Found {len(events)} events")

            if events:
                print()
                print("  Sample events:")
                for event in events[:3]:
                    start = event.get('start', 'Unknown time')
                    summary = event.get('summary', 'No title')
                    print(f"    - {start}: {summary}")
            else:
                print("  (No upcoming events found)")

        print()

    except Exception as e:
        print(f"✗ Error listing events: {e}")
        print()

    # Test 4: Get upcoming meetings
    print("4. Testing: Get upcoming meetings (next 24 hours)...")
    try:
        result = calendar.get_upcoming_meetings(hours=24)

        if 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            meetings = result['meetings']
            summary = result['summary']
            print(f"✓ {summary}")

            if meetings:
                print()
                print("  Next meetings:")
                for meeting in meetings[:3]:
                    time_until = meeting.get('timeUntil', 'Unknown')
                    summary_text = meeting.get('summary', 'No title')
                    attendees = meeting.get('attendees', [])
                    print(f"    - {time_until}: {summary_text}")
                    if attendees:
                        print(f"      Attendees: {len(attendees)} people")

        print()

    except Exception as e:
        print(f"✗ Error getting upcoming meetings: {e}")
        print()

    # Test 5: Analyze time blocks
    print("5. Testing: Analyze time blocks for today...")
    try:
        result = calendar.analyze_time_blocks()

        if 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            date = result.get('date')
            total_blocked = result.get('totalBlocked', 0)
            blocks = result.get('blocks', [])

            print(f"✓ Date: {date}")
            print(f"  Total blocked: {total_blocked} minutes ({total_blocked/60:.1f} hours)")
            print(f"  Number of blocks: {len(blocks)}")

            if blocks:
                print()
                print("  Block types:")
                block_types = {}
                for block in blocks:
                    block_type = block.get('type', 'unknown')
                    block_types[block_type] = block_types.get(block_type, 0) + 1

                for block_type, count in block_types.items():
                    print(f"    - {block_type}: {count}")

        print()

    except Exception as e:
        print(f"✗ Error analyzing blocks: {e}")
        print()

    # Test 6: Summarize past week
    print("6. Testing: Summarize meetings (past 7 days)...")
    try:
        now = datetime.now(ZoneInfo("UTC"))
        time_min = now - timedelta(days=7)

        result = calendar.summarize_meetings(
            time_min=time_min,
            time_max=now
        )

        if 'error' in result:
            print(f"✗ Error: {result['error']}")
        else:
            summary = result.get('summary', '')
            total_meetings = result.get('totalMeetings', 0)
            total_hours = result.get('totalHours', 0)
            top_attendees = result.get('topAttendees', [])

            print(f"✓ {summary}")

            if top_attendees:
                print()
                print("  Most frequent meeting partners:")
                for attendee in top_attendees[:5]:
                    email = attendee.get('email', 'Unknown')
                    count = attendee.get('count', 0)
                    print(f"    - {email}: {count} meetings")

        print()

    except Exception as e:
        print(f"✗ Error summarizing meetings: {e}")
        print()

    # Summary
    print("=" * 60)
    print("✓ All tests completed successfully!")
    print()
    print("Your calendar MCP is ready to use.")
    print()
    print("Next steps:")
    print("1. Add calendar-mcp to Claude Desktop config")
    print("2. Restart Claude Desktop")
    print("3. Ask Claude about your calendar!")
    print()


if __name__ == '__main__':
    main()
