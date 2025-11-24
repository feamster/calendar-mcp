#!/usr/bin/env python3
"""OAuth2 authentication for Google Calendar API."""

import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Calendar scopes - full access for read/write/respond to events
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Config directory
CONFIG_DIR = Path.home() / ".config" / "calendar-mcp"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
CLIENT_SECRET_FILE = Path("client_secret.json")


def get_config_dir() -> Path:
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_credentials() -> Optional[Credentials]:
    """Load credentials from stored token."""
    if not CREDENTIALS_FILE.exists():
        return None

    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            creds_data = json.load(f)

        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        return creds
    except Exception:
        return None


def save_credentials(creds: Credentials):
    """Save credentials to config directory."""
    get_config_dir()

    creds_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(creds_data, f, indent=2)


def get_credentials() -> Optional[Credentials]:
    """Get valid credentials, refreshing if necessary."""
    creds = load_credentials()

    if not creds:
        return None

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
        except Exception:
            # Token invalid, need to re-authenticate
            return None

    return creds


def authenticate(client_secret_path: Optional[str] = None) -> Credentials:
    """Run OAuth2 flow to get credentials.

    Args:
        client_secret_path: Path to client_secret.json file

    Returns:
        Credentials object

    Raises:
        FileNotFoundError: If client_secret.json not found
    """
    # Determine client secret file path
    if client_secret_path:
        secret_file = Path(client_secret_path)
    else:
        secret_file = CLIENT_SECRET_FILE

    if not secret_file.exists():
        raise FileNotFoundError(
            f"Client secret file not found: {secret_file}\n"
            f"Please download OAuth2 credentials from Google Cloud Console.\n"
            f"See README.md for setup instructions."
        )

    # Run OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(
        str(secret_file),
        SCOPES,
        redirect_uri='http://localhost:8080/'
    )

    # This will open a browser window
    creds = flow.run_local_server(
        port=8080,
        success_message='Authentication successful! You can close this window.',
        open_browser=True
    )

    # Save credentials
    save_credentials(creds)

    return creds


def main():
    """Main entry point for authentication setup."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Authenticate with Google Calendar API'
    )
    parser.add_argument(
        '--credentials',
        type=str,
        help='Path to client_secret.json file'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test existing credentials'
    )

    args = parser.parse_args()

    if args.test:
        # Test existing credentials
        print("Testing existing credentials...")
        creds = get_credentials()

        if creds:
            print("✓ Credentials loaded successfully")
            print(f"✓ Scopes: {', '.join(creds.scopes)}")
            print(f"✓ Token valid: {not creds.expired}")

            if creds.expired:
                print("! Token expired, attempting refresh...")
                try:
                    creds.refresh(Request())
                    save_credentials(creds)
                    print("✓ Token refreshed successfully")
                except Exception as e:
                    print(f"✗ Token refresh failed: {e}")
                    print("! Please re-authenticate")
        else:
            print("✗ No credentials found")
            print("! Please run: python -m calendar_mcp.auth")

    else:
        # Run authentication flow
        print("Google Calendar MCP - Authentication Setup")
        print("=" * 50)
        print()
        print("This will open your browser to authenticate with Google.")
        print("Please grant access to read and write your calendar events.")
        print()
        input("Press Enter to continue...")

        try:
            creds = authenticate(args.credentials)
            print()
            print("=" * 50)
            print("✓ Authentication successful!")
            print(f"✓ Credentials saved to: {CREDENTIALS_FILE}")
            print()
            print("Next steps:")
            print("1. Add calendar-mcp to Claude Desktop config")
            print("2. Restart Claude Desktop")
            print("3. Ask Claude about your calendar!")
            print()

        except FileNotFoundError as e:
            print()
            print("=" * 50)
            print("✗ Setup Error")
            print()
            print(str(e))
            print()
            exit(1)

        except Exception as e:
            print()
            print("=" * 50)
            print("✗ Authentication failed")
            print()
            print(f"Error: {e}")
            print()
            exit(1)


if __name__ == '__main__':
    main()
