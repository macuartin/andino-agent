from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from andino.hitl import HitlConfig
from andino.home import resolve_data_path

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider: str = "bedrock"
    model_id: str = "us.anthropic.claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float | None = None
    extras: dict[str, Any] = {}


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8100
    api_key: str = ""


class LimitsConfig(BaseModel):
    max_concurrent_tasks: int = 1
    task_timeout_seconds: int = 600


class WorkspaceConfig(BaseModel):
    enabled: bool = False
    base_dir: str = ".workspaces"


class ConversationConfig(BaseModel):
    manager: str = "sliding_window"  # sliding_window | summarizing | null
    window_size: int = 40
    should_truncate_results: bool = True
    per_turn: bool | int = False
    summary_ratio: float = 0.3
    preserve_recent_messages: int = 10


class SessionConfig(BaseModel):
    storage_dir: str = ".sessions"
    max_pool_size: int = 20


class AgentConfig(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    model: ModelConfig = ModelConfig()
    system_prompt: str = ""
    tools: list[str] = []
    mcp_servers: list[dict[str, Any]] = []
    channels: dict[str, dict[str, Any]] = {}
    hitl: HitlConfig = HitlConfig()
    server: ServerConfig = ServerConfig()
    limits: LimitsConfig = LimitsConfig()
    conversation: ConversationConfig = ConversationConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    session: SessionConfig = SessionConfig()

    @classmethod
    def from_yaml(cls, path: str) -> AgentConfig:
        """Load agent config from a YAML file.

        If ``system_prompt`` is a relative path ending in ``.md``, it is
        resolved relative to the YAML file's directory and its contents are
        read as the system prompt text.

        String values matching ``${VAR}`` are expanded from environment
        variables.
        """
        yaml_path = Path(path).resolve()
        raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        # Expand ${VAR} references from environment
        _expand_env_vars(raw)

        # Resolve system_prompt file reference
        sp = raw.get("system_prompt", "")
        if isinstance(sp, str) and sp.endswith(".md"):
            sp_path = yaml_path.parent / sp
            if sp_path.is_file():
                raw["system_prompt"] = sp_path.read_text(encoding="utf-8")
                logger.info("loaded_system_prompt path=%s", sp_path)
            else:
                logger.warning("system_prompt file not found: %s", sp_path)

        config = cls.model_validate(raw)

        # Resolve relative data paths against ANDINO_HOME
        config.session.storage_dir = str(resolve_data_path(config.session.storage_dir))
        config.workspace.base_dir = str(resolve_data_path(config.workspace.base_dir))

        return config


_ENV_VAR_RE = re.compile(r"\$\{([^}]+)}")


def _expand_env_vars(data: Any) -> Any:
    """Recursively replace ``${VAR}`` patterns with values from ``os.environ``."""
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = _expand_env_vars(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            data[i] = _expand_env_vars(item)
    elif isinstance(data, str) and "${" in data:
        data = _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), data)
    return data
