#!/usr/bin/env bash
# One-liner installer for Health Tracker Bot.
# Usage: curl -sSL https://raw.githubusercontent.com/omid3098/aceso/main/install.sh | bash
#    or: curl -sSL https://raw.githubusercontent.com/omid3098/aceso/main/install.sh | bash -s -- /path/to/install
# For Linux/macOS (VPS). Not for Windows.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/omid3098/aceso.git}"
INSTALL_DIR="${1:-$HOME/health-tracker-bot}"

echo "Health Tracker Bot - Installer"
echo "Install directory: $INSTALL_DIR"
echo ""

# ── Bootstrap ────────────────────────────────────────────────────────────────
# When piped via `curl | bash`, bash reads the script from the pipe and keeps
# executing that in-memory copy even after `git pull` updates files on disk.
# Fix: clone/pull first, then `exec` the fresh on-disk copy so the rest of
# the installation always runs from the latest code.
# _ACESO_FROM_DISK is exported before exec to prevent an infinite loop.
if [ -z "${_ACESO_FROM_DISK:-}" ]; then
  if git -C "$INSTALL_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    echo "Updating existing installation..."
    git -C "$INSTALL_DIR" pull || true
  elif [ -d "$INSTALL_DIR" ]; then
    echo "Directory '$INSTALL_DIR' exists but is not a git repo. Re-cloning..."
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  export _ACESO_FROM_DISK=1
  exec bash "$INSTALL_DIR/install.sh" "$INSTALL_DIR"
fi

# ── Everything below runs from the on-disk copy ──────────────────────────────
cd "$INSTALL_DIR"

# Helper: create venv
try_venv() {
  python3 -m venv venv
}

# Helper: install python3.X-venv on Debian/Ubuntu when ensurepip is missing
install_venv_package() {
  PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "3")"
  if [ -f /etc/debian_version ] || grep -qEi 'debian|ubuntu' /etc/os-release 2>/dev/null; then
    echo "python3-venv (ensurepip) is missing. Required package: python${PY_VER}-venv"
    if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
      echo "Installing python${PY_VER}-venv (running as root)..."
      apt-get update -qq && apt-get install -y "python${PY_VER}-venv"
    else
      echo "Run: sudo apt-get update && sudo apt-get install -y python${PY_VER}-venv"
      exit 1
    fi
  else
    echo "Please install Python venv/ensurepip for your distribution and re-run."
    exit 1
  fi
}

# Create venv if missing or broken (venv/bin/activate absent = broken)
if [ ! -f "venv/bin/activate" ]; then
  [ -d "venv" ] && rm -rf venv
  echo "Creating virtual environment..."
  if ! try_venv; then
    install_venv_package
    rm -rf venv
    try_venv
  fi
fi

# shellcheck source=/dev/null
source venv/bin/activate

echo "Upgrading pip..."
pip install -q --upgrade pip

echo "Installing requirements..."
pip install -q -r requirements.txt

# .env from example if missing
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example - please set BOT_TOKEN and ADMIN_IDS in the TUI."
fi

echo ""
echo "Setup complete. Launching management TUI..."
echo ""

exec python manage.py
