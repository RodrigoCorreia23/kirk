#!/bin/bash
# claude-trigger.sh — Condition-gated agent triggers for Claude Code agents.
#
# This script checks conditions (free API calls) before invoking the agent.
# Only sends a prompt when there is actual work to do, saving tokens.
#
# Add a check_<profile> and briefing_<profile> function for each agent.
# The example below shows a Todoist-based task board pattern.
#
# Usage:
#   claude-trigger.sh <profile>           # conditional check
#   claude-trigger.sh <profile> --daily   # unconditional morning briefing
#
# Install to: ~/.local/bin/claude-trigger.sh

set -euo pipefail

PROFILE="${1:-}"
DAILY="${2:-}"

if [[ -z "$PROFILE" ]]; then
    echo "Usage: claude-trigger.sh <profile> [--daily]" >&2
    exit 1
fi

LOG_PREFIX="$(date -u +%Y-%m-%dT%H:%M:%SZ) [trigger:${PROFILE}]"
STATE_DIR="$HOME/.local/state/claude-triggers"
mkdir -p "$STATE_DIR"

log() { echo "${LOG_PREFIX} $*"; }

# ---------------------------------------------------------------------------
# Debounce — skip agent call if conditions haven't changed since last run
# ---------------------------------------------------------------------------

debounce_check() {
    local profile="$1"
    local fingerprint="$2"
    local state_file="${STATE_DIR}/${profile}.fingerprint"

    if [[ -f "$state_file" ]] && [[ "$(cat "$state_file")" == "$fingerprint" ]]; then
        return 0  # same as last time — skip
    fi
    return 1  # new conditions — run
}

debounce_save() {
    local profile="$1"
    local fingerprint="$2"
    echo "$fingerprint" > "${STATE_DIR}/${profile}.fingerprint"
}

debounce_clear() {
    local profile="$1"
    rm -f "${STATE_DIR}/${profile}.fingerprint"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

trigger_agent() {
    local profile="$1"
    local message="$2"
    local socket_path="$HOME/.claude-agents/${profile}/state/trigger.sock"

    log "Triggering agent with: ${message:0:100}..."
    if [[ ! -S "$socket_path" ]]; then
        log "ERROR: Socket not found at $socket_path — is claude-agent-${profile}.service running?"
        return 1
    fi
    echo "$message" | socat - UNIX-CONNECT:"$socket_path"
}

# Parse JSON array length from todoist.py --json output.
json_count() {
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        print(len(data))
    elif isinstance(data, dict) and 'results' in data:
        print(len(data['results']))
    else:
        print(0)
except:
    print(0)
"
}

# Extract first task title and ID from todoist.py --json output.
first_task_info() {
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tasks = data if isinstance(data, list) else data.get('results', [])
    if tasks:
        t = tasks[0]
        tid = t.get('id', 'unknown')
        title = t.get('content', t.get('title', 'untitled'))
        print(f'{tid}|{title}')
    else:
        print('')
except:
    print('')
"
}

# ---------------------------------------------------------------------------
# Example: task board agent (Todoist DOING/NEEDS REVIEW/TODO pattern)
#
# Copy and adapt for each profile. Update the TODOIST variable to point
# to the profile's todoist.py script.
# ---------------------------------------------------------------------------

# TODOIST_example="$HOME/.claude-agents/example/workspace/tools/todoist.py"
#
# check_example() {
#     local doing_output doing_count
#     doing_output=$("$TODOIST_example" list --section DOING --json 2>/dev/null) || true
#     doing_count=$(echo "$doing_output" | json_count)
#     if (( doing_count > 0 )); then
#         log "DOING has ${doing_count} task(s) — busy, skipping"
#         debounce_clear example
#         return 0
#     fi
#
#     local review_output review_count
#     review_output=$("$TODOIST_example" list --section "NEEDS REVIEW" --json 2>/dev/null) || true
#     review_count=$(echo "$review_output" | json_count)
#     if (( review_count > 0 )); then
#         log "NEEDS REVIEW has ${review_count} task(s) — waiting, skipping"
#         debounce_clear example
#         return 0
#     fi
#
#     local todo_output todo_info task_id task_title
#     todo_output=$("$TODOIST_example" list --section TODO --json 2>/dev/null) || true
#     todo_info=$(echo "$todo_output" | first_task_info)
#     if [[ -z "$todo_info" ]]; then
#         log "TODO is empty — skipping"
#         debounce_clear example
#         return 0
#     fi
#
#     task_id="${todo_info%%|*}"
#     task_title="${todo_info#*|}"
#
#     if debounce_check example "$task_id"; then
#         log "Same TODO task (${task_id}) as last trigger — skipping agent call"
#         return 0
#     fi
#
#     trigger_agent example \
#         "Trigger: You have a task waiting in TODO. Next task: \"${task_title}\" (${task_id}).
#
# Follow your Heartbeat Procedures in CLAUDE.md — check board state, then pick up the task."
#     debounce_save example "$task_id"
# }
#
# briefing_example() {
#     trigger_agent example \
#         "Morning briefing: Check all board sections (TODO, DOING, NEEDS REVIEW) and post a status summary."
# }

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Add your profiles to this case statement:
case "$PROFILE" in
    # example)
    #     if [[ "$DAILY" == "--daily" ]]; then
    #         log "Running daily briefing"
    #         briefing_example
    #     else
    #         log "Running condition check"
    #         check_example
    #     fi
    #     ;;
    *)
        echo "Unknown profile: $PROFILE" >&2
        echo "Add a check_${PROFILE} function to this script." >&2
        exit 1
        ;;
esac
