#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Hakumo (New-Pro).
# No Discord TOKEN required — tests and demo panel work without it.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt -r requirements-panel.txt --quiet
.venv/bin/python -c "import discord, flask, dotenv; print('deps ok', discord.__version__)"
