---
name: generate-brief
description: "Generate a standardized research brief for the BDR team from collected prospecting data. The brief is saved as a markdown file in the workspace."
---
# Generate Brief

Generate a standardized research brief for the BDR team from collected prospecting data. The brief is saved as a markdown file in the workspace.

## Arguments

- `$0` (required): Company name
- `$1` (required): Company domain

All other data should already be available from previous analysis steps (org enrichment, website analysis, contact enrichment).

## Steps

1. **Compile all collected data** from the current conversation:
   - Organization enrichment data (Apollo)
   - Website analysis results (payment capabilities, tech stack, business model)
   - Contact information (names, titles, emails, phones)
   - Payment processor detection results
   - ICP validation status

2. **Classify the industry tier** (A or B) based on the system prompt tier tables.

3. **Identify opportunities** — suggest 2-4 specific product angles based on:
   - Current payment setup (if using a competitor, highlight your advantages)
   - Business model (subscription → recurring billing optimization, ecommerce → checkout conversion)
   - Missing capabilities (no local payment methods, limited card processing)
   - Pain points typical for the industry

4. **Craft a messaging angle** personalized to:
   - The company's industry and business model
   - Their current payment infrastructure
   - A relevant case study or value proposition

5. **Write the brief** using the template from the system prompt. Save it to the workspace using `file_write`:
   - Filename: `{company_domain}_research_brief.md` (e.g. `totalpass.com.mx_research_brief.md`)
   - Use the workspace directory path

6. **Confirm completion** — tell the user the brief has been generated and summarize key findings.

## Important Notes

- The brief must be in Spanish (Latin American, CDMX tone).
- Be specific in opportunity identification — generic statements like "improve payments" are not useful.
- If data is missing for any section, explicitly note "No detectado" or "Información no disponible".
- The messaging angle should be actionable — something the BDR can use directly in their first conversation.
