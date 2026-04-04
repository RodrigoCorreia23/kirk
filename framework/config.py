"""Profile configuration loader for Claude agents."""

import json
from pathlib import Path

BASE_DIR = Path.home() / ".claude-agents"


def load_config(profile: str) -> dict:
    """Load config.json for the given profile."""
    config_path = BASE_DIR / profile / "config.json"
    with open(config_path) as f:
        return json.load(f)


def profile_dir(profile: str) -> Path:
    """Return the profile's root directory."""
    return BASE_DIR / profile


def workspace_dir(profile: str) -> Path:
    """Return the profile's workspace directory (Claude Code -C target)."""
    return BASE_DIR / profile / "workspace"


def read_credential(profile: str, name: str) -> str:
    """Read a credential file and return its contents stripped."""
    cred_path = BASE_DIR / profile / "credentials" / name
    return cred_path.read_text().strip()
