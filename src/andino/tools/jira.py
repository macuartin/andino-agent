from __future__ import annotations

import logging
import os

import httpx
from strands import tool

logger = logging.getLogger(__name__)


def _jira_auth() -> tuple[str, str, str]:
    """Return (cloud_id, email, api_token) from environment."""
    cloud_id = os.environ.get("JIRA_CLOUD_ID", "").strip()
    email = os.environ.get("JIRA_USER_EMAIL", "")
    api_token = os.environ.get("JIRA_API_TOKEN", "")
    return cloud_id, email, api_token


@tool
async def jira_add_comment(issue_key: str, comment: str) -> dict:
    """Add a comment to a Jira issue.

    Use this tool to post findings, analysis results, or status updates
    as a comment on a Jira ticket.

    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123", "AD-1").
        comment: The comment text to add to the issue.

    Returns:
        A dict with the operation status and details.
    """
    cloud_id, email, api_token = _jira_auth()

    if not all([cloud_id, email, api_token]):
        return {
            "status": "error",
            "content": [
                {
                    "text": (
                        "Jira credentials not configured. "
                        "Set JIRA_CLOUD_ID, JIRA_USER_EMAIL, and JIRA_API_TOKEN environment variables."
                    )
                }
            ],
        }

    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/{issue_key}/comment"

    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment}],
                }
            ],
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json=body,
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.exception("jira_add_comment_failed issue=%s", issue_key)
        return {
            "status": "error",
            "content": [{"text": f"HTTP error while contacting Jira: {exc}"}],
        }

    if resp.status_code in (200, 201):
        data = resp.json()
        comment_id = data.get("id", "unknown")
        return {
            "status": "success",
            "content": [{"text": f"Comment added to {issue_key}. Comment ID: {comment_id}"}],
        }

    return {
        "status": "error",
        "content": [{"text": f"Jira API error {resp.status_code}: {resp.text[:500]}"}],
    }
