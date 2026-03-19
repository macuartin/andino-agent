from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from andino.channels.slack_upload import (
    _contexts,
    clear_upload_context,
    register_upload_context,
    slack_upload_file,
)


@pytest.fixture(autouse=True)
def _clean_contexts():
    """Ensure the context registry is empty before and after each test."""
    _contexts.clear()
    yield
    _contexts.clear()


@pytest.fixture()
def mock_client():
    client = MagicMock()
    client.files_upload_v2 = AsyncMock()
    return client


class TestContextRegistry:
    def test_register_and_clear(self, mock_client):
        register_upload_context("/ws/session-1", mock_client, "C123", "1234.5678")
        assert "/ws/session-1" in _contexts
        assert _contexts["/ws/session-1"]["channel_id"] == "C123"

        clear_upload_context("/ws/session-1")
        assert "/ws/session-1" not in _contexts

    def test_clear_nonexistent(self):
        # Should not raise
        clear_upload_context("/nonexistent")


class TestSlackUploadFile:
    async def test_uploads_file(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        # Create a test file
        test_file = tmp_path / "report.csv"
        test_file.write_text("col1,col2\na,b\n")

        result = await slack_upload_file(file_path=str(test_file))

        assert result["status"] == "success"
        assert "report.csv" in result["content"][0]["text"]
        mock_client.files_upload_v2.assert_called_once()
        call_kwargs = mock_client.files_upload_v2.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert call_kwargs["thread_ts"] == "ts123"
        assert call_kwargs["filename"] == "report.csv"

    async def test_uploads_with_comment(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        test_file = tmp_path / "data.json"
        test_file.write_text('{"key": "value"}')

        result = await slack_upload_file(file_path=str(test_file), comment="Here's the data")

        assert result["status"] == "success"
        call_kwargs = mock_client.files_upload_v2.call_args[1]
        assert call_kwargs["initial_comment"] == "Here's the data"

    async def test_relative_path_resolution(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        test_file = tmp_path / "output.txt"
        test_file.write_text("hello")

        result = await slack_upload_file(file_path="output.txt")

        assert result["status"] == "success"
        assert "output.txt" in result["content"][0]["text"]

    async def test_no_context_error(self):
        result = await slack_upload_file(file_path="/some/file.csv")

        assert result["status"] == "error"
        assert "No Slack upload context" in result["content"][0]["text"]

    async def test_file_not_found(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        result = await slack_upload_file(file_path=str(tmp_path / "nonexistent.csv"))

        assert result["status"] == "error"
        assert "File not found" in result["content"][0]["text"]

    async def test_empty_file(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = await slack_upload_file(file_path=str(empty_file))

        assert result["status"] == "error"
        assert "empty" in result["content"][0]["text"]

    async def test_upload_error_handled(self, tmp_path, mock_client):
        ws_dir = str(tmp_path)
        mock_client.files_upload_v2 = AsyncMock(side_effect=RuntimeError("API error"))
        register_upload_context(ws_dir, mock_client, "C123", "ts123")

        test_file = tmp_path / "report.csv"
        test_file.write_text("data")

        result = await slack_upload_file(file_path=str(test_file))

        assert result["status"] == "error"
        assert "Failed to upload" in result["content"][0]["text"]
