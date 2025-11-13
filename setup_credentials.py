#!/usr/bin/env python3
"""Helper script to provision Connectivity API users and credentials."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException

from scripts.bootstrap_support import ensure_env_file, set_env_values

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
ENV_TEMPLATE = PROJECT_ROOT / ".env.example"
ensure_env_file(ENV_PATH, ENV_TEMPLATE)
load_dotenv(dotenv_path=ENV_PATH, override=False)

BASE_URL = "https://production.runalloy.com"
API_VERSION = "2025-09"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

SHOPIFY_CONNECTOR_ID = os.getenv("SHOPIFY_CONNECTOR_ID", "shopify")
SLACK_CONNECTOR_ID = os.getenv("SLACK_CONNECTOR_ID", "slack")

HEADERS: Dict[str, str] = {
    "x-api-version": API_VERSION,
    "Content-Type": "application/json",
}

_callback_result: Optional[Dict[str, Any]] = None
_callback_event = threading.Event()


class SetupError(RuntimeError):
    """Raised when the automated setup flow fails."""


@dataclass
class SetupOptions:
    """Arguments that control the bootstrap flow."""

    api_key: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    shop_domain: Optional[str] = None
    slack_channel_id: Optional[str] = None
    open_browser: bool = True
    non_interactive: bool = False


@dataclass
class SetupResult:
    """Values created by the bootstrap script."""

    user_id: str
    shopify_credential_id: str
    slack_credential_id: str


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callbacks."""

    def log_message(self, *_: Any) -> None:  # pragma: no cover - suppress default logging
        pass

    def do_GET(self) -> None:  # pragma: no cover - simple HTTP server
        """Handle GET requests sent by Shopify/Slack OAuth."""
        global _callback_result

        parsed_path = urlparse(self.path)
        if parsed_path.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        query_params = parse_qs(parsed_path.query)
        _callback_result = {"query_params": query_params, "success": True}

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(_SUCCESS_HTML.encode())

        _callback_event.set()


_SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Authorization Complete</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            background: white;
            padding: 3rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
        }
        h1 { color: #1f2937; margin-bottom: 0.5rem; }
        p { color: #6b7280; margin-bottom: 0; }
        .info { background: #f3f4f6; padding: 1rem; border-radius: 0.5rem; margin-top: 1.5rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Authorization Successful!</h1>
        <p>You can close this window and return to the terminal.</p>
        <div class="info">
            <p style="margin: 0; font-size: 0.875rem;">The credential has been captured and will be saved automatically.</p>
        </div>
    </div>
</body>
</html>
"""


def start_callback_server() -> HTTPServer:
    """Start the OAuth callback server in a background thread."""
    server = HTTPServer(("localhost", CALLBACK_PORT), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_for_oauth_callback(timeout: int = 300) -> Optional[Dict[str, Any]]:
    """Wait for OAuth callback with a timeout."""
    global _callback_result
    _callback_result = None
    _callback_event.clear()
    if _callback_event.wait(timeout=timeout):
        return _callback_result
    return None


def update_env_file(key: str, value: str) -> None:
    """Persist a value to the .env file."""
    set_env_values(ENV_PATH, {key: value})


def _safe_request(method: str, path: str, **kwargs: Any) -> Optional[requests.Response]:
    """Execute a requests call with shared error handling."""
    try:
        response = requests.request(
            method=method,
            url=f"{BASE_URL}{path}",
            headers=HEADERS,
            timeout=30,
            **kwargs,
        )
        return response
    except RequestException as exc:  # pragma: no cover - network helper
        print(f"✗ Request failed: {exc}")
        return None


def configure_api_key(cli_api_key: Optional[str]) -> str:
    """Ensure an API key exists and hydrate the default headers."""
    api_key = cli_api_key or os.getenv("ALLOY_API_KEY")
    if not api_key:
        raise SetupError("ALLOY_API_KEY is missing. Pass --api-key or set it in .env.")

    HEADERS["Authorization"] = f"Bearer {api_key}"
    os.environ["ALLOY_API_KEY"] = api_key
    if cli_api_key:
        update_env_file("ALLOY_API_KEY", api_key)
    return api_key


def create_user(username: str, full_name: str) -> str:
    """Create a Connectivity API user."""
    print(f"\n=== Creating user: {username} ===")
    payload = {"username": username, "fullName": full_name or username}
    response = _safe_request("POST", "/users", json=payload)
    if response is None:
        raise SetupError("Unable to reach the Connectivity API when creating the user.")

    if response.status_code in (200, 201):
        body = response.json()
        user_id = body.get("userId")
        if user_id:
            print("✓ User created successfully!")
            print(f"  User ID: {user_id}")
            return user_id

    raise SetupError(f"Failed to create user: {response.text}")


def list_connectors() -> Dict[str, Any]:
    """Return the Shopify and Slack connector objects."""
    print("\n=== Listing connectors ===")
    response = _safe_request("GET", "/connectors")
    if response is None:
        raise SetupError("Unable to reach the Connectivity API when listing connectors.")

    if response.status_code != 200:
        raise SetupError(f"Failed to list connectors: {response.text}")

    body = response.json()
    connectors = body.get("connectors", [])
    shopify = next((c for c in connectors if c.get("id") == SHOPIFY_CONNECTOR_ID), None)
    slack = next((c for c in connectors if c.get("id") == SLACK_CONNECTOR_ID), None)
    if not shopify or not slack:
        raise SetupError("Required connectors (shopify/slack) are not available for this API key.")
    print(f"✓ Shopify connector found: {shopify.get('name')}")
    print(f"✓ Slack connector found: {slack.get('name')}")
    return {"shopify": shopify, "slack": slack}


def get_credential_requirements(connector_id: str) -> List[Dict[str, Any]]:
    """Print and return credential metadata for a connector."""
    print(f"\n=== Getting credential requirements for {connector_id} ===")
    response = _safe_request("GET", f"/connectors/{connector_id}/credentials/metadata")
    if response is None:
        raise SetupError("Unable to read credential metadata.")

    if response.status_code != 200:
        raise SetupError(f"Failed to get metadata: {response.text}")

    metadata = response.json().get("metadata") or []
    if isinstance(metadata, dict):
        metadata = [metadata]
    for entry in metadata:
        auth_type = entry.get("authenticationType", "unknown")
        print(f"  Authentication Type: {auth_type}")
        for prop in entry.get("properties", []):
            name = prop.get("name")
            required = prop.get("required")
            print(f"    - {name} (required={required})")
    return metadata


def list_credentials(user_id: str, connector_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List credentials for a user."""
    params: Dict[str, Any] = {}
    if connector_id:
        params["connectorId"] = connector_id

    response = _safe_request("GET", f"/users/{user_id}/credentials", params=params or None)
    if response is None:
        raise SetupError("Unable to list credentials.")

    if response.status_code != 200:
        raise SetupError(f"Failed to list credentials: {response.text}")

    return response.json().get("data", [])


def _recent_credential_id(creds: List[Dict[str, Any]]) -> Optional[str]:
    """Return the last credential ID from the response list."""
    if not creds:
        return None
    return creds[-1].get("credentialId")


def _handle_oauth_flow(oauth_url: str, open_browser: bool) -> None:
    """Open the OAuth URL (or print it) and wait for the callback."""
    if open_browser:
        try:
            webbrowser.open(oauth_url)
            print("✓ Browser opened. Complete the OAuth authorization.")
        except Exception as exc:  # pragma: no cover - GUI availability
            print(f"⚠️  Could not open browser automatically: {exc}")
            print(f"   Please open this link manually:\n   {oauth_url}")
    else:
        print("🌐 OAuth URL:")
        print(f"   {oauth_url}")
        print("   Open the link in your browser to continue.")

    print("⏳ Waiting for authorization callback...")
    callback_result = wait_for_oauth_callback(timeout=300)
    if not callback_result or not callback_result.get("success"):
        raise SetupError("Authorization callback timed out or failed.")

    print("✓ Authorization callback received!")
    time.sleep(2)  # allow Alloy to finish processing


def create_shopify_credential(
    user_id: str,
    connector_id: str,
    shop_subdomain: Optional[str],
    *,
    open_browser: bool,
) -> str:
    """Create the Shopify credential and return its ID."""
    print("\n=== Creating Shopify credential ===")
    payload: Dict[str, Any] = {
        "userId": user_id,
        "authenticationType": "oauth2",
        "redirectUri": REDIRECT_URI,
    }
    if shop_subdomain:
        payload["data"] = {"shopName": shop_subdomain}

    response = _safe_request("POST", f"/connectors/{connector_id}/credentials", json=payload)
    if response is None:
        raise SetupError("Unable to initiate the Shopify OAuth flow.")

    if response.status_code not in (200, 201):
        raise SetupError(f"Failed to create Shopify credential: {response.text}")

    data = response.json()
    oauth_url = data.get("oauthUrl")
    credential_id = data.get("credentialId")

    if oauth_url:
        _handle_oauth_flow(oauth_url, open_browser=open_browser)
        creds = list_credentials(user_id, connector_id)
        credential_id = _recent_credential_id(creds)

    if not credential_id:
        raise SetupError("Could not find Shopify credential after OAuth completion.")

    print(f"✓ Shopify credential created: {credential_id}")
    update_env_file("SHOPIFY_CREDENTIAL_ID", credential_id)
    return credential_id


def create_slack_credential(
    user_id: str,
    connector_id: str,
    *,
    open_browser: bool,
) -> str:
    """Create the Slack credential and return its ID."""
    print("\n=== Creating Slack credential ===")
    payload = {
        "userId": user_id,
        "authenticationType": "oauth2",
        "redirectUri": REDIRECT_URI,
    }
    response = _safe_request("POST", f"/connectors/{connector_id}/credentials", json=payload)
    if response is None:
        raise SetupError("Unable to initiate the Slack OAuth flow.")

    if response.status_code not in (200, 201):
        raise SetupError(f"Failed to create Slack credential: {response.text}")

    data = response.json()
    oauth_url = data.get("oauthUrl")
    credential_id = data.get("credentialId")

    if oauth_url:
        _handle_oauth_flow(oauth_url, open_browser=open_browser)
        creds = list_credentials(user_id, connector_id)
        credential_id = _recent_credential_id(creds)

    if not credential_id:
        raise SetupError("Could not find Slack credential after OAuth completion.")

    print(f"✓ Slack credential created: {credential_id}")
    update_env_file("SLACK_CREDENTIAL_ID", credential_id)
    return credential_id


def sanitize_shop_domain(domain: str) -> str:
    """Normalize a Shopify store domain down to the subdomain."""
    sanitized = domain.strip().replace("https://", "").replace("http://", "")
    sanitized = sanitized.replace(".myshopify.com", "")
    return sanitized


def resolve_user(options: SetupOptions) -> str:
    """Return (or create) the Alloy user ID."""
    existing = options.user_id or os.getenv("ALLOY_USER_ID")
    if existing and existing != "user_xxxxx":
        print(f"\nℹ️  Using existing ALLOY_USER_ID from .env: {existing}")
        return existing

    if options.non_interactive and not options.username:
        raise SetupError("Username is required in non-interactive mode.")

    username = options.username or input("\nEnter the user's username/email: ").strip()
    if not username:
        raise SetupError("Username cannot be empty.")

    if options.full_name:
        full_name = options.full_name
    elif options.non_interactive:
        full_name = username
    else:
        full_name = input("Enter the user's full name: ").strip() or username

    user_id = create_user(username, full_name)
    update_env_file("ALLOY_USER_ID", user_id)
    return user_id


def resolve_shop_domain(options: SetupOptions) -> Optional[str]:
    """Return the Shopify store subdomain."""
    domain = options.shop_domain or os.getenv("SHOPIFY_STORE_DOMAIN")
    if not domain:
        if options.non_interactive:
            raise SetupError("SHOPIFY_STORE_DOMAIN is required in non-interactive mode.")
        domain = input(
            "\nEnter your Shopify store subdomain (e.g., 'my-store' from my-store.myshopify.com): "
        ).strip()

    if not domain:
        return None

    subdomain = sanitize_shop_domain(domain)
    update_env_file("SHOPIFY_STORE_DOMAIN", subdomain)
    print(f"ℹ️  Using Shopify store: {subdomain}")
    return subdomain


def bootstrap(options: SetupOptions) -> SetupResult:
    """Run the automated provisioning routine."""
    print("=" * 60)
    print("Alloy Connectivity API - Automated Credential Setup")
    print("=" * 60)

    configure_api_key(options.api_key)

    callback_server = start_callback_server()
    print(f"\n🚀 OAuth callback server listening on {REDIRECT_URI}")

    try:
        user_id = resolve_user(options)
        list_connectors()
        get_credential_requirements(SHOPIFY_CONNECTOR_ID)
        get_credential_requirements(SLACK_CONNECTOR_ID)

        shop_subdomain = resolve_shop_domain(options)
        shopify_cred = create_shopify_credential(
            user_id,
            SHOPIFY_CONNECTOR_ID,
            shop_subdomain,
            open_browser=options.open_browser,
        )
        slack_cred = create_slack_credential(
            user_id,
            SLACK_CONNECTOR_ID,
            open_browser=options.open_browser,
        )

        if options.slack_channel_id:
            update_env_file("SLACK_CHANNEL_ID", options.slack_channel_id)

        print("\n" + "=" * 60)
        print("✅ Setup Complete!")
        print("=" * 60)
        print(f"\n✓ ALLOY_USER_ID={user_id}")
        print(f"✓ SHOPIFY_CREDENTIAL_ID={shopify_cred}")
        print(f"✓ SLACK_CREDENTIAL_ID={slack_cred}")
        return SetupResult(user_id=user_id, shopify_credential_id=shopify_cred, slack_credential_id=slack_cred)
    finally:
        print("\n🛑 Shutting down callback server...")
        callback_server.shutdown()
        print("✓ Server stopped")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", help="Override ALLOY_API_KEY (also saved to .env).")
    parser.add_argument("--user-id", help="Use an existing Alloy user ID (optional).")
    parser.add_argument("--username", help="Username/email to create when no user exists.")
    parser.add_argument("--full-name", help="Full name to associate with the new user.")
    parser.add_argument("--shop-domain", help="Shopify store domain (subdomain or full domain).")
    parser.add_argument("--slack-channel", help="Slack channel ID to store in .env.")
    parser.add_argument("--no-browser", action="store_true", help="Print OAuth URLs instead of auto-opening a browser.")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting for missing values.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    options = SetupOptions(
        api_key=args.api_key,
        user_id=args.user_id,
        username=args.username,
        full_name=args.full_name,
        shop_domain=args.shop_domain,
        slack_channel_id=args.slack_channel,
        open_browser=not args.no_browser,
        non_interactive=args.non_interactive,
    )

    try:
        bootstrap(options)
    except SetupError as exc:
        print(f"\n✗ Setup failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
