from __future__ import annotations

from pathlib import Path

import pytest

from andino.config import AgentConfig

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_config_dict():
    return {
        "name": "test-agent",
        "version": "1.0.0",
        "description": "A test agent",
        "model": {
            "provider": "bedrock",
            "model_id": "us.anthropic.claude-sonnet-4-6",
            "max_tokens": 2048,
        },
        "system_prompt": "You are helpful.",
        "tools": [],
        "server": {"host": "127.0.0.1", "port": 9999},
        "limits": {"max_concurrent_tasks": 2, "task_timeout_seconds": 30},
    }


@pytest.fixture()
def sample_config(sample_config_dict):
    return AgentConfig.model_validate(sample_config_dict)


@pytest.fixture()
def jira_env(monkeypatch):
    monkeypatch.setenv("JIRA_CLOUD_ID", "test-cloud-id")
    monkeypatch.setenv("JIRA_USER_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
