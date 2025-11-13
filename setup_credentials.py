#!/usr/bin/env python3
"""Helper script to set up Connectivity API credentials."""

from __future__ import annotations

import os
import sys
import webbrowser
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import requests
from dotenv import load_dotenv, set_key
from requests.exceptions import RequestException

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

API_KEY = os.getenv("ALLOY_API_KEY")
SHOPIFY_CONNECTOR_ID = os.getenv("SHOPIFY_CONNECTOR_ID", "shopify")
SLACK_CONNECTOR_ID = os.getenv("SLACK_CONNECTOR_ID", "slack")
SHOPIFY_STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN")
BASE_URL = "https://production.runalloy.com"
HEADERS = {
    "x-api-version": "2025-09",
    "Content-Type": "application/json",
}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"

# OAuth callback configuration
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

# Global variable to store callback result
_callback_result = None
_callback_event = threading.Event()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callbacks."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET request from OAuth callback."""
        global _callback_result

        parsed_path = urlparse(self.path)

        if parsed_path.path == CALLBACK_PATH:
            # Parse query parameters
            query_params = parse_qs(parsed_path.query)

            # Store the result
            _callback_result = {
                "query_params": query_params,
                "success": True
            }

            # Send success response to browser
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            html = """
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
                    .checkmark {
                        width: 80px;
                        height: 80px;
                        border-radius: 50%;
                        display: block;
                        margin: 0 auto 1.5rem;
                        stroke-width: 3;
                        stroke: #4ade80;
                        stroke-miterlimit: 10;
                        box-shadow: inset 0px 0px 0px #4ade80;
                        animation: fill .4s ease-in-out .4s forwards, scale .3s ease-in-out .9s both;
                    }
                    .checkmark__circle {
                        stroke-dasharray: 166;
                        stroke-dashoffset: 166;
                        stroke-width: 3;
                        stroke-miterlimit: 10;
                        stroke: #4ade80;
                        fill: none;
                        animation: stroke 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
                    }
                    .checkmark__check {
                        transform-origin: 50% 50%;
                        stroke-dasharray: 48;
                        stroke-dashoffset: 48;
                        animation: stroke 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.8s forwards;
                    }
                    @keyframes stroke {
                        100% { stroke-dashoffset: 0; }
                    }
                    @keyframes scale {
                        0%, 100% { transform: none; }
                        50% { transform: scale3d(1.1, 1.1, 1); }
                    }
                    @keyframes fill {
                        100% { box-shadow: inset 0px 0px 0px 30px #4ade80; }
                    }
                    h1 { color: #1f2937; margin-bottom: 0.5rem; }
                    p { color: #6b7280; margin-bottom: 0; }
                    .info { background: #f3f4f6; padding: 1rem; border-radius: 0.5rem; margin-top: 1.5rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <svg class="checkmark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                        <circle class="checkmark__circle" cx="26" cy="26" r="25" fill="none"/>
                        <path class="checkmark__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                    </svg>
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                    <div class="info">
                        <p style="margin: 0; font-size: 0.875rem;">The credential has been captured and will be saved automatically.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())

            # Signal that callback was received
            _callback_event.set()
        else:
            self.send_response(404)
            self.end_headers()


def start_callback_server() -> HTTPServer:
    """Start the OAuth callback server."""
    server = HTTPServer(("localhost", CALLBACK_PORT), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_for_oauth_callback(timeout: int = 300) -> Optional[Dict[str, Any]]:
    """Wait for OAuth callback with timeout."""
    global _callback_result, _callback_event

    # Reset state
    _callback_result = None
    _callback_event.clear()

    # Wait for callback
    if _callback_event.wait(timeout=timeout):
        return _callback_result
    return None


def update_env_file(key: str, value: str) -> None:
    """Update a key in the .env file."""
    try:
        set_key(ENV_PATH, key, value)
        print(f"✓ Updated .env: {key}={value}")
    except Exception as exc:
        print(f"⚠️  Failed to update .env: {exc}")
        print(f"   Please manually add: {key}={value}")


def _safe_request(method: str, path: str, **kwargs) -> Optional[requests.Response]:
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


def create_user(username: str, full_name: str) -> Optional[str]:
    """Step 1: Create a user."""

    print(f"\n=== Creating user: {username} ===")
    payload = {
        "username": username,
        "fullName": full_name or username,
    }
    if "Authorization" not in HEADERS:
        print("⚠️  Authorization header missing before user creation request")
    response = _safe_request("POST", "/users", json=payload)
    if response is None:
        return None

    if response.status_code in (200, 201):
        response_body = response.json()
        # API returns userId directly at top level, not wrapped in data
        user_id = response_body.get("userId")
        if user_id:
            print("✓ User created successfully!")
            print(f"  User ID: {user_id}")
            print("\n👉 Add this to your .env file:")
            print(f"   ALLOY_USER_ID={user_id}")
            return user_id

    print(f"✗ Failed to create user: {response.text}")
    return None


def list_connectors() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Step 2: List available connectors."""

    print("\n=== Listing connectors ===")
    response = _safe_request("GET", "/connectors")
    if response is None:
        return None, None

    if response.status_code == 200:
        # API returns connectors directly, not wrapped in data
        connectors = response.json().get("connectors", [])
        shopify = next((c for c in connectors if c.get("id") == SHOPIFY_CONNECTOR_ID), None)
        slack = next((c for c in connectors if c.get("id") == SLACK_CONNECTOR_ID), None)
        if shopify:
            print(f"✓ Shopify connector found: {shopify.get('name')}")
        if slack:
            print(f"✓ Slack connector found: {slack.get('name')}")
        return shopify, slack

    print(f"✗ Failed to list connectors: {response.text}")
    return None, None


