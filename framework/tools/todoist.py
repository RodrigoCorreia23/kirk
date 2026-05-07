#!/usr/bin/env python3
"""
todoist.py — Todoist CLI for Claude Code agents.

Supports multiple projects (e.g. agent's own project + user's personal).
Default project is read from credentials/todoist-projects.json["default"];
override per-call with --project NAME.

Usage:
  todoist.py list [--project NAME] [--section NAME] [--json]
  todoist.py get <task_id> [--json]
  todoist.py comments <task_id> [--json]
  todoist.py create --content TEXT [--project NAME] [--section NAME]
                    [--due DATE] [--description TEXT] [--priority N] [--json]
  todoist.py move-section <task_id> <section_name> [--project NAME] [--json]
  todoist.py update <task_id> [--title T] [--due D] [--description X]
                    [--priority N] [--json]
  todoist.py complete <task_id> [--json]
  todoist.py comment <task_id> --content TEXT [--json]
  todoist.py projects [--json]
  todoist.py sections [--project NAME] [--json]

Credentials:
  ~/.claude-agents/<profile>/credentials/todoist-token       (mode 600)
  ~/.claude-agents/<profile>/credentials/todoist-projects.json (mode 600)

todoist-projects.json schema:
  {
    "default": "kirk",
    "projects": {
      "kirk":     { "project_id": "...", "name": "Kirk"     },
      "personal": { "project_id": "...", "name": "Personal" }
    }
  }
"""

import argparse
import json
import sys
from pathlib import Path

import requests

REST_BASE = "https://api.todoist.com/api/v1"


# ---------------------------------------------------------------------------
# Profile + credential discovery (same pattern as discord_tool.py)
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


def get_token() -> str:
    p = find_profile_dir() / "credentials" / "todoist-token"
    if not p.exists():
        sys.exit(f"Todoist token not found at {p}")
    token = p.read_text().strip()
    if not token:
        sys.exit(f"Todoist token is empty at {p}")
    return token


def get_projects_config() -> dict:
    p = find_profile_dir() / "credentials" / "todoist-projects.json"
    if not p.exists():
        sys.exit(f"Projects config not found at {p}. Run setup first.")
    with open(p) as f:
        return json.load(f)


def resolve_project_id(name: str | None) -> tuple[str, str]:
    """Return (project_name, project_id). Falls back to the default project."""
    cfg = get_projects_config()
    projects = cfg.get("projects", {})
    name = name or cfg.get("default")
    if not name:
        sys.exit("No project specified and no default in todoist-projects.json")
    project = projects.get(name)
    if not project:
        sys.exit(f"Project '{name}' not in todoist-projects.json. "
                 f"Known: {list(projects.keys())}")
    return name, project["project_id"]


def headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}",
            "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict | list:
    r = requests.get(f"{REST_BASE}{path}", headers=headers(), params=params)
    if not r.ok:
        sys.exit(f"Todoist API error {r.status_code}: {r.text}")
    return r.json()


def api_list(path: str, params: dict = None) -> list:
    """Fetch a list endpoint, transparently following pagination via next_cursor."""
    items: list = []
    params = dict(params or {})
    while True:
        data = api_get(path, params)
        if isinstance(data, list):
            return data
        items.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not cursor:
            return items
        params["cursor"] = cursor


def api_post(path: str, data: dict = None) -> dict:
    r = requests.post(f"{REST_BASE}{path}", headers=headers(), json=data or {})
    if not r.ok:
        sys.exit(f"Todoist API error {r.status_code}: {r.text}")
    return r.json() if r.text else {}


# ---------------------------------------------------------------------------
# Section lookup
# ---------------------------------------------------------------------------

