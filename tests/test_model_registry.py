from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from andino.model_registry import build_model


class TestBuildModel:
    @patch("andino.model_registry._build_bedrock")
    def test_bedrock_provider(self, mock_build):
        mock_build.return_value = MagicMock()
        result = build_model("bedrock", "model-id", max_tokens=2048)
        mock_build.assert_called_once_with("model-id", 2048)
        assert result is mock_build.return_value

    @patch("andino.model_registry._build_anthropic")
    def test_anthropic_provider(self, mock_build):
        mock_build.return_value = MagicMock()
        result = build_model("anthropic", "claude-3", max_tokens=1024)
        mock_build.assert_called_once_with("claude-3", 1024)
        assert result is mock_build.return_value

    @patch("andino.model_registry._build_openai")
    def test_openai_provider(self, mock_build):
        mock_build.return_value = MagicMock()
        result = build_model("openai", "gpt-4", max_tokens=4096)
        mock_build.assert_called_once_with("gpt-4")
        assert result is mock_build.return_value

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unsupported model provider"):
            build_model("invalid", "model-id")

    @patch("andino.model_registry._build_bedrock")
    def test_case_insensitive(self, mock_build):
        mock_build.return_value = MagicMock()
        build_model("  Bedrock  ", "model-id")
        mock_build.assert_called_once()

    @patch("strands.models.BedrockModel")
    def test_bedrock_with_region(self, mock_cls, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        mock_cls.return_value = MagicMock()
        from andino.model_registry import _build_bedrock

        _build_bedrock("model-id", 4096)
        mock_cls.assert_called_once_with(model_id="model-id", max_tokens=4096, region_name="us-west-2")

    @patch("strands.models.BedrockModel")
    def test_bedrock_without_region(self, mock_cls, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        mock_cls.return_value = MagicMock()
        from andino.model_registry import _build_bedrock

        _build_bedrock("model-id", 4096)
        mock_cls.assert_called_once_with(model_id="model-id", max_tokens=4096)
