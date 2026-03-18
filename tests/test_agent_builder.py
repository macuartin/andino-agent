from __future__ import annotations

from unittest.mock import MagicMock, patch

from strands.agent.conversation_manager import (
    NullConversationManager,
    SlidingWindowConversationManager,
    SummarizingConversationManager,
)

from andino.agent_builder import _build_conversation_manager, build_agent
from andino.config import ConversationConfig


class TestBuildConversationManager:
    def test_default_sliding_window(self):
        config = ConversationConfig()
        cm = _build_conversation_manager(config)
        assert isinstance(cm, SlidingWindowConversationManager)

    def test_sliding_window_with_params(self):
        config = ConversationConfig(manager="sliding_window", window_size=10, per_turn=True)
        cm = _build_conversation_manager(config)
        assert isinstance(cm, SlidingWindowConversationManager)

    def test_null_manager(self):
        config = ConversationConfig(manager="null")
        cm = _build_conversation_manager(config)
        assert isinstance(cm, NullConversationManager)

    def test_summarizing_manager(self):
        config = ConversationConfig(manager="summarizing", summary_ratio=0.5, preserve_recent_messages=5)
        cm = _build_conversation_manager(config)
        assert isinstance(cm, SummarizingConversationManager)

    def test_case_insensitive(self):
        config = ConversationConfig(manager="  Sliding_Window  ")
        cm = _build_conversation_manager(config)
        assert isinstance(cm, SlidingWindowConversationManager)


class TestWorkspace:
    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_workspace_creates_directory(self, mock_build_model, mock_agent_cls, sample_config, tmp_path):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.workspace.enabled = True
        sample_config.workspace.base_dir = str(tmp_path / "workspaces")

        build_agent(sample_config, session_id="test-session")

        workspace_dir = tmp_path / "workspaces" / "test-session"
        assert workspace_dir.exists()
        assert workspace_dir.is_dir()

    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_workspace_enriches_system_prompt(self, mock_build_model, mock_agent_cls, sample_config, tmp_path):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.system_prompt = "You are helpful."
        sample_config.workspace.enabled = True
        sample_config.workspace.base_dir = str(tmp_path / "workspaces")

        build_agent(sample_config, session_id="test-session")

        call_kwargs = mock_agent_cls.call_args[1]
        assert "## Workspace" in call_kwargs["system_prompt"]
        assert "test-session" in call_kwargs["system_prompt"]
        assert "You are helpful." in call_kwargs["system_prompt"]

    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_workspace_disabled_no_enrichment(self, mock_build_model, mock_agent_cls, sample_config):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.system_prompt = "You are helpful."
        sample_config.workspace.enabled = False

        build_agent(sample_config, session_id="test-session")

        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["system_prompt"] == "You are helpful."

    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_workspace_no_session_no_enrichment(self, mock_build_model, mock_agent_cls, sample_config, tmp_path):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.system_prompt = "You are helpful."
        sample_config.workspace.enabled = True
        sample_config.workspace.base_dir = str(tmp_path / "workspaces")

        build_agent(sample_config, session_id=None)

        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["system_prompt"] == "You are helpful."
        # Directory should NOT be created for stateless agents
        assert not (tmp_path / "workspaces").exists()