def find_section_id(project_id: str, section_name: str) -> str:
    sections = api_list("/sections", {"project_id": project_id})
    for s in sections:
        if s["name"] == section_name:
            return s["id"]
    available = ", ".join(s["name"] for s in sections)
    sys.exit(f"Section '{section_name}' not found in project {project_id}. "
             f"Available: {available}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    pname, pid = resolve_project_id(args.project)
    params = {"project_id": pid}
    if args.section:
        params["section_id"] = find_section_id(pid, args.section)
    tasks = api_list("/tasks", params)

    if args.json:
        print(json.dumps(tasks, indent=2))
    else:
        if not tasks:
            print(f"No tasks in {pname}" + (f" / {args.section}" if args.section else ""))
            return
        for t in tasks:
            print(f"  [{t['id']}] {t['content']}")


def cmd_get(args):
    t = api_get(f"/tasks/{args.task_id}")
    if args.json:
        print(json.dumps(t, indent=2))
    else:
        print(f"Task: {t['content']}")
        print(f"  id: {t['id']}, project: {t['project_id']}, "
              f"section: {t.get('section_id', '—')}")
        if t.get("description"):
            print(f"  description: {t['description']}")
        if t.get("due"):
            print(f"  due: {t['due'].get('string', '?')}")


def cmd_comments(args):
    comments = api_list("/comments", {"task_id": args.task_id})
    if args.json:
        print(json.dumps(comments, indent=2))
    else:
        if not comments:
            print("(no comments)")
            return
        for c in comments:
            print(f"  [{c['posted_at']}] {c['content']}")


def cmd_create(args):
    pname, pid = resolve_project_id(args.project)
    data = {"content": args.content, "project_id": pid}
    if args.section:
        data["section_id"] = find_section_id(pid, args.section)
    if args.due:
        data["due_string"] = args.due
    if args.description:
        data["description"] = args.description
    if args.priority:
        data["priority"] = args.priority

    created = api_post("/tasks", data)
    if args.json:
        print(json.dumps(created, indent=2))
    else:
        print(f"Created [{created['id']}] in {pname}: {created['content']}")


def cmd_move_section(args):
    _, pid = resolve_project_id(args.project)
    sec_id = find_section_id(pid, args.section)
    moved = api_post(f"/tasks/{args.task_id}/move", {"section_id": sec_id})
    if args.json:
        print(json.dumps({"task_id": args.task_id, "section": args.section,
                          "section_id": sec_id, "result": moved}, indent=2))
    else:
        print(f"Task {args.task_id} moved to '{args.section}'")


def cmd_update(args):
    data = {}
    if args.title:
        data["content"] = args.title
    if args.due:
        data["due_string"] = args.due
    if args.description is not None:
        data["description"] = args.description
    if args.priority:
        data["priority"] = args.priority
    if not data:
        sys.exit("Nothing to update — pass at least one of --title/--due/--description/--priority")

    updated = api_post(f"/tasks/{args.task_id}", data)
    if args.json:
        print(json.dumps(updated, indent=2))
    else:
        print(f"Updated [{args.task_id}]")


def cmd_complete(args):
    api_post(f"/tasks/{args.task_id}/close")
    if args.json:
        print(json.dumps({"task_id": args.task_id, "completed": True}, indent=2))
    else:
        print(f"Completed [{args.task_id}]")


def cmd_comment(args):
    data = {"task_id": args.task_id, "content": args.content}
    created = api_post("/comments", data)
    if args.json:
        print(json.dumps(created, indent=2))
    else:
        print(f"Comment added to [{args.task_id}]")


def cmd_projects(args):
    projects = api_list("/projects")
    if args.json:
        print(json.dumps(projects, indent=2))
    else:
        for p in projects:
            print(f"  {p['name']}  (id: {p['id']})")


def cmd_sections(args):
    pname, pid = resolve_project_id(args.project)
    sections = api_list("/sections", {"project_id": pid})
    if args.json:
        print(json.dumps(sections, indent=2))
    else:
        print(f"Sections in {pname}:")
        for s in sections:
            print(f"  {s['name']}  (id: {s['id']})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Todoist CLI for Claude Code agents")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List tasks")
    p.add_argument("--project")
    p.add_argument("--section")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("get", help="Get a task")
    p.add_argument("task_id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("comments", help="List comments on a task")
    p.add_argument("task_id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("create", help="Create a task")
    p.add_argument("--content", required=True)
    p.add_argument("--project")
    p.add_argument("--section")
    p.add_argument("--due", help="Natural-language due date, e.g. 'tomorrow at 9am'")
    p.add_argument("--description")
    p.add_argument("--priority", type=int, help="1 (highest) - 4 (lowest)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("move-section", help="Move a task to a different section")
    p.add_argument("task_id")
    p.add_argument("section")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("update", help="Update a task")
    p.add_argument("task_id")
    p.add_argument("--title")
    p.add_argument("--due")
    p.add_argument("--description")
    p.add_argument("--priority", type=int)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("complete", help="Mark a task complete")
    p.add_argument("task_id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("comment", help="Add a comment to a task")
    p.add_argument("task_id")
    p.add_argument("--content", required=True)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("projects", help="List all projects")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("sections", help="List sections in a project")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")

    args = parser.parse_args()
    commands = {
        "list": cmd_list,
        "get": cmd_get,
        "comments": cmd_comments,
        "create": cmd_create,
        "move-section": cmd_move_section,
        "update": cmd_update,
        "complete": cmd_complete,
        "comment": cmd_comment,
        "projects": cmd_projects,
        "sections": cmd_sections,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
