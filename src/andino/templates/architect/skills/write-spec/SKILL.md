---
name: write-spec
description: "Create a technical specification document in Confluence from analysis findings"
---
# Write Spec

## Arguments
- `$0` (required): Feature name or Jira key
- `space` (optional): Confluence space key (default: from context.md)
- `parent_page_id` (optional): Parent page ID for nesting

## Steps

1. **Gather context** — read existing analysis from workspace files or Jira comments

2. **Search for existing spec** — `confluence_search` to avoid duplicating an existing page

3. **Write specification** with this structure:
   ```
   # [Feature Name] — Technical Specification

   ## Overview
   What this feature does and why it's needed.

   ## Background
   Current state, related systems, prior art.

   ## Proposed Solution
   ### Architecture
   High-level design, component diagram (text-based).

   ### Data Model
   New tables/fields, schema changes.

   ### API Changes
   New/modified endpoints, request/response formats.

   ### Implementation Plan
   1. Phase 1 — description
   2. Phase 2 — description

   ## Acceptance Criteria
   - [ ] Functional criteria
   - [ ] Performance criteria
   - [ ] Testing criteria

   ## Edge Cases & Error Handling
   - Case 1 — how it's handled
   - Case 2 — how it's handled

   ## Dependencies
   - External service X
   - Internal module Y

   ## Risks & Mitigations
   | Risk | Impact | Mitigation |
   |------|--------|------------|
   | Risk 1 | High | Plan B |

   ## Open Questions
   - Question for product
   - Question for team
   ```

4. **Create Confluence page** — `confluence_create_page` with the spec content

5. **Link from Jira** — `jira_add_comment` with link to the Confluence page

6. **Report** — share the Confluence URL in Slack thread
