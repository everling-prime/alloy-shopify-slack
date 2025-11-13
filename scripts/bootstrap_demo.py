#!/usr/bin/env python3
"""One-stop bootstrapper for the Shopify → Slack Connectivity demo."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
ENV_TEMPLATE = PROJECT_ROOT / ".env.example"

sys.path.insert(0, str(PROJECT_ROOT))
from setup_credentials import SetupOptions, SetupError, bootstrap  # noqa: E402
from scripts.bootstrap_support import (  # noqa: E402
    ensure_env_file,
    run_post_setup_verification,
    run_uv_sync,
    set_env_values,
)


def prompt_required(prompt: str, *, default: str | None = None, secret: bool = False) -> str:
    """Prompt the user for a value, optionally supplying a default."""

    while True:
        if secret:
            value = getpass.getpass(f"{prompt}: " if default is None else f"{prompt} [hidden]: ").strip()
        else:
            suffix = f" [{default}]" if default else ""
            value = input(f"{prompt}{suffix}: ").strip()

        if value:
            return value
        if default:
            return default
        print("This value is required. Please try again.")


def prompt_yes_no(question: str, *, default: bool = True) -> bool:
    """Prompt for a yes/no response."""

    suffix = "Y/n" if default else "y/N"
    while True:
        response = input(f"{question} ({suffix}): ").strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please enter 'y' or 'n'.")
def main() -> None:
    print("=" * 72)
    print("Alloy Connectivity API - Guided Bootstrap")
    print("=" * 72)

    api_key = prompt_required("Enter your Alloy API key", secret=True)
    shop_domain = prompt_required("Enter your Shopify store domain (subdomain or full domain)")
    slack_channel = prompt_required("Enter the Slack channel ID that should receive notifications")
    username = prompt_required("Enter the Alloy username/email", default="connectivity-demo-user")
    full_name = prompt_required("Enter the Alloy user's full name", default="Connectivity Demo User")
    skip_uv_sync = prompt_yes_no("Skip running `uv sync`?", default=False)
    skip_verify = prompt_yes_no("Skip post-setup verification?", default=False)
    open_browser = prompt_yes_no("Open OAuth URLs in your browser automatically?", default=True)

    ensure_env_file(ENV_PATH, ENV_TEMPLATE)
    set_env_values(
        ENV_PATH,
        {
            "ALLOY_API_KEY": api_key,
            "SHOPIFY_STORE_DOMAIN": shop_domain,
            "SLACK_CHANNEL_ID": slack_channel,
        },
    )

    run_uv_sync(skip_uv_sync)

    options = SetupOptions(
        api_key=api_key,
        username=username,
        full_name=full_name,
        shop_domain=shop_domain,
        slack_channel_id=slack_channel,
        non_interactive=False,
        open_browser=open_browser,
    )

    try:
        result = bootstrap(options)
    except SetupError as exc:
        print(f"\n✗ Bootstrap failed: {exc}")
        sys.exit(1)

    if not skip_verify:
        run_post_setup_verification(result)


if __name__ == "__main__":
    main()
