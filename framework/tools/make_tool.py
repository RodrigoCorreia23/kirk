#!/usr/bin/env python3
"""
make_tool.py — Make.com (Integromat) CLI for Claude Code agents.

Two modes:
  - api: full automation via Make API (requires Pro/Teams/Enterprise plan +
         API token in credentials/make-api-token).
  - ui:  prints step-by-step UI instructions and prompts the operator for the
         new scenario ID and webhook URL after they clone manually.

Auto-detects mode: API if credentials/make-api-token exists, else UI.
Override with --mode=api|ui.

Usage:
  make_tool.py list-scenarios [--team-id ID] [--json]
  make_tool.py get-scenario --scenario-id ID [--json]
  make_tool.py get-webhook-url --scenario-id ID [--json]
  make_tool.py clone-scenario --template-id ID --name NAME
                              [--team-id ID] [--mode api|ui] [--json]

Config (in profile config.json under "automation.make"):
  zone:    Make zone hostname, e.g. "eu1.make.com", "eu2.make.com", "us1.make.com"
  team_id: default team ID for scenario operations (optional)

Credentials:
  ~/.claude-agents/<profile>/credentials/make-api-token  (mode 600, API mode only)
"""

import argparse
import json
import sys
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Profile + config discovery (same pattern as discord_tool.py)
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


def get_config() -> dict:
    profile = find_profile_dir()
    with open(profile / "config.json") as f:
        return json.load(f)


def get_make_config() -> dict:
    cfg = get_config().get("automation", {}).get("make", {})
    if not cfg.get("zone"):
        sys.exit("Missing automation.make.zone in profile config.json "
                 "(e.g. 'eu2.make.com').")
    return cfg


def api_base() -> str:
    return f"https://{get_make_config()['zone']}/api/v2"


def token_path() -> Path:
    return find_profile_dir() / "credentials" / "make-api-token"


def has_api_token() -> bool:
    p = token_path()
    return p.exists() and p.read_text().strip() != ""


def get_token() -> str:
    p = token_path()
    if not p.exists():
        sys.exit(f"Make API token not found at {p}")
    token = p.read_text().strip()
    if not token:
        sys.exit(f"Make API token is empty at {p}")
    return token


def headers() -> dict:
    return {"Authorization": f"Token {get_token()}", "Content-Type": "application/json"}


def resolve_mode(requested: str | None) -> str:
    if requested in ("api", "ui"):
        return requested
    return "api" if has_api_token() else "ui"


