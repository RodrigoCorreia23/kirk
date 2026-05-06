# Andavira — cooperative management app

The user's separate project. You have read access to its historical context
(snapshot in `./context/andavira/`) and SSH access to the production VM.

## Context (read-only background)

`./context/andavira/` contains a snapshot of the user's Claude memory, taken
at handoff time. Two folders:

- `current/` — recent state (April 23 onward): VM access, deployment layout,
  ToConline integration, member refactor, drive backups, fornecedores plan,
  features shipped, n8n cleanup, rosita agent.
- `older/` — earlier sessions and roadmaps (Apr 8–14): security roadmap,
  payments standby, registo anual plan, candidatura form spec, cents
  rounding rule, user profile.

Start by reading `./context/andavira/current/MEMORY.md` (the index) when the
user asks anything Andavira-related. Open specific files only when relevant.

**These files are a frozen snapshot — they will not auto-update.** If facts
in them conflict with what you observe on the live VM, trust the live VM.

## Live VM access

```bash
ssh ctvc@192.168.59.210
```

VM hostname is `andavira-app`. Key auth is set up; no password needed. This
is the **production** VM running the cooperative app — be careful.

### Permission tiers (HARD rules)

- **Read-only** (cat/ls/grep/git log/journalctl/psql SELECT): free.
- **Service status** (`systemctl status andavira-api`, port checks): free.
- **Service restart / deploys / DB writes / git push / file modification on
  the VM:** confirm in Discord first. Describe what and why, wait for "yes"
  / "avança" / "ok".
- **Destructive ops** (rm, drop tables, kill processes, sudo of any kind):
  confirm in Discord, AND state what you'll roll back to if it goes wrong.

## Credentials hygiene (HARD)

If you encounter literal passwords, tokens, or secrets in any context file
or live VM output, you must NEVER echo them to Discord, write them to logs,
or repeat them in commands you display. Refer to them only by description
("the formbricks DB password from the May 5 incident", "the
INTEGRATIONS_ENC_KEY in the systemd drop-in"). The context files were
sanitized at handoff, but the live VM still has real secrets.

## "Study the project" workflow

1. Read `./context/andavira/current/MEMORY.md`.
2. Skim file titles, decide which 2–4 are most relevant. Don't bulk-read.
3. SSH only when context isn't enough.
4. Report concisely: what you learned, what's still unclear.
