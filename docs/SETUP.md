# Connectivity API Setup Guide

This guide walks through every step required to run the Shopify → Slack demo using Alloy's Connectivity API.

## 1. Core Concepts

| Term | Description |
| ---- | ----------- |
| **Connector** | Integration target (e.g., `shopify`, `slack`). Each connector exposes resources and actions. |
| **Action** | A callable operation on a connector such as `listOrders` or `postMessage`. |
| **User** | A tenant/merchant that owns credentials. Required for multi-tenancy. |
| **Credential** | OAuth/API token created for a user + connector. Identified by `credentialId`. |
| **Execution** | A single action invocation created via `POST /users/{userId}/executions`. |

Every execution requires the tuple: `(userId, connectorId, actionId, credentialId)`.

## 2. Create a Connectivity API User

1. Generate an API key in the Alloy dashboard.
2. Call `POST https://api.runalloy.com/2025-09/users` using `Authorization: Bearer <API_KEY>`.
3. Provide a unique `username` (e.g., your tenant ID).
4. Store the returned `userId`; this value is required for all future requests.

```
curl -X POST https://api.runalloy.com/2025-09/users \
  -H "Authorization: Bearer $ALLOY_API_KEY" \
  -H "x-api-version: 2025-09" \
  -H "Content-Type: application/json" \
  -d '{"username": "merchant_acme"}'
```

## 3. Shopify Credential via OAuth

1. Call `POST /users/{userId}/credentials` with the payload:
   ```json
   {
     "connectorId": "shopify",
     "scopes": ["read_orders"],
     "redirectUrl": "https://your-app/callback"
   }
   ```
2. The response includes `oauthUrl`; redirect the merchant to complete Shopify OAuth.
3. After authorization, poll `GET /users/{userId}/credentials` to find the new `credentialId`.
4. Copy the ID into your `.env` under `SHOPIFY_CREDENTIAL_ID`.

## 4. Slack Credential via OAuth

Repeat the same flow with `connectorId=slack`. Request scopes like `chat:write` and redirect users to the returned link. Save the resulting `credentialId` as `SLACK_CREDENTIAL_ID`.

## 5. Discover Connector & Action IDs

- `GET /connectors` – verify `shopify` and `slack` connectors are available.
- `GET /connectors/{connectorId}/actions` – list actions for each connector.
- `GET /connectors/{connectorId}/actions/{actionId}` – inspect schema, required parameters, and sample responses.

For this demo we rely on:

- Shopify `listOrders` (READ)
- Slack `postMessage` (WRITE)

## 6. Test Action Executions

Use `POST /users/{userId}/executions` directly to validate credentials before running the Python app.

### Example: listOrders

```json
{
  "connectorId": "shopify",
  "actionId": "listOrders",
  "credentialId": "<SHOPIFY_CREDENTIAL_ID>",
  "queryParameters": {
    "limit": 5,
    "status": "any"
  }
}
```

### Example: postMessage

```json
{
  "connectorId": "slack",
  "actionId": "postMessage",
  "credentialId": "<SLACK_CREDENTIAL_ID>",
  "requestBody": {
    "channel": "C0123456789",
    "text": "Connectivity API test message"
  }
}
```

Confirm the responses succeed before wiring everything together.

## 7. Configure the Demo Application

1. `cp .env.example .env` and set every variable (API key, user ID, credential IDs, Slack channel, optional store domain).
2. Run `uv sync` to install dependencies.
3. Execute `uv run python -m src.main` for a single pass or use `--continuous` for polling.
4. Optionally run `uv run python tests/test_integration.py` to step through the READ/WRITE tests. The script prompts before sending a Slack message.

### Helper Script

The repository includes `setup_credentials.py`, which guides you through the same provisioning steps (user creation plus Shopify/Slack OAuth) and prints the credential IDs to paste into `.env`. Run it with:

```bash
uv run python setup_credentials.py
```

Once configured the demo will:

1. Fetch Shopify orders via Connectivity API.
2. Apply the order value threshold.
3. Post Slack messages using the stored credentials.
