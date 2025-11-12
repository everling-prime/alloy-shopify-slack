"""Business logic for Shopify order processing."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Processes Shopify orders and applies business rules."""

    def __init__(self, threshold: float = 500.0) -> None:
        self.threshold = threshold

    def filter_high_value_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return only orders whose total price meets the threshold."""

        qualifying: List[Dict[str, Any]] = []
        for order in orders:
            try:
                total = float(order.get("total_price", 0))
            except (TypeError, ValueError):
                logger.warning("Skipping order with invalid total: %s", order.get("id"))
                continue

            if total >= self.threshold:
                qualifying.append(order)
                logger.info(
                    "High-value order detected: #%s (%.2f)",
                    order.get("order_number", "unknown"),
                    total,
                )

        logger.info("Filtered %s/%s orders above threshold", len(qualifying), len(orders))
        return qualifying

    def extract_order_summary(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the data fields required for Slack notifications."""

        customer = order.get("customer", {}) or {}
        shipping = order.get("shipping_address", {}) or {}
        line_items = order.get("line_items", []) or []
        created_at = order.get("created_at")

        return {
            "order_id": order.get("id"),
            "order_number": order.get("order_number", "Unknown"),
            "total": self._safe_float(order.get("total_price", 0)),
            "currency": order.get("currency", "USD"),
            "customer_name": self._format_customer_name(customer),
            "customer_email": customer.get("email", "unknown"),
            "items_count": len(line_items),
            "top_items": self._get_top_items(line_items),
            "shipping_address": self._format_address(shipping),
            "created_at": created_at,
            "created_at_display": self._format_timestamp(created_at),
            "financial_status": order.get("financial_status", "unknown"),
        }

    def _get_top_items(
        self, line_items: List[Dict[str, Any]], limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Return up to ``limit`` line items with normalized fields."""

        normalized: List[Dict[str, Any]] = []
        for item in line_items[:limit]:
            normalized.append(
                {
                    "name": item.get("name", "Unknown Item"),
                    "quantity": item.get("quantity", 1),
                    "price": self._safe_float(item.get("price", 0)),
                }
            )
        return normalized

    @staticmethod
    def _format_address(address: Dict[str, Any]) -> str:
        if not address:
            return "No shipping address"
        parts = [
            address.get("city", ""),
            address.get("province_code", ""),
            address.get("country_code", ""),
        ]
        return ", ".join(part for part in parts if part)

    @staticmethod
    def _format_customer_name(customer: Dict[str, Any]) -> str:
        first = customer.get("first_name", "")
        last = customer.get("last_name", "")
        name = f"{first} {last}".strip()
        return name or customer.get("email", "Unknown Customer")

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _format_timestamp(timestamp: Any) -> str:
        if not timestamp:
            return ""
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            return str(timestamp)
        return dt.strftime("%b %d, %Y %H:%M %Z").strip()
