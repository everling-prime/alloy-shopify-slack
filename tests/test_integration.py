"""Integration tests for Alloy's Connectivity API demo."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings  # noqa: E402
from src.connectivity_client import AlloyConnectivityClient  # noqa: E402
from src.order_processor import OrderProcessor  # noqa: E402
from src.slack_formatter import SlackMessageFormatter  # noqa: E402

SHOPIFY_CONNECTOR_ID = settings.shopify_connector_id
SLACK_CONNECTOR_ID = settings.slack_connector_id


def step_list_connectors() -> None:
    """Test 1: List available connectors."""

    print("\n=== Test 1: List Connectors ===")
    client = AlloyConnectivityClient(
        api_key=settings.alloy_api_key,
        api_version=settings.alloy_api_version,
    )
    connectors = client.list_connectors()
    print(f"✓ Found {len(connectors)} connectors")
    shopify = next((c for c in connectors if c.get("id") == "shopify"), None)
    slack = next((c for c in connectors if c.get("id") == "slack"), None)
    if shopify:
        print("  ✓ Shopify connector available")
    if slack:
        print("  ✓ Slack connector available")


def step_list_credentials() -> None:
    """Test 2: List user credentials."""

    print("\n=== Test 2: List User Credentials ===")
    client = AlloyConnectivityClient(
        api_key=settings.alloy_api_key,
        api_version=settings.alloy_api_version,
    )
    credentials = client.list_credentials(user_id=settings.alloy_user_id)
    print(f"✓ User has {len(credentials)} credentials")
    for cred in credentials:
        print(f"  - {cred.get('connectorId')}: {cred.get('credentialId')}")


def step_read_shopify_orders() -> None:
    """Test 3: READ from Shopify via Connectivity API."""

    print("\n=== Test 3: Read Orders from Shopify ===")
    client = AlloyConnectivityClient(
        api_key=settings.alloy_api_key,
        api_version=settings.alloy_api_version,
    )
    orders = client.list_orders_shopify(
        user_id=settings.alloy_user_id,
        credential_id=settings.shopify_credential_id,
        limit=5,
        connector_id=SHOPIFY_CONNECTOR_ID,
    )
    print(f"✓ Successfully fetched {len(orders)} orders via Connectivity API")
    if orders:
        sample = orders[0]
        print(
            f"  Sample order: #{sample.get('order_number')} ($ {sample.get('total_price')})"
        )


def step_process_orders() -> None:
    """Test 4: Process and filter orders."""

    print("\n=== Test 4: Process Orders ===")
    sample_order = {
        "id": 4302345678901,
        "order_number": 1234,
        "total_price": "1250.00",
        "currency": "USD",
        "customer": {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
        },
        "line_items": [
            {"name": "Product A", "quantity": 2, "price": "299.99"},
            {"name": "Product B", "quantity": 1, "price": "149.99"},
        ],
        "shipping_address": {
            "city": "San Francisco",
            "province_code": "CA",
            "country_code": "US",
        },
    }
    processor = OrderProcessor(threshold=settings.order_value_threshold)
    high_value = processor.filter_high_value_orders([sample_order])
    print(f"✓ Filtered: {len(high_value)} high-value orders")
    if high_value:
        summary = processor.extract_order_summary(high_value[0])
        print(f"  Order: #{summary['order_number']} (${summary['total']:.2f})")


def step_format_slack_message() -> None:
    """Test 5: Format Slack message."""

    print("\n=== Test 5: Format Slack Message ===")
    order_summary = {
        "order_number": 1234,
        "order_id": 4302345678901,
        "total": 1250.00,
        "currency": "USD",
        "customer_name": "Jane Smith",
        "customer_email": "jane@example.com",
        "items_count": 2,
        "top_items": [{"name": "Product A", "quantity": 2, "price": 299.99}],
        "shipping_address": "San Francisco, CA, US",
    }
    formatter = SlackMessageFormatter(shopify_store_domain=settings.shopify_store_domain)
    blocks = formatter.format_order_notification(order_summary)
    print(f"✓ Generated Slack message with {len(blocks)} blocks")
    print(f"  Header: {blocks[0]['text']['text']}")


def step_write_slack_message() -> None:
    """Test 6: WRITE to Slack via Connectivity API."""

    print("\n=== Test 6: Write to Slack ===")
    response = input("This will send a test message to Slack. Continue? (y/n): ")
    if response.lower() != "y":
        print("Skipped")
        return

    client = AlloyConnectivityClient(
        api_key=settings.alloy_api_key,
        api_version=settings.alloy_api_version,
    )
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🧪 *Test Message from Connectivity API*\n\n"
                    "This is a test notification from the Shopify-Slack integration."
                ),
            },
        }
    ]
    client.post_message_slack(
        user_id=settings.alloy_user_id,
        credential_id=settings.slack_credential_id,
        channel=settings.slack_channel_id,
        blocks=blocks,
        connector_id=SLACK_CONNECTOR_ID,
    )
    print("✓ Test message sent via Connectivity API")
    print(f"  Check Slack channel: {settings.slack_channel_id}")


def run_all_tests() -> None:
    print("=" * 60)
    print("Shopify-Slack Integration Tests (Connectivity API)")
    print("=" * 60)
    try:
        step_list_connectors()
        step_list_credentials()
        step_read_shopify_orders()
        step_process_orders()
        step_format_slack_message()
        step_write_slack_message()
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except Exception as exc:  # pragma: no cover - interactive script
        print(f"\n✗ Test failed: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
