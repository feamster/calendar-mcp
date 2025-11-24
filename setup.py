#!/usr/bin/env python3
"""Setup script for calendar-mcp package."""

from setuptools import setup, find_packages

setup(
    name="calendar-mcp",
    version="0.1.0",
    description="MCP server for Google Calendar access and analysis",
    author="Nick Feamster",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "google-auth-oauthlib>=1.0.0",
        "google-auth-httplib2>=0.2.0",
        "google-api-python-client>=2.100.0",
        "mcp>=0.9.0",
    ],
    entry_points={
        "console_scripts": [
            "calendar-mcp=calendar_mcp.server:main",
            "calendar-mcp-auth=calendar_mcp.auth:main",
        ],
    },
)
