"""Entry point for the Shopify-to-Slack demo using Alloy's Connectivity API."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from src.config import settings
from src.connectivity_client import AlloyConnectivityClient, ConnectivityAPIError
from src.order_processor import OrderProcessor
from src.slack_formatter import SlackMessageFormatter

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class ShopifySlackIntegration:
    """Coordinates Connectivity API calls, processing, and Slack notifications."""

    def __init__(self) -> None:
        logger.info("Initializing Shopify → Slack integration using Connectivity API")
        self.client = AlloyConnectivityClient(
            api_key=settings.alloy_api_key,
            api_version=settings.alloy_api_version,
        )
        self.shopify_connector_id = settings.shopify_connector_id
        self.slack_connector_id = settings.slack_connector_id
        self.order_processor = OrderProcessor(threshold=settings.order_value_threshold)
        self.slack_formatter = SlackMessageFormatter(
            shopify_store_domain=settings.shopify_store_domain
        )
        self.last_check = datetime.now(timezone.utc) - timedelta(hours=24)

    def verify_setup(self) -> bool:
        """Ensure both Shopify and Slack credentials exist for the user."""

        logger.info("Verifying Connectivity API credentials for user %s", settings.alloy_user_id)
        try:
            credentials = self.client.list_credentials(user_id=settings.alloy_user_id)
        except ConnectivityAPIError as exc:
            logger.error("Unable to list credentials: %s", exc)
            return False

        required_credentials = {
            settings.shopify_credential_id: "Shopify",
            settings.slack_credential_id: "Slack",
        }

        found = {cred.get("credentialId") for cred in credentials}
        missing = [cid for cid in required_credentials if cid not in found]
        if missing:
            for cid in missing:
                logger.error("Missing credential %s (%s)", cid, required_credentials[cid])
            return False

        logger.info("All required credentials were found")
        return True

    def process_orders(self) -> int:
        """Execute listOrders, filter, and post Slack notifications."""

        created_at_min = self._format_shopify_timestamp(self.last_check)
        logger.info(
            "Fetching Shopify orders created after %s via Connectivity API", created_at_min
        )
        try:
            orders = self.client.list_orders_shopify(
                user_id=settings.alloy_user_id,
                credential_id=settings.shopify_credential_id,
                limit=50,
                status="any",
                created_at_min=created_at_min,
                connector_id=self.shopify_connector_id,
            )
        except ConnectivityAPIError as exc:
            logger.error("Failed to fetch Shopify orders: %s", exc)
            return 0

        if not orders:
            logger.info("No new orders returned by Shopify")
            self.last_check = datetime.now(timezone.utc)
            return 0

        high_value_orders = self.order_processor.filter_high_value_orders(orders)
        if not high_value_orders:
            logger.info("No orders exceeded the threshold")
            self.last_check = datetime.now(timezone.utc)
            return 0

        sent = 0
        for order in high_value_orders:
            summary = self.order_processor.extract_order_summary(order)
            blocks = self.slack_formatter.format_order_notification(summary)
            try:
                logger.info(
                    "Posting Slack notification for order #%s", summary.get("order_number")
                )
                self.client.post_message_slack(
                    user_id=settings.alloy_user_id,
                    credential_id=settings.slack_credential_id,
                    channel=settings.slack_channel_id,
                    blocks=blocks,
                    connector_id=self.slack_connector_id,
                )
                sent += 1
            except ConnectivityAPIError as exc:
                logger.error("Failed to notify Slack for order %s: %s", summary.get("order_number"), exc)

        self.last_check = datetime.now(timezone.utc)
        return sent

    def run_once(self) -> None:
        if not self.verify_setup():
            logger.error("Setup verification failed; exiting")
            sys.exit(1)
        logger.info(
            "Monitoring for orders ≥ %.2f; Slack channel %s",
            settings.order_value_threshold,
            settings.slack_channel_id,
        )
        notifications = self.process_orders()
        logger.info("Run complete; sent %s notification(s)", notifications)

    def run_continuous(self) -> None:
        if not self.verify_setup():
            logger.error("Setup verification failed; exiting")
            sys.exit(1)

        logger.info(
            "Starting continuous polling every %s seconds (threshold %.2f)",
            settings.check_interval_seconds,
            settings.order_value_threshold,
        )
        logger.info("Press Ctrl+C to stop")

        try:
            while True:
                sent = self.process_orders()
                if sent:
                    logger.info("Sent %s notification(s) this cycle", sent)
                time.sleep(settings.check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Integration stopped by user")

    @staticmethod
    def _format_shopify_timestamp(moment: datetime) -> str:
        ts = moment.astimezone(timezone.utc).replace(microsecond=0)
        return ts.isoformat().replace("+00:00", "Z")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Poll Shopify continuously instead of running once",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    integration = ShopifySlackIntegration()
    if args.continuous:
        integration.run_continuous()
    else:
        integration.run_once()


if __name__ == "__main__":
    main()
