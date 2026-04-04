"""Discord bot that routes messages to Claude Code CLI."""

import asyncio
import json
import logging
import os

import discord

log = logging.getLogger(__name__)


def split_message(text: str, limit: int = 2000) -> list[str]:
    """Split a message into chunks that fit within Discord's character limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at a newline near the limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


class AgentDiscordBot(discord.Client):
    def __init__(self, config: dict, workspace_dir: str):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.config = config
        self._workspace_dir = workspace_dir
        self._allowed_channel = int(config["discord"]["channel_id"])
        self._allowed_guild = int(config["discord"]["guild_id"])
        self._user_allowlist = set(config["discord"].get("user_allowlist", []))
        self._query_lock = asyncio.Lock()

    async def on_ready(self):
        log.info(f"Logged in to Discord as {self.user} (id: {self.user.id})")

    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.user:
            return
        # Allowlist enforcement
        if not message.guild or message.guild.id != self._allowed_guild:
            return
        if message.channel.id != self._allowed_channel:
            return
        if self._user_allowlist and str(message.author.id) not in self._user_allowlist:
            return

        log.info(f"Discord message from {message.author}: {message.content[:100]}")

        async with message.channel.typing():
            response = await self.invoke_claude(
                message.content, continue_session=True
            )

        for chunk in split_message(response):
            await message.channel.send(chunk)

    async def invoke_claude(
        self, prompt: str, continue_session: bool = False
    ) -> str:
        """Spawn claude CLI as subprocess and return the result text."""
        claude_cfg = self.config["claude"]
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--model",
            claude_cfg["model"],
            "--max-turns",
            str(claude_cfg["max_turns"]),
            "--allowedTools",
            claude_cfg["allowed_tools"],
            "--dangerously-skip-permissions",
        ]
        if continue_session:
            cmd.append("--continue")

        timeout = claude_cfg.get("timeout", 600)

        # Force Max plan auth by unsetting API key
        env = {**os.environ, "ANTHROPIC_API_KEY": ""}

        async with self._query_lock:
            log.info(f"Invoking Claude Code in {self._workspace_dir} (continue={continue_session})")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._workspace_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                log.error(f"Claude Code timed out after {timeout}s")
                return f"Error: Claude Code timed out after {timeout}s."

        if proc.returncode != 0:
            err = stderr.decode()[:500] if stderr else "unknown error"
            log.error(f"Claude Code exited {proc.returncode}: {err}")
            return f"Error (exit {proc.returncode}): {err}"

        try:
            result = json.loads(stdout.decode())
            return result.get("result", "No response.")
        except json.JSONDecodeError:
            # Fall back to raw text output
            text = stdout.decode().strip()
            return text if text else "No response."

    async def post_to_channel(self, text: str):
        """Post a message to the agent's Discord channel."""
        channel = self.get_channel(self._allowed_channel)
        if not channel:
            log.error(f"Channel {self._allowed_channel} not found")
            return
        for chunk in split_message(text):
            await channel.send(chunk)
