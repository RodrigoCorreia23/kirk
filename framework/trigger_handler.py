"""Unix socket listener for systemd timer triggers."""

import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SILENT_PREFIX = "[SILENT]"


class TriggerListener:
    def __init__(self, socket_path: str, bot, workspace_dir: str):
        self.socket_path = socket_path
        self.bot = bot
        self._workspace_dir = workspace_dir

    async def listen(self):
        """Listen on Unix socket for trigger prompts."""
        # Clean up stale socket
        sock_path = Path(self.socket_path)
        if sock_path.exists():
            sock_path.unlink()

        server = await asyncio.start_unix_server(
            self._handle_connection, self.socket_path
        )
        os.chmod(self.socket_path, 0o600)
        log.info(f"Trigger listener started on {self.socket_path}")

        async with server:
            await server.serve_forever()

    async def _handle_connection(self, reader, writer):
        """Handle an incoming trigger prompt."""
        try:
            data = await reader.read(8192)
            prompt = data.decode().strip()
        except Exception as e:
            log.error(f"Failed to read trigger prompt: {e}")
            return
        finally:
            writer.close()
            await writer.wait_closed()

        if not prompt:
            log.warning("Empty trigger prompt received — ignoring")
            return

        log.info(f"Trigger received: {prompt[:100]}...")

        # Invoke Claude without session tracking (ephemeral)
        response = await self.bot.invoke_claude(
            prompt, session_id=None, is_new_session=True
        )

        # Only post to Discord if the response is meaningful
        if response.startswith(SILENT_PREFIX):
            log.info(f"Trigger response is silent: {response[:80]}")
            return

        log.info(f"Posting trigger response to Discord ({len(response)} chars)")
        await self.bot.post_to_channel(response)
