from __future__ import annotations

from unittest.mock import patch

from andino.tools.confluence import (
    _confluence_auth,
    _strip_html,
    confluence_create_page,
    confluence_get_page,
    confluence_list_spaces,
    confluence_search,
    confluence_update_page,
)


class TestConfluenceAuth:
    def test_reads_confluence_env(self, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_CLOUD_ID", "conf-123")
        monkeypatch.setenv("CONFLUENCE_USER_EMAIL", "user@co.com")
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")
        monkeypatch.delenv("JIRA_CLOUD_ID", raising=False)
        assert _confluence_auth() == ("conf-123", "user@co.com", "tok")

    def test_falls_back_to_jira_env(self, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_CLOUD_ID", raising=False)
        monkeypatch.delenv("CONFLUENCE_USER_EMAIL", raising=False)
        monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
        monkeypatch.setenv("JIRA_CLOUD_ID", "jira-id")
        monkeypatch.setenv("JIRA_USER_EMAIL", "jira@co.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "jira-tok")
        assert _confluence_auth() == ("jira-id", "jira@co.com", "jira-tok")

    def test_confluence_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_CLOUD_ID", "conf")
        monkeypatch.setenv("JIRA_CLOUD_ID", "jira")
        monkeypatch.setenv("CONFLUENCE_USER_EMAIL", "c@co.com")
        monkeypatch.setenv("JIRA_USER_EMAIL", "j@co.com")
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "c-tok")
        monkeypatch.setenv("JIRA_API_TOKEN", "j-tok")
        assert _confluence_auth() == ("conf", "c@co.com", "c-tok")


class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_preserves_newlines(self):
        result = _strip_html("<p>A</p><p>B</p>")
        assert "A" in result
        assert "B" in result

    def test_handles_br(self):
        assert "line1" in _strip_html("line1<br/>line2")


class TestGetPage:
    @patch("andino.tools.confluence._confluence_request")
    async def test_returns_page_content(self, mock_req):
        mock_req.return_value = (True, {
            "title": "Runbook: Deploy",
            "id": "12345",
            "spaceId": "sp-1",
            "version": {"number": 3},
            "body": {"storage": {"value": "<p>Step 1: Pull latest</p>"}},
            "_links": {"webui": "/pages/12345", "base": "https://wiki.co.com"},
        })
        result = await confluence_get_page(page_id="12345")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Runbook: Deploy" in text
        assert "Step 1: Pull latest" in text
        assert "Version: 3" in text

    @patch("andino.tools.confluence._confluence_request")
    async def test_missing_creds(self, mock_req):
        mock_req.return_value = (False, "credentials not configured")
        result = await confluence_get_page(page_id="999")
        assert result["status"] == "error"


class TestCreatePage:
    @patch("andino.tools.confluence._confluence_request")
    async def test_creates_page(self, mock_req):
        mock_req.return_value = (True, {
            "id": "67890",
            "title": "New Page",
            "_links": {"webui": "/pages/67890", "base": "https://wiki.co.com"},
        })
        result = await confluence_create_page(
            space_id="sp-1", title="New Page", body="<p>Content</p>",
        )
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "New Page" in text
        assert "67890" in text

    @patch("andino.tools.confluence._confluence_request")
    async def test_creates_with_parent(self, mock_req):
        mock_req.return_value = (True, {"id": "111", "title": "Child", "_links": {}})
        result = await confluence_create_page(
            space_id="sp-1", title="Child", body="<p>Sub</p>", parent_id="222",
        )
        assert result["status"] == "success"
        # Verify parent_id was passed in the payload
        call_json = mock_req.call_args.kwargs.get("json") or mock_req.call_args[1].get("json")
        assert call_json["parentId"] == "222"


class TestUpdatePage:
    @patch("andino.tools.confluence._confluence_request")
    async def test_updates_with_version_increment(self, mock_req):
        # First call: GET current version
        # Second call: PUT update
        mock_req.side_effect = [
            (True, {"version": {"number": 5}}),
            (True, {
                "id": "12345", "title": "Updated",
                "version": {"number": 6},
                "_links": {"webui": "/pages/12345", "base": "https://wiki.co.com"},
            }),
        ]
        result = await confluence_update_page(
            page_id="12345", title="Updated", body="<p>New content</p>",
        )
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Version: 6" in text

    @patch("andino.tools.confluence._confluence_request")
    async def test_update_fails_on_get(self, mock_req):
        mock_req.return_value = (False, "Not found")
        result = await confluence_update_page(
            page_id="999", title="X", body="<p>Y</p>",
        )
        assert result["status"] == "error"


class TestSearch:
    @patch("andino.tools.confluence._confluence_request")
    async def test_returns_results(self, mock_req):
        mock_req.return_value = (True, {
            "results": [
                {
                    "content": {"id": "111", "title": "Deploy Guide", "space": {"key": "ENG"}},
                    "excerpt": "How to deploy <b>services</b>",
                },
                {
                    "content": {"id": "222", "title": "Rollback", "space": {"key": "ENG"}},
                    "excerpt": "",
                },
            ],
            "totalSize": 2,
        })
        result = await confluence_search(cql='type=page AND space="ENG"')
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Deploy Guide" in text
        assert "Rollback" in text
        assert "ENG" in text

    @patch("andino.tools.confluence._confluence_request")
    async def test_no_results(self, mock_req):
        mock_req.return_value = (True, {"results": [], "totalSize": 0})
        result = await confluence_search(cql="title=nonexistent")
        assert "No results" in result["content"][0]["text"]


class TestListSpaces:
    @patch("andino.tools.confluence._confluence_request")
    async def test_returns_spaces(self, mock_req):
        mock_req.return_value = (True, {
            "results": [
                {"key": "ENG", "name": "Engineering", "type": "global", "id": "sp-1"},
                {"key": "OPS", "name": "Operations", "type": "global", "id": "sp-2"},
            ]
        })
        result = await confluence_list_spaces()
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Engineering" in text
        assert "ENG" in text
        assert "Operations" in text

    @patch("andino.tools.confluence._confluence_request")
    async def test_no_spaces(self, mock_req):
        mock_req.return_value = (True, {"results": []})
        result = await confluence_list_spaces()
        assert "No spaces" in result["content"][0]["text"]
