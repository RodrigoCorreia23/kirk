# Todoist — full reference

Heartbeat commands are in CLAUDE.md. This file covers everything else.

**Script:** `./tools/todoist.py`
**Config:** `~/.claude-agents/PROFILE_NAME/credentials/todoist-projects.json`
**Token:** `~/.claude-agents/PROFILE_NAME/credentials/todoist-token`

## Two projects, two policies

`todoist-projects.json` defines named projects. Currently:
- `kirk` (default) -- your own project. Sections: TODO, DOING, NEEDS REVIEW, DONE.
- `personal` -- the user's personal task list.

If you omit `--project`, the tool uses `kirk`. Run
`./tools/todoist.py projects` to see all configured projects.

## Confirmation rule (HARD)

- **Reads on either project (`list`, `get`, `comments`, `sections`, `projects`):** free.
- **Writes on `kirk`** (`move-section`, `update` of tasks the user assigned to you): free.
- **`create` on `personal`:** free. The user expects you to add the task immediately and report how it ended up (id, content, section, due) — do not ask for re-confirmation.
- **`update` / `move-section` / `complete` / `comment` on `personal`** (anything that changes a task that already exists in the user's list): **must be confirmed in Discord first.** Describe the target task and the change, wait for explicit "yes" / "avança" / "ok", then run.

## Commands

```bash
./tools/todoist.py list [--project NAME] [--section SECTION] [--json]
./tools/todoist.py get <task_id> [--json]
./tools/todoist.py comments <task_id> [--json]
./tools/todoist.py create --content TEXT [--project NAME] [--section SECTION] [--due DATE] [--description TEXT] [--priority N] [--json]
./tools/todoist.py move-section <task_id> <section> [--project NAME] [--json]
./tools/todoist.py update <task_id> [--title T] [--due D] [--description X] [--priority N] [--json]
./tools/todoist.py complete <task_id> [--json]
./tools/todoist.py comment <task_id> --content TEXT [--json]
./tools/todoist.py projects [--json]
./tools/todoist.py sections [--project NAME] [--json]
```

`--priority`: 1 (highest) to 4 (lowest). `--due` accepts natural language
("tomorrow at 9am", "next Monday").

Sections in `kirk`: TODO  DOING  NEEDS REVIEW  DONE
