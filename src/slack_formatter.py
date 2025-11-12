"""Slack Block Kit formatting helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SlackMessageFormatter:
    """Formats Shopify order summaries into Slack block payloads."""

    def __init__(self, shopify_store_domain: Optional[str] = None) -> None:
        self.shopify_store_domain = shopify_store_domain

    def format_order_notification(self, order_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build a Slack Block Kit message from an order summary."""

        order_number = order_summary.get("order_number")
        total = order_summary.get("total", 0.0)
        currency = order_summary.get("currency", "USD")
        customer_name = order_summary.get("customer_name", "Unknown Customer")
        customer_email = order_summary.get("customer_email", "unknown@example.com")
        items_count = order_summary.get("items_count", 0)
        top_items = order_summary.get("top_items", [])
        shipping_address = order_summary.get("shipping_address", "")
        order_id = order_summary.get("order_id")
        created_at = order_summary.get("created_at_display", "")
        financial_status = order_summary.get("financial_status", "unknown")

        items_text_lines = [
            f"• {item['quantity']}× {item['name']} ({currency} {item['price']:.2f})"
            for item in top_items
        ]
        if items_count > len(top_items):
            items_text_lines.append(
                f"• ...and {items_count - len(top_items)} more item(s)"
            )
        items_text = "\n".join(items_text_lines) or "No line items available"

        view_order_url = self._build_shopify_admin_url(order_id)

        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎉 High-Value Order: #{order_number}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Amount:*\n{currency} {total:,.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Items:*\n{items_count} item(s)",
                    },
                ],
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer:*\n{customer_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Email:*\n{customer_email}",
                    },
                ],
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Financial Status:*\n{financial_status}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Created:*\n{created_at}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Order Items:*\n{items_text}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Shipping To:*\n{shipping_address}",
                },
            },
            {"type": "divider"},
        ]

        if view_order_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in Shopify Admin"},
                            "url": view_order_url,
                            "style": "primary",
                        }
                    ],
                }
            )

        return blocks

    def _build_shopify_admin_url(self, order_id: Any) -> Optional[str]:
        if not (self.shopify_store_domain and order_id):
            return None
        return (
            f"https://admin.shopify.com/store/{self.shopify_store_domain}/orders/{order_id}"
        )
