# Connectivity API Setup Guide

This guide walks through every step required to run the Shopify → Slack demo using Alloy's Connectivity API.

## 1. Core Concepts

| Term | Description |
| ---- | ----------- |
| **Connector** | Integration target (e.g., `shopify`, `slack`). Each connector exposes resources and actions. |
| **Action** | A callable operation on a connector such as `listOrders` or `chat_postMessage`. |
| **User** | A tenant/merchant that owns credentials. Required for multi-tenancy. |
| **Credential** | OAuth/API token created for a user + connector. Identified by `credentialId`. |
| **Execution** | A single action invocation created via `POST /connectors/{connectorId}/actions/{actionId}/execute` with `x-alloy-userid` header. |

Every execution requires the tuple: `(userId, connectorId, actionId, credentialId)`.

## 2. Create a Connectivity API User

1. Generate an API key in the Alloy dashboard.
2. Call `POST https://production.runalloy.com/users` using `Authorization: Bearer <API_KEY>`.
3. Provide both a unique `username` (e.g., tenant ID or email) and a descriptive `fullName`.
4. Store the returned `userId`; this value is required for all future requests.

```
curl -X POST https://production.runalloy.com/users \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{"username": "merchant_acme", "fullName": "Merchant ACME"}'
```

## 3. Inspect Credential Requirements

Before creating credentials, fetch the connector's metadata to understand which fields are required (e.g., `redirectUri`, `shopSubdomain`, scopes):

```
curl -X GET https://production.runalloy.com/connectors/shopify/credentials/metadata \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09"
```

The response contains a `metadata` array describing `authenticationType` plus the property list (name + `required` flag). Use this to build the credential payload.

## 4. Shopify Credential via OAuth

1. Call `POST https://production.runalloy.com/connectors/shopify/credentials`:
   ```json
   {
     "userId": "<USER_ID>",
     "authenticationType": "oauth2",
     "redirectUri": "https://your-app/callback",
     "shopSubdomain": "your-store"
   }
   ```
2. The response includes an `oauthUrl`; redirect the merchant to this URL to finish OAuth.
3. After authorization, query `GET /users/{userId}/credentials?connectorId=shopify` to retrieve the resulting `credentialId`.
4. Store the ID in `.env` as `SHOPIFY_CREDENTIAL_ID`.

## 5. Slack Credential via OAuth

Repeat with the Slack connector:

```
curl -X POST https://production.runalloy.com/connectors/slack/credentials \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "<USER_ID>",
    "authenticationType": "oauth2",
    "redirectUri": "https://your-app/callback"
  }'
```

Redirect the user to the returned `oauthUrl`, then look up the Slack `credentialId` the same way.

## 5. Discover Connector & Action IDs

- `GET /connectors` – verify `shopify` and `slack` connectors are available.
- `GET /connectors/{connectorId}/actions` – list actions for each connector.
- `GET /connectors/{connectorId}/actions/{actionId}` – inspect schema, required parameters, and sample responses.

For this demo we rely on:

- Shopify `listOrders` (READ)
- Slack `chat_postMessage` (WRITE)

## 6. Test Action Executions

Use `POST /connectors/{connectorId}/actions/{actionId}/execute` with the `x-alloy-userid` header to validate credentials before running the Python app.

### Example: listOrders

```bash
curl -X POST https://production.runalloy.com/connectors/shopify/actions/listOrders/execute \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "x-alloy-userid: $USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "credentialId": "<SHOPIFY_CREDENTIAL_ID>",
    "queryParameters": {
      "limit": 5,
      "status": "any"
    }
  }'
```

### Example: chat_postMessage

```bash
curl -X POST https://production.runalloy.com/connectors/slack/actions/chat_postMessage/execute \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "x-alloy-userid: $USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "credentialId": "<SLACK_CREDENTIAL_ID>",
    "requestBody": {
      "channel": "C0123456789",
      "text": "Connectivity API test message"
    }
  }'
```

Confirm the responses succeed before wiring everything together.

## 7. Configure the Demo Application

1. `cp .env.example .env` and set every variable (API key, user ID, credential IDs, Slack channel, optional store domain).
2. Run `uv sync` to install dependencies.
3. Execute `uv run python -m src.main` for a single pass or use `--continuous` for polling.
4. Optionally run `uv run python tests/test_integration.py` to step through the READ/WRITE tests. The script prompts before sending a Slack message.

### Automated Helper Script

The repository includes `setup_credentials.py`, which **fully automates** the credential provisioning process:

```bash
uv run python setup_credentials.py
```

**What it does:**

1. **Starts a local OAuth callback server** on `http://localhost:8080/callback`
2. **Creates or reuses a user** from your `.env` file
3. **Verifies connector availability** (Shopify and Slack)
4. **Automatically extracts** your Shopify store subdomain from `SHOPIFY_STORE_DOMAIN` in `.env`
5. **Opens your browser** to the Shopify OAuth authorization page
6. **Captures the callback** when you authorize, automatically retrieving the credential ID
7. **Saves the Shopify credential** to `.env`
8. **Repeats steps 5-7** for Slack
9. **Updates your `.env` file** with all credential IDs

**No manual credential copying required!** The entire OAuth flow is handled automatically.

Once configured the demo will:

1. Fetch Shopify orders via Connectivity API.
2. Apply the order value threshold.
3. Post Slack messages using the stored credentials.

## 8. Extending the Demo: Interactive Buttons

The Slack notifications include an "Acknowledge Order" button as a placeholder example of how you could extend this integration using Alloy's Connectivity API.

### What the Button Demonstrates

The button shows how you could implement multi-connector orchestration:

1. **User clicks button** → Slack sends interaction payload to your webhook server
2. **Webhook processes** → Uses Alloy's `chat_update` action to update the message
3. **Optional logging** → Uses Alloy's `appendRow` action to log to Google Sheets

This would demonstrate: **Shopify → Slack → Google Sheets** orchestration.

### How to Implement (Future Extension)

To make the button functional, you would:

1. **Create a webhook server** (Flask/Express/etc.) to receive Slack interaction payloads
2. **Parse the payload** to extract order info and user details
3. **Use Alloy's Connectivity API** to execute actions:
   ```bash
   # Update the Slack message
   POST /connectors/slack/actions/chat_update/execute

   # Log to Google Sheets
   POST /connectors/googlesheets/actions/appendRow/execute
   ```
4. **Configure Slack App** to point to your webhook URL in "Interactivity & Shortcuts"

This is left as an exercise to show how Alloy enables chaining multiple connector actions together beyond the basic read/write flow demonstrated in this repo.
