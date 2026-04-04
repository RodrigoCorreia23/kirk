"""Discord bot that routes messages to Claude Code CLI."""

import asyncio
import json
import logging
import os

import discord

from session_manager import SessionManager

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
        self._session_mgr = SessionManager(workspace_dir, self)

    async def on_ready(self):
        log.info(f"Logged in to Discord as {self.user} (id: {self.user.id})")
        self._session_mgr.load_thread_sessions()
        asyncio.create_task(self._session_mgr.start_cleanup_loop())

    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.user:
            return

        # Determine if this is a thread message
        is_thread = isinstance(message.channel, discord.Thread)

        # Allowlist enforcement — check parent channel for threads
        if is_thread:
            if not message.channel.parent:
                return
            if message.channel.parent.id != self._allowed_channel:
                return
        else:
            if not message.guild or message.guild.id != self._allowed_guild:
                return
            if message.channel.id != self._allowed_channel:
                return

        if self._user_allowlist and str(message.author.id) not in self._user_allowlist:
            return

        log.info(f"Discord message from {message.author}: {message.content[:100]}")

        # Get or create session for this channel/thread
        channel_id = message.channel.id
        session, is_new = self._session_mgr.get_or_create_session(
            channel_id, is_thread
        )

        async with message.channel.typing():
            response = await self.invoke_claude(
                message.content,
                session_id=session.session_id,
                is_new_session=is_new,
            )

        for chunk in split_message(response):
            await message.channel.send(chunk)

    async def invoke_claude(
        self,
        prompt: str,
        session_id: str | None = None,
        is_new_session: bool = True,
    ) -> str:
        """Spawn claude CLI as subprocess and return the result text.

        session_id=None: ephemeral session (triggers)
        session_id + is_new_session=True: create new session with --session-id
        session_id + is_new_session=False: resume existing session with --resume
        """
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

        if session_id:
            if is_new_session:
                cmd.extend(["--session-id", session_id])
            else:
                cmd.extend(["--resume", session_id])

        timeout = claude_cfg.get("timeout", 600)

        # Force Max plan auth by unsetting API key
        env = {**os.environ, "ANTHROPIC_API_KEY": ""}

        async with self._query_lock:
            session_info = f"session={session_id[:8] if session_id else 'ephemeral'}"
            log.info(
                f"Invoking Claude Code in {self._workspace_dir} "
                f"({session_info}, new={is_new_session})"
            )
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

    def save_sessions(self):
        """Save thread sessions for restart resilience."""
        self._session_mgr.save_thread_sessions()
