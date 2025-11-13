#!/usr/bin/env python3
"""Utility commands to validate Connectivity API configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import List, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(ENV_PATH, override=False)

from src.config import Settings  # noqa: E402
from src.connectivity_client import (  # noqa: E402
    AlloyConnectivityClient,
    ConnectivityAPIError,
)


CFG = Settings()
CLIENT = AlloyConnectivityClient(
    api_key=CFG.alloy_api_key,
    api_version=CFG.alloy_api_version,
)


def run_status() -> None:
    """Print connector availability and credential IDs."""
    client = CLIENT
    print("=== Connector Catalog ===")
    connectors = client.list_connectors()
    for connector in connectors:
        cid = connector.get("id")
        name = connector.get("name")
        print(f"- {cid}: {name}")

    print("\n=== Credentials for User ===")
    creds = client.list_credentials(CFG.alloy_user_id)
    if not creds:
        print("No credentials found for this user.")
        return
    for cred in creds:
        print(f"- {cred.get('credentialId')} ({cred.get('type')})")


def run_list_orders(limit: int = 5, query: Optional[str] = None) -> List[dict]:
    """Execute Shopify listOrders and print the number of rows returned."""
    client = CLIENT
    orders = client.list_orders_shopify(
        user_id=CFG.alloy_user_id,
        credential_id=CFG.shopify_credential_id,
        limit=limit,
        query=query,
        connector_id=CFG.shopify_connector_id,
    )
    count = len(orders)
    print(f"\n✓ Retrieved {count} order(s) from Shopify (limit={limit}).")
    if count:
        example = orders[0]
        order_number = example.get("order_number") or example.get("name")
        total = example.get("total_price") or example.get("totalPrice")
        print(f"  Example Order: #{order_number} total={total}")
    return orders


def run_chat_post(
    *,
    text: str,
    channel: Optional[str],
    dry_run: bool = False,
) -> None:
    """Execute Slack chat_postMessage or simulate it via dry-run."""
    channel_id = channel or CFG.slack_channel_id
    if not channel_id:
        raise ConnectivityAPIError("SLACK_CHANNEL_ID is not configured.")

    if dry_run:
        print(f"\n[DRY-RUN] Would send to #{channel_id}: {text}")
        return

    response = CLIENT.post_message_slack(
        user_id=CFG.alloy_user_id,
        credential_id=CFG.slack_credential_id,
        channel=channel_id,
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
        connector_id=CFG.slack_connector_id,
    )
    ok = response.get("ok")
    ts = response.get("ts")
    print(f"\n✓ Slack message sent (ok={ok}, ts={ts})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show configured connectors and credentials.")

    list_orders_parser = subparsers.add_parser("list-orders", help="Execute Shopify listOrders.")
    list_orders_parser.add_argument("--limit", type=int, default=5, help="Number of orders to fetch.")
    list_orders_parser.add_argument(
        "--query",
        help="Optional Shopify query string filter (e.g., \"created_at:>='2024-01-01'\").",
    )

    chat_post_parser = subparsers.add_parser("chat-post", help="Post (or simulate) a Slack message.")
    chat_post_parser.add_argument("--text", default="Connectivity API test message", help="Message body.")
    chat_post_parser.add_argument("--channel", help="Override Slack channel ID.")
    chat_post_parser.add_argument(
        "--dry-run", action="store_true", help="Print the payload instead of executing the action."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.command == "status":
            run_status()
        elif args.command == "list-orders":
            run_list_orders(limit=args.limit, query=args.query)
        elif args.command == "chat-post":
            run_chat_post(text=args.text, channel=args.channel, dry_run=args.dry_run)
    except ConnectivityAPIError as exc:
        print(f"\n✗ Verification failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
