#!/bin/bash
# install.sh — Install the shared framework and dependencies.
#
# Run once on a fresh Ubuntu machine. Installs the shared Python framework
# that all agent profiles use.
#
# Prerequisites:
#   - Ubuntu 24.04 (or any systemd Linux with Python 3.12+)
#   - Claude Code CLI installed and logged in (claude login)
#   - sudo access (for socat)
#
# Usage:
#   ./scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/.claude-agents"
SHARED_DIR="$AGENTS_DIR/shared"

echo "=== Remote Claude Setup — Install ==="
echo ""

# --- Check prerequisites ---

echo "[1/5] Checking prerequisites..."

if ! command -v claude &>/dev/null; then
    echo "ERROR: Claude Code CLI not found. Install it first:"
    echo "  https://claude.ai/code"
    exit 1
fi
echo "  Claude Code CLI: $(claude --version 2>/dev/null || echo 'found')"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYTHON_VERSION"

if ! python3 -c "import sys; assert sys.version_info >= (3, 10)" 2>/dev/null; then
    echo "ERROR: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi

if ! command -v socat &>/dev/null; then
    echo "  socat: not found — installing..."
    sudo apt-get update -qq && sudo apt-get install -y -qq socat
    echo "  socat: installed"
else
    echo "  socat: found"
fi

# --- Create shared directory ---

echo ""
echo "[2/5] Creating shared framework directory..."

mkdir -p "$SHARED_DIR"

# --- Copy framework files ---

echo "[3/5] Copying framework files..."

cp "$REPO_DIR/framework/config.py" "$SHARED_DIR/"
cp "$REPO_DIR/framework/discord_bot.py" "$SHARED_DIR/"
cp "$REPO_DIR/framework/trigger_handler.py" "$SHARED_DIR/"
cp "$REPO_DIR/framework/session_manager.py" "$SHARED_DIR/"
cp "$REPO_DIR/framework/agent_main.py" "$SHARED_DIR/"
cp "$REPO_DIR/framework/requirements.txt" "$SHARED_DIR/"

chmod +x "$SHARED_DIR/agent_main.py"

# Copy shared tools
mkdir -p "$SHARED_DIR/tools"
for TOOL in discord_tool.py elevenlabs_tool.py make_tool.py ghl_tool.py; do
    if [[ -f "$REPO_DIR/framework/tools/$TOOL" ]]; then
        cp "$REPO_DIR/framework/tools/$TOOL" "$SHARED_DIR/tools/"
        chmod +x "$SHARED_DIR/tools/$TOOL"
    fi
done

# --- Create Python venv ---

echo "[4/5] Setting up Python virtual environment..."

if [[ ! -d "$SHARED_DIR/.venv" ]]; then
    python3 -m venv "$SHARED_DIR/.venv"
fi
"$SHARED_DIR/.venv/bin/pip" install -q -r "$SHARED_DIR/requirements.txt"

echo "  Installed: $(${SHARED_DIR}/.venv/bin/pip show discord.py 2>/dev/null | grep Version)"

# --- Copy trigger script ---

echo "[5/5] Installing trigger script..."

mkdir -p "$HOME/.local/bin"
cp "$REPO_DIR/scripts/claude-trigger.sh" "$HOME/.local/bin/claude-trigger.sh"
chmod +x "$HOME/.local/bin/claude-trigger.sh"

echo ""
echo "=== Install complete ==="
echo ""
echo "Shared framework installed to: $SHARED_DIR"
echo "Trigger script installed to:   $HOME/.local/bin/claude-trigger.sh"
echo ""
echo "Next: Create an agent profile with:"
echo "  ./scripts/add-agent.sh <profile-name>"
