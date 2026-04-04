#!/usr/bin/env python3
"""
discord_tool.py — Discord CLI for Claude Code agents.

Interact with Discord channels and threads via the Discord REST API.
Reads credentials from the agent's credentials/ directory.

Usage:
  discord_tool.py create-thread --name NAME [--channel CHANNEL_ID] [--message MESSAGE] [--message-file FILE] [--json]
  discord_tool.py send --channel CHANNEL_ID --message MESSAGE [--json]
  discord_tool.py send --channel CHANNEL_ID --message-file FILE [--json]
  discord_tool.py list-threads [--channel CHANNEL_ID] [--json]
  discord_tool.py read-messages --channel CHANNEL_ID [--limit N] [--json]

Thread creation posts in the agent's configured channel by default.
Messages longer than 2000 chars are automatically split into multiple posts.

Credential discovery: walks up from cwd to find credentials/discord-bot-token
and config.json in the agent profile directory.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://discord.com/api/v10"
DISCORD_MSG_LIMIT = 2000


# ---------------------------------------------------------------------------
# Credential discovery — find the agent profile from cwd
# ---------------------------------------------------------------------------

def find_profile_dir() -> Path:
    """Walk up from cwd to find the agent profile directory."""
    cwd = Path.cwd()
    # If we're in workspace/ or workspace/tools/, the profile is 1-2 levels up
    for parent in [cwd, cwd.parent, cwd.parent.parent]:
        if (parent / "config.json").exists() and (parent / "credentials").is_dir():
            return parent
    # Fallback: check if cwd is inside ~/.claude-agents/<profile>/
    agents_dir = Path.home() / ".claude-agents"
    if str(cwd).startswith(str(agents_dir)):
        relative = cwd.relative_to(agents_dir)
        profile_name = relative.parts[0] if relative.parts else None
        if profile_name and profile_name != "shared":
            profile = agents_dir / profile_name
            if (profile / "config.json").exists():
                return profile
    sys.exit("Could not find agent profile directory. Run from within a workspace.")


def get_token() -> str:
    profile = find_profile_dir()
    token_path = profile / "credentials" / "discord-bot-token"
    if not token_path.exists():
        sys.exit(f"Discord bot token not found at {token_path}")
    token = token_path.read_text().strip()
    if not token:
        sys.exit(f"Discord bot token is empty at {token_path}")
    return token


def get_config() -> dict:
    profile = find_profile_dir()
    config_path = profile / "config.json"
    with open(config_path) as f:
        return json.load(f)


def get_headers() -> dict:
    return {
        "Authorization": f"Bot {get_token()}",
        "Content-Type": "application/json",
    }


def get_default_channel() -> str:
    return get_config()["discord"]["channel_id"]


# ---------------------------------------------------------------------------
# Message splitting
# ---------------------------------------------------------------------------

def split_message(text: str, limit: int = DISCORD_MSG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_post(path: str, data: dict) -> dict:
    resp = requests.post(f"{API_BASE}{path}", headers=get_headers(), json=data)
    if not resp.ok:
        sys.exit(f"Discord API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_get(path: str, params: dict = None) -> dict | list:
    resp = requests.get(f"{API_BASE}{path}", headers=get_headers(), params=params)
    if not resp.ok:
        sys.exit(f"Discord API error {resp.status_code}: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create_thread(args):
    channel_id = args.channel or get_default_channel()
    message = _resolve_message(args)

    thread = api_post(f"/channels/{channel_id}/threads", {
        "name": args.name,
        "type": 11,  # PUBLIC_THREAD
        "auto_archive_duration": 10080,  # 7 days
    })

    if message:
        for chunk in split_message(message):
            api_post(f"/channels/{thread['id']}/messages", {"content": chunk})
            time.sleep(0.5)

    if args.json:
        print(json.dumps({
            "id": thread["id"],
            "name": thread["name"],
            "parent_id": thread.get("parent_id"),
        }, indent=2))
    else:
        print(f"Thread created: {thread['name']} (id: {thread['id']})")


def cmd_send(args):
    channel_id = args.channel
    if not channel_id:
        sys.exit("--channel is required for send command")

    message = _resolve_message(args)
    if not message:
        sys.exit("--message or --message-file is required")

    chunks = split_message(message)
    sent = []
    for chunk in chunks:
        resp = api_post(f"/channels/{channel_id}/messages", {"content": chunk})
        sent.append(resp)
        if len(chunks) > 1:
            time.sleep(0.5)

    if args.json:
        print(json.dumps({
            "messages_sent": len(sent),
            "channel_id": channel_id,
            "first_message_id": sent[0]["id"] if sent else None,
        }, indent=2))
    else:
        print(f"Sent {len(sent)} message(s) to channel {channel_id}")


def cmd_list_threads(args):
    channel_id = args.channel or get_default_channel()
    config = get_config()
    guild_id = config["discord"]["guild_id"]

    data = api_get(f"/guilds/{guild_id}/threads/active")
    all_threads = [
        t for t in data.get("threads", [])
        if t.get("parent_id") == str(channel_id)
    ]

    archived = api_get(f"/channels/{channel_id}/threads/archived/public")
    all_threads += archived.get("threads", [])

    if args.json:
        result = [
            {
                "id": t["id"],
                "name": t["name"],
                "archived": t.get("thread_metadata", {}).get("archived", False),
                "message_count": t.get("message_count", 0),
            }
            for t in all_threads
        ]
        print(json.dumps(result, indent=2))
    else:
        if not all_threads:
            print("No threads found.")
        for t in all_threads:
            status = "archived" if t.get("thread_metadata", {}).get("archived") else "active"
            print(f"  {t['name']} (id: {t['id']}, {status})")


def cmd_read_messages(args):
    """Read recent messages from a channel or thread."""
    channel_id = args.channel
    if not channel_id:
        sys.exit("--channel is required for read-messages command")

    limit = min(args.limit or 10, 50)
    messages = api_get(f"/channels/{channel_id}/messages", {"limit": limit})

    # Reverse to chronological order (API returns newest first)
    messages = list(reversed(messages))

    if args.json:
        result = [
            {
                "id": m["id"],
                "author": m["author"]["username"],
                "content": m["content"],
                "timestamp": m["timestamp"],
            }
            for m in messages
        ]
        print(json.dumps(result, indent=2))
    else:
        for m in messages:
            author = m["author"]["username"]
            content = m["content"][:200]
            print(f"  [{author}] {content}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_message(args) -> str | None:
    if hasattr(args, "message_file") and args.message_file:
        with open(args.message_file) as f:
            return f.read().strip()
    if hasattr(args, "message") and args.message:
        return args.message
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Discord CLI for Claude Code agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p_thread = sub.add_parser("create-thread", help="Create a new thread")
    p_thread.add_argument("--name", required=True, help="Thread name")
    p_thread.add_argument("--channel", help="Channel ID (default: agent channel)")
    p_thread.add_argument("--message", help="Initial message content")
    p_thread.add_argument("--message-file", help="Read initial message from file")
    p_thread.add_argument("--json", action="store_true")

    p_send = sub.add_parser("send", help="Send message to channel or thread")
    p_send.add_argument("--channel", required=True, help="Channel or thread ID")
    p_send.add_argument("--message", help="Message content")
    p_send.add_argument("--message-file", help="Read message from file")
    p_send.add_argument("--json", action="store_true")

    p_list = sub.add_parser("list-threads", help="List threads in channel")
    p_list.add_argument("--channel", help="Channel ID (default: agent channel)")
    p_list.add_argument("--json", action="store_true")

    p_read = sub.add_parser("read-messages", help="Read recent messages from a channel or thread")
    p_read.add_argument("--channel", required=True, help="Channel or thread ID")
    p_read.add_argument("--limit", type=int, default=10, help="Number of messages (max 50)")
    p_read.add_argument("--json", action="store_true")

    args = parser.parse_args()

    commands = {
        "create-thread": cmd_create_thread,
        "send": cmd_send,
        "list-threads": cmd_list_threads,
        "read-messages": cmd_read_messages,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
