#!/usr/bin/env bash
# NEXUS OS — Quick Boot
# Usage: bash boot.sh [install|test|status|interactive]
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

case "${1:-install}" in
  install)
    echo "▸ Installing NEXUS OS..."
    pip install -e ".[dev]" 2>&1 | tail -3
    echo "✓ Installed. Run: nexusctl status"
    ;;
  test)
    echo "▸ Running smoke tests..."
    pytest tests/ -v --tb=short
    ;;
  status)
    nexusctl status
    ;;
  providers)
    nexusctl providers
    ;;
  interactive)
    nexusctl interactive
    ;;
  all)
    echo "▸ Full boot: install → test → status"
    pip install -e ".[dev]" 2>&1 | tail -3
    echo ""
    pytest tests/ -v --tb=short
    echo ""
    nexusctl status
    ;;
  *)
    echo "Usage: bash boot.sh [install|test|status|providers|interactive|all]"
    exit 1
    ;;
esac
