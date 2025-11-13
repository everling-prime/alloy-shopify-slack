# Shopify → Slack Connectivity API Demo

This project showcases how to use [Alloy's Connectivity API](https://docs.runalloy.com/reference/connectivity-api/) to *directly* execute connector actions without workflows. It reads high-value Shopify orders using the `listOrders` action and posts notifications to Slack using the `chat_postMessage` action.

## Connectivity API Overview

The Connectivity API exposes every Alloy connector as REST resources so you can:

- Discover connectors, actions, and schemas from your backend.
- Programmatically create users and credentials (OAuth/API keys).
- Execute actions on behalf of a user by referencing connector IDs and credential IDs.

Each request is a standard HTTP call against `https://production.runalloy.com` with the following headers:

```
Authorization: Bearer <ALLOY_API_KEY>
x-api-version: 2025-09
Content-Type: application/json
```

Unlike the Embedded/Unified API, Connectivity gives you direct, low-level access to connector actions that you can orchestrate yourself.

## Authentication & Provisioning Flow

1. **Create a user** via `POST /users` to represent your merchant/tenant and store the returned `userId`.
2. **Create credentials** for that user by:
   - Fetching connector requirements via `GET /connectors/{connectorId}/credentials/metadata`.
   - Calling `POST /connectors/{connectorId}/credentials` with `userId`, `authenticationType`, `redirectUri`, and any connector-specific properties (e.g., `data.shopName` for Shopify).
   - Redirecting the merchant to the returned `oauthUrl` (for OAuth connectors) and capturing the resulting `credentialId`.
3. **Execute actions** by calling `POST /connectors/{connectorId}/actions/{actionId}/execute` with the `x-alloy-userid` header and providing `credentialId` in the request body.

The `userId` + `credentialId` pair is all the code needs to invoke Shopify and Slack on behalf of the merchant.

## READ/WRITE Demo Flow

- **READ** – `listOrders` on the Shopify connector retrieves recent orders. Orders above the configured dollar threshold are considered high-value.
- **WRITE** – For each qualifying order, the app calls Slack's `chat_postMessage` action to send a richly formatted Block Kit notification to the configured channel.

### Extension Opportunity: Interactive Buttons

The Slack notifications include an "Acknowledge Order" button as a placeholder example. This demonstrates how you could extend the integration using Alloy's Connectivity API to:

- Handle Slack interactive component callbacks via a webhook server
- Update the Slack message using the `chat_update` action
- Log acknowledgments to Google Sheets using the `appendRow` action
- Chain multiple connector actions together (Shopify → Slack → Google Sheets)

This button is currently non-functional but shows how Alloy enables multi-connector orchestration beyond basic read/write operations.

## Project Structure

```
├── src/
│   ├── config.py              # Pydantic settings loader
│   ├── connectivity_client.py # Thin Connectivity API wrapper
│   ├── order_processor.py     # Business logic for filtering orders
│   ├── slack_formatter.py     # Slack Block Kit formatting helpers
│   └── main.py                # Shopify → Slack workflow
├── setup_credentials.py       # Automated OAuth credential setup
├── tests/test_integration.py  # End-to-end Connectivity API checks
├── examples/                  # Sample responses/payloads
├── docs/SETUP.md              # Detailed setup guide
├── .env.example               # Environment template
└── pyproject.toml             # uv / Python project file
```

## Prerequisites & Setup

1. **Sign up at [runalloy.com](https://runalloy.com)** and create an API key from the dashboard.
2. **Install uv** (https://github.com/astral-sh/uv) and Python 3.11.
3. **Create a Connectivity API user** with `POST /users` supplying both `username` and `fullName`, then save the returned `userId`.
4. **Check credential requirements** per connector via `GET /connectors/{connectorId}/credentials/metadata` to learn which fields (e.g., `redirectUri`, `shopSubdomain`) are mandatory.
5. **Create a Shopify credential**
   - Call `POST /connectors/shopify/credentials` with `userId`, `authenticationType`, and `redirectUri` (plus any metadata-required properties).
   - Redirect the merchant to the returned `oauthUrl` and capture the `credentialId` once authorization completes.
6. **Create a Slack credential** via `POST /connectors/slack/credentials` using the same flow.
7. **Bootstrap credentials (automated helper script)** – run the fully automated setup:
   ```bash
   uv run python setup_credentials.py
   ```
   The script will:
   - Start a local OAuth callback server on http://localhost:8080
   - Create or use an existing user
   - Show connector metadata
   - Automatically open your browser for Shopify OAuth authorization
   - Capture the credential and save it to `.env`
   - Repeat the process for Slack
   - Update your `.env` file with all credential IDs automatically

   No manual copying of credentials needed!
8. **Copy `.env.example` to `.env`** and populate every setting:
   ```bash
   cp .env.example .env
   # edit the file with your ALLOY_API_KEY, USER_ID, credential IDs, Slack channel, etc.
   ```
9. **Install dependencies** (handled automatically if you ran `uv init`, but you can re-sync at any time):
   ```bash
   uv sync
   ```

## Running the Integration

Run once (fetch + notify):

```bash
uv run python -m src.main
```

Run continuously with polling:

```bash
uv run python -m src.main --continuous
```

Environment variable overrides (e.g., `ORDER_VALUE_THRESHOLD`) can also be exported directly; Pydantic reads values from the environment before `.env`.

## Tests

`tests/test_integration.py` exercises the same READ and WRITE endpoints in a guided fashion:

1. Lists available connectors.
2. Lists credentials for your user.
3. Reads Shopify orders via `listOrders`.
4. Processes sample orders locally.
5. Formats a Slack message.
6. (Optional) posts a test message to Slack.

Run:

```bash
uv run python tests/test_integration.py
```

> ⚠️ The tests invoke live Connectivity API endpoints. Ensure `ALLOY_API_KEY`, `ALLOY_USER_ID`, and credential IDs are valid before running them.

## Example Payloads

- `examples/sample_shopify_response.json` – Realistic order response from Shopify's `listOrders` action.
- `examples/sample_slack_blocks.json` – Example Slack Block Kit payload generated by the formatter.

## Emphasis on Connectivity API Usage

- All HTTP calls are made directly with `requests` against `/users`, `/connectors`, and `/executions` endpoints.
- No SDKs or workflow automation features are used; the demo shows how to orchestrate actions yourself.
- The code keeps connector IDs (`shopify`, `slack`) and credential IDs configurable so you can swap environments or tenants easily.

Refer to `docs/SETUP.md` for a deeper dive into provisioning credentials and verifying executions.
