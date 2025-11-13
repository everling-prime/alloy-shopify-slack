import importlib
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeClient:
    def __init__(self, shopify_cred: str, slack_cred: str) -> None:
        self.shopify_cred = shopify_cred
        self.slack_cred = slack_cred
        self.messages_sent = 0

    def list_credentials_for_connector(self, connector_id: str, user_id: str):
        if connector_id == "shopify":
            return [{"credentialId": self.shopify_cred}]
        if connector_id == "slack":
            return [{"credentialId": self.slack_cred}]
        return []

    def list_orders_shopify(self, **_: object):
        return [
            {
                "id": "gid://shopify/Order/1",
                "order_number": "1001",
                "total_price": "50.00",
                "currency": "USD",
                "customer": {"first_name": "Test", "last_name": "Buyer", "email": "buyer@example.com"},
                "line_items": [{"name": "Widget", "quantity": 1, "price": "50.00"}],
                "shipping_address": {"city": "SF", "province_code": "CA", "country_code": "US"},
                "created_at": "2024-01-01T00:00:00Z",
                "financial_status": "paid",
            },
            {
                "id": "gid://shopify/Order/2",
                "order_number": "1002",
                "total_price": "250.00",
                "currency": "USD",
                "customer": {"first_name": "High", "last_name": "Value", "email": "vip@example.com"},
                "line_items": [{"name": "Gadget", "quantity": 2, "price": "125.00"}],
                "shipping_address": {"city": "NYC", "province_code": "NY", "country_code": "US"},
                "created_at": "2024-01-02T00:00:00Z",
                "financial_status": "paid",
            },
        ]

    def post_message_slack(self, **_: object):
        self.messages_sent += 1
        return {"ok": True, "ts": "123.456"}


class MainSummaryTest(TestCase):
    def test_run_once_outputs_summary_and_posts_message(self):
        env = {
            "ALLOY_API_KEY": "test",
            "ALLOY_USER_ID": "user_test",
            "SHOPIFY_CREDENTIAL_ID": "shop_cred",
            "SLACK_CREDENTIAL_ID": "slack_cred",
            "SLACK_CHANNEL_ID": "C123",
            "SHOPIFY_CONNECTOR_ID": "shopify",
            "SLACK_CONNECTOR_ID": "slack",
            "ALLOY_API_VERSION": "2025-09",
            "ORDER_VALUE_THRESHOLD": "200",
            "SHOPIFY_STORE_DOMAIN": "demo-store",
            "CHECK_INTERVAL_SECONDS": "60",
        }

        with mock.patch.dict(os.environ, env, clear=True):
            import src.main as main_module

            importlib.reload(main_module)
            integration = main_module.ShopifySlackIntegration()
            fake_client = FakeClient(env["SHOPIFY_CREDENTIAL_ID"], env["SLACK_CREDENTIAL_ID"])
            integration.client = fake_client

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                integration.run_once()

            output = buffer.getvalue()
            self.assertIn("Run Summary", output)
            self.assertIn("Slack messages sent", output)
            self.assertEqual(fake_client.messages_sent, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
