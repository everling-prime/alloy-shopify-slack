"""Entry point for the Shopify-to-Slack demo using Alloy's Connectivity API."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List

from src.config import settings
from src.connectivity_client import AlloyConnectivityClient, ConnectivityAPIError
from src.order_processor import OrderProcessor
from src.slack_formatter import SlackMessageFormatter

logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class ConsoleReporter:
    """Lightweight helper for human-friendly console sections."""

    def section(self, title: str) -> None:
        bar = "=" * len(title)
        print(f"\n{bar}\n{title}\n{bar}")

    def info(self, message: str) -> None:
        print(f"• {message}")

    def success(self, message: str) -> None:
        print(f"✓ {message}")

    def warning(self, message: str) -> None:
        print(f"! {message}")

    def error(self, message: str) -> None:
        print(f"✗ {message}")

    def summary(self, rows: List[tuple[str, str]]) -> None:
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            print(f"{label:<{width}} : {value}")


@dataclass
class RunStats:
    """Tracks metrics from a single run."""

    total_orders: int = 0
    high_value_orders: int = 0
    slack_messages_sent: int = 0
    errors: List[str] = field(default_factory=list)


class ShopifySlackIntegration:
    """Coordinates Connectivity API calls, processing, and Slack notifications."""

    def __init__(self) -> None:
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
        self.reporter = ConsoleReporter()
        self.last_check = datetime.now(timezone.utc) - timedelta(hours=24)

    def verify_setup(self) -> bool:
        """Ensure both Shopify and Slack credentials exist for the user.
        Prefer connector-based listing (per docs) to avoid 401s from /users endpoint.
        """

        self.reporter.section("Step 1: Verify Credentials")
        self.reporter.info(f"Alloy User ID: {settings.alloy_user_id}")

        # Try connector-based listing first
        try:
            shopify_creds = self.client.list_credentials_for_connector(
                self.shopify_connector_id, user_id=settings.alloy_user_id
            )
            slack_creds = self.client.list_credentials_for_connector(
                self.slack_connector_id, user_id=settings.alloy_user_id
            )
        except ConnectivityAPIError as exc:
            logger.error("Unable to list credentials via connector endpoints: %s", exc)
            # Fallback to user endpoint if connector listing fails
            try:
                combined = self.client.list_credentials(user_id=settings.alloy_user_id)
                shopify_creds = [c for c in combined if c.get("credentialId")]
                slack_creds = shopify_creds  # reuse combined since we only check IDs below
            except ConnectivityAPIError as exc2:
                logger.error("Unable to list credentials: %s", exc2)
                return False

        required_credentials = {
            settings.shopify_credential_id: "Shopify",
            settings.slack_credential_id: "Slack",
        }

        shopify_found = {c.get("credentialId") for c in shopify_creds}
        slack_found = {c.get("credentialId") for c in slack_creds}
        missing = []
        if settings.shopify_credential_id not in shopify_found:
            missing.append(settings.shopify_credential_id)
        if settings.slack_credential_id not in slack_found:
            missing.append(settings.slack_credential_id)

        if missing:
            for cid in missing:
                label = required_credentials.get(cid, "Unknown")
                self.reporter.error(f"Missing credential {cid} ({label})")
            return False

        self.reporter.success("All required credentials were found.")
        return True

    def process_orders(self) -> RunStats:
        """Execute listOrders, filter, and post Slack notifications."""

        stats = RunStats()

        created_at_min = self._format_shopify_timestamp(self.last_check)
        self.reporter.section("Step 2: Fetch Shopify Orders")
        self.reporter.info(f"Created after: {created_at_min}")

        # Build Shopify GraphQL query for filtering by created date
        # Format: "created_at:>='2024-01-01T00:00:00Z'"
        query_filter = f"created_at:>='{created_at_min}'"

        try:
            orders = self.client.list_orders_shopify(
                user_id=settings.alloy_user_id,
                credential_id=settings.shopify_credential_id,
                limit=50,
                query=query_filter,
                connector_id=self.shopify_connector_id,
            )
        except ConnectivityAPIError as exc:
            stats.errors.append(f"Failed to fetch Shopify orders: {exc}")
            self.reporter.error(stats.errors[-1])
            return stats

        stats.total_orders = len(orders)
        self.reporter.info(f"Total orders returned: {stats.total_orders}")

        if not orders:
            self.reporter.warning("No new orders returned by Shopify.")
            self.last_check = datetime.now(timezone.utc)
            return stats

        high_value_orders = self.order_processor.filter_high_value_orders(orders)
        stats.high_value_orders = len(high_value_orders)

        if not high_value_orders:
            self.reporter.warning("No orders exceeded the configured threshold.")
            self.last_check = datetime.now(timezone.utc)
            return stats

        self.reporter.section("Step 3: Notify Slack")
        self.reporter.info(f"High-value orders identified: {stats.high_value_orders}")

        sent = 0
        for order in high_value_orders:
            summary = self.order_processor.extract_order_summary(order)
            blocks = self.slack_formatter.format_order_notification(summary)
            try:
                self.reporter.info(f"Posting Slack notification for order #{summary.get('order_number')}")
                self.client.post_message_slack(
                    user_id=settings.alloy_user_id,
                    credential_id=settings.slack_credential_id,
                    channel=settings.slack_channel_id,
                    blocks=blocks,
                    connector_id=self.slack_connector_id,
                )
                sent += 1
            except ConnectivityAPIError as exc:
                error_message = f"Failed to notify Slack for order {summary.get('order_number')}: {exc}"
                stats.errors.append(error_message)
                self.reporter.error(error_message)

        self.last_check = datetime.now(timezone.utc)
        stats.slack_messages_sent = sent
        return stats

    def run_once(self) -> None:
        if not self.verify_setup():
            logger.error("Setup verification failed; exiting")
            sys.exit(1)
        stats = self.process_orders()
        self._render_summary(stats)

    def run_continuous(self) -> None:
        if not self.verify_setup():
            logger.error("Setup verification failed; exiting")
            sys.exit(1)

        self.reporter.section("Continuous Mode")
        self.reporter.info(
            f"Polling every {settings.check_interval_seconds}s (threshold {settings.order_value_threshold:.2f})"
        )
        self.reporter.info("Press Ctrl+C to stop")

        try:
            while True:
                stats = self.process_orders()
                self._render_summary(stats)
                time.sleep(settings.check_interval_seconds)
        except KeyboardInterrupt:
            self.reporter.warning("Integration stopped by user.")

    def _render_summary(self, stats: RunStats) -> None:
        self.reporter.section("Run Summary")
        rows = [
            ("Shopify orders fetched", str(stats.total_orders)),
            ("High-value orders", str(stats.high_value_orders)),
            ("Slack messages sent", str(stats.slack_messages_sent)),
            ("Threshold (USD)", f"{settings.order_value_threshold:.2f}"),
            ("Slack channel", settings.slack_channel_id),
        ]
        self.reporter.summary(rows)
        if stats.errors:
            self.reporter.warning("Errors occurred:")
            for err in stats.errors:
                self.reporter.error(f"  {err}")
        else:
            self.reporter.success("Completed without errors.")

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
