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
├── scripts/                   # Bootstrap + verification helpers
├── tests/test_integration.py  # End-to-end Connectivity API checks
├── examples/                  # Sample responses/payloads
├── docs/SETUP.md              # Detailed setup guide
├── .env.example               # Environment template
└── pyproject.toml             # uv / Python project file
```

## Quick Start (Automated Setup)

1. **Install uv + Python 3.11, clone the repo, and `cd` into it.**
2. **Run the bootstrap script** and answer the prompts for your Alloy API key, Shopify store, Slack channel, etc. The script creates `.env` automatically:

   ```bash
   uv run python scripts/bootstrap_demo.py
   ```

   The script:

   - Runs `uv sync` to install dependencies.
   - Seeds `.env` with your API key, Shopify store, and Slack channel.
   - Starts a local OAuth callback server on `http://localhost:8080/callback`.
   - Creates (or reuses) a Connectivity API user.
   - Performs both Shopify + Slack OAuth flows without manual cURL commands.
   - Writes the resulting `ALLOY_USER_ID`, `SHOPIFY_CREDENTIAL_ID`, and `SLACK_CREDENTIAL_ID` to `.env`.
   - Calls the verification helper to ensure both actions succeed.

Need a more surgical flow (or to re-run a subset)? The lower-level CLI exposes the same building blocks:

```bash
uv run python setup_credentials.py \
  --api-key "runalloy_xxx" \
  --shop-domain your-store \
  --username your-email \
  --full-name "Your Name" \
  --non-interactive \
  --no-browser         # optional: prints OAuth URLs instead
```

> Prefer the raw HTTP walkthrough? See the “Manual API Walkthrough” section in `docs/SETUP.md`.

### Useful Make/uv Targets

```bash
make bootstrap   # runs scripts/bootstrap_demo.py (interactive prompts)
make run         # uv run python -m src.main
make verify      # quick status check via scripts/verify_connectivity.py
```

### Verification Helpers

Use the Python verifier instead of hand-written curl snippets:

```bash
uv run python scripts/verify_connectivity.py status        # connectors + credentials
uv run python scripts/verify_connectivity.py list-orders   # fetch Shopify orders
uv run python scripts/verify_connectivity.py chat-post --dry-run
```

All helpers rely on `.env` / environment variables, so storing secrets in `.env` keeps commands simple.

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
