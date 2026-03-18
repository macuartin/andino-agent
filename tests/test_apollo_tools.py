from __future__ import annotations

from unittest.mock import patch

from andino.tools.apollo import (
    _apollo_auth,
    apollo_enrich_organization,
    apollo_enrich_person,
    apollo_search_contacts,
    apollo_search_people,
)


class TestApolloAuth:
    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("APOLLO_API_KEY", "key-123")
        assert _apollo_auth() == "key-123"

    def test_default_empty(self, monkeypatch):
        monkeypatch.delenv("APOLLO_API_KEY", raising=False)
        assert _apollo_auth() == ""


class TestSearchPeople:
    @patch("andino.tools.apollo._apollo_request")
    async def test_returns_people(self, mock_req):
        mock_req.return_value = (True, {
            "people": [
                {"name": "Jane Doe", "title": "CTO", "organization": {"name": "Acme"}, "linkedin_url": "https://linkedin.com/in/jane"},
            ],
            "pagination": {"total_entries": 42},
        })
        result = await apollo_search_people(person_titles="CTO")
        assert result["status"] == "success"
        assert "Jane Doe" in result["content"][0]["text"]
        assert "42" in result["content"][0]["text"]

    @patch("andino.tools.apollo._apollo_request")
    async def test_no_results(self, mock_req):
        mock_req.return_value = (True, {"people": [], "pagination": {"total_entries": 0}})
        result = await apollo_search_people(query="nonexistent")
        assert "No people found" in result["content"][0]["text"]

    @patch("andino.tools.apollo._apollo_request")
    async def test_missing_credentials(self, mock_req):
        mock_req.return_value = (False, "APOLLO_API_KEY")
        result = await apollo_search_people(query="test")
        assert result["status"] == "error"


class TestEnrichPerson:
    @patch("andino.tools.apollo._apollo_request")
    async def test_enriches_by_email(self, mock_req):
        mock_req.return_value = (True, {
            "person": {
                "name": "John Smith", "title": "Engineer", "email": "john@acme.com",
                "linkedin_url": "https://linkedin.com/in/john", "city": "SF", "state": "CA", "country": "US",
                "organization": {"name": "Acme", "primary_domain": "acme.com", "industry": "Tech", "estimated_num_employees": 500},
                "phone_numbers": [{"sanitized_number": "+1555123"}],
            }
        })
        result = await apollo_enrich_person(email="john@acme.com")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "John Smith" in text
        assert "john@acme.com" in text
        assert "+1555123" in text

    @patch("andino.tools.apollo._apollo_request")
    async def test_no_match(self, mock_req):
        mock_req.return_value = (True, {"person": None})
        result = await apollo_enrich_person(email="nobody@nowhere.com")
        assert "No match" in result["content"][0]["text"]

    async def test_requires_identifier(self):
        result = await apollo_enrich_person()
        assert result["status"] == "error"
        assert "Provide at least" in result["content"][0]["text"]


class TestSearchContacts:
    @patch("andino.tools.apollo._apollo_request")
    async def test_returns_contacts(self, mock_req):
        mock_req.return_value = (True, {
            "contacts": [
                {"name": "Alice", "email": "alice@co.com", "title": "PM", "organization_name": "Co"},
            ],
            "pagination": {"total_entries": 1},
        })
        result = await apollo_search_contacts(query="Alice")
        assert result["status"] == "success"
        assert "Alice" in result["content"][0]["text"]


class TestEnrichOrganization:
    @patch("andino.tools.apollo._apollo_request")
    async def test_enriches_org(self, mock_req):
        mock_req.return_value = (True, {
            "organization": {
                "name": "Stripe", "primary_domain": "stripe.com", "industry": "Fintech",
                "estimated_num_employees": 8000, "annual_revenue_printed": "$1B",
                "total_funding": 2200000000, "founded_year": 2010,
                "linkedin_url": "https://linkedin.com/company/stripe",
                "city": "San Francisco", "state": "CA", "country": "US",
                "current_technologies": [{"name": "Ruby"}, {"name": "React"}],
            }
        })
        result = await apollo_enrich_organization(domain="stripe.com")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Stripe" in text
        assert "Fintech" in text
        assert "Ruby" in text

    @patch("andino.tools.apollo._apollo_request")
    async def test_no_org(self, mock_req):
        mock_req.return_value = (True, {"organization": None})
        result = await apollo_enrich_organization(domain="nope.xyz")
        assert "No organization" in result["content"][0]["text"]
