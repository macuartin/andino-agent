"""ANDINO_HOME directory resolver.

All persistent data (agent configs, sessions, workspaces, logs) lives under
a single home directory, defaulting to ``~/.andino``.  Override with the
``ANDINO_HOME`` environment variable.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_HOME = "~/.andino"


def get_andino_home() -> Path:
    """Return the resolved ANDINO_HOME path."""
    return Path(os.environ.get("ANDINO_HOME", _DEFAULT_HOME)).expanduser().resolve()


def resolve_agent_dir(name: str) -> Path:
    """Return the directory for a named agent: ``$ANDINO_HOME/agents/<name>``."""
    return get_andino_home() / "agents" / name


def resolve_data_path(relative_path: str) -> Path:
    """Resolve a path against ANDINO_HOME.

    Absolute paths are returned unchanged.  Relative paths are resolved
    relative to ANDINO_HOME (not the current working directory).
    """
    p = Path(relative_path)
    if p.is_absolute():
        return p
    return get_andino_home() / relative_path
