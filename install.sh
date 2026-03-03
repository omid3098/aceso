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

# If current dir is already a git repo (e.g. cloned manually), use it
if git rev-parse --git-dir >/dev/null 2>&1; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel)"
  echo "Using existing repo at: $PROJECT_ROOT"
  cd "$PROJECT_ROOT"
else
  # Clone into INSTALL_DIR
  if [ -d "$INSTALL_DIR" ]; then
    echo "Directory exists: $INSTALL_DIR"
    if [ -d "$INSTALL_DIR/.git" ]; then
      PROJECT_ROOT="$INSTALL_DIR"
      cd "$PROJECT_ROOT"
      git pull || true
    else
      echo "Not a git repo. Clone into a new folder? (y/n)"
      read -r ans
      if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
        echo "Aborted."
        exit 1
      fi
      git clone "$REPO_URL" "$INSTALL_DIR.clone"
      rm -rf "$INSTALL_DIR"
      mv "$INSTALL_DIR.clone" "$INSTALL_DIR"
      PROJECT_ROOT="$INSTALL_DIR"
      cd "$PROJECT_ROOT"
    fi
  else
    git clone "$REPO_URL" "$INSTALL_DIR"
    PROJECT_ROOT="$INSTALL_DIR"
    cd "$PROJECT_ROOT"
  fi
fi

# Virtual environment
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi
# Activate for this script (and child processes)
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
