#!/usr/bin/env python3
"""OAuth2 authentication for Google Calendar API with multi-account support."""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Calendar scopes - full access for read/write/respond to events
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Config directories - split between non-sensitive config and auth
MCP_CONFIG_DIR = Path.home() / ".mcp-config" / "calendar"
MCP_AUTH_DIR = Path.home() / ".mcp-auth" / "calendar"
TOKENS_DIR = MCP_AUTH_DIR / "tokens"
CREDENTIALS_FILE = MCP_AUTH_DIR / "credentials.json"  # Legacy single-account file
ACCOUNTS_CONFIG_FILE = MCP_CONFIG_DIR / "accounts.json"
CLIENT_SECRET_FILE = Path("client_secret.json")


def get_config_dir() -> Path:
    """Ensure config directory exists."""
    MCP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return MCP_CONFIG_DIR


def get_auth_dir() -> Path:
    """Ensure auth directory exists."""
    MCP_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    return MCP_AUTH_DIR


def get_tokens_dir() -> Path:
    """Ensure tokens directory exists."""
    get_auth_dir()  # Ensure parent exists
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return TOKENS_DIR


def get_token_file(account_email: str) -> Path:
    """Get the token file path for a specific account."""
    # Sanitize email for filename
    safe_email = account_email.replace('@', '_at_').replace('.', '_')
    return get_tokens_dir() / f"{safe_email}.json"


def load_accounts_config() -> Dict[str, Any]:
    """Load accounts configuration."""
    if not ACCOUNTS_CONFIG_FILE.exists():
        return {"accounts": [], "default": None}

    try:
        with open(ACCOUNTS_CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"accounts": [], "default": None}


def save_accounts_config(config: Dict[str, Any]):
    """Save accounts configuration."""
    get_config_dir()
    with open(ACCOUNTS_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_configured_accounts() -> List[str]:
    """Get list of configured account emails."""
    config = load_accounts_config()
    return config.get("accounts", [])


def get_default_account() -> Optional[str]:
    """Get the default account email."""
    config = load_accounts_config()
    return config.get("default")


def set_default_account(email: str) -> bool:
    """Set the default account.

    Args:
        email: Account email to set as default

    Returns:
        True if successful, False if account not found
    """
    config = load_accounts_config()
    if email not in config.get("accounts", []):
        return False
    config["default"] = email
    save_accounts_config(config)
    return True


def add_account_to_config(email: str, set_as_default: bool = False):
    """Add an account to the configuration."""
    config = load_accounts_config()
    if email not in config.get("accounts", []):
        config.setdefault("accounts", []).append(email)
    if set_as_default or not config.get("default"):
        config["default"] = email
    save_accounts_config(config)


def remove_account_from_config(email: str) -> bool:
    """Remove an account from configuration.

    Returns:
        True if account was removed, False if not found
    """
    config = load_accounts_config()
    if email not in config.get("accounts", []):
        return False

    config["accounts"].remove(email)

    # Update default if needed
    if config.get("default") == email:
        config["default"] = config["accounts"][0] if config["accounts"] else None

    save_accounts_config(config)

    # Remove token file
    token_file = get_token_file(email)
    if token_file.exists():
        token_file.unlink()

    return True


def load_credentials_for_account(email: str) -> Optional[Credentials]:
    """Load credentials for a specific account."""
    token_file = get_token_file(email)

    if not token_file.exists():
        return None

    try:
        with open(token_file, 'r') as f:
            creds_data = json.load(f)
        return Credentials.from_authorized_user_info(creds_data, SCOPES)
    except Exception:
        return None


def save_credentials_for_account(email: str, creds: Credentials):
    """Save credentials for a specific account."""
    get_tokens_dir()

    creds_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES,
        'account': email
    }

    token_file = get_token_file(email)
    with open(token_file, 'w') as f:
        json.dump(creds_data, f, indent=2)


def get_credentials_for_account(email: str) -> Optional[Credentials]:
    """Get valid credentials for a specific account, refreshing if necessary."""
    creds = load_credentials_for_account(email)

    if not creds:
        return None

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials_for_account(email, creds)
        except Exception:
            return None

    return creds


# Legacy single-account functions for backwards compatibility

