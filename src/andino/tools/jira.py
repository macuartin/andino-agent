from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from strands import tool

logger = logging.getLogger(__name__)

_CREDS_ERROR = (
    "Jira credentials not configured. "
    "Set JIRA_CLOUD_ID, JIRA_USER_EMAIL, and JIRA_API_TOKEN environment variables."
)


def _jira_auth() -> tuple[str, str, str]:
    """Return (cloud_id, email, api_token) from environment."""
    cloud_id = os.environ.get("JIRA_CLOUD_ID", "").strip()
    email = os.environ.get("JIRA_USER_EMAIL", "")
    api_token = os.environ.get("JIRA_API_TOKEN", "")
    return cloud_id, email, api_token


def _ok(text: str) -> dict:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}


async def _jira_request(
    method: str,
    path: str,
    json: dict | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[bool, dict | str]:
    """Execute a Jira Cloud API request.

    Returns (success, data_or_error_message).
    For 204 responses data is an empty dict.
    """
    cloud_id, email, api_token = _jira_auth()
    if not all([cloud_id, email, api_token]):
        return False, _CREDS_ERROR

    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/{path}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                json=json,
                params=params,
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.exception("jira_request_failed method=%s path=%s", method, path)
        return False, f"HTTP error while contacting Jira: {exc}"

    if resp.status_code in (200, 201):
        return True, resp.json()
    if resp.status_code == 204:
        return True, {}
    return False, f"Jira API error {resp.status_code}: {resp.text[:500]}"


def _adf_text(text: str) -> dict:
    """Wrap plain text in Atlassian Document Format."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
async def jira_get_issue(issue_key: str) -> dict:
    """Get details of a Jira issue.

    Returns the issue summary, status, assignee, priority, type, and dates.

    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123").

    Returns:
        A dict with the operation status and issue details.
    """
    ok, data = await _jira_request(
        "GET",
        f"issue/{issue_key}",
        params={"fields": "summary,status,assignee,priority,issuetype,created,updated,description"},
    )
    if not ok:
        return _err(data)

    f = data.get("fields", {})
    assignee = f.get("assignee")
    assignee_name = assignee.get("displayName", "Unknown") if assignee else "Unassigned"
    priority = f.get("priority")
    priority_name = priority.get("name", "None") if priority else "None"
    issue_type = f.get("issuetype", {}).get("name", "Unknown")
    status = f.get("status", {}).get("name", "Unknown")

    lines = [
        f"Key: {data.get('key', issue_key)}",
        f"Summary: {f.get('summary', '')}",
        f"Type: {issue_type}",
        f"Status: {status}",
        f"Priority: {priority_name}",
        f"Assignee: {assignee_name}",
        f"Created: {f.get('created', '')}",
        f"Updated: {f.get('updated', '')}",
    ]
    return _ok("\n".join(lines))


@tool
async def jira_get_transitions(issue_key: str) -> dict:
    """Get the available status transitions for a Jira issue.

    Use this before transitioning an issue to know which statuses are
    available and their transition IDs.

    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123").

    Returns:
        A dict listing available transitions with their IDs.
    """
    ok, data = await _jira_request("GET", f"issue/{issue_key}/transitions")
    if not ok:
        return _err(data)

    transitions = data.get("transitions", [])
    if not transitions:
        return _ok(f"No transitions available for {issue_key}.")

    lines = [f"Available transitions for {issue_key}:"]
    for t in transitions:
        target = t.get("to", {}).get("name", "Unknown")
        lines.append(f"  ID {t['id']}: {t['name']} → {target}")
    return _ok("\n".join(lines))


@tool
async def jira_transition_issue(issue_key: str, transition_id: str) -> dict:
    """Change the status of a Jira issue by executing a transition.

    Call jira_get_transitions first to get the valid transition IDs.

    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123").
        transition_id: The transition ID to execute (from jira_get_transitions).

    Returns:
        A dict confirming the transition.
    """
    ok, data = await _jira_request(
        "POST",
        f"issue/{issue_key}/transitions",
        json={"transition": {"id": transition_id}},
    )
    if not ok:
        return _err(data)

    return _ok(f"Issue {issue_key} transitioned successfully (transition ID: {transition_id}).")


@tool
async def jira_search_issues(jql: str, max_results: int = 20) -> dict:
    """Search for Jira issues using JQL (Jira Query Language).

    Common JQL examples:
    - project = AD
    - project = AD AND status = "To Do"
    - assignee = currentUser() ORDER BY updated DESC
    - project = AD AND created >= -7d

    Args:
        jql: The JQL query string.
        max_results: Maximum number of results to return (default 20, max 50).

    Returns:
        A dict with matching issues.
    """
    max_results = min(max_results, 50)
    ok, data = await _jira_request(
        "POST",
        "search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["key", "summary", "status", "assignee", "priority"],
        },
    )
    if not ok:
        return _err(data)

    issues = data.get("issues", [])
    total = data.get("total", 0)

    if not issues:
        return _ok(f"No issues found for: {jql}")

    lines = [f"Found {total} issue(s) (showing {len(issues)}):"]
    for issue in issues:
        f = issue.get("fields", {})
        key = issue.get("key", "?")
        summary = f.get("summary", "")
        status = f.get("status", {}).get("name", "?")
        assignee = f.get("assignee")
        assignee_name = assignee.get("displayName", "?") if assignee else "Unassigned"
        priority = f.get("priority", {}).get("name", "?") if f.get("priority") else "?"
        lines.append(f"  {key}: {summary} [{status}] ({assignee_name}) P:{priority}")
    return _ok("\n".join(lines))


@tool
async def jira_assign_issue(issue_key: str, account_id: str | None = None) -> dict:
    """Assign or unassign a Jira issue.

    To find a user's account ID, use jira_search_issues with JQL like
    'assignee = "user@email.com"' and note the assignee info, or check
    the issue details with jira_get_issue.

    Args:
        issue_key: The Jira issue key (e.g., "PROJ-123").
        account_id: The Atlassian account ID of the user. Pass None or omit to unassign.

    Returns:
        A dict confirming the assignment.
    """
    ok, data = await _jira_request(
        "PUT",
        f"issue/{issue_key}/assignee",
        json={"accountId": account_id},
    )
    if not ok:
        return _err(data)

    if account_id:
        return _ok(f"Issue {issue_key} assigned to account {account_id}.")
    return _ok(f"Issue {issue_key} unassigned.")


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
    ok, data = await _jira_request(
        "POST",
        f"issue/{issue_key}/comment",
        json={"body": _adf_text(comment)},
    )
    if not ok:
        return _err(data)

    comment_id = data.get("id", "unknown")
    return _ok(f"Comment added to {issue_key}. Comment ID: {comment_id}")


@tool
async def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    priority: str = "",
) -> dict:
    """Create a new Jira issue.

    Args:
        project_key: The project key (e.g., "AD", "PROJ").
        summary: The issue title/summary.
        issue_type: The issue type name (default "Task"). Common: Task, Bug, Story, Epic.
        description: Optional description text for the issue.
        priority: Optional priority name (e.g., "High", "Medium", "Low").

    Returns:
        A dict with the created issue key.
    """
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = _adf_text(description)
    if priority:
        fields["priority"] = {"name": priority}

    ok, data = await _jira_request("POST", "issue", json={"fields": fields})
    if not ok:
        return _err(data)

    return _ok(f"Issue created: {data.get('key', 'unknown')} (ID: {data.get('id', '?')})")
