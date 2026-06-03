#!/usr/bin/env bash
set -e


# Requires: pip install uv  (or: curl -LsSf https://astral.sh/uv/install.sh | sh)
uv venv --python 3.12 .venv
source .venv/bin/activate

echo "Setup complete. Activate your environment with:"
echo "source .venv/bin/activate"
