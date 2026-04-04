#!/usr/bin/env python3
"""Main entrypoint for Claude Code Discord agents.

Usage:
    agent_main.py --profile <name>

Runs a long-lived process with three concurrent tasks:
  1. Discord bot (listens for messages, routes to Claude Code CLI)
  2. Trigger listener (Unix socket for systemd timer prompts)
  3. Watchdog (monitors Discord connection health)
"""

import argparse
import asyncio
import logging
import signal
import sys

from config import load_config, read_credential, workspace_dir, profile_dir
from discord_bot import AgentDiscordBot
from trigger_handler import TriggerListener

log = logging.getLogger("claude-agent")


async def watchdog(bot: AgentDiscordBot, restart_event: asyncio.Event):
    """Monitor Discord connection health. Signals restart if stuck."""
    while not restart_event.is_set():
        await asyncio.sleep(300)  # Check every 5 minutes
        if bot.is_closed():
            log.warning("Discord bot is closed — signaling restart")
            restart_event.set()
            return
        if not bot.is_ready():
            log.warning("Discord bot not ready — will check again in 5 min")


async def run_agent(profile: str):
    """Run the agent's Discord bot, trigger listener, and watchdog."""
    config = load_config(profile)
    ws_dir = str(workspace_dir(profile))
    discord_token = read_credential(profile, "discord-bot-token")

    # Resolve trigger socket path
    trigger_cfg = config.get("trigger", {})
    socket_path = trigger_cfg.get("socket_path", "state/trigger.sock")
    if not socket_path.startswith("/"):
        socket_path = str(profile_dir(profile) / socket_path)

    bot = AgentDiscordBot(config, ws_dir)
    trigger = TriggerListener(socket_path, bot, ws_dir)
    restart_event = asyncio.Event()

    async def run_bot():
        try:
            await bot.start(discord_token)
        except Exception as e:
            log.error(f"Discord bot crashed: {e}")
            restart_event.set()

    async def run_trigger():
        try:
            await trigger.listen()
        except Exception as e:
            log.error(f"Trigger listener crashed: {e}")
            restart_event.set()

    # Run all three tasks concurrently
    tasks = [
        asyncio.create_task(run_bot(), name="discord-bot"),
        asyncio.create_task(run_trigger(), name="trigger-listener"),
        asyncio.create_task(watchdog(bot, restart_event), name="watchdog"),
    ]

    # Wait until restart is signaled or a task finishes unexpectedly
    done, pending = await asyncio.wait(
        [*tasks, asyncio.create_task(restart_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Clean up
    log.info("Shutting down...")
    bot.save_sessions()
    for task in pending:
        task.cancel()
    if not bot.is_closed():
        await bot.close()

    # If restart was signaled, exit with non-zero so systemd restarts us
    if restart_event.is_set():
        log.warning("Restarting due to watchdog or crash")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Claude Code Discord Agent")
    parser.add_argument("--profile", required=True, help="Agent profile name")
    args = parser.parse_args()

    # Logging to stderr (journalctl captures it)
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [%(levelname)s] [{args.profile}] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        stream=sys.stderr,
    )

    log.info(f"Starting Claude agent: {args.profile}")

    # Handle SIGTERM gracefully
    loop = asyncio.new_event_loop()

    def handle_signal():
        log.info("Received shutdown signal")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    try:
        loop.run_until_complete(run_agent(args.profile))
    except asyncio.CancelledError:
        log.info("Agent stopped")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
