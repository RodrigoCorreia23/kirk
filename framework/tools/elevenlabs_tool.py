#!/usr/bin/env python3
"""
elevenlabs_tool.py — ElevenLabs Conversational AI CLI for Claude Code agents.

Manages Conversational AI agents: list, fetch config, clone from a template,
update the system prompt, and rewrite webhook URLs on the agent's tools.

Usage:
  elevenlabs_tool.py list-agents [--json]
  elevenlabs_tool.py get-agent --agent-id ID [--json]
  elevenlabs_tool.py clone-agent --template-id ID --name NAME
                                 [--prompt-file FILE | --prompt TEXT]
                                 [--webhook-map JSON]
                                 [--json]
  elevenlabs_tool.py update-prompt --agent-id ID
                                   (--prompt-file FILE | --prompt TEXT)
                                   [--json]
  elevenlabs_tool.py update-webhook --agent-id ID --tool-name NAME --url URL [--json]
  elevenlabs_tool.py list-workspace-webhooks [--json]
  elevenlabs_tool.py create-workspace-webhook --name NAME --url URL [--auth-type TYPE] [--json]
  elevenlabs_tool.py set-post-call-webhook --agent-id ID --webhook-id ID [--json]

Credentials:
  ~/.claude-agents/<profile>/credentials/elevenlabs-api-key  (mode 600)

The clone operation fetches the template agent's full config, overrides the
prompt and any matching tool webhook URLs from --webhook-map, and creates a
new agent with that config. --webhook-map is a JSON object of
{tool_name: new_url} pairs, e.g. '{"book_appointment": "https://..."}'.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

import requests

API_BASE = "https://api.elevenlabs.io"


# ---------------------------------------------------------------------------
# Credential discovery — same pattern as discord_tool.py
# ---------------------------------------------------------------------------

def find_profile_dir() -> Path:
    cwd = Path.cwd()
    for parent in [cwd, cwd.parent, cwd.parent.parent]:
        if (parent / "config.json").exists() and (parent / "credentials").is_dir():
            return parent
    agents_dir = Path.home() / ".claude-agents"
    if str(cwd).startswith(str(agents_dir)):
        relative = cwd.relative_to(agents_dir)
        profile_name = relative.parts[0] if relative.parts else None
        if profile_name and profile_name != "shared":
            profile = agents_dir / profile_name
            if (profile / "config.json").exists():
                return profile
    sys.exit("Could not find agent profile directory. Run from within a workspace.")


def get_api_key() -> str:
    profile = find_profile_dir()
    key_path = profile / "credentials" / "elevenlabs-api-key"
    if not key_path.exists():
        sys.exit(f"ElevenLabs API key not found at {key_path}")
    key = key_path.read_text().strip()
    if not key:
        sys.exit(f"ElevenLabs API key is empty at {key_path}")
    return key


def headers() -> dict:
    return {"xi-api-key": get_api_key(), "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict:
    resp = requests.get(f"{API_BASE}{path}", headers=headers(), params=params)
    if not resp.ok:
        sys.exit(f"ElevenLabs API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_post(path: str, data: dict) -> dict:
    resp = requests.post(f"{API_BASE}{path}", headers=headers(), json=data)
    if not resp.ok:
        sys.exit(f"ElevenLabs API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_patch(path: str, data: dict) -> dict:
    resp = requests.patch(f"{API_BASE}{path}", headers=headers(), json=data)
    if not resp.ok:
        sys.exit(f"ElevenLabs API error {resp.status_code}: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# Agent config helpers
# ---------------------------------------------------------------------------

def fetch_agent(agent_id: str) -> dict:
    return api_get(f"/v1/convai/agents/{agent_id}")


def set_prompt(config: dict, prompt_text: str) -> None:
    """Mutate config in-place: set the system prompt under conversation_config."""
    cc = config.setdefault("conversation_config", {})
    agent = cc.setdefault("agent", {})
    prompt = agent.setdefault("prompt", {})
    prompt["prompt"] = prompt_text


def get_tools(config: dict) -> list:
    """Return the list of tools from agent config (location varies by version)."""
    cc = config.get("conversation_config", {})
    agent = cc.get("agent", {})
    prompt = agent.get("prompt", {})
    return prompt.get("tools", []) or []


def rewrite_tool_webhooks(config: dict, webhook_map: dict) -> list:
    """Rewrite webhook URLs on tools whose name matches a key in webhook_map.
    Returns list of {tool_name, old_url, new_url} for tools that were updated.
    """
    updates = []
    for tool in get_tools(config):
        name = tool.get("name")
        if name not in webhook_map:
            continue
        new_url = webhook_map[name]
        api_schema = tool.get("api_schema") or {}
        old_url = api_schema.get("url")
        api_schema["url"] = new_url
        tool["api_schema"] = api_schema
        updates.append({"tool_name": name, "old_url": old_url, "new_url": new_url})
    return updates


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list_agents(args):
    data = api_get("/v1/convai/agents")
    agents = data.get("agents", data) if isinstance(data, dict) else data
    total = len(agents)
    if args.limit and args.limit > 0:
        agents = agents[:args.limit]
    if args.json:
        print(json.dumps(agents, indent=2))
    else:
        if not agents:
            print("No agents found.")
            return
        for a in agents:
            print(f"  {a.get('name', '?')}  (id: {a.get('agent_id', '?')})")
        if len(agents) < total:
            print(f"\n... showing {len(agents)} of {total}. Use --limit 0 for all.")


def cmd_get_agent(args):
    config = fetch_agent(args.agent_id)
    if args.json:
        print(json.dumps(config, indent=2))
    else:
        name = config.get("name", "?")
        tools = get_tools(config)
        print(f"Agent: {name} (id: {args.agent_id})")
        print(f"Tools: {len(tools)}")
        for t in tools:
            url = (t.get("api_schema") or {}).get("url", "—")
            print(f"  - {t.get('name', '?')}: {url}")


def cmd_clone_agent(args):
    template = fetch_agent(args.template_id)

    new_config = copy.deepcopy(template)
    new_config.pop("agent_id", None)
    new_config["name"] = args.name

    prompt_text = _resolve_prompt(args)
    if prompt_text is not None:
        set_prompt(new_config, prompt_text)

    webhook_updates = []
    if args.webhook_map:
        try:
            wmap = json.loads(args.webhook_map)
        except json.JSONDecodeError as e:
            sys.exit(f"--webhook-map is not valid JSON: {e}")
        webhook_updates = rewrite_tool_webhooks(new_config, wmap)

    created = api_post("/v1/convai/agents/create", new_config)
    new_id = created.get("agent_id") or created.get("id")

    if args.json:
        print(json.dumps({
            "agent_id": new_id,
            "name": args.name,
            "webhook_updates": webhook_updates,
        }, indent=2))
    else:
        print(f"Cloned agent: {args.name} (id: {new_id})")
        for u in webhook_updates:
            print(f"  webhook[{u['tool_name']}]: {u['old_url']} -> {u['new_url']}")


def cmd_update_prompt(args):
    config = fetch_agent(args.agent_id)
    prompt_text = _resolve_prompt(args)
    if prompt_text is None:
        sys.exit("--prompt or --prompt-file required")

    set_prompt(config, prompt_text)
    api_patch(f"/v1/convai/agents/{args.agent_id}", {
        "conversation_config": config["conversation_config"],
    })

    if args.json:
        print(json.dumps({"agent_id": args.agent_id, "updated": "prompt"}, indent=2))
    else:
        print(f"Prompt updated on agent {args.agent_id}")


def cmd_list_workspace_webhooks(args):
    data = api_get("/v1/workspace/webhooks")
    webhooks = data.get("webhooks", []) if isinstance(data, dict) else data
    if args.json:
        print(json.dumps(webhooks, indent=2))
    else:
        for w in webhooks:
            print(f"  {w.get('name', '?')}")
            print(f"    id:  {w.get('webhook_id', '?')}")
            print(f"    url: {w.get('webhook_url', '?')}")


def cmd_create_workspace_webhook(args):
    payload = {
        "name": args.name,
        "webhook_url": args.url,
        "auth_type": args.auth_type or "hmac",
    }
    created = api_post("/v1/workspace/webhooks", payload)
    new_id = created.get("webhook_id") or created.get("id")
    if args.json:
        print(json.dumps({"webhook_id": new_id, "name": args.name, "url": args.url}, indent=2))
    else:
        print(f"Created workspace webhook: {args.name} (id: {new_id})")


def cmd_set_post_call_webhook(args):
    config = fetch_agent(args.agent_id)
    ps = config.setdefault("platform_settings", {})
    wo = ps.setdefault("workspace_overrides", {})
    wh = wo.setdefault("webhooks", {})
    wh["post_call_webhook_id"] = args.webhook_id

    api_patch(f"/v1/convai/agents/{args.agent_id}", {
        "platform_settings": {"workspace_overrides": {"webhooks": wh}},
    })

    if args.json:
        print(json.dumps({"agent_id": args.agent_id,
                          "post_call_webhook_id": args.webhook_id}, indent=2))
    else:
        print(f"Agent {args.agent_id} now uses webhook {args.webhook_id} for post-call")


def cmd_update_webhook(args):
    config = fetch_agent(args.agent_id)
    updates = rewrite_tool_webhooks(config, {args.tool_name: args.url})
    if not updates:
        sys.exit(f"Tool '{args.tool_name}' not found on agent {args.agent_id}")

    api_patch(f"/v1/convai/agents/{args.agent_id}", {
        "conversation_config": config["conversation_config"],
    })

    if args.json:
        print(json.dumps({"agent_id": args.agent_id, "updates": updates}, indent=2))
    else:
        for u in updates:
            print(f"webhook[{u['tool_name']}]: {u['old_url']} -> {u['new_url']}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_prompt(args) -> str | None:
    if getattr(args, "prompt_file", None):
        return Path(args.prompt_file).read_text().strip()
    if getattr(args, "prompt", None):
        return args.prompt
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ElevenLabs Conversational AI CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-agents", help="List all agents")
    p_list.add_argument("--limit", type=int, default=50,
                        help="Max results to display (0 = all). Default 50.")
    p_list.add_argument("--json", action="store_true")

    p_get = sub.add_parser("get-agent", help="Fetch full agent config")
    p_get.add_argument("--agent-id", required=True)
    p_get.add_argument("--json", action="store_true")

    p_clone = sub.add_parser("clone-agent", help="Clone an agent from a template")
    p_clone.add_argument("--template-id", required=True)
    p_clone.add_argument("--name", required=True)
    p_clone.add_argument("--prompt-file", help="Read new system prompt from file")
    p_clone.add_argument("--prompt", help="New system prompt text")
    p_clone.add_argument("--webhook-map",
                         help='JSON map of tool_name -> new webhook URL')
    p_clone.add_argument("--json", action="store_true")

    p_up = sub.add_parser("update-prompt", help="Update an agent's system prompt")
    p_up.add_argument("--agent-id", required=True)
    p_up.add_argument("--prompt-file")
    p_up.add_argument("--prompt")
    p_up.add_argument("--json", action="store_true")

    p_uw = sub.add_parser("update-webhook", help="Update a tool's webhook URL")
    p_uw.add_argument("--agent-id", required=True)
    p_uw.add_argument("--tool-name", required=True)
    p_uw.add_argument("--url", required=True)
    p_uw.add_argument("--json", action="store_true")

    p_lw = sub.add_parser("list-workspace-webhooks",
                          help="List workspace-level webhooks (post-call targets)")
    p_lw.add_argument("--json", action="store_true")

    p_cw = sub.add_parser("create-workspace-webhook",
                          help="Create a new workspace webhook")
    p_cw.add_argument("--name", required=True)
    p_cw.add_argument("--url", required=True)
    p_cw.add_argument("--auth-type", help="Auth type (default: hmac)")
    p_cw.add_argument("--json", action="store_true")

    p_pc = sub.add_parser("set-post-call-webhook",
                          help="Point an agent's post-call webhook to a workspace webhook")
    p_pc.add_argument("--agent-id", required=True)
    p_pc.add_argument("--webhook-id", required=True)
    p_pc.add_argument("--json", action="store_true")

    args = parser.parse_args()
    commands = {
        "list-agents": cmd_list_agents,
        "get-agent": cmd_get_agent,
        "clone-agent": cmd_clone_agent,
        "update-prompt": cmd_update_prompt,
        "update-webhook": cmd_update_webhook,
        "list-workspace-webhooks": cmd_list_workspace_webhooks,
        "create-workspace-webhook": cmd_create_workspace_webhook,
        "set-post-call-webhook": cmd_set_post_call_webhook,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
