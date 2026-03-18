from __future__ import annotations

from unittest.mock import patch

from andino.tools.lusha import (
    _lusha_auth,
    lusha_enrich_company,
    lusha_enrich_person,
    lusha_search_contacts,
)


class TestLushaAuth:
    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("LUSHA_API_KEY", "lusha-key")
        assert _lusha_auth() == "lusha-key"

    def test_default_empty(self, monkeypatch):
        monkeypatch.delenv("LUSHA_API_KEY", raising=False)
        assert _lusha_auth() == ""


class TestEnrichPerson:
    @patch("andino.tools.lusha._lusha_request")
    async def test_enriches_by_email(self, mock_req):
        mock_req.return_value = (True, {
            "firstName": "Ana", "lastName": "Garcia", "title": "VP Sales",
            "location": "Madrid, Spain",
            "emails": [{"email": "ana@co.com", "type": "work"}],
            "phones": [{"number": "+34600123", "type": "mobile"}],
            "company": {"name": "BigCo", "industry": "SaaS"},
        })
        result = await lusha_enrich_person(email="ana@co.com")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Ana Garcia" in text
        assert "ana@co.com" in text
        assert "+34600123" in text

    @patch("andino.tools.lusha._lusha_request")
    async def test_enriches_by_linkedin(self, mock_req):
        mock_req.return_value = (True, {
            "firstName": "Bob", "lastName": "Lee", "title": "CTO",
            "emails": [], "phones": [], "company": {},
        })
        result = await lusha_enrich_person(linkedin_url="https://linkedin.com/in/bob")
        assert result["status"] == "success"
        assert "Bob Lee" in result["content"][0]["text"]

    async def test_requires_identifier(self):
        result = await lusha_enrich_person()
        assert result["status"] == "error"
        assert "Provide at least" in result["content"][0]["text"]


class TestEnrichCompany:
    @patch("andino.tools.lusha._lusha_request")
    async def test_enriches_by_domain(self, mock_req):
        mock_req.return_value = (True, {
            "data": [{
                "name": "Shopify", "domain": "shopify.com",
                "industry": "E-commerce", "employeeCount": 10000,
                "revenue": "$5B", "location": "Ottawa, Canada", "foundedYear": 2006,
            }]
        })
        result = await lusha_enrich_company(domain="shopify.com")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Shopify" in text
        assert "E-commerce" in text

    async def test_requires_input(self):
        result = await lusha_enrich_company()
        assert result["status"] == "error"

    @patch("andino.tools.lusha._lusha_request")
    async def test_no_company(self, mock_req):
        mock_req.return_value = (True, {"data": []})
        result = await lusha_enrich_company(domain="nope.xyz")
        assert "No company" in result["content"][0]["text"]


class TestSearchContacts:
    @patch("andino.tools.lusha._lusha_request")
    async def test_returns_contacts(self, mock_req):
        mock_req.return_value = (True, {
            "data": [
                {"firstName": "Carlos", "lastName": "Ruiz", "title": "CEO",
                 "companyName": "TechCo", "location": "Barcelona"},
            ],
            "totalResults": 1,
        })
        result = await lusha_search_contacts(job_titles="CEO", locations="Barcelona")
        assert result["status"] == "success"
        text = result["content"][0]["text"]
        assert "Carlos Ruiz" in text
        assert "TechCo" in text

    @patch("andino.tools.lusha._lusha_request")
    async def test_no_contacts(self, mock_req):
        mock_req.return_value = (True, {"data": [], "totalResults": 0})
        result = await lusha_search_contacts(job_titles="nonexistent")
        assert "No contacts" in result["content"][0]["text"]

    async def test_requires_filter(self):
        result = await lusha_search_contacts()
        assert result["status"] == "error"
        assert "at least one filter" in result["content"][0]["text"]
