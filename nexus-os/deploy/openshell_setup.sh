#!/usr/bin/env bash
# openshell_setup.sh — Install NVIDIA OpenShell CLI
# Usage: bash deploy/openshell_setup.sh
set -euo pipefail

echo "═══════════════════════════════════════════════"
echo "  NVIDIA OpenShell CLI — Setup"
echo "═══════════════════════════════════════════════"

# ── 1. Check if already installed ──────────────────
if command -v openshell &>/dev/null; then
  echo "[✓] OpenShell already installed: $(openshell --version 2>&1 || echo 'version check failed')"
  echo "    Path: $(which openshell)"
  exit 0
fi

# ── 2. Detect container runtime ───────────────────
CONTAINER_RT=""
if command -v docker &>/dev/null; then
  CONTAINER_RT="docker"
  echo "[✓] Docker detected"
elif command -v podman &>/dev/null; then
  CONTAINER_RT="podman"
  echo "[✓] Podman detected (rootless mode)"
else
  echo "[!] Neither Docker nor Podman found."
  echo "[i] Installing rootless Podman as fallback..."

  # Detect package manager
  if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq podman
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y -q podman
  elif command -v yum &>/dev/null; then
    sudo yum install -y -q podman
  elif command -v brew &>/dev/null; then
    brew install podman
  else
    echo "[✗] Cannot auto-install Podman. Install Docker or Podman manually."
    exit 1
  fi

  CONTAINER_RT="podman"
  echo "[✓] Podman installed"
fi

# ── 3. Install OpenShell via official installer ────
echo "[i] Downloading OpenShell installer..."

INSTALL_DIR="${HOME}/.nvidia/openshell"
mkdir -p "$INSTALL_DIR"

# Try the official NVIDIA installer script
if curl -fsSL "https://install.nvidia.com/openshell/install.sh" -o /tmp/openshell-install.sh 2>/dev/null; then
  chmod +x /tmp/openshell-install.sh
  bash /tmp/openshell-install.sh --prefix="$INSTALL_DIR"
  rm -f /tmp/openshell-install.sh
else
  echo "[i] Official installer unavailable, trying container-based install..."
  # Fallback: run via container
  if [ "$CONTAINER_RT" = "docker" ]; then
    docker pull nvcr.io/nvidia/openshell:latest
    docker run --rm -v "$INSTALL_DIR:/out" nvcr.io/nvidia/openshell:latest cp /usr/local/bin/openshell /out/
  else
    podman pull nvcr.io/nvidia/openshell:latest
    podman run --rm -v "$INSTALL_DIR:/out:Z" nvcr.io/nvidia/openshell:latest cp /usr/local/bin/openshell /out/
  fi
fi

# ── 4. PATH setup ──────────────────────────────────
echo "[i] Configuring PATH..."

SHELL_RC=""
if [ -n "${BASH_VERSION:-}" ]; then
  SHELL_RC="$HOME/.bashrc"
elif [ -n "${ZSH_VERSION:-}" ]; then
  SHELL_RC="$HOME/.zshrc"
else
  SHELL_RC="$HOME/.profile"
fi

PATH_LINE="export PATH=\"\$HOME/.nvidia/openshell:\$PATH\""
if [ -f "$SHELL_RC" ] && grep -qF ".nvidia/openshell" "$SHELL_RC"; then
  echo "[✓] PATH already configured in $SHELL_RC"
else
  echo "" >> "$SHELL_RC"
  echo "# NVIDIA OpenShell CLI" >> "$SHELL_RC"
  echo "$PATH_LINE" >> "$SHELL_RC"
  echo "[✓] Added OpenShell to PATH in $SHELL_RC"
fi

export PATH="$HOME/.nvidia/openshell:$PATH"

# ── 5. Verify installation ─────────────────────────
echo ""
echo "[i] Verifying installation..."
if command -v openshell &>/dev/null; then
  VERSION=$(openshell --version 2>&1 || echo "installed (version check not supported)")
  echo "[✓] OpenShell installed successfully"
  echo "    Version: $VERSION"
  echo "    Path:    $(which openshell)"
else
  echo "[✗] OpenShell not found in PATH after installation"
  echo "    Try: source $SHELL_RC && openshell --version"
  exit 1
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  Setup complete!"
echo "  Run: source $SHELL_RC  (or open new terminal)"
echo "  Then: openshell --help"
echo "═══════════════════════════════════════════════"
