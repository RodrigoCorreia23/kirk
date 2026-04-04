#!/bin/bash
# remove-agent.sh — Stop and remove an agent profile.
#
# Stops systemd services, disables timers, and optionally deletes the profile
# directory. Credentials are never deleted without confirmation.
#
# Usage:
#   ./scripts/remove-agent.sh <profile-name>

set -euo pipefail

PROFILE="${1:-}"

if [[ -z "$PROFILE" ]]; then
    echo "Usage: remove-agent.sh <profile-name>" >&2
    exit 1
fi

PROFILE_DIR="$HOME/.claude-agents/$PROFILE"
SYSTEMD_DIR="$HOME/.config/systemd/user"

if [[ ! -d "$PROFILE_DIR" ]]; then
    echo "ERROR: Profile '$PROFILE' not found at $PROFILE_DIR" >&2
    exit 1
fi

echo "=== Removing agent profile: $PROFILE ==="
echo ""

# --- Stop services ---

echo "[1/3] Stopping services..."

systemctl --user stop "claude-agent-${PROFILE}.service" 2>/dev/null || true
systemctl --user stop "claude-trigger-${PROFILE}.timer" 2>/dev/null || true
systemctl --user stop "claude-briefing-${PROFILE}.timer" 2>/dev/null || true
systemctl --user disable "claude-agent-${PROFILE}.service" 2>/dev/null || true
systemctl --user disable "claude-trigger-${PROFILE}.timer" 2>/dev/null || true
systemctl --user disable "claude-briefing-${PROFILE}.timer" 2>/dev/null || true

echo "  Services stopped and disabled."

# --- Remove systemd units ---

echo "[2/3] Removing systemd unit files..."

for UNIT in \
    "claude-agent-${PROFILE}.service" \
    "claude-trigger-${PROFILE}.timer" \
    "claude-trigger-${PROFILE}.service" \
    "claude-briefing-${PROFILE}.timer" \
    "claude-briefing-${PROFILE}.service"; do
    rm -f "$SYSTEMD_DIR/$UNIT"
done

systemctl --user daemon-reload
echo "  Unit files removed."

# --- Remove profile directory ---

echo "[3/3] Profile directory: $PROFILE_DIR"
echo ""
read -rp "Delete profile directory and all credentials? (y/N): " CONFIRM

if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    rm -rf "$PROFILE_DIR"
    echo "  Profile directory deleted."
else
    echo "  Profile directory kept. Remove manually:"
    echo "    rm -rf $PROFILE_DIR"
fi

echo ""
echo "=== Profile '$PROFILE' removed ==="