def load_credentials() -> Optional[Credentials]:
    """Load credentials from stored token (legacy single-account)."""
    # First try the new multi-account system
    config = load_accounts_config()
    default = config.get("default")
    if default:
        creds = load_credentials_for_account(default)
        if creds:
            return creds

    # Fall back to legacy credentials file
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
    """Save credentials to auth directory (legacy single-account)."""
    get_auth_dir()

    creds_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES
    }

    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(creds_data, f, indent=2)


def get_credentials() -> Optional[Credentials]:
    """Get valid credentials, refreshing if necessary (legacy single-account)."""
    # First try multi-account system
    config = load_accounts_config()
    default = config.get("default")
    if default:
        creds = get_credentials_for_account(default)
        if creds:
            return creds

    # Fall back to legacy
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


def get_account_email_from_credentials(creds: Credentials) -> Optional[str]:
    """Get the email address associated with credentials by querying the API."""
    try:
        service = build('calendar', 'v3', credentials=creds)
        # Get the primary calendar which has the user's email
        calendar = service.calendars().get(calendarId='primary').execute()
        return calendar.get('id')  # Primary calendar ID is the user's email
    except Exception:
        return None


def authenticate(client_secret_path: Optional[str] = None, account_email: Optional[str] = None) -> Credentials:
    """Run OAuth2 flow to get credentials.

    Args:
        client_secret_path: Path to client_secret.json file
        account_email: Optional email hint for the account to authenticate

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

    # Determine the account email
    email = account_email or get_account_email_from_credentials(creds)

    if email:
        # Save to multi-account system
        save_credentials_for_account(email, creds)
        add_account_to_config(email)
    else:
        # Fall back to legacy single-account save
        save_credentials(creds)

    return creds


def authenticate_account(account_email: str, client_secret_path: Optional[str] = None,
                         set_as_default: bool = False) -> Credentials:
    """Authenticate a specific account.

    Args:
        account_email: The email of the account to authenticate
        client_secret_path: Path to client_secret.json file
        set_as_default: Whether to set this as the default account

    Returns:
        Credentials object
    """
    creds = authenticate(client_secret_path, account_email)

    # Verify we got the right account
    actual_email = get_account_email_from_credentials(creds)
    if actual_email and actual_email.lower() != account_email.lower():
        print(f"Warning: Authenticated as {actual_email}, not {account_email}")
        account_email = actual_email

    # Save and configure
    save_credentials_for_account(account_email, creds)
    add_account_to_config(account_email, set_as_default)

    return creds


def main():
    """Main entry point for authentication setup."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Authenticate with Google Calendar API (supports multiple accounts)'
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

    # Multi-account commands
    subparsers = parser.add_subparsers(dest='command', help='Account management commands')

    # Add account command
    add_parser = subparsers.add_parser('add', help='Add a new Google account')
    add_parser.add_argument('email', help='Email address of the account to add')
    add_parser.add_argument('--default', action='store_true', help='Set as default account')
    add_parser.add_argument('--credentials', type=str, help='Path to client_secret.json')

    # List accounts command
    subparsers.add_parser('list', help='List configured accounts')

    # Set default command
    default_parser = subparsers.add_parser('default', help='Set the default account')
    default_parser.add_argument('email', help='Email to set as default')

    # Remove account command
    remove_parser = subparsers.add_parser('remove', help='Remove an account')
    remove_parser.add_argument('email', help='Email of the account to remove')

    # Test specific account
    test_parser = subparsers.add_parser('test', help='Test a specific account')
    test_parser.add_argument('email', nargs='?', help='Email to test (default: default account)')

    args = parser.parse_args()

    if args.command == 'add':
        # Add a new account
        print(f"Adding account: {args.email}")
        print("=" * 50)
        print()
        print("This will open your browser to authenticate with Google.")
        print(f"Please sign in with: {args.email}")
        print()
        input("Press Enter to continue...")

        try:
            creds = authenticate_account(
                args.email,
                args.credentials,
                set_as_default=args.default
            )
            actual_email = get_account_email_from_credentials(creds) or args.email
            print()
            print("=" * 50)
            print(f"✓ Account added: {actual_email}")
            token_file = get_token_file(actual_email)
            print(f"✓ Token saved to: {token_file}")

            if args.default:
                print(f"✓ Set as default account")
            print()

        except Exception as e:
            print(f"✗ Failed to add account: {e}")
            exit(1)

    elif args.command == 'list':
        # List configured accounts
        accounts = get_configured_accounts()
        default = get_default_account()

        if not accounts:
            print("No accounts configured.")
            print("Run: python -m calendar_mcp.auth add <email>")
        else:
            print("Configured accounts:")
            print("-" * 40)
            for email in accounts:
                marker = " (default)" if email == default else ""
                creds = get_credentials_for_account(email)
                status = "✓ valid" if creds else "✗ needs re-auth"
                print(f"  {email}{marker} - {status}")
            print()

    elif args.command == 'default':
        # Set default account
        if set_default_account(args.email):
            print(f"✓ Default account set to: {args.email}")
        else:
            print(f"✗ Account not found: {args.email}")
            print("Run 'python -m calendar_mcp.auth list' to see configured accounts")
            exit(1)

    elif args.command == 'remove':
        # Remove an account
        if remove_account_from_config(args.email):
            print(f"✓ Account removed: {args.email}")
        else:
            print(f"✗ Account not found: {args.email}")
            exit(1)

    elif args.command == 'test':
        # Test a specific account
        email = args.email or get_default_account()
        if not email:
            print("No account specified and no default account configured.")
            exit(1)

        print(f"Testing account: {email}")
        creds = get_credentials_for_account(email)

        if creds:
            print(f"✓ Credentials loaded for {email}")
            print(f"✓ Token valid: {not creds.expired}")

            if creds.expired:
                print("! Token expired, attempting refresh...")
                try:
                    creds.refresh(Request())
                    save_credentials_for_account(email, creds)
                    print("✓ Token refreshed successfully")
                except Exception as e:
                    print(f"✗ Token refresh failed: {e}")
                    print(f"! Please re-authenticate: python -m calendar_mcp.auth add {email}")
        else:
            print(f"✗ No credentials found for {email}")
            print(f"! Please run: python -m calendar_mcp.auth add {email}")

    elif args.test:
        # Legacy test command
        print("Testing existing credentials...")

        # Show multi-account status first
        accounts = get_configured_accounts()
        default = get_default_account()

        if accounts:
            print(f"\nConfigured accounts: {len(accounts)}")
            print(f"Default account: {default or 'none'}")
            print()

        creds = get_credentials()

        if creds:
            print("✓ Credentials loaded successfully")
            print(f"✓ Scopes: {', '.join(creds.scopes) if creds.scopes else 'N/A'}")
            print(f"✓ Token valid: {not creds.expired}")

            if creds.expired:
                print("! Token expired, attempting refresh...")
                try:
                    creds.refresh(Request())
                    if default:
                        save_credentials_for_account(default, creds)
                    else:
                        save_credentials(creds)
                    print("✓ Token refreshed successfully")
                except Exception as e:
                    print(f"✗ Token refresh failed: {e}")
                    print("! Please re-authenticate")
        else:
            print("✗ No credentials found")
            print("! Please run: python -m calendar_mcp.auth")
            print("! Or add an account: python -m calendar_mcp.auth add <email>")

    else:
        # Run authentication flow (legacy single-account or new)
        print("Google Calendar MCP - Authentication Setup")
        print("=" * 50)
        print()
        print("This will open your browser to authenticate with Google.")
        print("Please grant access to read and write your calendar events.")
        print()
        print("TIP: For multi-account support, use:")
        print("  python -m calendar_mcp.auth add <email>")
        print()
        input("Press Enter to continue...")

        try:
            creds = authenticate(args.credentials)

            # Get the email from credentials
            email = get_account_email_from_credentials(creds)

            print()
            print("=" * 50)
            print("✓ Authentication successful!")
            if email:
                print(f"✓ Account: {email}")
                print(f"✓ Token saved to: {get_token_file(email)}")
            else:
                print(f"✓ Credentials saved to: {CREDENTIALS_FILE}")
            print()
            print("Next steps:")
            print("1. Add calendar-mcp to Claude Desktop config")
            print("2. Restart Claude Desktop")
            print("3. Ask Claude about your calendar!")
            print()
            print("To add another account:")
            print("  python -m calendar_mcp.auth add <email>")
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
