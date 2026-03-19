from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx
from strands import tool

logger = logging.getLogger(__name__)

_CREDS_ERROR = (
    "Confluence credentials not configured. "
    "Set CONFLUENCE_CLOUD_ID (or JIRA_CLOUD_ID), "
    "CONFLUENCE_USER_EMAIL (or JIRA_USER_EMAIL), and "
    "CONFLUENCE_API_TOKEN (or JIRA_API_TOKEN)."
)


def _confluence_auth() -> tuple[str, str, str]:
    """Return (cloud_id, email, api_token) from environment.

    Falls back to JIRA_* variables when CONFLUENCE_* are not set — most
    Atlassian Cloud instances share credentials across products.
    """
    cloud_id = os.environ.get("CONFLUENCE_CLOUD_ID", "") or os.environ.get("JIRA_CLOUD_ID", "")
    email = os.environ.get("CONFLUENCE_USER_EMAIL", "") or os.environ.get("JIRA_USER_EMAIL", "")
    token = os.environ.get("CONFLUENCE_API_TOKEN", "") or os.environ.get("JIRA_API_TOKEN", "")
    return cloud_id.strip(), email, token


def _ok(text: str) -> dict:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}


def _strip_html(html: str) -> str:
    """Naive HTML → plain text for readable output."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


async def _confluence_request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    api_version: str = "v2",
) -> tuple[bool, dict | list | str]:
    """Execute a Confluence Cloud API request.

    *api_version* controls the base URL:
    - ``"v2"`` → ``/wiki/api/v2/{path}``
    - ``"v1"`` → ``/wiki/rest/api/{path}``
    """
    cloud_id, email, token = _confluence_auth()
    if not all([cloud_id, email, token]):
        return False, _CREDS_ERROR

    if api_version == "v2":
        url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/api/v2/{path}"
    else:
        url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api/{path}"

    headers = {"Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers, json=json, params=params,
                auth=(email, token),
            )
    except httpx.HTTPError as exc:
        logger.exception("confluence_request_failed method=%s path=%s", method, path)
        return False, f"HTTP error while contacting Confluence: {exc}"

    if resp.status_code in (200, 201):
        return True, resp.json()
    if resp.status_code == 204:
        return True, {}
    return False, f"Confluence API error {resp.status_code}: {resp.text[:500]}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
async def confluence_get_page(page_id: str) -> dict:
    """Read a Confluence page by its ID and return the title and content.

    Args:
        page_id: The numeric ID of the Confluence page.

    Returns:
        A dict with the page title, content (plain text), version, and link.
    """
    ok, data = await _confluence_request(
        "GET", f"pages/{page_id}", params={"body-format": "storage"},
    )
    if not ok:
        return _err(data)

    title = data.get("title", "Untitled")
    version = data.get("version", {}).get("number", "?")
    space_id = data.get("spaceId", "")
    body_storage = data.get("body", {}).get("storage", {}).get("value", "")
    body_text = _strip_html(body_storage) if body_storage else "(empty page)"
    link = data.get("_links", {}).get("webui", "")
    base = data.get("_links", {}).get("base", "")
    full_link = f"{base}{link}" if base and link else link

    lines = [
        f"Title: {title}",
        f"Page ID: {page_id}",
        f"Space ID: {space_id}",
        f"Version: {version}",
    ]
    if full_link:
        lines.append(f"Link: {full_link}")
    lines.append(f"\n--- Content ---\n{body_text}")
    return _ok("\n".join(lines))


@tool
async def confluence_create_page(
    space_id: str,
    title: str,
    body: str,
    parent_id: str = "",
) -> dict:
    """Create a new Confluence page in a space.

    The body should be HTML (Confluence storage format). Common tags:
    <h1>, <h2>, <p>, <ul><li>, <ol><li>, <table><tr><td>, <code>,
    <ac:structured-macro> for macros.

    Args:
        space_id: The ID of the space to create the page in.
        title: Page title.
        body: Page content in HTML storage format.
        parent_id: Optional parent page ID for nesting.

    Returns:
        A dict with the created page ID, title, and link.
    """
    payload: dict[str, Any] = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {
            "representation": "storage",
            "value": body,
        },
    }
    if parent_id:
        payload["parentId"] = parent_id

    ok, data = await _confluence_request("POST", "pages", json=payload)
    if not ok:
        return _err(data)

    page_id = data.get("id", "?")
    link = data.get("_links", {}).get("webui", "")
    base = data.get("_links", {}).get("base", "")
    full_link = f"{base}{link}" if base and link else link

    lines = [
        f"Page created: {title}",
        f"Page ID: {page_id}",
    ]
    if full_link:
        lines.append(f"Link: {full_link}")
    return _ok("\n".join(lines))


@tool
async def confluence_update_page(
    page_id: str,
    title: str,
    body: str,
    version_message: str = "",
) -> dict:
    """Update an existing Confluence page's title and content.

    Automatically fetches the current version number for optimistic locking.
    The body should be HTML storage format (same as confluence_create_page).

    Args:
        page_id: The numeric ID of the page to update.
        title: New page title (required by Confluence even if unchanged).
        body: New page content in HTML storage format.
        version_message: Optional message describing the change.

    Returns:
        A dict confirming the update with page ID, new version, and link.
    """
    # Fetch current version
    ok, current = await _confluence_request("GET", f"pages/{page_id}")
    if not ok:
        return _err(f"Failed to fetch current page: {current}")

    current_version = current.get("version", {}).get("number", 0)

    version_payload: dict[str, Any] = {"number": current_version + 1}
    if version_message:
        version_payload["message"] = version_message

    payload: dict[str, Any] = {
        "id": page_id,
        "status": "current",
        "title": title,
        "body": {
            "representation": "storage",
            "value": body,
        },
        "version": version_payload,
    }

    ok, data = await _confluence_request("PUT", f"pages/{page_id}", json=payload)
    if not ok:
        return _err(data)

    new_version = data.get("version", {}).get("number", "?")
    link = data.get("_links", {}).get("webui", "")
    base = data.get("_links", {}).get("base", "")
    full_link = f"{base}{link}" if base and link else link

    lines = [
        f"Page updated: {title}",
        f"Page ID: {page_id}",
        f"Version: {new_version}",
    ]
    if full_link:
        lines.append(f"Link: {full_link}")
    return _ok("\n".join(lines))


@tool
async def confluence_search(
    cql: str,
    max_results: int = 10,
) -> dict:
    """Search Confluence using CQL (Confluence Query Language).

    Common CQL patterns:
    - type=page AND space="ENG" — pages in a space
    - type=page AND title~"runbook" — pages with title containing "runbook"
    - type=page AND text~"deployment" — full-text search
    - type=page AND label="incident" — pages with a label
    - lastModified > startOfMonth() — recently modified

    Args:
        cql: CQL query string.
        max_results: Maximum results to return (default 10, max 50).

    Returns:
        A dict with matching pages (title, ID, space, excerpt).
    """
    max_results = min(max_results, 50)

    ok, data = await _confluence_request(
        "GET", "search",
        params={"cql": cql, "limit": max_results},
        api_version="v1",
    )
    if not ok:
        return _err(data)

    results = data.get("results", [])
    total = data.get("totalSize", len(results))

    if not results:
        return _ok(f"No results found for CQL: {cql}")

    lines = [f"Found {total} result(s) (showing {len(results)}):"]
    for r in results:
        content = r.get("content", {}) or r
        title = content.get("title", r.get("title", "Untitled"))
        page_id = content.get("id", "?")
        space_key = content.get("space", {}).get("key", "") if isinstance(content.get("space"), dict) else ""
        excerpt = r.get("excerpt", "")
        # Clean excerpt HTML
        if excerpt:
            excerpt = _strip_html(excerpt)[:150]

        parts = [f"  [{page_id}] {title}"]
        if space_key:
            parts.append(f"(space: {space_key})")
        lines.append(" ".join(parts))
        if excerpt:
            lines.append(f"    {excerpt}")

    return _ok("\n".join(lines))


@tool
async def confluence_list_spaces(max_results: int = 25) -> dict:
    """List available Confluence spaces.

    Args:
        max_results: Maximum spaces to return (default 25, max 100).

    Returns:
        A dict with space names, keys, and types.
    """
    max_results = min(max_results, 100)

    ok, data = await _confluence_request(
        "GET", "spaces", params={"limit": max_results},
    )
    if not ok:
        return _err(data)

    spaces = data.get("results", [])
    if not spaces:
        return _ok("No spaces found.")

    lines = [f"Spaces ({len(spaces)}):"]
    for s in spaces:
        name = s.get("name", "Unnamed")
        key = s.get("key", "?")
        space_type = s.get("type", "")
        space_id = s.get("id", "")
        lines.append(f"  [{key}] {name} (type: {space_type}, id: {space_id})")

    return _ok("\n".join(lines))
