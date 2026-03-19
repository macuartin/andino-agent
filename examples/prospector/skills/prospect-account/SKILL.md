---
name: prospect-account
description: "Full prospecting workflow for a single company. Validates ICP, analyzes website, enriches contacts, and generates a research brief."
---
# Prospect Account

Full prospecting workflow for a single company. Validates ICP, analyzes website, enriches contacts, and generates a research brief.

## Arguments

- `$0` (required): Company domain (e.g. "totalpass.com.mx") or company name

## Steps

1. **Enrich the organization** using `apollo_enrich_organization` with the domain. Note the industry, employee count, location, funding, and technologies.

2. **Validate ICP criteria:**
   - Geography: Does the company operate in Mexico or sell to Mexican customers?
   - Size: Does it have 10+ employees?
   - Payment capability: Any evidence of payment processing?
   - If the company does NOT meet ICP → report "Not Qualified" with specific reasons and stop.

3. **Determine industry tier** based on the system prompt tier tables. Tier A companies get higher priority.

4. **Analyze the website** using the `analyze-website` skill with the company domain. This will detect payment capabilities, current payment processor, tech stack, and business model.

5. **Enrich contacts** using the `enrich-contacts` skill with the domain and company name. This finds 2+ decision-makers with email and phone numbers.

6. **Generate the research brief** using the `generate-brief` skill. Pass all collected data: org info, website analysis results, contacts, and tier classification.

7. **Report the result** to the user with a summary: company name, ICP status, tier, number of contacts found, and key findings.

## Important Notes

- If the company is detected as already using your company's payment processor, flag it and stop — they are an existing merchant.
- Always try to estimate monthly payment volume based on available signals.
- Prioritize quality over speed — a thorough brief is more valuable than a fast incomplete one.
