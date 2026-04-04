#!/bin/bash
# add-agent.sh — Create a new agent profile.
#
# Creates the directory structure, config, CLAUDE.md template, and systemd
# services for a new agent. Prompts for Discord bot token and channel info.
#
# Usage:
#   ./scripts/add-agent.sh <profile-name>
#
# Example:
#   ./scripts/add-agent.sh stark

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/.claude-agents"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PROFILE="${1:-}"

if [[ -z "$PROFILE" ]]; then
    echo "Usage: add-agent.sh <profile-name>" >&2
    echo "Example: add-agent.sh stark" >&2
    exit 1
fi

PROFILE_DIR="$AGENTS_DIR/$PROFILE"

if [[ -d "$PROFILE_DIR" ]]; then
    echo "ERROR: Profile '$PROFILE' already exists at $PROFILE_DIR" >&2
    echo "To remove it: ./scripts/remove-agent.sh $PROFILE" >&2
    exit 1
fi

# Check shared framework is installed
if [[ ! -f "$AGENTS_DIR/shared/agent_main.py" ]]; then
    echo "ERROR: Shared framework not installed. Run ./scripts/install.sh first." >&2
    exit 1
fi

echo "=== Creating agent profile: $PROFILE ==="
echo ""

# --- Collect Discord info ---

read -rp "Discord bot token: " DISCORD_TOKEN
read -rp "Discord guild (server) ID: " GUILD_ID
read -rp "Discord channel ID: " CHANNEL_ID
read -rp "Discord user ID (your ID, for allowlist): " USER_ID
echo ""

read -rp "Claude model (sonnet/opus/haiku) [sonnet]: " MODEL
MODEL="${MODEL:-sonnet}"

# --- Create directories ---

echo "[1/5] Creating directory structure..."

mkdir -p "$PROFILE_DIR"/{credentials,workspace/tools,state,logs}

# --- Save credentials ---

echo "[2/5] Saving credentials..."

echo -n "$DISCORD_TOKEN" > "$PROFILE_DIR/credentials/discord-bot-token"
chmod 600 "$PROFILE_DIR/credentials/discord-bot-token"

# --- Create config.json ---

echo "[3/5] Creating config.json..."

cat > "$PROFILE_DIR/config.json" << EOF
{
  "profile": "$PROFILE",
  "discord": {
    "channel_id": "$CHANNEL_ID",
    "guild_id": "$GUILD_ID",
    "user_allowlist": ["$USER_ID"]
  },
  "claude": {
    "model": "$MODEL",
    "max_turns": 25,
    "timeout": 600,
    "allowed_tools": "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
  },
  "trigger": {
    "socket_path": "state/trigger.sock"
  }
}
EOF

# --- Create CLAUDE.md ---

echo "[4/5] Creating workspace CLAUDE.md template..."

sed "s/PROFILE_NAME/$PROFILE/g; s/AGENT_NAME/${PROFILE^}/g" \
    "$REPO_DIR/templates/workspace/CLAUDE.md" \
    > "$PROFILE_DIR/workspace/CLAUDE.md"

# Ensure no MEMORY.md or memory/ in workspace root — context system handles all memory
mkdir -p "$PROFILE_DIR/workspace/context"

# --- Create systemd services ---

echo "[5/5] Creating systemd services..."

mkdir -p "$SYSTEMD_DIR"

for TEMPLATE in claude-agent.service claude-trigger.timer claude-trigger.service claude-briefing.timer claude-briefing.service; do
    # Determine output filename (inject profile name)
    BASENAME="${TEMPLATE%%.*}"
    EXTENSION="${TEMPLATE#*.}"
    OUTPUT_NAME="${BASENAME}-${PROFILE}.${EXTENSION}"

    sed "s/PROFILE_NAME/$PROFILE/g" \
        "$REPO_DIR/templates/systemd/$TEMPLATE" \
        > "$SYSTEMD_DIR/$OUTPUT_NAME"
done

systemctl --user daemon-reload

echo ""
echo "=== Profile '$PROFILE' created ==="
echo ""
echo "Directory:  $PROFILE_DIR"
echo "Config:     $PROFILE_DIR/config.json"
echo "Workspace:  $PROFILE_DIR/workspace/"
echo "CLAUDE.md:  $PROFILE_DIR/workspace/CLAUDE.md"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit CLAUDE.md to define your agent's identity and instructions:"
echo "     \$EDITOR $PROFILE_DIR/workspace/CLAUDE.md"
echo ""
echo "  2. Add any tools (todoist.py, etc.) to the workspace:"
echo "     cp /path/to/todoist.py $PROFILE_DIR/workspace/tools/"
echo ""
echo "  3. Add additional credentials if needed:"
echo "     echo '<token>' > $PROFILE_DIR/credentials/todoist-token"
echo "     chmod 600 $PROFILE_DIR/credentials/todoist-token"
echo ""
echo "  4. Add the profile to the trigger script:"
echo "     Edit ~/.local/bin/claude-trigger.sh to add check_${PROFILE} and briefing_${PROFILE}"
echo ""
echo "  5. Start the agent:"
echo "     systemctl --user enable --now claude-agent-${PROFILE}.service"
echo "     systemctl --user enable --now claude-trigger-${PROFILE}.timer"
echo "     systemctl --user enable --now claude-briefing-${PROFILE}.timer"
echo ""
echo "  6. Verify:"
echo "     systemctl --user status claude-agent-${PROFILE}.service"
echo "     journalctl --user -u claude-agent-${PROFILE}.service -f"
