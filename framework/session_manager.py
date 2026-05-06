"""Session lifecycle management for Claude Code Discord agents.

Tracks conversation sessions per Discord channel/thread:
- Channel sessions expire after 10 minutes of inactivity
- Thread sessions persist indefinitely
- On session close, generates a summary and writes it to context/
- Triggers run without session tracking (ephemeral)
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

INACTIVITY_TIMEOUT = 600  # 10 minutes — channel sessions
THREAD_INACTIVITY_TIMEOUT = 24 * 60 * 60  # 24 hours — thread sessions
CLEANUP_INTERVAL = 60  # Check for expired sessions every 60 seconds
MIN_MESSAGES_FOR_SUMMARY = 2


def _session_expired(session, now: float) -> bool:
    """Check if a session has gone idle past its timeout."""
    timeout = THREAD_INACTIVITY_TIMEOUT if session.is_thread else INACTIVITY_TIMEOUT
    return (now - session.last_activity) >= timeout

SUMMARY_PROMPT = (
    "Summarize this conversation concisely for future reference. "
    "Include: main topics discussed, any decisions made, any action items or outcomes. "
    "Start with a line: topics: keyword1, keyword2, keyword3 "
    "(comma-separated keywords that someone could search for later). "
    "Then write a short markdown summary with bullet points. "
    "Keep it under 300 words total."
)


@dataclass
class Session:
    session_id: str
    channel_id: int
    created_at: float
    last_activity: float
    is_thread: bool = False
    message_count: int = 0


class SessionManager:
    def __init__(self, workspace_dir: str, bot):
        self._sessions: dict[int, Session] = {}
        self._workspace_dir = workspace_dir
        self._bot = bot
        self._state_file = Path(workspace_dir).parent / "state" / "sessions.json"

    def get_or_create_session(
        self, channel_id: int, is_thread: bool = False
    ) -> tuple[Session, bool]:
        """Get existing session or create a new one.

        Returns (session, is_new). If a channel session expired, schedules
        async close (summary generation) and creates a fresh session.
        """
        existing = self._sessions.get(channel_id)
        now = time.time()

        if existing:
            if not _session_expired(existing, now):
                existing.last_activity = now
                existing.message_count += 1
                return existing, False

            # Expired session — close it asynchronously
            kind = "thread" if existing.is_thread else "channel"
            log.info(
                f"{kind.capitalize()} session {existing.session_id[:8]} expired "
                f"for channel {channel_id} ({existing.message_count} messages)"
            )
            asyncio.create_task(self._close_session(existing))

        # Create new session
        session = Session(
            session_id=str(uuid.uuid4()),
            channel_id=channel_id,
            created_at=now,
            last_activity=now,
            is_thread=is_thread,
            message_count=1,
        )
        self._sessions[channel_id] = session
        log.info(
            f"New {'thread' if is_thread else 'channel'} session "
            f"{session.session_id[:8]} for {channel_id}"
        )
        return session, True

    async def start_cleanup_loop(self):
        """Background task: periodically close expired channel sessions."""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            now = time.time()
            expired = [
                s for s in list(self._sessions.values())
                if _session_expired(s, now)
            ]
            for session in expired:
                log.info(
                    f"Cleanup: closing expired session {session.session_id[:8]} "
                    f"for channel {session.channel_id}"
                )
                del self._sessions[session.channel_id]
                await self._close_session(session)

    async def _close_session(self, session: Session):
        """Generate a summary and write context files."""
        if session.message_count < MIN_MESSAGES_FOR_SUMMARY:
            log.info(
                f"Skipping summary for session {session.session_id[:8]} "
                f"({session.message_count} message(s))"
            )
            return

        try:
            summary = await self._bot.invoke_claude(
                SUMMARY_PROMPT,
                session_id=session.session_id,
                is_new_session=False,
            )
        except Exception as e:
            log.error(f"Failed to generate summary: {e}")
            return

        if not summary or summary.startswith("Error"):
            log.error(f"Summary generation failed: {summary[:100]}")
            return

        # Write summary file
        context_dir = Path(self._workspace_dir) / "context"
        context_dir.mkdir(exist_ok=True)

        timestamp = time.strftime(
            "%Y-%m-%d-%Hh%M", time.localtime(session.created_at)
        )
        filepath = context_dir / f"{timestamp}.md"
        filepath.write_text(summary)
        log.info(f"Wrote context summary: {filepath.name}")

        # Update index
        self._update_index(filepath.name, summary)

    def _update_index(self, filename: str, summary: str):
        """Add an entry to context/INDEX.md."""
        index_path = Path(self._workspace_dir) / "context" / "INDEX.md"

        # Extract topics from summary
        topics = ""
        for line in summary.split("\n"):
            stripped = line.strip().lower()
            if stripped.startswith("topics:"):
                topics = line.split(":", 1)[1].strip()
                break

        if not topics:
            topics = filename

        date_str = filename[:10]
        time_str = filename[11:16].replace("h", ":")
        entry = f"- **{time_str}** -- [{topics}]({filename})"

        if index_path.exists():
            content = index_path.read_text()
        else:
            content = "# Conversation Context Index\n"

        date_heading = f"\n## {date_str}\n"
        if date_heading.strip() in content:
            # Insert entry after the date heading
            pos = content.index(date_heading.strip()) + len(date_heading.strip())
            content = content[:pos] + "\n" + entry + content[pos:]
        else:
            # Add new date heading after the title
            content = content.replace(
                "# Conversation Context Index\n",
                f"# Conversation Context Index\n{date_heading}{entry}\n",
            )

        index_path.write_text(content)
        log.info(f"Updated INDEX.md with {filename}")

    def save_thread_sessions(self):
        """Persist thread session IDs for restart resilience."""
        threads = {
            str(s.channel_id): s.session_id
            for s in self._sessions.values()
            if s.is_thread
        }
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(threads, indent=2))
        log.info(f"Saved {len(threads)} thread session(s)")

    def load_thread_sessions(self):
        """Restore thread session IDs from disk."""
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            now = time.time()
            for channel_id_str, session_id in data.items():
                self._sessions[int(channel_id_str)] = Session(
                    session_id=session_id,
                    channel_id=int(channel_id_str),
                    created_at=now,
                    last_activity=now,
                    is_thread=True,
                )
            log.info(f"Loaded {len(data)} thread session(s)")
        except Exception as e:
            log.error(f"Failed to load thread sessions: {e}")
