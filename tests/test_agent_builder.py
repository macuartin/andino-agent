from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel
from strands.agent.conversation_manager import (
    NullConversationManager,
    SlidingWindowConversationManager,
    SummarizingConversationManager,
)

from andino.agent_builder import _build_conversation_manager, _load_output_schema, build_agent
from andino.config import AgentConfig, ConversationConfig


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


class TestSkills:
    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_no_skills_no_plugins(self, mock_build_model, mock_agent_cls, sample_config):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.skills = []

        build_agent(sample_config)

        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs.get("plugins") is None

    @patch("strands.vended_plugins.skills.AgentSkills")
    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_skills_creates_plugin(self, mock_build_model, mock_agent_cls, mock_agent_skills, sample_config, tmp_path):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()
        mock_agent_skills.return_value = MagicMock()

        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: A test\n---\nInstructions here.\n"
        )

        sample_config.skills = [str(tmp_path / "skills")]

        build_agent(sample_config)

        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs.get("plugins") is not None
        assert len(call_kwargs["plugins"]) == 1


class _SampleSchema(BaseModel):
    name: str
    score: float


class _NotPydantic:
    pass


@pytest.fixture
def schema_module():
    """Install a temporary module exposing _SampleSchema for output_schema tests."""
    mod = types.ModuleType("andino_test_schemas")
    mod.SampleSchema = _SampleSchema
    mod.NotPydantic = _NotPydantic
    sys.modules["andino_test_schemas"] = mod
    yield mod
    sys.modules.pop("andino_test_schemas", None)


class TestLoadOutputSchema:
    def test_colon_form(self, schema_module):
        cls = _load_output_schema("andino_test_schemas:SampleSchema")
        assert cls is _SampleSchema

    def test_dot_form(self, schema_module):
        cls = _load_output_schema("andino_test_schemas.SampleSchema")
        assert cls is _SampleSchema

    def test_missing_attribute(self, schema_module):
        with pytest.raises(ValueError, match="Attribute 'Ghost' not found"):
            _load_output_schema("andino_test_schemas:Ghost")

    def test_invalid_ref_format(self):
        with pytest.raises(ValueError, match="Invalid output_schema"):
            _load_output_schema("no_separator")

    def test_not_pydantic_subclass(self, schema_module):
        with pytest.raises(TypeError, match="not a Pydantic BaseModel"):
            _load_output_schema("andino_test_schemas:NotPydantic")


class TestOutputSchemaWiring:
    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_no_schema_no_kwarg(self, mock_build_model, mock_agent_cls, sample_config):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.output_schema = ""

        build_agent(sample_config)
        call_kwargs = mock_agent_cls.call_args[1]
        assert "structured_output_model" not in call_kwargs

    @patch("andino.agent_builder.Agent")
    @patch("andino.agent_builder.build_model")
    def test_schema_passed_to_agent(self, mock_build_model, mock_agent_cls, sample_config, schema_module):
        mock_build_model.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        sample_config.output_schema = "andino_test_schemas:SampleSchema"

        build_agent(sample_config)
        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["structured_output_model"] is _SampleSchema
