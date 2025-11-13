"""Thin client for interacting with Alloy's Connectivity API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)


class ConnectivityAPIError(Exception):
    """Base exception for Connectivity API errors."""


class ConnectivityAuthError(ConnectivityAPIError):
    """Raised when the API rejects authentication."""


class ConnectivityRateLimitError(ConnectivityAPIError):
    """Raised when Alloy applies rate limiting."""


class AlloyConnectivityClient:
    """Helper around Alloy's Connectivity API endpoints."""

    def __init__(
        self,
        api_key: str,
        api_version: str = "2025-09",
        base_url: str = "https://production.runalloy.com",
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-version": api_version,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        logger.info("Alloy Connectivity API client initialized")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a request to the Connectivity API with common error handling."""

        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json_data,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            if status == 401:
                raise ConnectivityAuthError("Invalid Alloy API key") from exc
            if status == 429:
                raise ConnectivityRateLimitError("Rate limit exceeded") from exc
            detail = exc.response.text if exc.response else str(exc)
            logger.error("Connectivity API HTTP error %s: %s", status, detail)
            raise ConnectivityAPIError(f"API error {status}: {detail}") from exc
        except RequestException as exc:  # network or serialization issues
            logger.error("Connectivity API request failed: %s", exc)
            raise ConnectivityAPIError(f"Request failed: {exc}") from exc

    def create_user(self, username: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a Connectivity API user for multi-tenancy."""

        logger.info("Creating Alloy user %s", username)
        payload = {"username": username}
        if full_name:
            payload["fullName"] = full_name
        response = self._make_request(
            method="POST",
            endpoint="/users",
            json_data=payload,
        )
        # Response returns userId directly, not wrapped in data
        return response

    def list_connectors(self) -> List[Dict[str, Any]]:
        """Return the catalog of available connectors."""

        response = self._make_request(method="GET", endpoint="/connectors")
        # Response returns connectors directly, not wrapped in data
        connectors = response.get("connectors", [])
        logger.info("Connectivity API returned %s connectors", len(connectors))
        return connectors

    def get_connector_resources(self, connector_id: str) -> List[Dict[str, Any]]:
        """Return resource metadata for a specific connector."""

        response = self._make_request(
            method="GET",
            endpoint=f"/connectors/{connector_id}/resources",
        )
        # Response returns resources directly, not wrapped in data
        resources = response.get("resources", [])
        logger.info("Connector %s exposes %s resources", connector_id, len(resources))
        return resources

    def get_action_details(self, connector_id: str, action_id: str) -> Dict[str, Any]:
        """Fetch the schema for a connector action."""

        response = self._make_request(
            method="GET",
            endpoint=f"/connectors/{connector_id}/actions/{action_id}",
        )
        # Response returns action directly, not wrapped in data
        return response.get("action", {})

    def create_credential(
        self,
        user_id: str,
        connector_id: str,
        credential_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a credential for a connector (OAuth/API key)."""

        payload = {"userId": user_id, **credential_data}
        response = self._make_request(
            method="POST",
            endpoint=f"/connectors/{connector_id}/credentials",
            json_data=payload,
        )
        # Response returns oauthUrl or credentialId directly, not wrapped in data
        if "oauthUrl" in response:
            logger.info("OAuth URL generated for %s: %s", connector_id, response["oauthUrl"])
        if "credentialId" in response:
            logger.info("Credential created: %s", response["credentialId"])
        return response

    def list_credentials(
        self, user_id: str, connector_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List credentials owned by the specified user (legacy endpoint)."""

        params: Dict[str, Any] = {}
        if connector_id:
            params["connectorId"] = connector_id
        response = self._make_request(
            method="GET",
            endpoint=f"/users/{user_id}/credentials",
            params=params or None,
        )
        credentials = response.get("data", [])
        logger.info("Retrieved %s credential(s) for user %s", len(credentials), user_id)
        return credentials

    def list_credentials_for_connector(self, connector_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List credentials for a specific connector by filtering user credentials.

        The /connectors/{connectorId}/credentials endpoint returns empty results,
        so we use /users/{userId}/credentials and filter by type field.

        Args:
            connector_id: The connector to filter by (e.g., 'shopify', 'slack')
            user_id: Optional user ID. If not provided, will try to use the user_id from the first request context.
        """
        if not user_id:
            raise ValueError("user_id is required to list credentials")

        # Get all credentials for the user
        all_credentials = self.list_credentials(user_id=user_id)

        # Filter by connector type (e.g., 'shopify-oauth2', 'slack-oauth2')
        # The type field includes the connector name as a prefix
        credentials = [
            c for c in all_credentials
            if c.get("type", "").startswith(f"{connector_id}-")
        ]

        logger.info(
            "Retrieved %s credential(s) for connector %s (user %s)",
            len(credentials), connector_id, user_id
        )
        return credentials

    def execute_action(
        self,
        user_id: str,
        connector_id: str,
        action_id: str,
        credential_id: str,
        request_body: Optional[Dict[str, Any]] = None,
        query_parameters: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, str]] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a connector action via the Connectivity API."""

        payload: Dict[str, Any] = {
            "credentialId": credential_id,
        }
        if request_body:
            payload["requestBody"] = request_body
        if query_parameters:
            payload["queryParameters"] = query_parameters
        if path_params:
            payload["pathParams"] = path_params
        if additional_headers:
            payload["additionalHeaders"] = additional_headers

        logger.info(
            "Executing action %s.%s for user %s",
            connector_id,
            action_id,
            user_id,
        )

        # Create a modified request that includes the x-alloy-userid header
        url = f"{self.base_url}/connectors/{connector_id}/actions/{action_id}/execute"
        headers = {**self.headers, "x-alloy-userid": user_id}

        try:
            response = requests.post(
                url=url,
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            if not response.content:
                return {}
            # The execute endpoint returns the full response (not wrapped in "data")
            # Response structure: {"responseData": {...actual data...}, "executionId": "...", "status": "..."}
            execution_response = response.json()
            execution_id = execution_response.get("executionId")
            status = execution_response.get("status")
            logger.info("Execution %s completed with status %s", execution_id, status)
            return execution_response
        except HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            if status == 401:
                raise ConnectivityAuthError("Invalid Alloy API key") from exc
            if status == 429:
                raise ConnectivityRateLimitError("Rate limit exceeded") from exc
            detail = exc.response.text if exc.response else str(exc)
            logger.error("Connectivity API HTTP error %s: %s", status, detail)
            raise ConnectivityAPIError(f"API error {status}: {detail}") from exc
        except RequestException as exc:
            logger.error("Connectivity API request failed: %s", exc)
            raise ConnectivityAPIError(f"Request failed: {exc}") from exc

    def list_orders_shopify(
        self,
        user_id: str,
        credential_id: str,
        *,
        limit: int = 50,
        query: Optional[str] = None,
        connector_id: str = "shopify",
        action_id: str = "listOrders",
    ) -> List[Dict[str, Any]]:
        """Convenience helper for Shopify `listOrders`.

        Args:
            user_id: Alloy user ID
            credential_id: Shopify credential ID
            limit: Number of orders to return (uses 'first' parameter)
            query: GraphQL query string for filtering (e.g., "created_at:>='2024-01-01'")
            connector_id: Connector ID (default: 'shopify')
            action_id: Action ID (default: 'listOrders')

        Returns:
            List of order dictionaries
        """
        query_params: Dict[str, Any] = {"first": limit}
        if query:
            query_params["query"] = query
        response = self.execute_action(
            user_id=user_id,
            connector_id=connector_id,
            action_id=action_id,
            credential_id=credential_id,
            query_parameters=query_params,
        )
        # Extract orders from responseData
        response_data = response.get("responseData", {})

        # Handle GraphQL response structure
        if "data" in response_data and "orders" in response_data["data"]:
            orders_connection = response_data["data"]["orders"]
            if "edges" in orders_connection:
                # GraphQL connection format
                return [edge["node"] for edge in orders_connection.get("edges", [])]
            elif "nodes" in orders_connection:
                return orders_connection["nodes"]

        # Fallback to direct orders array
        return response_data.get("orders", [])

    def post_message_slack(
        self,
        user_id: str,
        credential_id: str,
        *,
        channel: str,
        blocks: List[Dict[str, Any]],
        connector_id: str = "slack",
        action_id: str = "chat_postMessage",
    ) -> Dict[str, Any]:
        """Convenience helper that executes Slack's `chat_postMessage` action."""

        response = self.execute_action(
            user_id=user_id,
            connector_id=connector_id,
            action_id=action_id,
            credential_id=credential_id,
            request_body={"channel": channel, "blocks": blocks},
        )
        return response.get("responseData", {})
