"""Shared helpers for bootstrap scripts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, TYPE_CHECKING

from dotenv import load_dotenv, set_key

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from setup_credentials import SetupResult


def ensure_env_file(env_path: Path, template_path: Path) -> None:
    """Ensure a .env file exists (copying from the template if needed)."""

    if env_path.exists():
        return
    if not template_path.exists():
        raise FileNotFoundError(
            f"Cannot create {env_path} because template {template_path} is missing."
        )
    shutil.copy(template_path, env_path)
    print(f"✓ Created {env_path.name} from {template_path.name}")


def set_env_values(env_path: Path, values: Dict[str, str]) -> None:
    """Persist a batch of key/value pairs into the .env file."""

    load_dotenv(env_path, override=False)
    for key, value in values.items():
        set_key(env_path, key, value)
        print(f"✓ Updated .env: {key}={value}")


def run_uv_sync(skip: bool) -> None:
    """Optionally invoke `uv sync` to install dependencies."""

    if skip:
        return

    print("🔧 Running `uv sync` to install dependencies…")
    subprocess.run(["uv", "sync"], check=True)


def run_post_setup_verification(result: "SetupResult") -> None:
    """Execute basic verification helpers after provisioning credentials."""

    from scripts.verify_connectivity import run_chat_post, run_list_orders, run_status

    print("\n🔍 Running post-setup verification…")
    run_status()
    run_list_orders(limit=3, query=None)
    run_chat_post(text="Connectivity API bootstrap validation 👍", dry_run=True, channel=None)
    print(f"\n✅ Verification complete for user {result.user_id}")