def get_credential_requirements(connector_id: str) -> Optional[Dict[str, Any]]:
    """Step 3: Get credential requirements for a connector."""

    print(f"\n=== Getting credential requirements for {connector_id} ===")
    response = _safe_request(
        "GET", f"/connectors/{connector_id}/credentials/metadata"
    )
    if response is None:
        return None

    if response.status_code == 200:
        body = response.json()
        metadata = body.get("metadata") or body.get("data") or {}
        # Some responses wrap metadata in a list
        entries = metadata if isinstance(metadata, list) else [metadata]
        for entry in entries:
            auth_type = entry.get("authenticationType")
            print(f"  Authentication Type: {auth_type or 'unknown'}")
            properties = entry.get("properties", [])
            if properties:
                print("  Required fields:")
                for prop in properties:
                    name = prop.get("name")
                    required = prop.get("required")
                    print(f"    - {name} (required={required})")
        return metadata

    print(f"✗ Failed to get metadata: {response.text}")
    return None


def list_credentials(user_id: str, connector_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List credentials for a user."""

    params: Dict[str, Any] = {}
    if connector_id:
        params["connectorId"] = connector_id

    response = _safe_request(
        "GET", f"/users/{user_id}/credentials", params=params or None
    )
    if response is None:
        return []

    if response.status_code == 200:
        return response.json().get("data", [])

    print(f"✗ Failed to list credentials: {response.text}")
    return []


def _pick_first_credential(creds: List[Dict[str, Any]], connector_id: str) -> Optional[str]:
    for cred in creds:
        if cred.get("connectorId") == connector_id:
            return cred.get("credentialId")
    return None


def create_shopify_credential(
    user_id: str,
    connector_id: str,
    shop_subdomain: Optional[str] = None,
) -> Optional[str]:
    """Step 4: Create Shopify credential (OAuth) with automated callback."""

    print("\n=== Creating Shopify credential ===")

    # Build the payload according to the API schema
    payload = {
        "userId": user_id,
        "authenticationType": "oauth2",
        "redirectUri": REDIRECT_URI,
    }

    # Add shopName in data object if provided (per API metadata requirements)
    if shop_subdomain:
        payload["data"] = {"shopName": shop_subdomain}

    response = _safe_request(
        "POST",
        f"/connectors/{connector_id}/credentials",
        json=payload,
    )
    if response is None:
        return None

    if response.status_code in (200, 201):
        # API returns response directly, not wrapped in data
        response_data = response.json()
        oauth_url = response_data.get("oauthUrl")
        if oauth_url:
            print("✓ OAuth URL generated!")
            print(f"🌐 Opening browser for authorization: {oauth_url[:60]}...")

            # Open browser automatically
            try:
                webbrowser.open(oauth_url)
                print("✓ Browser opened. Please authorize the application.")
            except Exception as exc:
                print(f"⚠️  Could not open browser automatically: {exc}")
                print(f"   Please manually open: {oauth_url}")

            print("⏳ Waiting for authorization callback...")

            # Wait for callback
            callback_result = wait_for_oauth_callback(timeout=300)

            if callback_result and callback_result.get("success"):
                print("✓ Authorization callback received!")

                # Give Alloy a moment to process the credential
                time.sleep(2)

                # Fetch credential ID
                print("  Fetching credential ID...")
                creds = list_credentials(user_id, connector_id)
                
                print(f"  Found {len(creds)} credential(s) for connector '{connector_id}'")
                
                # Since the API returns connectorId=None, we'll use the most recent credential
                # (the last one in the list, which is the one we just created)
                if creds:
                    credential_id = creds[-1].get('credentialId')
                    print(f"  Using most recent credential: {credential_id}")
                    
                    print("✓ Shopify credential created!")
                    print(f"  Credential ID: {credential_id}")

                    # Update .env file
                    update_env_file("SHOPIFY_CREDENTIAL_ID", credential_id)
                    return credential_id
                else:
                    print("✗ No credentials found after OAuth callback")
            else:
                print("✗ Authorization callback timed out or failed")

        elif response_data.get("credentialId"):
            credential_id = response_data["credentialId"]
            print(f"✓ Credential created directly: {credential_id}")
            update_env_file("SHOPIFY_CREDENTIAL_ID", credential_id)
            return credential_id

    print(f"✗ Failed to create credential: {response.text if response else 'unknown error'}")
    return None


def create_slack_credential(
    user_id: str,
    connector_id: str,
) -> Optional[str]:
    """Step 5: Create Slack credential (OAuth) with automated callback."""

    print("\n=== Creating Slack credential ===")
    response = _safe_request(
        "POST",
        f"/connectors/{connector_id}/credentials",
        json={
            "userId": user_id,
            "authenticationType": "oauth2",
            "redirectUri": REDIRECT_URI,
        },
    )
    if response is None:
        return None

    if response.status_code in (200, 201):
        # API returns response directly, not wrapped in data
        response_data = response.json()
        oauth_url = response_data.get("oauthUrl")
        if oauth_url:
            print("✓ OAuth URL generated!")
            print(f"🌐 Opening browser for authorization: {oauth_url[:60]}...")

            # Open browser automatically
            try:
                webbrowser.open(oauth_url)
                print("✓ Browser opened. Please authorize the application.")
            except Exception as exc:
                print(f"⚠️  Could not open browser automatically: {exc}")
                print(f"   Please manually open: {oauth_url}")

            print("⏳ Waiting for authorization callback...")

            # Wait for callback
            callback_result = wait_for_oauth_callback(timeout=300)

            if callback_result and callback_result.get("success"):
                print("✓ Authorization callback received!")

                # Give Alloy a moment to process the credential
                time.sleep(2)

                # Fetch credential ID
                print("  Fetching credential ID...")
                creds = list_credentials(user_id, connector_id)
                
                print(f"  Found {len(creds)} credential(s) for connector '{connector_id}'")
                
                # Since the API returns connectorId=None, we'll use the most recent credential
                # (the last one in the list, which is the one we just created)
                if creds:
                    credential_id = creds[-1].get('credentialId')
                    print(f"  Using most recent credential: {credential_id}")
                    
                    print("✓ Slack credential created!")
                    print(f"  Credential ID: {credential_id}")

                    # Update .env file
                    update_env_file("SLACK_CREDENTIAL_ID", credential_id)
                    return credential_id
                else:
                    print("✗ No credentials found after OAuth callback")
            else:
                print("✗ Authorization callback timed out or failed")

        elif response_data.get("credentialId"):
            credential_id = response_data["credentialId"]
            print(f"✓ Credential created directly: {credential_id}")
            update_env_file("SLACK_CREDENTIAL_ID", credential_id)
            return credential_id

    print(f"✗ Failed to create credential: {response.text if response else 'unknown error'}")
    return None


def ensure_api_key() -> bool:
    if API_KEY:
        return True
    print("✗ ALLOY_API_KEY not found in environment or .env file!")
    print("  Please add your API key to .env first.")
    return False


def main() -> None:
    print("=" * 60)
    print("Alloy Connectivity API - Automated Credential Setup")
    print("=" * 60)

    if not ensure_api_key():
        sys.exit(1)

    # Start the OAuth callback server
    print(f"\n🚀 Starting OAuth callback server on {REDIRECT_URI}")
    callback_server = start_callback_server()
    print("✓ Callback server is running")

    try:
        # Step 1: Get or create user
        user_id = os.getenv("ALLOY_USER_ID")
        if user_id and user_id != "user_xxxxx":
            print(f"\nℹ️  Using existing ALLOY_USER_ID from .env: {user_id}")
        else:
            full_name = input("\nEnter the user's full name: ").strip()
            email = input("Enter a username (e.g., your email): ").strip()
            user_id = create_user(email, full_name)
            if not user_id:
                sys.exit(1)
            # Save user ID to .env
            update_env_file("ALLOY_USER_ID", user_id)

        # Step 2: Verify connectors are available
        shopify_connector, slack_connector = list_connectors()
        if not shopify_connector or not slack_connector:
            print("✗ Required connectors not available. Please verify your API key permissions.")
            sys.exit(1)

        # Step 3: Check credential requirements
        if not get_credential_requirements(SHOPIFY_CONNECTOR_ID):
            print("✗ Unable to fetch Shopify credential requirements.")
            sys.exit(1)
        if not get_credential_requirements(SLACK_CONNECTOR_ID):
            print("✗ Unable to fetch Slack credential requirements.")
            sys.exit(1)

        # Step 4: Get shop subdomain
        shop_subdomain = None
        if SHOPIFY_STORE_DOMAIN:
            # Extract subdomain from formats like "my-store.myshopify.com" or "my-store"
            subdomain = SHOPIFY_STORE_DOMAIN.replace(".myshopify.com", "").replace("https://", "").replace("http://", "")
            shop_subdomain = subdomain.strip()
            print(f"\nℹ️  Using Shopify store from .env: {shop_subdomain}")
        else:
            shop_subdomain = input(
                "\nEnter your Shopify store subdomain (e.g., 'my-store' from my-store.myshopify.com): "
            ).strip() or None

        # Step 5: Create Shopify credential
        shopify_cred_id = create_shopify_credential(
            user_id,
            SHOPIFY_CONNECTOR_ID,
            shop_subdomain,
        )
        if not shopify_cred_id:
            print("✗ Shopify credential setup failed. Exiting.")
            sys.exit(1)

        # Step 6: Create Slack credential
        slack_cred_id = create_slack_credential(user_id, SLACK_CONNECTOR_ID)
        if not slack_cred_id:
            print("✗ Slack credential setup failed. Exiting.")
            sys.exit(1)

        # Success!
        print("\n" + "=" * 60)
        print("✅ Setup Complete!")
        print("=" * 60)
        print("\n✓ Your .env file has been automatically updated with:")
        print(f"  • ALLOY_USER_ID={user_id}")
        print(f"  • SHOPIFY_CREDENTIAL_ID={shopify_cred_id}")
        print(f"  • SLACK_CREDENTIAL_ID={slack_cred_id}")

        print("\nℹ️  Connector IDs (already configured):")
        print(f"  • SHOPIFY_CONNECTOR_ID={SHOPIFY_CONNECTOR_ID}")
        print(f"  • SLACK_CONNECTOR_ID={SLACK_CONNECTOR_ID}")

        print("\n⚠️  Don't forget to also add your SLACK_CHANNEL_ID to .env!")
        print("\n🎉 You can now run the integration:")
        print("   uv run python -m src.main")

    finally:
        # Shutdown the callback server
        print("\n🛑 Shutting down callback server...")
        callback_server.shutdown()
        print("✓ Server stopped")


if __name__ == "__main__":
    main()
