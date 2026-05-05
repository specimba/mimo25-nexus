#!/usr/bin/env bash
# NEXUS 25 — Quick Boot
# Usage: bash boot.sh [install|test|status|providers|interactive|deploy|all]
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

case "${1:-install}" in
  install)
    echo "▸ Installing NEXUS 25..."
    pip install -e ".[dev]" 2>&1 | tail -3
    echo "✓ Installed. Run: nexus25 status"
    ;;
  test)
    echo "▸ Running smoke tests..."
    pytest tests/ -v --tb=short
    ;;
  status)
    nexus25 status
    ;;
  providers)
    nexus25 providers
    ;;
  interactive)
    nexus25 interactive
    ;;
  deploy)
    echo "▸ Gastown quick deploy..."
    bash deploy/gastown_quickstart.sh
    ;;
  all)
    echo "▸ Full boot: install → test → status"
    pip install -e ".[dev]" 2>&1 | tail -3
    echo ""
    pytest tests/ -v --tb=short
    echo ""
    nexus25 status
    ;;
  *)
    echo "Usage: bash boot.sh [install|test|status|providers|interactive|deploy|all]"
    exit 1
    ;;
esac
