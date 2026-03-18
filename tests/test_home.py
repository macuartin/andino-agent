from __future__ import annotations

from pathlib import Path

from andino.home import get_andino_home, resolve_agent_dir, resolve_data_path


class TestGetAndinoHome:
    def test_default_home(self, monkeypatch):
        monkeypatch.delenv("ANDINO_HOME", raising=False)
        home = get_andino_home()
        assert home == Path.home() / ".andino"

    def test_custom_home(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/custom/path")
        home = get_andino_home()
        assert home == Path("/custom/path")

    def test_tilde_expansion(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "~/my-andino")
        home = get_andino_home()
        assert home == Path.home() / "my-andino"


class TestResolveAgentDir:
    def test_resolve_agent_dir(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/opt/andino")
        result = resolve_agent_dir("researcher")
        assert result == Path("/opt/andino/agents/researcher")


class TestResolveDataPath:
    def test_relative_path_resolved_against_home(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/opt/andino")
        result = resolve_data_path(".sessions")
        assert result == Path("/opt/andino/.sessions")

    def test_absolute_path_unchanged(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/opt/andino")
        result = resolve_data_path("/data/sessions")
        assert result == Path("/data/sessions")

    def test_relative_workspace_path(self, monkeypatch):
        monkeypatch.setenv("ANDINO_HOME", "/opt/andino")
        result = resolve_data_path(".workspaces")
        assert result == Path("/opt/andino/.workspaces")