def resolve_team_id(provided: str | None) -> str | None:
    return provided or get_make_config().get("team_id")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict:
    resp = requests.get(f"{api_base()}{path}", headers=headers(), params=params)
    if not resp.ok:
        sys.exit(f"Make API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_post(path: str, data: dict, params: dict = None) -> dict:
    resp = requests.post(f"{api_base()}{path}", headers=headers(),
                         json=data, params=params)
    if not resp.ok:
        sys.exit(f"Make API error {resp.status_code}: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# Commands — API mode
# ---------------------------------------------------------------------------

def cmd_list_scenarios(args):
    if resolve_mode(args.mode) == "ui":
        zone = get_make_config()["zone"]
        print(f"UI mode — open https://{zone}/scenarios to view scenarios.")
        return

    team_id = resolve_team_id(args.team_id)
    params = {"teamId": team_id} if team_id else None
    data = api_get("/scenarios", params=params)
    scenarios = data.get("scenarios", data) if isinstance(data, dict) else data

    total = len(scenarios)
    if args.limit and args.limit > 0:
        scenarios = scenarios[:args.limit]

    if args.json:
        print(json.dumps(scenarios, indent=2))
    else:
        if not scenarios:
            print("No scenarios found.")
            return
        for s in scenarios:
            print(f"  {s.get('name', '?')}  (id: {s.get('id', '?')})")
        if len(scenarios) < total:
            print(f"\n... showing {len(scenarios)} of {total}. Use --limit 0 for all.")


def cmd_get_scenario(args):
    if resolve_mode(args.mode) == "ui":
        sys.exit("get-scenario requires API mode (set --mode=api once token is in place).")

    data = api_get(f"/scenarios/{args.scenario_id}")
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        s = data.get("scenario", data)
        print(f"Scenario: {s.get('name', '?')} (id: {s.get('id', '?')})")


def cmd_get_webhook_url(args):
    """Find the first webhook hook in a scenario's blueprint and print its URL."""
    if resolve_mode(args.mode) == "ui":
        sys.exit("get-webhook-url requires API mode. In UI mode, copy the URL "
                 "from the webhook module config in the Make UI.")

    bp = api_get(f"/scenarios/{args.scenario_id}/blueprint")
    flow = (bp.get("response", {}).get("blueprint", {}).get("flow")
            or bp.get("blueprint", {}).get("flow")
            or [])

    hook_id = None
    for module in flow:
        if "webhook" in (module.get("module", "") or "").lower():
            hook_id = (module.get("parameters") or {}).get("hook")
            if hook_id:
                break
    if not hook_id:
        sys.exit(f"No webhook module found in scenario {args.scenario_id}")

    hook = api_get(f"/hooks/{hook_id}")
    url = (hook.get("hook") or hook).get("url")

    if args.json:
        print(json.dumps({"scenario_id": args.scenario_id,
                          "hook_id": hook_id, "url": url}, indent=2))
    else:
        print(url)


def cmd_clone_scenario(args):
    mode = resolve_mode(args.mode)

    if mode == "ui":
        _clone_scenario_ui(args)
        return

    bp = api_get(f"/scenarios/{args.template_id}/blueprint")
    blueprint = bp.get("response", {}).get("blueprint") or bp.get("blueprint") or bp

    team_id = resolve_team_id(args.team_id)
    if not team_id:
        sys.exit("--team-id required (or set automation.make.team_id in config.json)")

    payload = {
        "blueprint": json.dumps(blueprint) if isinstance(blueprint, dict) else blueprint,
        "name": args.name,
        "teamId": int(team_id),
        "scheduling": json.dumps({"type": "indefinitely"}),
    }
    created = api_post("/scenarios", payload)
    new_scenario = created.get("scenario", created)
    new_id = new_scenario.get("id")

    out = {"scenario_id": new_id, "name": args.name, "mode": "api"}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Cloned scenario: {args.name} (id: {new_id})")
        print(f"Next: run get-webhook-url --scenario-id {new_id} to fetch the new webhook.")


def cmd_clone_template_set(args):
    """Clone every scenario in automation.make.template_scenarios for a new client."""
    templates = get_make_config().get("template_scenarios") or []
    if not templates:
        sys.exit("No template_scenarios configured under automation.make in config.json")

    if resolve_mode(args.mode) == "ui":
        sys.exit("clone-template-set requires API mode (Pro+ plan).")

    team_id = resolve_team_id(args.team_id)
    if not team_id:
        sys.exit("--team-id required (or set automation.make.team_id in config.json)")

    results = []
    for tpl in templates:
        role = tpl.get("role", "?")
        src_id = tpl.get("scenario_id")
        name = tpl.get("name_template", "{client}").format(client=args.client)

        bp = api_get(f"/scenarios/{src_id}/blueprint")
        blueprint = bp.get("response", {}).get("blueprint") or bp.get("blueprint") or bp

        payload = {
            "blueprint": json.dumps(blueprint) if isinstance(blueprint, dict) else blueprint,
            "name": name,
            "teamId": int(team_id),
            "scheduling": json.dumps({"type": "indefinitely"}),
        }
        created = api_post("/scenarios", payload)
        new_scenario = created.get("scenario", created)
        new_id = new_scenario.get("id")

        webhook_url = None
        try:
            bp2 = api_get(f"/scenarios/{new_id}/blueprint")
            flow = (bp2.get("response", {}).get("blueprint", {}).get("flow")
                    or bp2.get("blueprint", {}).get("flow") or [])
            for module in flow:
                if "webhook" in (module.get("module", "") or "").lower():
                    hook_id = (module.get("parameters") or {}).get("hook")
                    if hook_id:
                        hook = api_get(f"/hooks/{hook_id}")
                        webhook_url = (hook.get("hook") or hook).get("url")
                        break
        except SystemExit:
            pass

        results.append({
            "role": role,
            "source_id": src_id,
            "scenario_id": new_id,
            "name": name,
            "webhook_url": webhook_url,
        })

    if args.json:
        print(json.dumps({"client": args.client, "scenarios": results}, indent=2))
    else:
        print(f"Cloned {len(results)} scenarios for client '{args.client}':")
        for r in results:
            url = r["webhook_url"] or "(no webhook)"
            print(f"  [{r['role']}] {r['name']}  id={r['scenario_id']}")
            print(f"    webhook: {url}")


def _clone_scenario_ui(args):
    """UI-helper mode: print steps, prompt for new IDs, emit JSON for downstream use."""
    zone = get_make_config()["zone"]
    template_url = f"https://{zone}/scenarios/{args.template_id}"

    print("=== Make UI clone helper ===", file=sys.stderr)
    print(f"1. Open the template scenario:  {template_url}", file=sys.stderr)
    print(f"2. Click ... menu -> Clone, name it: {args.name}", file=sys.stderr)
    print("3. Open the cloned scenario; copy:", file=sys.stderr)
    print("   - the scenario ID (in the URL)", file=sys.stderr)
    print("   - the webhook URL (from the webhook module's config)", file=sys.stderr)
    print("", file=sys.stderr)

    new_id = input("New scenario ID: ").strip()
    new_url = input("New webhook URL: ").strip()

    out = {"scenario_id": new_id, "webhook_url": new_url, "name": args.name, "mode": "ui"}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Recorded: scenario_id={new_id}, webhook_url={new_url}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Make.com CLI for Claude Code agents")
    parser.add_argument("--mode", choices=["api", "ui"],
                        help="Force API or UI mode (default: auto-detect)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-scenarios", help="List scenarios in team")
    p_list.add_argument("--team-id")
    p_list.add_argument("--limit", type=int, default=50,
                        help="Max results to display (0 = all). Default 50.")
    p_list.add_argument("--json", action="store_true")

    p_get = sub.add_parser("get-scenario", help="Fetch scenario metadata")
    p_get.add_argument("--scenario-id", required=True)
    p_get.add_argument("--json", action="store_true")

    p_hook = sub.add_parser("get-webhook-url", help="Get the webhook URL of a scenario")
    p_hook.add_argument("--scenario-id", required=True)
    p_hook.add_argument("--json", action="store_true")

    p_clone = sub.add_parser("clone-scenario", help="Clone a scenario from a template")
    p_clone.add_argument("--template-id", required=True)
    p_clone.add_argument("--name", required=True)
    p_clone.add_argument("--team-id")
    p_clone.add_argument("--json", action="store_true")

    p_set = sub.add_parser("clone-template-set",
                           help="Clone every scenario in automation.make.template_scenarios")
    p_set.add_argument("--client", required=True,
                       help="Client name to substitute into name_template ({client})")
    p_set.add_argument("--team-id")
    p_set.add_argument("--json", action="store_true")

    args = parser.parse_args()
    commands = {
        "list-scenarios": cmd_list_scenarios,
        "get-scenario": cmd_get_scenario,
        "get-webhook-url": cmd_get_webhook_url,
        "clone-scenario": cmd_clone_scenario,
        "clone-template-set": cmd_clone_template_set,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
