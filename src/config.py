"""Configuration management using Pydantic settings."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    # Alloy Connectivity API configuration
    alloy_api_key: str
    alloy_api_version: str = "2025-09"

    # User (required for multi-tenancy)
    alloy_user_id: str

    # Credential IDs created after authenticating connectors
    shopify_credential_id: str
    slack_credential_id: str

    # Connector IDs (from Alloy's connector catalog)
    shopify_connector_id: str = "shopify"
    slack_connector_id: str = "slack"

    # Business configuration
    order_value_threshold: float = 500.0
    slack_channel_id: str

    # Shopify store info
    shopify_store_domain: Optional[str] = None

    # Polling configuration
    check_interval_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
