from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from strands import tool

logger = logging.getLogger(__name__)

_CREDS_ERROR = (
    "Apollo credentials not configured. "
    "Set APOLLO_API_KEY environment variable."
)


def _apollo_auth() -> str:
    """Return api_key from environment."""
    return os.environ.get("APOLLO_API_KEY", "").strip()


def _ok(text: str) -> dict:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}


async def _apollo_request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[bool, dict | list | str]:
    """Execute an Apollo.io API request.

    Returns (success, data_or_error_message).
    """
    api_key = _apollo_auth()
    if not api_key:
        return False, _CREDS_ERROR

    url = f"https://api.apollo.io/api/v1/{path}"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers, json=json, params=params,
            )
    except httpx.HTTPError as exc:
        logger.exception("apollo_request_failed method=%s path=%s", method, path)
        return False, f"HTTP error while contacting Apollo: {exc}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"Apollo API error {resp.status_code}: {resp.text[:500]}"


def _format_person(p: dict) -> str:
    """Format a person record into a readable line."""
    name = p.get("name", "Unknown")
    title = p.get("title", "")
    org = p.get("organization", {}) or {}
    org_name = org.get("name", p.get("organization_name", ""))
    email = p.get("email", "")
    linkedin = p.get("linkedin_url", "")
    city = p.get("city", "")
    state = p.get("state", "")
    country = p.get("country", "")
    location = ", ".join(filter(None, [city, state, country]))

    parts = [name]
    if title:
        parts.append(f"({title})")
    if org_name:
        parts.append(f"@ {org_name}")
    if email:
        parts.append(f"| {email}")
    if linkedin:
        parts.append(f"| {linkedin}")
    if location:
        parts.append(f"| {location}")
    return "  " + " ".join(parts)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
async def apollo_search_people(
    query: str = "",
    person_titles: str = "",
    organization_domains: str = "",
    person_locations: str = "",
    per_page: int = 25,
    page: int = 1,
) -> dict:
    """Search for people in Apollo's database.

    This endpoint does NOT consume credits and does NOT return emails/phones.
    Use apollo_enrich_person to get contact details for specific people.

    Common searches: find CTOs at fintech companies, engineers in San Francisco,
    VPs of Sales at companies using Kubernetes.

    Args:
        query: General search term (name, keyword).
        person_titles: Comma-separated job titles to filter (e.g. "CTO,VP Engineering").
        organization_domains: Comma-separated domains (e.g. "stripe.com,shopify.com").
        person_locations: Comma-separated locations (e.g. "San Francisco,New York").
        per_page: Results per page (default 25, max 100).
        page: Page number (default 1).

    Returns:
        A dict with matching people.
    """
    per_page = min(per_page, 100)
    body: dict[str, Any] = {"page": page, "per_page": per_page}
    if query:
        body["q_keywords"] = query
    if person_titles:
        body["person_titles"] = [t.strip() for t in person_titles.split(",")]
    if organization_domains:
        body["q_organization_domains"] = organization_domains
    if person_locations:
        body["person_locations"] = [loc.strip() for loc in person_locations.split(",")]

    ok, data = await _apollo_request("POST", "mixed_people/api_search", json=body)
    if not ok:
        return _err(data)

    people = data.get("people", [])
    total = data.get("pagination", {}).get("total_entries", 0)

    if not people:
        return _ok("No people found matching the search criteria.")

    lines = [f"Found {total} people (showing {len(people)}, page {page}):"]
    for p in people:
        lines.append(_format_person(p))
    return _ok("\n".join(lines))


