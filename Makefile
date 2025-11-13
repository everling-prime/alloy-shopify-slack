SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables

.PHONY: bootstrap run run-continuous verify status

bootstrap:
	uv run python scripts/bootstrap_demo.py

run:
	uv run python -m src.main

run-continuous:
	uv run python -m src.main --continuous

verify:
	uv run python scripts/verify_connectivity.py status

status:
	uv run python scripts/verify_connectivity.py list-orders --limit 5
