---
name: enrich-contacts
description: "Find and enrich at least 2 decision-maker contacts for a company. Uses Apollo for search and email enrichment, Lusha for phone numbers."
---
# Enrich Contacts

Find and enrich at least 2 decision-maker contacts for a company. Uses Apollo for search and email enrichment, Lusha for phone numbers.

## Arguments

- `$0` (required): Company domain (e.g. "totalpass.com.mx")
- `$1` (optional): Company name for better search accuracy

## Steps

1. **Search for people** using `apollo_search_people` with:
   - `organization_domains`: the company domain
   - `person_titles`: prioritize these titles in order:
     - First search: "CEO,CTO,CIO,COO,CFO" (C-Suite)
     - Second search (if needed): "Head of Finance,Head of Payments,Head of Product,Head of Growth,Head of Ecommerce"
     - Third search (if needed): "VP Finance,Director of Operations,Product Manager,Finance Manager"
   - Request up to 25 results per search

2. **Filter and rank contacts** by relevance:
   - Prefer C-Suite and VP-level contacts
   - Prefer departments: Finance, Payments, Product, Engineering, Operations
   - Avoid: local branch managers, junior roles, irrelevant departments (HR, legal, admin)
   - Avoid: contacts clearly outside Mexico unless they are global decision-makers
   - Select the **top 2-3 most relevant contacts**

3. **Enrich each selected contact with email** using `apollo_enrich_person`:
   - Pass the person's LinkedIn URL if available (most accurate match)
   - Otherwise pass first_name + last_name + domain
   - Record: name, title, email, LinkedIn URL, location

4. **Enrich each contact with phone number** using `lusha_enrich_person`:
   - Pass the email obtained from Apollo
   - Or pass the LinkedIn URL
   - Record: phone number and type (mobile, work)

5. **Report contacts** in structured format:
   ```
   Contact 1:
     Name: {name}
     Title: {title}
     Department: {department}
     Email: {email}
     Phone: {phone}
     LinkedIn: {linkedin_url}
   ```

## Important Notes

- Always identify at least 2 contacts. For large enterprises (500+ employees), try for 3-4.
- If Apollo returns no results for a domain, try searching by company name instead.
- If Lusha has no phone for a contact, note "Phone: Not available" rather than skipping the contact.
- Quality matters more than quantity — 2 well-targeted contacts are better than 5 irrelevant ones.
