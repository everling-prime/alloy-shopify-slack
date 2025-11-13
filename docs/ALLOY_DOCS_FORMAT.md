# Building a Shopify to Slack Integration with Connectivity API

Send high-value Shopify order notifications to Slack in real-time using Alloy's Connectivity API. This guide demonstrates how to implement a multi-connector integration that monitors Shopify orders and posts formatted notifications to Slack—all without building or maintaining individual API integrations.

## What You'll Learn

- How to authenticate with Shopify and Slack using OAuth via Alloy
- How to execute connector actions (read from Shopify, write to Slack)
- How to chain multiple connector actions together
- Best practices for multi-tenant credential management
- Error handling and retry strategies for production use

## Use Case

This integration monitors Shopify orders and automatically notifies your team in Slack when high-value orders are placed. Common applications include:

- **Operations teams** tracking VIP customer orders
- **Fulfillment teams** prioritizing large orders for expedited processing
- **Customer success teams** getting early visibility into high-value purchases
- **Sales teams** monitoring B2B order patterns

The integration can be extended to log order acknowledgments to Google Sheets, update order tags in Shopify, or trigger custom workflows—demonstrating Alloy's multi-connector orchestration capabilities.

## Prerequisites

Before you begin, ensure you have:

- An Alloy account with API access ([sign up at runalloy.com](https://runalloy.com))
- Your Alloy API key from the dashboard
- A Shopify store with admin access
- A Slack workspace where you can create apps
- Python 3.11+ and [uv](https://github.com/astral-sh/uv) installed
- Basic familiarity with REST APIs and OAuth 2.0

### Required Credentials

You'll need to provision OAuth credentials for:
- **Shopify**: Requires store subdomain and standard read permissions
- **Slack**: Requires `chat:write` and `channels:read` scopes

> **Security Note**: Never expose your Alloy API key in client-side code. All API calls must originate from your backend server.

## Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌──────────────┐
│   Shopify   │         │  Your App    │         │    Slack     │
│   Orders    │────────▶│  (Python)    │────────▶│   Channel    │
└─────────────┘         └──────────────┘         └──────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ Alloy        │
                        │ Connectivity │
                        │ API          │
                        └──────────────┘
```

Your application:
1. Polls Shopify for new orders via Alloy's `listOrders` action
2. Filters orders by value threshold
3. Posts formatted notifications to Slack via Alloy's `chat_postMessage` action

Alloy handles authentication, rate limiting, API versioning, and data transformation for both connectors.

---

## Quick Start

### 1. Clone the Demo Repository

```bash
git clone https://github.com/skip/alloy-shopify-slack.git
cd alloy-shopify-slack
```

### 2. Run the Interactive Bootstrap Script

```bash
make bootstrap
# (wraps `uv run python scripts/bootstrap_demo.py`)
```

The target/script guides you through the entire setup:

- Prompts for your Alloy API key, Shopify store subdomain, Slack channel ID, and desired Alloy username/full name.
- Copies `.env.example` to `.env` (if needed) and writes every value you provide.
- Runs `uv sync` to install Python dependencies.
- Starts a local OAuth callback server on `http://localhost:8080/callback`.
- Creates or reuses a Connectivity API user.
- Launches Shopify + Slack OAuth flows, captures the resulting credential IDs, and stores `ALLOY_USER_ID`, `SHOPIFY_CREDENTIAL_ID`, and `SLACK_CREDENTIAL_ID` in `.env`.
- Runs a quick verification (list connectors, fetch orders, dry-run Slack post) so you know everything works end-to-end.

All you need is your browser and credentials—the script handles the rest.

> Need more control? Run the lower-level CLI directly:
> ```bash
> uv run python setup_credentials.py \
>   --api-key "runalloy_xxx" \
>   --shop-domain your-store \
>   --username your-email \
>   --full-name "Demo User" \
>   --non-interactive \
>   --no-browser \
>   --slack-channel C0123456789
> ```
> Leave `ALLOY_USER_ID`, `SHOPIFY_CREDENTIAL_ID`, and `SLACK_CREDENTIAL_ID` blank in `.env`; the script will populate them automatically.

### 3. Verification Helpers (Optional)

Re-run the connectivity checks at any time:

```bash
make verify                    # wraps status
uv run python scripts/verify_connectivity.py list-orders --limit 5
uv run python scripts/verify_connectivity.py chat-post --dry-run
```

These commands reuse the values in `.env`, so no additional configuration is required.

### 4. Run the Integration

Execute a single sync:

```bash
make run             # wraps uv run python -m src.main
```

Or run continuously with polling:

```bash
make run-continuous  # wraps uv run python -m src.main --continuous
```

You should see human-friendly sections similar to:

```
=============================
Step 1: Verify Credentials
=============================
• Alloy User ID: user_abc123
✓ All required credentials were found.

=============================
Step 2: Fetch Shopify Orders
=============================
• Created after: 2024-01-15T10:00:00Z
• Total orders returned: 3

=====================
Run Summary
=====================
Shopify orders fetched : 3
High-value orders       : 1
Slack messages sent     : 1
Threshold (USD)         : 500.00
Slack channel           : C01234567890
✓ Completed without errors.
```

---

## Step-by-Step Implementation

### Step 0: Understanding Key Concepts

| Term | Description | Example |
|------|-------------|---------|
| **Connector** | Pre-built integration for a third-party API | `shopify`, `slack`, `googlesheets` |
| **Action** | A specific operation you can perform on a connector | `listOrders`, `chat_postMessage`, `appendRow` |
| **User** | Represents a tenant/merchant in multi-tenant applications | Your customer who connects their Shopify store |
| **Credential** | OAuth token or API key for a user + connector | `cred_shopify_abc123` |
| **Execution** | A single API call to a connector action | Fetching orders or posting a message |

Every action execution requires: `(userId, connectorId, actionId, credentialId)`

### Step 1: Create a Connectivity API User

Users represent tenants in multi-tenant applications. Each user owns their own credentials.

**HTTP Request:**

```bash
curl -X POST https://production.runalloy.com/users \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "merchant_acme_inc",
    "fullName": "ACME Inc Merchant"
  }'
```

**Response:**

```json
{
  "userId": "user_abc123xyz"
}
```

**Python Implementation:**

```python
import requests

def create_user(api_key: str, username: str, full_name: str) -> str:
    """Create a Connectivity API user."""
    response = requests.post(
        "https://production.runalloy.com/users",
        headers={
            "Authorization": f"Bearer {api_key}",
            "x-api-version": "2025-09",
            "Content-Type": "application/json",
        },
        json={
            "username": username,
            "fullName": full_name,
        },
    )
    response.raise_for_status()
    return response.json()["userId"]
```

> **Important**: Store the `userId` securely. You'll need it for all subsequent API calls.

### Step 2: Create Shopify OAuth Credential

Before creating credentials, you can optionally inspect requirements:

```bash
curl -X GET https://production.runalloy.com/connectors/shopify/credentials/metadata \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09"
```

**Create the credential:**

```bash
curl -X POST https://production.runalloy.com/connectors/shopify/credentials \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user_abc123xyz",
    "authenticationType": "oauth2",
    "redirectUri": "http://localhost:8080/callback",
    "data": {
      "shopName": "your-store"
    }
  }'
```

**Response:**

```json
{
  "oauthUrl": "https://your-store.myshopify.com/admin/oauth/authorize?client_id=..."
}
```

**Next steps:**

1. Redirect the user to the `oauthUrl`
2. User authorizes your app in Shopify
3. Shopify redirects to your `redirectUri` with an authorization code
4. Alloy completes the OAuth flow and creates the credential
5. Retrieve the `credentialId` by listing credentials:

```bash
curl -X GET https://production.runalloy.com/users/user_abc123xyz/credentials \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09"
```

**Python Implementation:**

```python
def create_shopify_credential(
    api_key: str,
    user_id: str,
    shop_subdomain: str,
    redirect_uri: str = "http://localhost:8080/callback"
) -> str:
    """Create Shopify OAuth credential and return the OAuth URL."""
    response = requests.post(
        "https://production.runalloy.com/connectors/shopify/credentials",
        headers={
            "Authorization": f"Bearer {api_key}",
            "x-api-version": "2025-09",
            "Content-Type": "application/json",
        },
        json={
            "userId": user_id,
            "authenticationType": "oauth2",
            "redirectUri": redirect_uri,
            "data": {
                "shopName": shop_subdomain,
            },
        },
    )
    response.raise_for_status()
    oauth_url = response.json()["oauthUrl"]

    # Open browser or return URL to user
    print(f"Please visit: {oauth_url}")
    return oauth_url
```

> **Security Best Practice**: Use HTTPS redirect URIs in production. The demo uses `localhost` for local development only.

### Step 3: Create Slack OAuth Credential

Follow the same pattern for Slack:

```bash
curl -X POST https://production.runalloy.com/connectors/slack/credentials \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user_abc123xyz",
    "authenticationType": "oauth2",
    "redirectUri": "http://localhost:8080/callback"
  }'
```

**Response:**

```json
{
  "oauthUrl": "https://slack.com/oauth/v2/authorize?client_id=..."
}
```

After the user authorizes, retrieve the credential ID the same way.

### Step 4: Execute Actions

Now you can execute connector actions using the credentials.

#### Fetch Shopify Orders

```bash
curl -X POST https://production.runalloy.com/connectors/shopify/actions/listOrders/execute \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "x-alloy-userid: user_abc123xyz" \
  -H "Content-Type: application/json" \
  -d '{
    "credentialId": "cred_shopify_abc123",
    "queryParameters": {
      "first": 50,
      "query": "created_at:>='\''2024-01-15T00:00:00Z'\''"
    }
  }'
```

**Response Structure:**

```json
{
  "executionId": "exec_xyz789",
  "status": "completed",
  "responseData": {
    "data": {
      "orders": {
        "edges": [
          {
            "node": {
              "id": "gid://shopify/Order/1234567890",
              "name": "#1001",
              "totalPriceSet": {
                "shopMoney": {
                  "amount": "1250.00",
                  "currencyCode": "USD"
                }
              },
              "customer": {
                "displayName": "John Doe",
                "email": "john@example.com"
              },
              "lineItems": {
                "edges": [
                  {
                    "node": {
                      "name": "Premium Widget",
                      "quantity": 5,
                      "originalUnitPriceSet": {
                        "shopMoney": {
                          "amount": "250.00"
                        }
                      }
                    }
                  }
                ]
              }
            }
          }
        ]
      }
    }
  }
}
```

**Python Implementation:**

```python
def list_shopify_orders(
    api_key: str,
    user_id: str,
    credential_id: str,
    created_after: str,
    limit: int = 50
) -> list:
    """Fetch Shopify orders created after a specific date."""
    response = requests.post(
        "https://production.runalloy.com/connectors/shopify/actions/listOrders/execute",
        headers={
            "Authorization": f"Bearer {api_key}",
            "x-api-version": "2025-09",
            "x-alloy-userid": user_id,
            "Content-Type": "application/json",
        },
        json={
            "credentialId": credential_id,
            "queryParameters": {
                "first": limit,
                "query": f"created_at:>='{created_after}'",
            },
        },
    )
    response.raise_for_status()

    # Extract orders from GraphQL response
    data = response.json()["responseData"]["data"]["orders"]
    return [edge["node"] for edge in data.get("edges", [])]
```

#### Post to Slack

```bash
curl -X POST https://production.runalloy.com/connectors/slack/actions/chat_postMessage/execute \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "x-alloy-userid: user_abc123xyz" \
  -H "Content-Type: application/json" \
  -d '{
    "credentialId": "cred_slack_def456",
    "requestBody": {
      "channel": "C01234567890",
      "blocks": [
        {
          "type": "header",
          "text": {
            "type": "plain_text",
            "text": "🎉 High-Value Order: #1001"
          }
        },
        {
          "type": "section",
          "fields": [
            {
              "type": "mrkdwn",
              "text": "*Total Amount:*\nUSD 1,250.00"
            },
            {
              "type": "mrkdwn",
              "text": "*Customer:*\nJohn Doe"
            }
          ]
        }
      ]
    }
  }'
```

**Python Implementation:**

```python
def post_slack_message(
    api_key: str,
    user_id: str,
    credential_id: str,
    channel: str,
    blocks: list
) -> dict:
    """Post a formatted message to Slack."""
    response = requests.post(
        "https://production.runalloy.com/connectors/slack/actions/chat_postMessage/execute",
        headers={
            "Authorization": f"Bearer {api_key}",
            "x-api-version": "2025-09",
            "x-alloy-userid": user_id,
            "Content-Type": "application/json",
        },
        json={
            "credentialId": credential_id,
            "requestBody": {
                "channel": channel,
                "blocks": blocks,
            },
        },
    )
    response.raise_for_status()
    return response.json()["responseData"]
```

---

## Complete Working Example

Here's a complete Python script that ties everything together:

```python
#!/usr/bin/env python3
"""
Shopify to Slack integration using Alloy Connectivity API.
Monitors high-value orders and sends Slack notifications.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ALLOY_API_KEY = os.getenv("ALLOY_API_KEY")
ALLOY_USER_ID = os.getenv("ALLOY_USER_ID")
SHOPIFY_CREDENTIAL_ID = os.getenv("SHOPIFY_CREDENTIAL_ID")
SLACK_CREDENTIAL_ID = os.getenv("SLACK_CREDENTIAL_ID")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
ORDER_VALUE_THRESHOLD = float(os.getenv("ORDER_VALUE_THRESHOLD", "500.0"))

BASE_URL = "https://production.runalloy.com"
HEADERS = {
    "Authorization": f"Bearer {ALLOY_API_KEY}",
    "x-api-version": "2025-09",
    "Content-Type": "application/json",
}


def execute_action(
    connector_id: str,
    action_id: str,
    credential_id: str,
    request_body: Dict[str, Any] = None,
    query_parameters: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Execute a connector action via Alloy's Connectivity API."""
    url = f"{BASE_URL}/connectors/{connector_id}/actions/{action_id}/execute"
    headers = {**HEADERS, "x-alloy-userid": ALLOY_USER_ID}

    payload = {"credentialId": credential_id}
    if request_body:
        payload["requestBody"] = request_body
    if query_parameters:
        payload["queryParameters"] = query_parameters

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def fetch_recent_orders(created_after: str, limit: int = 50) -> List[Dict]:
    """Fetch Shopify orders created after a specific timestamp."""
    result = execute_action(
        connector_id="shopify",
        action_id="listOrders",
        credential_id=SHOPIFY_CREDENTIAL_ID,
        query_parameters={
            "first": limit,
            "query": f"created_at:>='{created_after}'",
        },
    )

    # Extract orders from GraphQL response
    orders_data = result["responseData"]["data"]["orders"]
    return [edge["node"] for edge in orders_data.get("edges", [])]


def filter_high_value_orders(orders: List[Dict]) -> List[Dict]:
    """Filter orders by value threshold."""
    high_value = []
    for order in orders:
        total = float(order["totalPriceSet"]["shopMoney"]["amount"])
        if total >= ORDER_VALUE_THRESHOLD:
            high_value.append(order)
    return high_value


def format_slack_message(order: Dict) -> List[Dict]:
    """Format order data into Slack Block Kit blocks."""
    order_number = order["name"]
    total = order["totalPriceSet"]["shopMoney"]["amount"]
    currency = order["totalPriceSet"]["shopMoney"]["currencyCode"]
    customer = order.get("customer", {}).get("displayName", "Unknown")
    email = order.get("customer", {}).get("email", "N/A")

    # Get line items
    line_items = order.get("lineItems", {}).get("edges", [])
    items_text = "\n".join([
        f"• {item['node']['quantity']}× {item['node']['name']}"
        for item in line_items[:3]
    ])

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🎉 High-Value Order: {order_number}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Total Amount:*\n{currency} {float(total):,.2f}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Customer:*\n{customer}",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Order Items:*\n{items_text}",
            },
        },
        {"type": "divider"},
    ]


def send_slack_notification(blocks: List[Dict]) -> None:
    """Post a message to Slack."""
    execute_action(
        connector_id="slack",
        action_id="chat_postMessage",
        credential_id=SLACK_CREDENTIAL_ID,
        request_body={
            "channel": SLACK_CHANNEL_ID,
            "blocks": blocks,
        },
    )


def main():
    """Main integration loop."""
    print("🚀 Starting Shopify → Slack integration")
    print(f"📊 Monitoring orders ≥ ${ORDER_VALUE_THRESHOLD}")

    # Check orders from the last 24 hours
    created_after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    print(f"📥 Fetching Shopify orders created after {created_after}")
    orders = fetch_recent_orders(created_after)
    print(f"✓ Found {len(orders)} total orders")

    high_value_orders = filter_high_value_orders(orders)
    print(f"💰 Found {len(high_value_orders)} high-value orders")

    for order in high_value_orders:
        order_number = order["name"]
        total = float(order["totalPriceSet"]["shopMoney"]["amount"])

        print(f"📤 Sending notification for order {order_number} (${total:.2f})")
        blocks = format_slack_message(order)
        send_slack_notification(blocks)
        print(f"✓ Notification sent for {order_number}")

    print(f"\n✅ Integration complete. Sent {len(high_value_orders)} notifications.")


if __name__ == "__main__":
    main()
```

**Run the script:**

```bash
python integration.py
```

**Expected output:**

```
🚀 Starting Shopify → Slack integration
📊 Monitoring orders ≥ $500.0
📥 Fetching Shopify orders created after 2024-01-15T10:00:00+00:00
✓ Found 12 total orders
💰 Found 3 high-value orders
📤 Sending notification for order #1001 ($1250.00)
✓ Notification sent for #1001
📤 Sending notification for order #1003 ($875.50)
✓ Notification sent for #1003
📤 Sending notification for order #1008 ($2100.00)
✓ Notification sent for #1008

✅ Integration complete. Sent 3 notifications.
```

---

## Authentication Deep Dive

### API Key Security

Your Alloy API key provides full access to your account. Follow these security practices:

✅ **DO:**
- Store API keys in environment variables or secret managers
- Use separate API keys for development, staging, and production
- Rotate API keys periodically
- Call Alloy's API from your backend server only

❌ **DON'T:**
- Commit API keys to version control
- Expose API keys in client-side JavaScript
- Share API keys across multiple applications
- Log API keys in application logs

### Multi-Tenant Architecture

For SaaS applications, each customer should have their own Connectivity API user:

```python
def provision_customer(customer_id: str, company_name: str) -> str:
    """Create a dedicated user for each customer."""
    response = requests.post(
        "https://production.runalloy.com/users",
        headers={
            "Authorization": f"Bearer {ALLOY_API_KEY}",
            "x-api-version": "2025-09",
            "Content-Type": "application/json",
        },
        json={
            "username": f"customer_{customer_id}",
            "fullName": company_name,
        },
    )
    response.raise_for_status()
    user_id = response.json()["userId"]

    # Store user_id in your database alongside customer record
    save_to_database(customer_id, user_id)

    return user_id
```

**Benefits of per-customer users:**
- Credentials are isolated between tenants
- Easy to revoke access for a single customer
- Simplified compliance and audit trails
- Natural multi-tenancy boundaries

### Credential Management

Credentials are tied to a specific user and connector:

```python
def list_customer_credentials(user_id: str) -> List[Dict]:
    """List all credentials for a customer."""
    response = requests.get(
        f"https://production.runalloy.com/users/{user_id}/credentials",
        headers={
            "Authorization": f"Bearer {ALLOY_API_KEY}",
            "x-api-version": "2025-09",
        },
    )
    response.raise_for_status()
    return response.json()["data"]
```

**Credential lifecycle:**
- Created via OAuth flow or API key input
- Stored encrypted by Alloy
- Automatically refreshed for OAuth tokens
- Can be deleted to revoke access

> **Important**: Credential IDs (`cred_*`) are safe to store in your database. They're useless without your API key.

---

## Error Handling & Troubleshooting

### Common Errors

#### 401 Unauthorized

**Symptom:**
```json
{
  "error": "Unauthorized",
  "message": "Invalid API key"
}
```

**Causes:**
- API key is missing or incorrect
- API key is not included in `Authorization` header
- Using a deleted or rotated API key

**Solution:**
```python
# Verify your API key is set correctly
import os
api_key = os.getenv("ALLOY_API_KEY")
if not api_key:
    raise ValueError("ALLOY_API_KEY environment variable not set")

# Ensure proper header format
headers = {
    "Authorization": f"Bearer {api_key}",  # Note: "Bearer " prefix required
    "x-api-version": "2025-09",
}
```

#### 404 Not Found

**Symptom:**
```json
{
  "error": "Not Found",
  "message": "Action 'postMessage' not found for connector 'slack'"
}
```

**Causes:**
- Incorrect action name (e.g., `postMessage` instead of `chat_postMessage`)
- Typo in connector ID
- Using an outdated API endpoint

**Solution:**
```python
# List available actions for a connector
def list_connector_actions(connector_id: str) -> List[Dict]:
    """Discover available actions for a connector."""
    response = requests.get(
        f"https://production.runalloy.com/connectors/{connector_id}/actions",
        headers={
            "Authorization": f"Bearer {ALLOY_API_KEY}",
            "x-api-version": "2025-09",
        },
    )
    response.raise_for_status()
    actions = response.json()["actions"]

    print(f"\nAvailable actions for {connector_id}:")
    for action in actions:
        print(f"  - {action['id']}: {action.get('displayName', 'N/A')}")

    return actions
```

#### 400 Bad Request - Invalid Parameters

**Symptom:**
```json
{
  "error": "Bad Request",
  "message": "Variable $first of type Int! was provided invalid value"
}
```

**Causes:**
- Using wrong parameter name (e.g., `limit` instead of `first` for Shopify)
- Missing required parameters
- Invalid parameter type or format

**Solution:**
```python
# Check action schema before calling
def get_action_schema(connector_id: str, action_id: str) -> Dict:
    """Get detailed schema for an action."""
    response = requests.get(
        f"https://production.runalloy.com/connectors/{connector_id}/actions/{action_id}",
        headers={
            "Authorization": f"Bearer {ALLOY_API_KEY}",
            "x-api-version": "2025-09",
        },
    )
    response.raise_for_status()
    action = response.json()["action"]

    print(f"\nAction: {action['id']}")
    print(f"Parameters:")
    for param in action.get("parameters", []):
        required = "REQUIRED" if param.get("required") else "optional"
        print(f"  - {param['name']} ({param['in']}): {required}")
        print(f"    Type: {param.get('schema', {}).get('type', 'N/A')}")

    return action
```

#### 429 Rate Limited

**Symptom:**
```json
{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded"
}
```

**Solution:**
```python
import time
from requests.exceptions import HTTPError

def execute_with_retry(
    connector_id: str,
    action_id: str,
    credential_id: str,
    max_retries: int = 3,
    **kwargs
) -> Dict:
    """Execute action with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return execute_action(
                connector_id, action_id, credential_id, **kwargs
            )
        except HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"⏳ Rate limited. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            raise
```

### Debugging Tips

#### Enable Request Logging

```python
import logging
import http.client

# Enable debug logging for HTTP requests
http.client.HTTPConnection.debuglevel = 1
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True
```

#### Validate Credentials

```python
def validate_credential(user_id: str, credential_id: str) -> bool:
    """Check if a credential is valid and active."""
    try:
        credentials = list_customer_credentials(user_id)
        cred = next((c for c in credentials if c["credentialId"] == credential_id), None)

        if not cred:
            print(f"❌ Credential {credential_id} not found")
            return False

        status = cred.get("status", "unknown")
        if status != "active":
            print(f"❌ Credential status: {status}")
            return False

        print(f"✓ Credential {credential_id} is valid")
        return True
    except Exception as e:
        print(f"❌ Error validating credential: {e}")
        return False
```

#### Test Individual Actions

```python
def test_shopify_connection(user_id: str, credential_id: str) -> bool:
    """Test Shopify connection by fetching shop info."""
    try:
        result = execute_action(
            connector_id="shopify",
            action_id="getShop",  # Simple action to test connectivity
            credential_id=credential_id,
        )
        shop_name = result["responseData"]["data"]["shop"]["name"]
        print(f"✓ Connected to Shopify store: {shop_name}")
        return True
    except Exception as e:
        print(f"❌ Shopify connection failed: {e}")
        return False
```

### Production Best Practices

#### Implement Health Checks

```python
def health_check() -> Dict[str, bool]:
    """Verify all credentials and connections are working."""
    results = {
        "shopify": False,
        "slack": False,
    }

    try:
        # Test Shopify
        fetch_recent_orders(
            created_after=datetime.now(timezone.utc).isoformat(),
            limit=1
        )
        results["shopify"] = True
    except Exception as e:
        print(f"Shopify health check failed: {e}")

    try:
        # Test Slack (dry run)
        execute_action(
            connector_id="slack",
            action_id="auth_test",
            credential_id=SLACK_CREDENTIAL_ID,
        )
        results["slack"] = True
    except Exception as e:
        print(f"Slack health check failed: {e}")

    return results
```

#### Add Structured Logging

```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

def log_execution(connector_id: str, action_id: str, result: str):
    """Log action executions with structured data."""
    logger.info(
        "Action executed",
        extra={
            "connector_id": connector_id,
            "action_id": action_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
```

#### Monitor for Credential Expiry

```python
def check_credential_expiry(user_id: str) -> None:
    """Alert if credentials are expiring soon."""
    credentials = list_customer_credentials(user_id)

    for cred in credentials:
        if "expiresAt" in cred:
            expires_at = datetime.fromisoformat(cred["expiresAt"])
            days_until_expiry = (expires_at - datetime.now(timezone.utc)).days

            if days_until_expiry < 7:
                logger.warning(
                    f"Credential {cred['credentialId']} expires in {days_until_expiry} days"
                )
```

---

## Extending the Integration

### Add Google Sheets Logging

Log order acknowledgments to a spreadsheet:

```python
def log_to_google_sheets(
    user_id: str,
    sheets_credential_id: str,
    spreadsheet_id: str,
    order_data: Dict,
) -> None:
    """Log order acknowledgment to Google Sheets."""
    execute_action(
        connector_id="googlesheets",
        action_id="appendRow",
        credential_id=sheets_credential_id,
        request_body={
            "spreadsheetId": spreadsheet_id,
            "range": "Orders!A:E",
            "values": [[
                order_data["order_number"],
                order_data["total"],
                order_data["customer_name"],
                order_data["acknowledged_by"],
                datetime.now(timezone.utc).isoformat(),
            ]],
        },
    )
```

### Add Interactive Slack Buttons

Create actionable notifications:

```python
def format_slack_message_with_button(order: Dict) -> List[Dict]:
    """Add an acknowledge button to Slack messages."""
    blocks = format_slack_message(order)  # Base message

    # Add action button
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Acknowledge Order",
                },
                "action_id": "acknowledge_order",
                "value": f"{order['name']}|{order['id']}",
                "style": "primary",
            }
        ],
    })

    return blocks
```

To handle button clicks, set up a webhook server that receives Slack interaction payloads and uses Alloy's `chat_update` action to modify the message.

### Multi-Channel Routing

Route orders to different channels based on value:

```python
def get_slack_channel(order_total: float) -> str:
    """Route orders to different channels by value."""
    if order_total >= 10000:
        return "C_VIP_ORDERS"
    elif order_total >= 1000:
        return "C_HIGH_VALUE"
    else:
        return "C_ALL_ORDERS"

# Use in notification
channel = get_slack_channel(float(order["totalPriceSet"]["shopMoney"]["amount"]))
send_slack_notification(blocks, channel=channel)
```

---

## Next Steps

Now that you've built a working Shopify → Slack integration, explore these resources:

- **[Connectivity API Reference](https://docs.runalloy.com/reference/connectivity-api)** - Complete API documentation
- **[Connector Catalog](https://docs.runalloy.com/connectors)** - Browse 200+ available connectors
- **[Multi-Connector Examples](https://docs.runalloy.com/use-cases)** - More integration patterns
- **[Webhook Setup Guide](https://docs.runalloy.com/webhooks)** - Build interactive workflows
- **[Rate Limits & Performance](https://docs.runalloy.com/rate-limits)** - Optimize for scale

### Get Help

- **Support**: support@runalloy.com
- **Sales**: sales@runalloy.com
- **Community**: Join our [Slack community](https://alloy-community.slack.com)

---

## Complete Code Repository

The full working example is available on GitHub:

**Repository**: [github.com/runalloy/shopify-slack-demo](https://github.com/runalloy/shopify-slack-demo)

Clone and run:
```bash
git clone https://github.com/runalloy/shopify-slack-demo.git
cd shopify-slack-demo
uv sync
uv run python setup_credentials.py
uv run python -m src.main
```

The repository includes:
- Complete working code with type hints
- Automated OAuth setup script
- Unit and integration tests
- Docker deployment configuration
- CI/CD pipeline examples
- Production-ready error handling

---

*Last updated: January 2025 | API Version: 2025-09*
