# Self-improvement workflow

You CAN modify the cloning automation, your own CLAUDE.md, and configs —
when the user asks for a fix or improvement. These rules exist so self-edits
don't silently break future runs.

## Where to edit (and where NOT to)

- **Source of truth:** the git repo at `~/remote-claude-setup/`.
  - Tools: `~/remote-claude-setup/framework/tools/{elevenlabs,make,ghl,todoist}.py`
  - CLAUDE.md template: `~/remote-claude-setup/templates/workspace/CLAUDE.md`
  - Docs: `~/remote-claude-setup/templates/workspace/docs/*.md`
  - Profile config template: `~/remote-claude-setup/templates/config.json`
- **NEVER** edit `~/.claude-agents/shared/tools/*` or `~/.claude-agents/kirk/*`
  directly. Those are deployment artifacts — direct edits get clobbered the
  next time `install.sh` runs and your changes vanish.

## Required steps for any edit

1. **Confirm first.** Before editing anything that runs in production
   (tools, CLAUDE.md, docs, config schemas), describe the change in Discord
   and wait for explicit approval ("yes" / "avança" / "ok"). HARD rule.
2. **Make the edit in the repo.** `cd ~/remote-claude-setup` and edit there.
3. **Commit + push.** Clear message describing what and why:
   ```bash
   cd ~/remote-claude-setup
   git checkout -b fix/<short-description>     # use a branch for risky changes
   git add <files>
   git commit -m "fix: <description>"
   git push -u origin <branch>
   ```
4. **Propagate.** For tool changes, run `bash scripts/install.sh` to copy
   the new tool into `~/.claude-agents/shared/tools/`.
5. **Restart for CLAUDE.md / docs / config changes.** Tool changes take
   effect immediately (next Bash invocation reads the file). CLAUDE.md,
   docs, and `config.json` changes only apply after a service restart — DO
   NOT restart yourself mid-conversation. Instead, post in Discord:
   > "Mudei X em CLAUDE.md/docs/config. Faz `ssh rcorreia@192.168.59.70 'systemctl --user restart claude-agent-kirk'` quando puderes."

## Branch policy

- **Trivial fix** (typo, single-line bug, doc clarification): commit to
  master is OK after confirmation.
- **Anything else** (new feature, schema change, refactor, anything
  touching destructive operations): use a feature branch and ask the user
  to review before merging. Do not merge to master yourself.

## Things you must NOT do

- Auto-restart your own systemd service (kills you mid-task).
- Edit credentials files programmatically.
- Force-push, rewrite history, or delete branches.
- Bypass the confirmation rule because "the change looks small".

## After a successful self-edit

Report concisely in Discord: what changed, the commit hash, whether a
restart is pending. Don't narrate the diff.
