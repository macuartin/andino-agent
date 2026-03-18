from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from strands import tool

logger = logging.getLogger(__name__)

_CREDS_ERROR = (
    "Lusha credentials not configured. "
    "Set LUSHA_API_KEY environment variable."
)


def _lusha_auth() -> str:
    """Return api_key from environment."""
    return os.environ.get("LUSHA_API_KEY", "").strip()


def _ok(text: str) -> dict:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}


async def _lusha_request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[bool, dict | list | str]:
    """Execute a Lusha API request.

    Returns (success, data_or_error_message).
    """
    api_key = _lusha_auth()
    if not api_key:
        return False, _CREDS_ERROR

    url = f"https://api.lusha.com{path}"
    headers = {
        "api_key": api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=headers, json=json, params=params,
            )
    except httpx.HTTPError as exc:
        logger.exception("lusha_request_failed method=%s path=%s", method, path)
        return False, f"HTTP error while contacting Lusha: {exc}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"Lusha API error {resp.status_code}: {resp.text[:500]}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
async def lusha_enrich_person(
    email: str = "",
    linkedin_url: str = "",
    first_name: str = "",
    last_name: str = "",
    company_name: str = "",
    company_domain: str = "",
) -> dict:
    """Enrich a person's contact data using Lusha.

    Provide at least an email or LinkedIn URL. Alternatively, provide
    first_name + last_name with company_name or company_domain.

    Args:
        email: Person's email address.
        linkedin_url: Person's LinkedIn profile URL.
        first_name: Person's first name.
        last_name: Person's last name.
        company_name: Company name (used with name for matching).
        company_domain: Company domain (used with name for matching).

    Returns:
        A dict with enriched contact data including emails, phones, and company info.
    """
    body: dict[str, Any] = {}
    if email:
        body["email"] = email
    if linkedin_url:
        body["linkedinUrl"] = linkedin_url
    if first_name:
        body["firstName"] = first_name
    if last_name:
        body["lastName"] = last_name

    metadata: dict[str, Any] = {}
    if company_name:
        metadata["companyName"] = company_name
    if company_domain:
        metadata["companyDomain"] = company_domain
    if metadata:
        body["metadata"] = metadata

    if not any([email, linkedin_url, first_name]):
        return _err("Provide at least email, linkedin_url, or first_name to enrich.")

    ok, data = await _lusha_request("POST", "/v2/person", json=body)
    if not ok:
        return _err(data)

    # Lusha returns data directly or nested
    emails = data.get("emails", [])
    phones = data.get("phones", [])
    company = data.get("company", {}) or {}

    email_str = ", ".join(
        f"{e.get('email', '')} ({e.get('type', '')})" for e in emails
    ) if emails else "N/A"
    phone_str = ", ".join(
        f"{p.get('number', '')} ({p.get('type', '')})" for p in phones
    ) if phones else "N/A"

    lines = [
        f"Name: {data.get('firstName', '')} {data.get('lastName', '')}".strip(),
        f"Title: {data.get('title', 'N/A')}",
        f"Emails: {email_str}",
        f"Phones: {phone_str}",
        f"Company: {company.get('name', 'N/A')}",
        f"Industry: {company.get('industry', 'N/A')}",
        f"Location: {data.get('location', 'N/A')}",
    ]
    return _ok("\n".join(lines))


@tool
async def lusha_enrich_company(
    domain: str = "",
    company_name: str = "",
) -> dict:
    """Enrich company data using Lusha by domain or company name.

    Args:
        domain: Company domain (e.g. "stripe.com").
        company_name: Company name (e.g. "Stripe").

    Returns:
        A dict with enriched company data including industry, size, and revenue.
    """
    if not domain and not company_name:
        return _err("Provide at least domain or company_name.")

    body: dict[str, Any] = {}
    if domain:
        body["domain"] = domain
    if company_name:
        body["companyName"] = company_name

    ok, data = await _lusha_request("POST", "/prospecting/company/enrich", json=body)
    if not ok:
        return _err(data)

    companies = data.get("data", [data]) if isinstance(data, dict) else data
    if not companies:
        return _ok(f"No company found for: {domain or company_name}")

    lines = []
    for c in companies[:5]:
        name = c.get("name", c.get("companyName", "Unknown"))
        lines.append(f"Company: {name}")
        lines.append(f"  Domain: {c.get('domain', c.get('website', 'N/A'))}")
        lines.append(f"  Industry: {c.get('industry', 'N/A')}")
        lines.append(f"  Employees: {c.get('employeeCount', c.get('size', 'N/A'))}")
        lines.append(f"  Revenue: {c.get('revenue', 'N/A')}")
        lines.append(f"  Location: {c.get('location', c.get('headquarters', 'N/A'))}")
        lines.append(f"  Founded: {c.get('foundedYear', 'N/A')}")

    return _ok("\n".join(lines))


@tool
async def lusha_search_contacts(
    job_titles: str = "",
    company_domains: str = "",
    locations: str = "",
    industries: str = "",
    limit: int = 25,
) -> dict:
    """Search for contacts in Lusha's database with filters.

    Args:
        job_titles: Comma-separated job titles (e.g. "CTO,VP Engineering").
        company_domains: Comma-separated domains (e.g. "stripe.com,shopify.com").
        locations: Comma-separated locations (e.g. "United States,United Kingdom").
        industries: Comma-separated industries (e.g. "Technology,Finance").
        limit: Max results to return (default 25, max 50).

    Returns:
        A dict with matching contacts.
    """
    limit = min(limit, 50)
    filters: dict[str, Any] = {}

    if job_titles:
        filters["jobTitles"] = [t.strip() for t in job_titles.split(",")]
    if company_domains:
        filters["companyDomains"] = [d.strip() for d in company_domains.split(",")]
    if locations:
        filters["locations"] = [loc.strip() for loc in locations.split(",")]
    if industries:
        filters["industries"] = [ind.strip() for ind in industries.split(",")]

    if not filters:
        return _err("Provide at least one filter: job_titles, company_domains, locations, or industries.")

    body: dict[str, Any] = {"filters": filters, "limit": limit}

    ok, data = await _lusha_request("POST", "/prospecting/contact/search", json=body)
    if not ok:
        return _err(data)

    contacts = data.get("data", [])
    total = data.get("totalResults", len(contacts))

    if not contacts:
        return _ok("No contacts found matching the criteria.")

    lines = [f"Found {total} contact(s) (showing {len(contacts)}):"]
    for c in contacts:
        name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or "Unknown"
        title = c.get("title", c.get("jobTitle", ""))
        company = c.get("companyName", c.get("company", {}).get("name", ""))
        location = c.get("location", "")
        parts = [f"  {name}"]
        if title:
            parts.append(f"({title})")
        if company:
            parts.append(f"@ {company}")
        if location:
            parts.append(f"| {location}")
        lines.append(" ".join(parts))

    return _ok("\n".join(lines))
