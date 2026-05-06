#!/usr/bin/env python3
"""
ghl_tool.py — GoHighLevel CLI for Claude Code agents.

Read-only commands work today; cloning a sub-account from a snapshot is
stubbed pending confirmation of the multi-tenant model (one location per
client vs. shared location).

Usage:
  ghl_tool.py list-locations [--json]
  ghl_tool.py list-snapshots [--json]
  ghl_tool.py list-workflows --location-id ID [--json]
  ghl_tool.py create-location --name NAME [--snapshot-id ID]
                              [--country CC] [--timezone TZ]
                              [--first-name N] [--last-name N] [--email E]
                              [--phone P] [--address A] [--city C]
                              [--state S] [--postal-code Z]
                              [--json]

Config (in profile config.json under "automation.ghl"):
  api_version:  GHL API version header, e.g. "2021-07-28"
  company_id:   Agency/company ID (for agency-level reads)

Credentials:
  ~/.claude-agents/<profile>/credentials/ghl-api-key  (mode 600)
    Agency-level token for snapshot/location operations, or location-level
    token for workflow reads — depending on the operation.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

API_BASE = "https://services.leadconnectorhq.com"
DEFAULT_VERSION = "2021-07-28"


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


def get_ghl_config() -> dict:
    return get_config().get("automation", {}).get("ghl", {})


def get_api_key() -> str:
    profile = find_profile_dir()
    p = profile / "credentials" / "ghl-api-key"
    if not p.exists():
        sys.exit(f"GHL API key not found at {p}")
    key = p.read_text().strip()
    if not key:
        sys.exit(f"GHL API key is empty at {p}")
    return key


def headers() -> dict:
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Version": get_ghl_config().get("api_version", DEFAULT_VERSION),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def api_get(path: str, params: dict = None) -> dict:
    resp = requests.get(f"{API_BASE}{path}", headers=headers(), params=params)
    if not resp.ok:
        sys.exit(f"GHL API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_post(path: str, data: dict) -> dict:
    resp = requests.post(f"{API_BASE}{path}", headers=headers(), json=data)
    if not resp.ok:
        sys.exit(f"GHL API error {resp.status_code}: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list_locations(args):
    company_id = get_ghl_config().get("company_id")
    if not company_id:
        sys.exit("Missing automation.ghl.company_id in config.json")
    data = api_get("/locations/search", params={"companyId": company_id, "limit": 100})
    locations = data.get("locations", [])
    if args.json:
        print(json.dumps(locations, indent=2))
    else:
        for loc in locations:
            print(f"  {loc.get('name', '?')}  (id: {loc.get('id', '?')})")


def cmd_list_snapshots(args):
    company_id = get_ghl_config().get("company_id")
    if not company_id:
        sys.exit("Missing automation.ghl.company_id in config.json")
    data = api_get("/snapshots/", params={"companyId": company_id})
    snapshots = data.get("snapshots", [])
    if args.json:
        print(json.dumps(snapshots, indent=2))
    else:
        for s in snapshots:
            print(f"  {s.get('name', '?')}  (id: {s.get('id', '?')})")


def cmd_list_workflows(args):
    data = api_get("/workflows/", params={"locationId": args.location_id})
    workflows = data.get("workflows", [])
    if args.json:
        print(json.dumps(workflows, indent=2))
    else:
        for w in workflows:
            print(f"  {w.get('name', '?')}  (id: {w.get('id', '?')})")


def cmd_create_location(args):
    cfg = get_ghl_config()
    company_id = cfg.get("company_id")
    if not company_id:
        sys.exit("Missing automation.ghl.company_id in config.json")

    snapshot_id = args.snapshot_id or cfg.get("template_snapshot_id")
    if not snapshot_id:
        sys.exit("--snapshot-id required (or set automation.ghl.template_snapshot_id)")

    payload = {
        "name": args.name,
        "companyId": company_id,
        "snapshotId": snapshot_id,
    }

    optional_fields = {
        "country": args.country,
        "timezone": args.timezone,
        "firstName": args.first_name,
        "lastName": args.last_name,
        "email": args.email,
        "phone": args.phone,
        "address": args.address,
        "city": args.city,
        "state": args.state,
        "postalCode": args.postal_code,
    }
    for k, v in optional_fields.items():
        if v:
            payload[k] = v

    created = api_post("/locations/", payload)
    new_id = created.get("id") or (created.get("location") or {}).get("id")

    if args.json:
        print(json.dumps({"location_id": new_id, "name": args.name,
                          "snapshot_id": snapshot_id}, indent=2))
    else:
        print(f"Created location: {args.name} (id: {new_id})")
        print(f"Snapshot {snapshot_id} loading in background — workflows/pipelines/etc.")
        print("Note: Forms in Sites are NOT carried over by snapshots — build manually.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GoHighLevel CLI for Claude Code agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p_loc = sub.add_parser("list-locations", help="List sub-accounts (locations)")
    p_loc.add_argument("--json", action="store_true")

    p_snap = sub.add_parser("list-snapshots", help="List available snapshots")
    p_snap.add_argument("--json", action="store_true")

    p_wf = sub.add_parser("list-workflows", help="List workflows in a location")
    p_wf.add_argument("--location-id", required=True)
    p_wf.add_argument("--json", action="store_true")

    p_cl = sub.add_parser("create-location",
                          help="Create a sub-account, optionally from a snapshot")
    p_cl.add_argument("--name", required=True)
    p_cl.add_argument("--snapshot-id",
                      help="Defaults to automation.ghl.template_snapshot_id")
    p_cl.add_argument("--country", default="PT", help="ISO country code (default: PT)")
    p_cl.add_argument("--timezone", default="Europe/Lisbon",
                      help="Timezone (default: Europe/Lisbon)")
    p_cl.add_argument("--first-name")
    p_cl.add_argument("--last-name")
    p_cl.add_argument("--email")
    p_cl.add_argument("--phone")
    p_cl.add_argument("--address")
    p_cl.add_argument("--city")
    p_cl.add_argument("--state")
    p_cl.add_argument("--postal-code")
    p_cl.add_argument("--json", action="store_true")

    args = parser.parse_args()
    commands = {
        "list-locations": cmd_list_locations,
        "list-snapshots": cmd_list_snapshots,
        "list-workflows": cmd_list_workflows,
        "create-location": cmd_create_location,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
