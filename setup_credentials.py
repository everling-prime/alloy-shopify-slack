#!/usr/bin/env python3
"""Helper script to set up Connectivity API credentials."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException

load_dotenv()

API_KEY = os.getenv("ALLOY_API_KEY")
SHOPIFY_CONNECTOR_ID = os.getenv("SHOPIFY_CONNECTOR_ID", "shopify")
SLACK_CONNECTOR_ID = os.getenv("SLACK_CONNECTOR_ID", "slack")
BASE_URL = "https://api.runalloy.com/2025-09"
HEADERS = {
    "x-api-version": "2025-09",
    "Content-Type": "application/json",
}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"


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


def create_user(username: str) -> Optional[str]:
    """Step 1: Create a user."""

    print(f"\n=== Creating user: {username} ===")
    response = _safe_request("POST", "/users", json={"username": username})
    if response is None:
        return None

    if response.status_code == 201:
        user_data = response.json().get("data", {})
        user_id = user_data.get("userId")
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
        connectors = response.json().get("data", [])
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
        metadata = response.json().get("data", {})
        print(f"  Connector: {metadata.get('name')}")
        print(f"  OAuth: {metadata.get('isOauth', False)}")
        properties = metadata.get("properties", [])
        if properties:
            print("  Required fields:")
            for prop in properties:
                print(
                    f"    - {prop.get('name')}: {prop.get('description', 'N/A')}"
                )
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


def create_shopify_credential(user_id: str, shop_subdomain: str, connector_id: str) -> Optional[str]:
    """Step 4: Create Shopify credential (OAuth)."""

    print("\n=== Creating Shopify credential ===")
    response = _safe_request(
        "POST",
        f"/users/{user_id}/credentials",
        json={"connectorId": connector_id, "shopSubdomain": shop_subdomain},
    )
    if response is None:
        return None

    if response.status_code in (200, 201):
        data = response.json().get("data", {})
        oauth_url = data.get("oauthUrl")
        if oauth_url:
            print("✓ OAuth URL generated!")
            print("\n🌐 Open this URL in your browser to authorize Shopify:")
            print(f"   {oauth_url}")
            input("\n⏳ After authorizing, press Enter to continue...")
            print("\n  Fetching credential ID...")
            creds = list_credentials(user_id, connector_id)
            credential_id = _pick_first_credential(creds, connector_id)
            if credential_id:
                print("✓ Shopify credential created!")
                print(f"  Credential ID: {credential_id}")
                print("\n👉 Add this to your .env file:")
                print(f"   SHOPIFY_CREDENTIAL_ID={credential_id}")
                return credential_id
            print("✗ Unable to locate Shopify credential after OAuth callback")
        elif data.get("credentialId"):
            credential_id = data["credentialId"]
            print(f"✓ Credential created directly: {credential_id}")
            return credential_id

    print(f"✗ Failed to create credential: {response.text if response else 'unknown error'}")
    return None


def create_slack_credential(user_id: str, connector_id: str) -> Optional[str]:
    """Step 5: Create Slack credential (OAuth)."""

    print("\n=== Creating Slack credential ===")
    response = _safe_request(
        "POST",
        f"/users/{user_id}/credentials",
        json={"connectorId": connector_id},
    )
    if response is None:
        return None

    if response.status_code in (200, 201):
        data = response.json().get("data", {})
        oauth_url = data.get("oauthUrl")
        if oauth_url:
            print("✓ OAuth URL generated!")
            print("\n🌐 Open this URL in your browser to authorize Slack:")
            print(f"   {oauth_url}")
            input("\n⏳ After authorizing, press Enter to continue...")
            print("\n  Fetching credential ID...")
            creds = list_credentials(user_id, connector_id)
            credential_id = _pick_first_credential(creds, connector_id)
            if credential_id:
                print("✓ Slack credential created!")
                print(f"  Credential ID: {credential_id}")
                print("\n👉 Add this to your .env file:")
                print(f"   SLACK_CREDENTIAL_ID={credential_id}")
                return credential_id
            print("✗ Unable to locate Slack credential after OAuth callback")
        elif data.get("credentialId"):
            credential_id = data["credentialId"]
            print(f"✓ Credential created directly: {credential_id}")
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
    print("Alloy Connectivity API - Credential Setup")
    print("=" * 60)

    if not ensure_api_key():
        sys.exit(1)

    email = input("\nEnter a username (e.g., your email): ")
    user_id = create_user(email.strip())
    if not user_id:
        sys.exit(1)

    shopify_connector, slack_connector = list_connectors()
    if not shopify_connector or not slack_connector:
        print("✗ Required connectors not available. Please verify your API key permissions.")
        sys.exit(1)

    if not get_credential_requirements(SHOPIFY_CONNECTOR_ID):
        print("✗ Unable to fetch Shopify credential requirements.")
        sys.exit(1)
    if not get_credential_requirements(SLACK_CONNECTOR_ID):
        print("✗ Unable to fetch Slack credential requirements.")
        sys.exit(1)

    shop_subdomain = input(
        "\nEnter your Shopify store subdomain (e.g., 'my-store' from my-store.myshopify.com): "
    ).strip()
    shopify_cred_id = create_shopify_credential(user_id, shop_subdomain, SHOPIFY_CONNECTOR_ID)
    if not shopify_cred_id:
        print("✗ Shopify credential setup failed. Exiting.")
        sys.exit(1)

    slack_cred_id = create_slack_credential(user_id, SLACK_CONNECTOR_ID)
    if not slack_cred_id:
        print("✗ Slack credential setup failed. Exiting.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ Setup Complete!")
    print("=" * 60)
    print("\nYour .env file should now have:")
    print(f"  ALLOY_USER_ID={user_id}")
    if shopify_cred_id:
        print(f"  SHOPIFY_CREDENTIAL_ID={shopify_cred_id}")
    if slack_cred_id:
        print(f"  SLACK_CREDENTIAL_ID={slack_cred_id}")

    print("\nConnector IDs (already correct):")
    print(f"  SHOPIFY_CONNECTOR_ID={SHOPIFY_CONNECTOR_ID}")
    print(f"  SLACK_CONNECTOR_ID={SLACK_CONNECTOR_ID}")
    print("\n⚠️  Don't forget to also add your SLACK_CHANNEL_ID!")


if __name__ == "__main__":
    main()
