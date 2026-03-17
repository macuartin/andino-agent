from __future__ import annotations

from pathlib import Path

import pytest

from andino.config import AgentConfig, LimitsConfig, ModelConfig, ServerConfig, SessionConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestModelConfig:
    def test_defaults(self):
        cfg = ModelConfig()
        assert cfg.provider == "bedrock"
        assert cfg.model_id == "us.anthropic.claude-sonnet-4-6"
        assert cfg.max_tokens == 4096
        assert cfg.temperature is None

    def test_custom_values(self):
        cfg = ModelConfig(provider="anthropic", model_id="claude-3", max_tokens=1024, temperature=0.5)
        assert cfg.provider == "anthropic"
        assert cfg.temperature == 0.5


class TestServerConfig:
    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8100

    def test_custom_port(self):
        cfg = ServerConfig(port=9090)
        assert cfg.port == 9090


class TestLimitsConfig:
    def test_defaults(self):
        cfg = LimitsConfig()
        assert cfg.max_concurrent_tasks == 1
        assert cfg.task_timeout_seconds == 600


class TestSessionConfig:
    def test_defaults(self):
        cfg = SessionConfig()
        assert cfg.storage_dir == ".sessions"
        assert cfg.max_pool_size == 20


class TestAgentConfig:
    def test_minimal_config(self):
        cfg = AgentConfig(name="minimal")
        assert cfg.name == "minimal"
        assert cfg.version == "1.0.0"
        assert cfg.description == ""
        assert cfg.tools == []
        assert cfg.mcp_servers == []

    def test_full_config(self, sample_config_dict):
        cfg = AgentConfig.model_validate(sample_config_dict)
        assert cfg.name == "test-agent"
        assert cfg.model.provider == "bedrock"
        assert cfg.server.port == 9999
        assert cfg.limits.max_concurrent_tasks == 2

    def test_from_yaml(self):
        cfg = AgentConfig.from_yaml(str(FIXTURES_DIR / "valid_agent.yaml"))
        assert cfg.name == "test-agent"
        assert cfg.system_prompt == "You are a test agent."
        assert cfg.server.port == 9999
        assert cfg.limits.task_timeout_seconds == 30

    def test_from_yaml_inline_prompt(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("name: inline\nsystem_prompt: 'Hello world'\n")
        cfg = AgentConfig.from_yaml(str(yaml_file))
        assert cfg.system_prompt == "Hello world"

    def test_from_yaml_missing_prompt_file(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("name: missing\nsystem_prompt: ./nonexistent.md\n")
        cfg = AgentConfig.from_yaml(str(yaml_file))
        assert cfg.system_prompt == "./nonexistent.md"

    def test_name_required(self):
        with pytest.raises(ValueError):
            AgentConfig.model_validate({})
