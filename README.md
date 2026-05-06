# Remote Claude Setup

Run autonomous Claude Code agents on a remote Linux machine, communicating through Discord. Each agent is an isolated profile with its own Discord bot, workspace, credentials, and systemd service.

## How It Works

```
You (phone/laptop)                    Remote Server (Ubuntu)
       |                                     |
  Discord message -----> Discord API ----> discord.py bot
                                             |
                                       claude -p "prompt"
                                             |
                                       Claude Code (Max plan)
                                             |
                                       reads CLAUDE.md,
                                       runs tools (Bash, etc.),
                                       returns result
                                             |
  Discord response <---- Discord API <---- discord.py bot
```

Each agent runs as a systemd user service:
- **Discord bot** (discord.py) listens for messages in an allowlisted channel
- **Trigger listener** (Unix socket) accepts prompts from scheduled condition checks
- **Watchdog** monitors Discord connection health

Scheduled triggers (systemd timers) check for work periodically (e.g., Todoist tasks) and only invoke the agent when there's something to do. This saves tokens and makes usage patterns natural.

## Prerequisites

- Ubuntu 24.04 (or any Linux with systemd and Python 3.10+)
- [Claude Code CLI](https://claude.ai/code) installed
- Claude Max plan subscription ($100/month)
- Logged in: `claude login`
- `ANTHROPIC_API_KEY` must **NOT** be set (forces Max plan auth)
- A Discord bot application per agent ([Discord Developer Portal](https://discord.com/developers/applications))

## Quick Start

### 1. Install the framework

```bash
git clone https://github.com/jborlido/remote-claude-setup.git
cd remote-claude-setup
./scripts/install.sh
```

This installs:
- Shared Python framework to `~/.claude-agents/shared/`
- Trigger script to `~/.local/bin/claude-trigger.sh`
- Python venv with discord.py

### 2. Create an agent

```bash
./scripts/add-agent.sh my-agent
```

The script prompts for:
- Discord bot token
- Discord guild (server) ID
- Discord channel ID
- Your Discord user ID (for the allowlist)
- Claude model (sonnet/opus/haiku)

### 3. Customize the agent

Edit the agent's CLAUDE.md to define its identity and instructions:

```bash
$EDITOR ~/.claude-agents/my-agent/workspace/CLAUDE.md
```

This file is read automatically by Claude Code. It replaces traditional system prompts. Define:
- Agent identity and personality
- Core rules and boundaries
- Heartbeat procedures (what to do when triggered)
- Tool documentation
- User info

### 4. Add tools (optional)

Place CLI scripts in the workspace tools directory:

```bash
cp my-tool.py ~/.claude-agents/my-agent/workspace/tools/
chmod +x ~/.claude-agents/my-agent/workspace/tools/my-tool.py
```

The agent invokes them via Claude Code's built-in Bash tool.

### 5. Set up triggers (optional)

Edit `~/.local/bin/claude-trigger.sh` to add condition checks for your agent. See the commented example in the script for the Todoist task board pattern.

### 6. Start the agent

```bash
systemctl --user enable --now claude-agent-my-agent.service
systemctl --user enable --now claude-trigger-my-agent.timer
systemctl --user enable --now claude-briefing-my-agent.timer
```

### 7. Check status

```bash
./scripts/status.sh
```

## Directory Structure

```
~/.claude-agents/
├── shared/                     # Shared framework (all agents)
│   ├── agent_main.py           # Entrypoint
│   ├── discord_bot.py          # Discord + Claude Code subprocess
│   ├── trigger_handler.py      # Unix socket listener
│   ├── config.py               # Config loader
│   ├── requirements.txt
│   └── .venv/
│
└── <profile>/                  # Per agent
    ├── config.json             # Discord, model, tools config
    ├── credentials/            # Bot tokens, API keys (chmod 600)
    ├── workspace/              # Claude Code working directory
    │   ├── CLAUDE.md           # Agent instructions (auto-read)
    │   └── tools/              # CLI scripts
    ├── state/                  # Runtime (socket, fingerprints)
    └── logs/
```

## Architecture

### Claude Code Invocation

When a Discord message arrives or a trigger fires, the bot spawns:

```
claude -p "prompt" \
  --output-format json \
  --model sonnet \
  --max-turns 25 \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch" \
  --dangerously-skip-permissions
```

The working directory is set to the agent's workspace, so Claude Code reads `CLAUDE.md` automatically.

- **Discord messages** use `--continue` (session context preserved across messages)
- **Trigger prompts** do NOT use `--continue` (fresh context each time)
- `ANTHROPIC_API_KEY` is explicitly unset to force Max plan auth

### Conditional Triggers

Systemd timers fire every 30 minutes (with 0-10 min random jitter). The trigger script:

1. Checks conditions with free API calls (e.g., Todoist HTTP API)
2. Compares a fingerprint to the last run (debounce)
3. Only invokes the agent if conditions changed and work exists
4. Sends the prompt via Unix socket to the running agent process

This pattern reduces Claude calls from ~48/day to ~2-6/day per agent.

### Selective Discord Posting

The `[SILENT]` prefix convention controls what gets posted to Discord:

- Agent responds normally -> posted to Discord
- Agent responds with `[SILENT] reason` -> logged only, not posted

This is configured in CLAUDE.md:
> When triggered and there is nothing to do, respond with exactly `[SILENT]` followed by a short reason.

## Managing Agents

```bash
# Check all agents
./scripts/status.sh

# View logs
journalctl --user -u claude-agent-<profile>.service -f

# Restart an agent
systemctl --user restart claude-agent-<profile>.service

# Stop an agent
systemctl --user stop claude-agent-<profile>.service

# Remove an agent
./scripts/remove-agent.sh <profile>

# Test trigger manually
~/.local/bin/claude-trigger.sh <profile>

# Send a test prompt to the agent socket
echo "Say hello" | socat - UNIX-CONNECT:~/.claude-agents/<profile>/state/trigger.sock
```

## Conversation Context

The framework includes a session tracking and context memory system:

- **Within 10 minutes:** Messages share a Claude session (full conversational context via `--session-id`/`--resume`)
- **After 10 min inactivity:** Session closes, Claude generates a summary saved to `context/YYYY-MM-DD-HHhMM.md`
- **Cross-session recall:** Summaries indexed in `context/INDEX.md` by topic. Agent looks up past conversations on demand (when you reference "remember when we...")
- **Threads:** Each Discord thread gets its own persistent session (never expires)
- **Triggers:** Run ephemeral (no session tracking, no interference)

**Important:** Do NOT place `MEMORY.md` or `memory/` directories in the workspace root. Claude Code auto-reads all `.md` files in the working directory, which causes unbounded context growth. The `context/` system replaces manual memory files entirely.

## Security

- Each agent's credentials are in `credentials/` with `chmod 600`
- Discord allowlist restricts which guild, channel, and user can interact
- `--dangerously-skip-permissions` is scoped to the agent's workspace directory
- No API keys in environment variables or systemd unit files
- Agents cannot access each other's workspaces or credentials

## License

MIT
