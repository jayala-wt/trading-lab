#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${ALPACA_MCP_DIR:-$HOME/services/alpaca-mcp-server}"

mkdir -p "$INSTALL_DIR"

if ! command -v uvx >/dev/null 2>&1; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Installing uv (official method)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  echo "uv installed. Restart your shell if uvx is not recognized."
fi

cd "$INSTALL_DIR"

# Official Alpaca MCP init (creates local .env and metadata)
uvx alpaca-mcp-server init

if [[ ! -f .env ]]; then
  cat <<'ENV' > .env
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ENV
  echo "Created .env template in $INSTALL_DIR"
fi

echo "Alpaca MCP server initialized in $INSTALL_DIR"
