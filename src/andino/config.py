from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    model_config = {"protected_namespaces": ()}

    provider: str = "bedrock"
    model_id: str = "us.anthropic.claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float | None = None


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8100


class LimitsConfig(BaseModel):
    max_concurrent_tasks: int = 1
    task_timeout_seconds: int = 600


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
    server: ServerConfig = ServerConfig()
    limits: LimitsConfig = LimitsConfig()
    session: SessionConfig = SessionConfig()

    @classmethod
    def from_yaml(cls, path: str) -> AgentConfig:
        """Load agent config from a YAML file.

        If ``system_prompt`` is a relative path ending in ``.md``, it is
        resolved relative to the YAML file's directory and its contents are
        read as the system prompt text.
        """
        yaml_path = Path(path).resolve()
        raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        # Resolve system_prompt file reference
        sp = raw.get("system_prompt", "")
        if isinstance(sp, str) and sp.endswith(".md"):
            sp_path = yaml_path.parent / sp
            if sp_path.is_file():
                raw["system_prompt"] = sp_path.read_text(encoding="utf-8")
                logger.info("loaded_system_prompt path=%s", sp_path)
            else:
                logger.warning("system_prompt file not found: %s", sp_path)

        return cls.model_validate(raw)
