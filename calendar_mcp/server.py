#!/usr/bin/env python3
"""Google Calendar MCP Server."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from .calendar_client import CalendarClient


# Initialize calendar client (errors will be logged by MCP framework)
try:
    calendar = CalendarClient()
except Exception:
    # Let MCP framework handle the error
    raise


# Create server instance
server = Server("calendar-mcp-server")


# Define tools - minimal descriptions following spark-mcp best practices
TOOLS: list[Tool] = [
    Tool(
        name="list_all_calendars",
        description="List all calendars",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="list_calendar_events",
        description="List calendar events from all calendars",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Days ahead to look (default: 7)", "default": 7},
                "maxResults": {"type": "number", "description": "Max results", "default": 20},
                "query": {"type": "string", "description": "Search query"}
            }
        }
    ),
    Tool(
        name="get_upcoming_meetings",
        description="Get upcoming meetings",
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {"type": "number", "description": "Hours ahead (default: 24)", "default": 24}
            }
        }
    ),
    Tool(
        name="find_meetings_with_person",
        description="Find meetings with someone",
        inputSchema={
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Person's email"},
                "name": {"type": "string", "description": "Person's name"},
                "maxResults": {"type": "number", "description": "Max results", "default": 10},
                "daysBack": {"type": "number", "description": "Days to look back", "default": 90}
            }
        }
    ),
    Tool(
        name="get_meeting_by_id",
        description="Get meeting details by ID",
        inputSchema={
            "type": "object",
            "properties": {
                "eventId": {"type": "string", "description": "Calendar event ID"}
            },
            "required": ["eventId"]
        }
    ),
    Tool(
        name="analyze_time_blocks",
        description="Analyze calendar blocks",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date (YYYY-MM-DD, default: today)"}
            }
        }
    ),
    Tool(
        name="summarize_meetings",
        description="Summarize meetings for period",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Days to look back", "default": 7}
            }
        }
    ),
    Tool(
        name="check_availability",
        description="Check availability at time",
        inputSchema={
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start time (ISO format)"},
                "end": {"type": "string", "description": "End time (ISO format)"},
                "respectFlexible": {"type": "boolean", "description": "Treat flexible as busy", "default": False}
            },
            "required": ["start", "end"]
        }
    ),
    Tool(
        name="find_meeting_times",
        description="Find best meeting times using user preferences from config (day-of-week ranking, adjacent to meetings, avoid deep work, never-available patterns)",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Days ahead to search (default: 7)", "default": 7},
                "duration": {"type": "number", "description": "Meeting duration in minutes (default: 30)", "default": 30},
                "maxSuggestions": {"type": "number", "description": "Max suggestions (default: 5)", "default": 5}
            }
        }
    ),
    Tool(
        name="create_event",
        description="Create a new calendar event with optional attendees/invitations",
        inputSchema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "start": {"type": "string", "description": "Start time (ISO format)"},
                "end": {"type": "string", "description": "End time (ISO format)"},
                "description": {"type": "string", "description": "Event description"},
                "location": {"type": "string", "description": "Event location"},
                "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses"},
                "sendNotifications": {"type": "boolean", "description": "Send email invitations (default: true)", "default": True},
                "calendarId": {"type": "string", "description": "Calendar ID (default: primary)", "default": "primary"}
            },
            "required": ["summary", "start", "end"]
        }
    ),
    Tool(
        name="delete_event",
        description="Delete a calendar event",
        inputSchema={
            "type": "object",
            "properties": {
                "eventId": {"type": "string", "description": "Event ID to delete"},
                "calendarId": {"type": "string", "description": "Calendar ID (default: primary)", "default": "primary"},
                "sendNotifications": {"type": "boolean", "description": "Send cancellation emails (default: true)", "default": True}
            },
            "required": ["eventId"]
        }
    ),
    Tool(
        name="respond_to_event",
        description="Accept, decline, or tentatively accept a calendar invitation",
        inputSchema={
            "type": "object",
            "properties": {
                "eventId": {"type": "string", "description": "Event ID to respond to"},
                "response": {"type": "string", "description": "Response: 'accepted', 'declined', or 'tentative'", "enum": ["accepted", "declined", "tentative"]},
                "calendarId": {"type": "string", "description": "Calendar ID (default: primary)", "default": "primary"},
                "comment": {"type": "string", "description": "Optional comment with response"}
            },
            "required": ["eventId", "response"]
        }
    )
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_all_calendars":
            calendars = calendar.get_all_calendars()

            result = {
                'calendars': [
                    {
                        'id': cal.get('id'),
                        'name': cal.get('summary'),
                        'description': cal.get('description', ''),
                        'primary': cal.get('primary', False),
                        'accessRole': cal.get('accessRole'),
                        'backgroundColor': cal.get('backgroundColor'),
                        'foregroundColor': cal.get('foregroundColor')
                    }
                    for cal in calendars
                ],
                'total': len(calendars)
            }

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "list_calendar_events":
            days = arguments.get('days', 7)
            max_results = arguments.get('maxResults', 20)
            query = arguments.get('query')

            now = datetime.now(ZoneInfo("UTC"))
            time_max = now + timedelta(days=days)

            result = calendar.list_events(
                time_min=now,
                time_max=time_max,
                max_results=max_results,
                query=query
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_upcoming_meetings":
            hours = arguments.get('hours', 24)

            result = calendar.get_upcoming_meetings(hours=hours)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_meetings_with_person":
            email = arguments.get('email')
            name_arg = arguments.get('name')
            max_results = arguments.get('maxResults', 10)
            days_back = arguments.get('daysBack', 90)

            result = calendar.find_meetings_with_person(
                email=email,
                name=name_arg,
                max_results=max_results,
                days_back=days_back
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_meeting_by_id":
            event_id = arguments.get('eventId')

            if not event_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({'error': 'eventId is required'})
                )]

            result = calendar.get_event_by_id(event_id)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "analyze_time_blocks":
            date_str = arguments.get('date')

            if date_str:
                try:
                    date = datetime.fromisoformat(date_str).replace(
                        tzinfo=ZoneInfo("UTC")
                    )
                except ValueError:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            'error': 'Invalid date format. Use YYYY-MM-DD'
                        })
                    )]
            else:
                date = datetime.now(ZoneInfo("UTC"))

            result = calendar.analyze_time_blocks(date=date)

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "summarize_meetings":
            days = arguments.get('days', 7)

            now = datetime.now(ZoneInfo("UTC"))
            time_min = now - timedelta(days=days)

            result = calendar.summarize_meetings(
                time_min=time_min,
                time_max=now
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "check_availability":
            start_str = arguments.get('start')
            end_str = arguments.get('end')
            respect_flexible = arguments.get('respectFlexible', False)

            if not start_str or not end_str:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        'error': 'start and end times are required'
                    })
                )]

            try:
                start = datetime.fromisoformat(start_str)
                end = datetime.fromisoformat(end_str)
            except ValueError:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        'error': 'Invalid datetime format. Use ISO format'
                    })
                )]

            result = calendar.check_availability(
                start=start,
                end=end,
                respect_flexible=respect_flexible
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_meeting_times":
            days = arguments.get('days', 7)
            duration = arguments.get('duration', 30)
            max_suggestions = arguments.get('maxSuggestions', 5)

            now = datetime.now(ZoneInfo("UTC"))
            end_date = now + timedelta(days=days)

            result = calendar.find_meeting_times(
                start_date=now,
                end_date=end_date,
                duration_minutes=duration,
                max_suggestions=max_suggestions
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "create_event":
            summary = arguments.get('summary')
            start_str = arguments.get('start')
            end_str = arguments.get('end')
            description = arguments.get('description')
            location = arguments.get('location')
            attendees = arguments.get('attendees')
            send_notifications = arguments.get('sendNotifications', True)
            calendar_id = arguments.get('calendarId', 'primary')

            if not summary or not start_str or not end_str:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        'error': 'summary, start, and end are required'
                    })
                )]

            try:
                start = datetime.fromisoformat(start_str)
                end = datetime.fromisoformat(end_str)
            except ValueError:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        'error': 'Invalid datetime format. Use ISO format'
                    })
                )]

            result = calendar.create_event(
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                attendees=attendees,
                send_notifications=send_notifications,
                calendar_id=calendar_id
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "delete_event":
            event_id = arguments.get('eventId')
            calendar_id = arguments.get('calendarId', 'primary')
            send_notifications = arguments.get('sendNotifications', True)

            if not event_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({'error': 'eventId is required'})
                )]

            result = calendar.delete_event(
                event_id=event_id,
                calendar_id=calendar_id,
                send_notifications=send_notifications
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "respond_to_event":
            event_id = arguments.get('eventId')
            response = arguments.get('response')
            calendar_id = arguments.get('calendarId', 'primary')
            comment = arguments.get('comment')

            if not event_id or not response:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        'error': 'eventId and response are required'
                    })
                )]

            result = calendar.respond_to_event(
                event_id=event_id,
                response=response,
                calendar_id=calendar_id,
                comment=comment
            )

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({'error': f'Unknown tool: {name}'})
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({'error': str(e)})
        )]


async def main():
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == '__main__':
    asyncio.run(main())
