#!/usr/bin/env bash
# gastown_quickstart.sh — One-shot deployment for Gastown Towns & Rigs
# Usage: bash deploy/gastown_quickstart.sh [repo_path]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(dirname "$SCRIPT_DIR")}"
cd "$REPO_ROOT"

echo "═══════════════════════════════════════════════"
echo "  Gastown Towns & Rigs — Quickstart Deployer"
echo "═══════════════════════════════════════════════"

# ── 1. Clone or verify repo ──────────────────────
if [ -d ".git" ]; then
  echo "[✓] Using existing repo at $REPO_ROOT"
else
  echo "[i] Not a git repo. Initializing..."
  git init
  echo "[✓] Git repo initialized"
fi

# ── 2. Install Python dependencies ───────────────
echo "[i] Checking Python dependencies..."

install_pkg() {
  local pkg="$1"
  if python3 -c "import $pkg" 2>/dev/null; then
    echo "  [✓] $pkg already installed"
  else
    echo "  [i] Installing $pkg..."
    pip install "$pkg" --quiet
    echo "  [✓] $pkg installed"
  fi
}

install_pkg "pymilvus"
install_pkg "dotenv"
install_pkg "pydantic"

# ── 3. Create .env template ──────────────────────
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  echo "[✓] .env already exists (not overwriting)"
else
  cat > "$ENV_FILE" <<'ENVEOF'
# ─── Zilliz Serverless Cluster ───────────────────
# Used for: EVENT, FAILURE_PATTERN tracks
ZILLIZ_SERVERLESS_URI=https://your-project.api.gcp-us-west1.zillizcloud.com
ZILLIZ_SERVERLESS_TOKEN=your-serverless-token

# ─── Zilliz Town Cluster ─────────────────────────
# Used for: TRUST, GOVERNANCE, CAPABILITY tracks
ZILLIZ_TOWN_URI=https://your-town-cluster.api.gcp-us-west1.zillizcloud.com
ZILLIZ_TOWN_TOKEN=your-town-token

# ─── Gastown / Nexus Config ──────────────────────
NEXUS_VERSION=25
GASTOWN_LOG_LEVEL=info
ENVEOF
  echo "[✓] Created .env template — edit with your Zilliz credentials"
fi

# ── 4. Health check ──────────────────────────────
echo ""
echo "[i] Running health check..."
if python3 "$SCRIPT_DIR/zilliz_client.py" 2>/dev/null; then
  echo "[✓] Zilliz client health check passed"
else
  echo "[!] Health check could not complete (expected if .env not yet configured)"
fi

# ── 5. Boot nexus25 ──────────────────────────────
echo ""
echo "[i] Booting Nexus v25..."
if [ -f "$SCRIPT_DIR/mission_router.py" ]; then
  python3 -c "
import sys, importlib.util
spec = importlib.util.spec_from_file_location('mr', '$SCRIPT_DIR/mission_router.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('[✓] Mission router loaded successfully')
print('    Available modes:', list(mod.MODE_HANDLERS.keys()) if hasattr(mod, 'MODE_HANDLERS') else '(check module)')
"
else
  echo "[!] mission_router.py not found"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  Deployment complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your Zilliz cluster credentials"
echo "    2. Run: python3 deploy/zilliz_client.py   # verify connectivity"
echo "    3. Run: python3 deploy/mission_router.py  # test routing"
echo "═══════════════════════════════════════════════"
