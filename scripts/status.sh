#!/bin/bash
# status.sh — Show status of all Claude agent profiles.
#
# Usage:
#   ./scripts/status.sh

set -euo pipefail

AGENTS_DIR="$HOME/.claude-agents"

echo "=== Claude Agent Status ==="
echo ""

# Find all profiles (directories with config.json)
FOUND=0
for PROFILE_DIR in "$AGENTS_DIR"/*/; do
    [[ -f "$PROFILE_DIR/config.json" ]] || continue
    PROFILE=$(basename "$PROFILE_DIR")
    FOUND=$((FOUND + 1))

    # Service status
    SERVICE_STATUS=$(systemctl --user is-active "claude-agent-${PROFILE}.service" 2>/dev/null || echo "not found")
    TRIGGER_STATUS=$(systemctl --user is-active "claude-trigger-${PROFILE}.timer" 2>/dev/null || echo "not found")
    BRIEFING_STATUS=$(systemctl --user is-active "claude-briefing-${PROFILE}.timer" 2>/dev/null || echo "not found")

    # Model from config
    MODEL=$(python3 -c "import json; print(json.load(open('${PROFILE_DIR}config.json'))['claude']['model'])" 2>/dev/null || echo "?")

    # Status indicator
    if [[ "$SERVICE_STATUS" == "active" ]]; then
        INDICATOR="[running]"
    elif [[ "$SERVICE_STATUS" == "inactive" ]]; then
        INDICATOR="[stopped]"
    elif [[ "$SERVICE_STATUS" == "failed" ]]; then
        INDICATOR="[FAILED]"
    else
        INDICATOR="[?]"
    fi

    printf "%-10s %-10s  model=%-8s  agent=%-8s  trigger=%-8s  briefing=%-8s\n" \
        "$PROFILE" "$INDICATOR" "$MODEL" "$SERVICE_STATUS" "$TRIGGER_STATUS" "$BRIEFING_STATUS"
done

if [[ $FOUND -eq 0 ]]; then
    echo "No agent profiles found in $AGENTS_DIR"
    echo "Create one with: ./scripts/add-agent.sh <name>"
fi

echo ""

# Show timers
TIMER_COUNT=$(systemctl --user list-timers 2>/dev/null | grep -c "claude-" || true)
if [[ $TIMER_COUNT -gt 0 ]]; then
    echo "--- Timers ---"
    systemctl --user list-timers 2>/dev/null | grep "claude-"
fi
