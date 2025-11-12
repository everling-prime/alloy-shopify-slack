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
        base_url: str = "https://api.runalloy.com",
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.api_version = api_version
        self.base_url = f"{base_url.rstrip('/')}/{api_version}"
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

    def create_user(self, username: str) -> Dict[str, Any]:
        """Create a Connectivity API user for multi-tenancy."""

        logger.info("Creating Alloy user %s", username)
        response = self._make_request(
            method="POST",
            endpoint="/users",
            json_data={"username": username},
        )
        return response.get("data", {})

    def list_connectors(self) -> List[Dict[str, Any]]:
        """Return the catalog of available connectors."""

        response = self._make_request(method="GET", endpoint="/connectors")
        connectors = response.get("data", [])
        logger.info("Connectivity API returned %s connectors", len(connectors))
        return connectors

    def get_connector_resources(self, connector_id: str) -> List[Dict[str, Any]]:
        """Return resource metadata for a specific connector."""

        response = self._make_request(
            method="GET",
            endpoint=f"/connectors/{connector_id}/resources",
        )
        resources = response.get("data", [])
        logger.info("Connector %s exposes %s resources", connector_id, len(resources))
        return resources

    def get_action_details(self, connector_id: str, action_id: str) -> Dict[str, Any]:
        """Fetch the schema for a connector action."""

        response = self._make_request(
            method="GET",
            endpoint=f"/connectors/{connector_id}/actions/{action_id}",
        )
        return response.get("data", {})

    def create_credential(
        self,
        user_id: str,
        connector_id: str,
        credential_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a credential for a connector (OAuth/API key)."""

        payload = {"connectorId": connector_id, **credential_data}
        response = self._make_request(
            method="POST",
            endpoint=f"/users/{user_id}/credentials",
            json_data=payload,
        )
        data = response.get("data", {})
        if "oauthUrl" in data:
            logger.info("OAuth URL generated for %s: %s", connector_id, data["oauthUrl"])
        if "credentialId" in data:
            logger.info("Credential created: %s", data["credentialId"])
        return data

    def list_credentials(
        self, user_id: str, connector_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List credentials owned by the specified user."""

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
            "connectorId": connector_id,
            "actionId": action_id,
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
        response = self._make_request(
            method="POST",
            endpoint=f"/users/{user_id}/executions",
            json_data=payload,
        )
        execution_data = response.get("data", {})
        execution_id = execution_data.get("executionId")
        status = execution_data.get("status")
        logger.info("Execution %s completed with status %s", execution_id, status)
        return execution_data

    def list_orders_shopify(
        self,
        user_id: str,
        credential_id: str,
        *,
        limit: int = 50,
        status: str = "any",
        created_at_min: Optional[str] = None,
        connector_id: str = "shopify",
        action_id: str = "listOrders",
    ) -> List[Dict[str, Any]]:
        """Convenience helper for Shopify `listOrders`."""

        query_params: Dict[str, Any] = {"limit": limit, "status": status}
        if created_at_min:
            query_params["created_at_min"] = created_at_min
        response = self.execute_action(
            user_id=user_id,
            connector_id=connector_id,
            action_id=action_id,
            credential_id=credential_id,
            query_parameters=query_params,
        )
        return response.get("responseData", {}).get("orders", [])

    def post_message_slack(
        self,
        user_id: str,
        credential_id: str,
        *,
        channel: str,
        blocks: List[Dict[str, Any]],
        connector_id: str = "slack",
        action_id: str = "postMessage",
    ) -> Dict[str, Any]:
        """Convenience helper that executes Slack's `postMessage`."""

        response = self.execute_action(
            user_id=user_id,
            connector_id=connector_id,
            action_id=action_id,
            credential_id=credential_id,
            request_body={"channel": channel, "blocks": blocks},
        )
        return response.get("responseData", {})
