from __future__ import annotations

import logging
from pathlib import Path

from andino.__main__ import _build_parser, _resolve_config_path
from andino.service import configure_logging


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


class TestBuildParser:
    def test_run_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "researcher"])
        assert args.command == "run"
        assert args.agent == "researcher"
        assert args.log_level == "info"
        assert args.log_file is None

    def test_run_with_options(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "researcher", "--log-level", "debug", "--log-file", "/tmp/test.log"])
        assert args.log_level == "debug"
        assert args.log_file == "/tmp/test.log"

    def test_init_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["init", "my-agent"])
        assert args.command == "init"
        assert args.name == "my-agent"

    def test_list_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"


class TestConfigureLogging:
    def test_sets_log_level(self):
        configure_logging("debug")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_default_info_level(self):
        configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
