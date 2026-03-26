from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from andino.__main__ import _resolve_config_path, app
from andino.service import configure_logging

runner = CliRunner()


class TestResolveConfigPath:
    def test_yaml_path_returned_directly(self):
        result = _resolve_config_path("./agent.yaml")
        assert result == Path("./agent.yaml")

    def test_yml_extension_returned_directly(self):
        result = _resolve_config_path("configs/my-agent.yml")
        assert result == Path("configs/my-agent.yml")

    def test_path_with_slash_returned_directly(self):
        result = _resolve_config_path("examples/researcher/agent.yaml")
        assert result == Path("examples/researcher/agent.yaml")

    def test_name_resolved_to_andino_home(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/opt/andino")
        result = _resolve_config_path("researcher")
        assert result == Path("/opt/andino/agents/researcher/agent.yaml")


class TestTyperCommands:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "init" in result.output
        assert "list" in result.output
        assert "validate" in result.output
        assert "info" in result.output
        assert "task" in result.output

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "andino" in result.output

    def test_list_no_agents(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No agents" in result.output

    def test_list_with_agents(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        agent_dir = tmp_path / "agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.yaml").write_text("name: test-agent\n")
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "test-agent" in result.output

    def test_init_creates_agent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["init", "my-agent"])
        assert result.exit_code == 0
        assert "my-agent" in result.output
        assert (tmp_path / "agents" / "my-agent" / "agent.yaml").is_file()
        assert (tmp_path / "agents" / "my-agent" / "system_prompt.md").is_file()
        assert (tmp_path / "agents" / "my-agent" / "skills" / "example" / "SKILL.md").is_file()

    def test_init_with_template(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["init", "my-sre", "--template", "sre"])
        assert result.exit_code == 0
        assert "my-sre" in result.output
        assert "sre" in result.output
        agent_dir = tmp_path / "agents" / "my-sre"
        assert (agent_dir / "agent.yaml").is_file()
        assert (agent_dir / "system_prompt.md").is_file()
        # Verify agent name was updated in agent.yaml
        content = (agent_dir / "agent.yaml").read_text()
        assert "name: my-sre" in content

    def test_init_invalid_template(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["init", "bad", "--template", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_init_rejects_existing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        (tmp_path / "agents" / "dup").mkdir(parents=True)
        result = runner.invoke(app, ["init", "dup"])
        assert result.exit_code == 1

    def test_templates_lists_available(self):
        result = runner.invoke(app, ["templates"])
        assert result.exit_code == 0
        assert "blank" in result.output
        assert "researcher" in result.output
        assert "prospector" in result.output
        assert "sre" in result.output
        assert "architect" in result.output
        # Deleted templates should not appear
        assert "coder" not in result.output
        assert "reviewer" not in result.output

    def test_run_missing_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_validate_missing_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["validate", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_info_missing_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        result = runner.invoke(app, ["info", "nonexistent"])
        assert result.exit_code == 1

    def test_validate_valid_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        config = tmp_path / "agent.yaml"
        config.write_text(
            "name: test\nmodel:\n  provider: bedrock\ntools: []\nserver:\n  port: 8100\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["validate", str(config)])
        assert result.exit_code == 0
        assert "valid" in result.output
        assert "passed" in result.output

    def test_info_shows_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        config = tmp_path / "agent.yaml"
        config.write_text(
            "name: researcher\nversion: '2.0.0'\ndescription: 'Test agent'\n"
            "model:\n  provider: bedrock\n  model_id: claude-sonnet\n  max_tokens: 4096\n"
            "tools:\n  - strands_tools.http_request:http_request\n"
            "server:\n  port: 8101\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["info", str(config)])
        assert result.exit_code == 0
        assert "researcher" in result.output
        assert "2.0.0" in result.output
        assert "bedrock" in result.output

    def test_task_agent_not_running(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
        config = tmp_path / "agent.yaml"
        config.write_text(
            "name: test\nmodel:\n  provider: bedrock\ntools: []\nserver:\n  host: '127.0.0.1'\n  port: 59999\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["task", str(config), "hello"])
        assert result.exit_code == 1
        assert "connect" in result.output.lower() or "running" in result.output.lower()


class TestConfigureLogging:
    def test_sets_log_level(self):
        configure_logging("debug")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_default_info_level(self):
        configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
