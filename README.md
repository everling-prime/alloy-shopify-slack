# Shopify → Slack Connectivity API Demo

Monitor Shopify orders and post beautifully formatted Slack notifications using [Alloy's Connectivity API](https://docs.runalloy.com/reference/connectivity-api/). The app demonstrates how to read data from Shopify (`listOrders`), filter for high-value purchases, and write to Slack (`chat_postMessage`) without building bespoke connector code.

## Quick Start

1. **Install prerequisites**
   - Python 3.11+
   - [uv](https://github.com/astral-sh/uv)
   - Alloy API key, Shopify store access, Slack workspace where you can install an app
2. **Clone this repo**
   ```bash
   git clone https://github.com/skip/alloy-shopify-slack.git
   cd alloy-shopify-slack
   ```
3. **Bootstrap everything (recommended)**
   ```bash
   make bootstrap          # wraps `uv run python scripts/bootstrap_demo.py`
   ```
   The interactive script copies `.env.example`, runs `uv sync`, creates or reuses your Connectivity API user, performs Shopify + Slack OAuth, writes all credential IDs to `.env`, and runs a verification pass.
4. **Run the demo**
   ```bash
   make run                # single pass
   # or
   make run-continuous     # poll Shopify on an interval
   ```

> Need granular control (CI/headless)? Use `uv run python setup_credentials.py --api-key ... --shop-domain ... --username ... --non-interactive --no-browser` and/or the raw HTTP flows documented in `docs/SETUP.md`.

## What You'll See

- **Step 1: Verify Credentials** – Confirms the `ALLOY_USER_ID`, Shopify credential, and Slack credential exist for your tenant.
- **Step 2: Fetch Shopify Orders** – Pulls recent orders via Connectivity API, logging how many items were returned.
- **Step 3: Notify Slack** – Formats high-value orders with Block Kit, including a placeholder "Acknowledge Order" button (non-functional but illustrates multi-connector workflows).
- **Run Summary** – Prints Shopify orders fetched, how many exceeded the threshold, Slack messages sent, and the channel used.

## Connectivity API Essentials

| Concept        | Description                                                                    |
| -------------- | ------------------------------------------------------------------------------ |
| User           | Represents your tenant/merchant. You create one per customer (`POST /users`).  |
| Credential     | OAuth/API token scoped to a user + connector (`POST /connectors/{id}/credentials`). |
| Action         | A callable operation such as `listOrders` or `chat_postMessage`.               |
| Execution      | `POST /connectors/{id}/actions/{action}/execute` with `x-alloy-userid` header. |

The tuple `(userId, connectorId, actionId, credentialId)` is all you need to call any connector. Alloy handles OAuth, rate limits, and versioning.

## Project Structure

```
├── src/
│   ├── main.py                # Orchestrates verify → fetch → notify flow
│   ├── connectivity_client.py # Thin wrapper around Connectivity API endpoints
│   ├── order_processor.py     # Filters and summarizes Shopify orders
│   └── slack_formatter.py     # Builds Slack Block Kit payloads
├── scripts/
│   ├── bootstrap_demo.py      # Interactive end-to-end setup
│   ├── bootstrap_support.py   # Shared env + verification helpers
│   └── verify_connectivity.py # Status, list-orders, chat-post commands
├── setup_credentials.py       # Advanced CLI for non-interactive provisioning
├── tests/
│   ├── test_main_summary.py   # Smoke test for console summary output
│   └── test_integration.py    # Live Connectivity API walkthrough (prompts)
├── docs/SETUP.md              # Detailed manual + curl commands
└── docs/ALLOY_DOCS_FORMAT.md  # Long-form tutorial
```

## Make Targets & Commands

| Command              | Description |
| -------------------- | ----------- |
| `make bootstrap`     | Interactive setup (`scripts/bootstrap_demo.py`). |
| `make run`           | Execute one fetch + notify pass (`uv run python -m src.main`). |
| `make run-continuous`| Poll continuously using `CHECK_INTERVAL_SECONDS`. |
| `make verify`        | Shows connector catalog and credential status. |

Equivalent `uv` commands are documented inside each script for environments that don’t allow GNU Make.

## Verification Helpers

Re-run the same checks the bootstrapper performs whenever you need:

```bash
make verify
uv run python scripts/verify_connectivity.py list-orders --limit 5
uv run python scripts/verify_connectivity.py chat-post --dry-run
```

All helpers read from `.env`, so once bootstrap finishes you don’t have to retype IDs.

## Tests

- `tests/test_main_summary.py` – Mocks Connectivity API calls to assert console output and Slack posting logic.
- `tests/test_integration.py` – Guides you through live Connectivity API steps (prompts before actually hitting Slack). Run with valid credentials:
  ```bash
  uv run python tests/test_integration.py
  ```

## Extending the Demo

- Make the "Acknowledge Order" button functional via a small webhook server and Alloy’s `chat_update` action.
- Log acknowledgments to Google Sheets using Alloy’s `appendRow`.
- Chain additional connectors (e.g., push ERP updates) by reusing the same `userId` + `credentialId` pair.

For the full manual API walkthrough, troubleshooting tips, and architecture deep dive, see `docs/SETUP.md` and `docs/ALLOY_DOCS_FORMAT.md`.
