# Voice Agent cloning workflow

Three tools clone a Voice Agent stack for a new client: a Make scenario set,
ElevenLabs Conversational AI agents + workspace webhooks, and a GoHighLevel
sub-account. Template IDs live in `config.json` under `automation.*`. API
keys live in `credentials/`.

## Scripts

- `./tools/elevenlabs_tool.py` — list/get/clone agents, update prompt + tool
  webhooks, manage workspace webhooks, set agents' post-call webhook
- `./tools/make_tool.py` — list/get/clone scenarios; `clone-template-set`
  clones every scenario in the configured set; auto-detects API vs UI mode
- `./tools/ghl_tool.py` — list locations/snapshots/workflows; `create-location`
  loads a snapshot to a new sub-account

## Confirmation rule (HARD)

**Read-only commands run freely.** Safe:
`list-agents`, `get-agent`, `list-scenarios`, `get-scenario`, `get-webhook-url`,
`list-workspace-webhooks`, `list-locations`, `list-snapshots`, `list-workflows`.

**Write commands MUST be confirmed in Discord before execution.** These create
or modify external resources:
`clone-agent`, `update-prompt`, `update-webhook`, `clone-scenario`,
`clone-template-set`, `create-workspace-webhook`, `set-post-call-webhook`,
`create-location`.

Before any write, post a message describing exactly what you are about to do
(template ID, new name, target IDs/URLs) and wait for explicit "yes" /
"avança" / "ok".

## New-client cloning workflow

Triggered when the user says something like "clona um cliente novo chamado X"
or "monta o setup para o cliente Y".

1. **Confirm scope.** Ask which template stack to clone from (if more than
   one) and the new client's name. Read `automation.*` from `config.json` for
   defaults.

2. **Make first.** Cloning order is fixed: Make produces new webhook URLs
   that ElevenLabs needs. Clients have a *set* of scenarios (booking + EOC
   variants); the set lives in
   `config.json -> automation.make.template_scenarios`.
   ```bash
   ./tools/make_tool.py clone-template-set --client "<client>" --json
   ```
   Output: JSON list with `role`, `scenario_id`, `webhook_url` per scenario.
   For ad-hoc single cloning use `clone-scenario --template-id ID --name NAME`.

3. **ElevenLabs second.** Three sub-steps:
   - Clone the workspace webhooks (one per Make EOC scenario), pointing to
     the new Make webhook URLs from step 2.
     ```bash
     ./tools/elevenlabs_tool.py create-workspace-webhook --name "<client> Ads" --url <new-make-url>
     ```
   - Clone each agent in the template set, with tool URLs updated to the new
     booking webhook URL.
     ```bash
     ./tools/elevenlabs_tool.py clone-agent \
         --template-id $TEMPLATE_AGENT_ID --name "<client>" \
         --webhook-map '{"bookAppointment": "<new-booking-url>", ...}'
     ```
   - Point each new agent's `post_call_webhook_id` at the matching new
     workspace webhook (use the `linked_make_role` mapping in config).
     ```bash
     ./tools/elevenlabs_tool.py set-post-call-webhook --agent-id <new> --webhook-id <new-wh>
     ```

4. **GoHighLevel third.** `create-location` defaults to the snapshot
   configured in `automation.ghl.template_snapshot_id`.
   ```bash
   ./tools/ghl_tool.py create-location --name "<client>"
   ```
   The snapshot loads asynchronously; workflows/funnels/calendars/forms come
   over. Lead Gen Forms and forms in Sites pages are NOT included — those
   the user builds manually.

5. **Report.** Post a summary in Discord: new Make scenario IDs + URLs, new
   ElevenLabs agent IDs + workspace webhook IDs, GHL location ID.

## Failure handling

If a step fails mid-flow (e.g. ElevenLabs clones ok but Make webhook fetch
errors), STOP and report state in Discord. Do not retry blindly — partial
state is worse than no state. Ask the user how to proceed.

## Never log or echo credentials

Tools read keys from `credentials/` automatically. Never `cat` a credentials
file, never print keys to Discord, never include them in commands you write
to logs.