@tool
async def apollo_enrich_person(
    email: str = "",
    linkedin_url: str = "",
    first_name: str = "",
    last_name: str = "",
    organization_name: str = "",
    domain: str = "",
) -> dict:
    """Enrich a person's data to get their email, phone, title, and company details.

    Provide at least one identifier: email, LinkedIn URL, or name + company/domain.
    This endpoint consumes credits.

    Args:
        email: Person's email address.
        linkedin_url: Person's LinkedIn profile URL.
        first_name: Person's first name (combine with last_name + organization_name/domain).
        last_name: Person's last name.
        organization_name: Company name (used with name for matching).
        domain: Company domain (used with name for matching).

    Returns:
        A dict with enriched person data including email, phone, title, and company.
    """
    body: dict[str, Any] = {"reveal_personal_emails": True, "reveal_phone_number": True}
    if email:
        body["email"] = email
    if linkedin_url:
        body["linkedin_url"] = linkedin_url
    if first_name:
        body["first_name"] = first_name
    if last_name:
        body["last_name"] = last_name
    if organization_name:
        body["organization_name"] = organization_name
    if domain:
        body["domain"] = domain

    if not any([email, linkedin_url, first_name]):
        return _err("Provide at least email, linkedin_url, or first_name to enrich.")

    ok, data = await _apollo_request("POST", "people/match", json=body)
    if not ok:
        return _err(data)

    person = data.get("person")
    if not person:
        return _ok("No match found for the provided criteria.")

    org = person.get("organization", {}) or {}
    phones = person.get("phone_numbers", [])
    phone_str = ", ".join(p.get("sanitized_number", "") for p in phones) if phones else "N/A"

    lines = [
        f"Name: {person.get('name', 'Unknown')}",
        f"Title: {person.get('title', 'N/A')}",
        f"Email: {person.get('email', 'N/A')}",
        f"Phone: {phone_str}",
        f"LinkedIn: {person.get('linkedin_url', 'N/A')}",
        f"Company: {org.get('name', 'N/A')}",
        f"Domain: {org.get('primary_domain', 'N/A')}",
        f"Industry: {org.get('industry', 'N/A')}",
        f"Company Size: {org.get('estimated_num_employees', 'N/A')}",
        f"Location: {person.get('city', '')}, {person.get('state', '')}, {person.get('country', '')}",
    ]
    return _ok("\n".join(lines))


@tool
async def apollo_search_contacts(
    query: str = "",
    per_page: int = 25,
    page: int = 1,
) -> dict:
    """Search contacts already saved in your Apollo account.

    Unlike apollo_search_people (which searches Apollo's full database),
    this searches only contacts your team has explicitly added.

    Args:
        query: Search term to filter contacts (name, email, company).
        per_page: Results per page (default 25, max 100).
        page: Page number (default 1).

    Returns:
        A dict with matching contacts from your account.
    """
    per_page = min(per_page, 100)
    body: dict[str, Any] = {"page": page, "per_page": per_page}
    if query:
        body["q_keywords"] = query

    ok, data = await _apollo_request("POST", "contacts/search", json=body)
    if not ok:
        return _err(data)

    contacts = data.get("contacts", [])
    total = data.get("pagination", {}).get("total_entries", 0)

    if not contacts:
        return _ok("No contacts found.")

    lines = [f"Found {total} contact(s) (showing {len(contacts)}, page {page}):"]
    for c in contacts:
        name = c.get("name", "Unknown")
        email = c.get("email", "N/A")
        title = c.get("title", "")
        org_name = c.get("organization_name", "")
        stage = c.get("contact_stage_id", "")
        parts = [f"  {name}"]
        if title:
            parts.append(f"({title})")
        if org_name:
            parts.append(f"@ {org_name}")
        parts.append(f"| {email}")
        if stage:
            parts.append(f"| stage:{stage}")
        lines.append(" ".join(parts))
    return _ok("\n".join(lines))


@tool
async def apollo_enrich_organization(domain: str) -> dict:
    """Enrich company data by domain to get industry, size, funding, and technologies.

    Args:
        domain: Company domain (e.g. "stripe.com", "shopify.com").

    Returns:
        A dict with enriched company data.
    """
    ok, data = await _apollo_request(
        "GET", "organizations/enrich", params={"domain": domain},
    )
    if not ok:
        return _err(data)

    org = data.get("organization")
    if not org:
        return _ok(f"No organization found for domain: {domain}")

    tech = org.get("current_technologies", [])
    tech_str = ", ".join(t.get("name", "") for t in tech[:10]) if tech else "N/A"
    funding = org.get("total_funding")
    funding_str = f"${funding:,.0f}" if funding else "N/A"

    lines = [
        f"Name: {org.get('name', 'Unknown')}",
        f"Domain: {org.get('primary_domain', domain)}",
        f"Industry: {org.get('industry', 'N/A')}",
        f"Employees: {org.get('estimated_num_employees', 'N/A')}",
        f"Annual Revenue: {org.get('annual_revenue_printed', 'N/A')}",
        f"Total Funding: {funding_str}",
        f"Founded: {org.get('founded_year', 'N/A')}",
        f"LinkedIn: {org.get('linkedin_url', 'N/A')}",
        f"HQ: {org.get('city', '')}, {org.get('state', '')}, {org.get('country', '')}",
        f"Technologies: {tech_str}",
    ]
    return _ok("\n".join(lines))
