"""Business logic for Shopify order processing."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Processes Shopify orders and applies business rules."""

    def __init__(self, threshold: float = 500.0) -> None:
        self.threshold = threshold

    def filter_high_value_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return only orders whose total price meets the threshold."""

        qualifying: List[Dict[str, Any]] = []
        for order in orders:
            order_id = order.get("id", "unknown")
            # Handle both REST (order_number) and GraphQL (name) formats
            order_num = order.get("order_number") or order.get("name", "unknown")
            
            # Try to get total price - handle both REST and GraphQL formats
            total_price_value = self._extract_total_price(order)
            
            logger.debug(
                "Processing order #%s (ID: %s): total_price=%s (type: %s)",
                order_num,
                order_id,
                total_price_value,
                type(total_price_value).__name__,
            )
            
            if total_price_value is None:
                logger.warning(
                    "Order #%s could not extract total price. Available keys: %s",
                    order_num,
                    list(order.keys())[:10],  # Limit to first 10 keys for readability
                )
            
            try:
                total = float(total_price_value or 0)
            except (TypeError, ValueError):
                logger.warning("Skipping order #%s with invalid total: %s", order_num, total_price_value)
                continue

            logger.debug(
                "Order #%s: total=%.2f, threshold=%.2f, qualifies=%s",
                order_num,
                total,
                self.threshold,
                total >= self.threshold,
            )

            if total >= self.threshold:
                qualifying.append(order)
                logger.debug("High-value order detected: #%s (%.2f)", order_num, total)

        logger.info("Filtered %s/%s orders above threshold", len(qualifying), len(orders))
        return qualifying

    def _extract_total_price(self, order: Dict[str, Any]) -> Optional[float]:
        """Extract total price handling both REST and GraphQL formats.
        
        REST format: {"total_price": "525.00"}
        GraphQL format: {"totalPrice": {"amount": "525.00", "currencyCode": "USD"}}
        or GraphQL format: {"totalPrice": "525.00"}
        """
        # Try REST format first (snake_case)
        if "total_price" in order:
            return order["total_price"]
        
        # Try GraphQL format (camelCase)
        if "totalPrice" in order:
            total_price = order["totalPrice"]
            # Could be a string or an object with amount
            if isinstance(total_price, dict):
                return total_price.get("amount")
            return total_price
        
        # Fallback to current_total_price
        if "current_total_price" in order:
            return order["current_total_price"]
        
        return None

    def extract_order_summary(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the data fields required for Slack notifications.
        Handles both REST (snake_case) and GraphQL (camelCase) formats.
        """

        # Handle both REST and GraphQL formats for customer
        customer = order.get("customer", {}) or {}
        # GraphQL may nest customer differently
        if not customer and "billingAddress" in order:
            billing = order.get("billingAddress", {}) or {}
            customer = {"email": billing.get("email")}
        
        # Handle shipping address
        shipping = order.get("shipping_address") or order.get("shippingAddress", {}) or {}
        
        # Handle line items
        line_items_data = order.get("line_items") or order.get("lineItems", {})
        if isinstance(line_items_data, dict):
            # GraphQL returns {edges: [{node: {...}}]}
            line_items = [edge.get("node", {}) for edge in line_items_data.get("edges", [])]
        else:
            line_items = line_items_data or []
        
        # Handle timestamps
        created_at = order.get("created_at") or order.get("createdAt") or order.get("updatedAt")
        
        # Handle order number/name
        order_num = order.get("order_number") or order.get("name", "Unknown")
        
        # Extract total price
        total_price = self._extract_total_price(order)
        
        # Extract currency
        currency = order.get("currency", "USD")
        if "totalPrice" in order and isinstance(order["totalPrice"], dict):
            currency = order["totalPrice"].get("currencyCode", "USD")

        return {
            "order_id": order.get("id"),
            "order_number": order_num,
            "total": self._safe_float(total_price),
            "currency": currency,
            "customer_name": self._format_customer_name(customer),
            "customer_email": customer.get("email", "unknown"),
            "items_count": len(line_items),
            "top_items": self._get_top_items(line_items),
            "shipping_address": self._format_address(shipping),
            "created_at": created_at,
            "created_at_display": self._format_timestamp(created_at),
            "financial_status": order.get("financial_status") or order.get("financialStatus", "unknown"),
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
