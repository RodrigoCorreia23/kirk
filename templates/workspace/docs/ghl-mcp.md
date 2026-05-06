# GoHighLevel MCP — operating inside a sub-account

The MCP gives you direct, location-scoped access to a GoHighLevel sub-account
(contacts, pipelines, calendars, conversations, tags, custom fields, social
posts, etc.). It complements `./tools/ghl_tool.py`, which handles
agency-level ops (creating sub-accounts, listing snapshots).

## When to use which

| You want to... | Use |
|---|---|
| Create a new sub-account from snapshot | `./tools/ghl_tool.py create-location` |
| List snapshots / locations across the agency | `./tools/ghl_tool.py list-snapshots/locations` |
| Read or change anything inside a specific sub-account (a contact, a deal, a calendar event, send a message) | MCP tools — `mcp__ghl-<location-key>__*` |

## Configured locations

The Claude Code config (`~/.claude.json`) defines one MCP server per
sub-account you have access to. Each is keyed by a short name:

- `ghl-honor` — HONOR GROWTH (location id `mKe7QyNomTBlKgcPPJI2`)

When new client sub-accounts are cloned, the user creates a new
location-level Private Integration Token in that sub-account and adds a
matching MCP server entry (e.g. `ghl-newclient1`) to `~/.claude.json`.
You CANNOT create or modify these MCP entries yourself — they require a
PIT created via the GHL UI.

## Tool naming

Each MCP server exposes tools under `mcp__<server-key>__<tool-name>`. To
discover them in a session, just call any one and Claude Code will offer
suggestions, or ask the runtime via the conversation.

## Confirmation rule (HARD)

**Reads** (`*-get-*`, `*-list-*`, `*-search-*`, `*-fetch-*`): free.

**Writes** (anything that creates, edits, deletes, sends, schedules):
**confirm in Discord first.** Describe what you'll do (which contact,
which pipeline stage, what message body, etc.) and wait for explicit
"yes" / "avança" / "ok" before executing.

## Credentials hygiene

The PIT for each sub-account lives in `~/.claude.json`. Never `cat` that
file, never echo the token in any Discord response, and never include
the token in commands you write to logs.
