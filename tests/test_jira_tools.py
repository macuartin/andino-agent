from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from andino.tools.jira import (
    _adf_text,
    _err,
    _jira_auth,
    _jira_request,
    _ok,
    jira_add_comment,
    jira_assign_issue,
    jira_create_issue,
    jira_get_issue,
    jira_get_transitions,
    jira_search_issues,
    jira_transition_issue,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_ok(self):
        result = _ok("done")
        assert result == {"status": "success", "content": [{"text": "done"}]}

    def test_err(self):
        result = _err("fail")
        assert result == {"status": "error", "content": [{"text": "fail"}]}

    def test_adf_text(self):
        adf = _adf_text("hello")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert adf["content"][0]["type"] == "paragraph"
        assert adf["content"][0]["content"][0]["text"] == "hello"


class TestJiraAuth:
    def test_with_env_vars(self, jira_env):
        cloud_id, email, token = _jira_auth()
        assert cloud_id == "test-cloud-id"
        assert email == "test@example.com"
        assert token == "test-token"

    def test_without_env_vars(self, monkeypatch):
        monkeypatch.delenv("JIRA_CLOUD_ID", raising=False)
        monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        cloud_id, email, token = _jira_auth()
        assert cloud_id == ""
        assert email == ""
        assert token == ""


# ---------------------------------------------------------------------------
# _jira_request
# ---------------------------------------------------------------------------


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


class TestJiraRequest:
    async def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("JIRA_CLOUD_ID", raising=False)
        monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        ok, data = await _jira_request("GET", "issue/X")
        assert ok is False
        assert "not configured" in data

    async def test_success_200(self, jira_env):
        mock_resp = _mock_response(200, {"key": "AD-1"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("andino.tools.jira.httpx.AsyncClient", return_value=mock_client):
            ok, data = await _jira_request("GET", "issue/AD-1")
        assert ok is True
        assert data == {"key": "AD-1"}

    async def test_success_204(self, jira_env):
        mock_resp = _mock_response(204)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("andino.tools.jira.httpx.AsyncClient", return_value=mock_client):
            ok, data = await _jira_request("POST", "issue/AD-1/transitions")
        assert ok is True
        assert data == {}

    async def test_error_response(self, jira_env):
        mock_resp = _mock_response(403, text="Forbidden")
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("andino.tools.jira.httpx.AsyncClient", return_value=mock_client):
            ok, data = await _jira_request("GET", "issue/AD-1")
        assert ok is False
        assert "403" in data

    async def test_http_exception(self, jira_env):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with patch("andino.tools.jira.httpx.AsyncClient", return_value=mock_client):
            ok, data = await _jira_request("GET", "issue/AD-1")
        assert ok is False
        assert "HTTP error" in data


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_jira_request():
    with patch("andino.tools.jira._jira_request", new_callable=AsyncMock) as mock:
        yield mock


class TestJiraGetIssue:
    async def test_success(self, mock_jira_request):
        mock_jira_request.return_value = (True, {
            "key": "AD-1",
            "fields": {
                "summary": "Test issue",
                "status": {"name": "To Do"},
                "assignee": {"displayName": "John"},
                "priority": {"name": "High"},
                "issuetype": {"name": "Task"},
                "created": "2026-01-01",
                "updated": "2026-01-02",
            },
        })
        result = await jira_get_issue("AD-1")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "AD-1" in text
        assert "To Do" in text
        assert "John" in text

    async def test_error(self, mock_jira_request):
        mock_jira_request.return_value = (False, "Not found")
        result = await jira_get_issue("AD-999")
        assert result["status"] == "error"

    async def test_unassigned(self, mock_jira_request):
        mock_jira_request.return_value = (True, {
            "key": "AD-1",
            "fields": {
                "summary": "No assignee",
                "status": {"name": "Open"},
                "assignee": None,
                "priority": None,
                "issuetype": {"name": "Bug"},
                "created": "",
                "updated": "",
            },
        })
        result = await jira_get_issue("AD-1")
        text = result["content"][0]["text"]
        assert "Unassigned" in text
        assert "None" in text  # priority


class TestJiraGetTransitions:
    async def test_with_transitions(self, mock_jira_request):
        mock_jira_request.return_value = (True, {
            "transitions": [
                {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
                {"id": "21", "name": "Done", "to": {"name": "Done"}},
            ]
        })
        result = await jira_get_transitions("AD-1")
        text = result["content"][0]["text"]
        assert "ID 11" in text
        assert "In Progress" in text

    async def test_no_transitions(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"transitions": []})
        result = await jira_get_transitions("AD-1")
        assert "No transitions" in result["content"][0]["text"]


class TestJiraTransitionIssue:
    async def test_success(self, mock_jira_request):
        mock_jira_request.return_value = (True, {})
        result = await jira_transition_issue("AD-1", "21")
        assert result["status"] == "success"
        assert "transitioned" in result["content"][0]["text"]

    async def test_error(self, mock_jira_request):
        mock_jira_request.return_value = (False, "Bad request")
        result = await jira_transition_issue("AD-1", "99")
        assert result["status"] == "error"


class TestJiraSearchIssues:
    async def test_with_results(self, mock_jira_request):
        mock_jira_request.return_value = (True, {
            "total": 1,
            "issues": [{
                "key": "AD-1",
                "fields": {
                    "summary": "Found it",
                    "status": {"name": "Open"},
                    "assignee": {"displayName": "Jane"},
                    "priority": {"name": "Low"},
                },
            }],
        })
        result = await jira_search_issues("project = AD")
        text = result["content"][0]["text"]
        assert "AD-1" in text
        assert "Found it" in text

    async def test_no_results(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"total": 0, "issues": []})
        result = await jira_search_issues("project = EMPTY")
        assert "No issues found" in result["content"][0]["text"]

    async def test_max_results_clamped(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"total": 0, "issues": []})
        await jira_search_issues("project = AD", max_results=100)
        call_params = mock_jira_request.call_args
        assert call_params[1]["json"]["maxResults"] == 50


class TestJiraAssignIssue:
    async def test_assign(self, mock_jira_request):
        mock_jira_request.return_value = (True, {})
        result = await jira_assign_issue("AD-1", "account-123")
        assert "assigned" in result["content"][0]["text"]

    async def test_unassign(self, mock_jira_request):
        mock_jira_request.return_value = (True, {})
        result = await jira_assign_issue("AD-1", None)
        assert "unassigned" in result["content"][0]["text"]


class TestJiraAddComment:
    async def test_success(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"id": "12345"})
        result = await jira_add_comment("AD-1", "Great work!")
        assert result["status"] == "success"
        assert "12345" in result["content"][0]["text"]


class TestJiraCreateIssue:
    async def test_minimal(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"key": "AD-50", "id": "10050"})
        result = await jira_create_issue("AD", "New task")
        assert "AD-50" in result["content"][0]["text"]

    async def test_with_all_fields(self, mock_jira_request):
        mock_jira_request.return_value = (True, {"key": "AD-51", "id": "10051"})
        result = await jira_create_issue("AD", "Bug fix", issue_type="Bug", description="Details", priority="High")
        assert result["status"] == "success"
        # Verify the request included description and priority
        call_json = mock_jira_request.call_args[1]["json"]
        assert "description" in call_json["fields"]
        assert call_json["fields"]["priority"] == {"name": "High"}

    async def test_error(self, mock_jira_request):
        mock_jira_request.return_value = (False, "Project not found")
        result = await jira_create_issue("INVALID", "Task")
        assert result["status"] == "error"
