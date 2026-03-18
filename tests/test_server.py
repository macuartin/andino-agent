from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from andino.config import AgentConfig
from andino.server import create_app
from andino.task_executor import TaskState, TaskStatus


def _mock_executor():
    mock = MagicMock()
    mock.running_count = 0
    mock.submit = AsyncMock()
    mock.get_status = MagicMock(return_value=None)
    mock.list_tasks = MagicMock(return_value=[])
    return mock


@pytest.fixture()
def app(sample_config):
    with patch("andino.server.TaskExecutor") as MockExecutor:
        mock_executor = _mock_executor()
        MockExecutor.return_value = mock_executor

        application = create_app(sample_config)
        application._test_executor = mock_executor
        yield application


@pytest.fixture()
def client(app):
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client, sample_config):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agent_name"] == sample_config.name

    def test_health_includes_uptime(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], float)


class TestInfoEndpoint:
    def test_info_returns_metadata(self, client, sample_config):
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == sample_config.name
        assert data["version"] == sample_config.version
        assert data["model"]["provider"] == sample_config.model.provider
        assert data["max_concurrent_tasks"] == sample_config.limits.max_concurrent_tasks


class TestTaskSubmission:
    def test_submit_task_returns_202(self, client, app):
        app._test_executor.submit.return_value = TaskStatus(
            task_id="abc-123",
            status=TaskState.queued,
        )
        resp = client.post("/task", json={"prompt": "Hello"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"

    def test_submit_queue_full_returns_429(self, client, app):
        app._test_executor.submit.side_effect = ValueError("full")
        resp = client.post("/task", json={"prompt": "Hello"})
        assert resp.status_code == 429

    def test_submit_requires_prompt(self, client):
        resp = client.post("/task", json={})
        assert resp.status_code == 422


class TestTaskRetrieval:
    def test_get_existing_task(self, client, app):
        app._test_executor.get_status.return_value = TaskStatus(
            task_id="t1",
            status=TaskState.completed,
            result="done",
        )
        resp = client.get("/task/t1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_get_missing_task_returns_404(self, client, app):
        app._test_executor.get_status.return_value = None
        resp = client.get("/task/nonexistent")
        assert resp.status_code == 404

    def test_list_tasks(self, client, app):
        app._test_executor.list_tasks.return_value = [
            TaskStatus(task_id="t1", status=TaskState.queued),
            TaskStatus(task_id="t2", status=TaskState.completed),
        ]
        resp = client.get("/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestAuth:
    """Test API key authentication."""

    @pytest.fixture()
    def auth_config(self, sample_config_dict):
        d = {**sample_config_dict, "server": {**sample_config_dict["server"], "api_key": "test-secret-key"}}
        return AgentConfig.model_validate(d)

    @pytest.fixture()
    def auth_app(self, auth_config):
        with patch("andino.server.TaskExecutor") as MockExecutor:
            mock_executor = _mock_executor()
            MockExecutor.return_value = mock_executor
            application = create_app(auth_config)
            application._test_executor = mock_executor
            yield application

    @pytest.fixture()
    def auth_client(self, auth_app):
        return TestClient(auth_app)

    def test_no_key_configured_allows_all(self, client):
        resp = client.get("/tasks")
        assert resp.status_code == 200

    def test_valid_key_returns_200(self, auth_client):
        resp = auth_client.get("/tasks", headers={"Authorization": "Bearer test-secret-key"})
        assert resp.status_code == 200

    def test_missing_key_returns_401(self, auth_client):
        resp = auth_client.get("/tasks")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, auth_client):
        resp = auth_client.get("/tasks", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_health_no_auth_required(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200
