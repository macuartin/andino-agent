---
name: estimate-effort
description: "Estimate implementation complexity and identify risks for a feature or task"
---
# Estimate Effort

## Arguments
- `$0` (required): Jira issue key or feature description
- `repo` (optional): GitHub repository if code analysis is needed

## Steps

1. **Read the task** — `jira_get_issue` for requirements and context

2. **Assess scope** — determine what needs to change:
   - New code vs. modifications to existing code
   - Number of modules/files affected
   - Database migrations or schema changes
   - API surface changes (breaking vs. additive)
   - Frontend changes (UI components, state management)

3. **Analyze code complexity** (if repo provided):
   - Clone and review the affected areas
   - Check existing test patterns and coverage
   - Identify integration points and coupling

4. **Identify unknowns and risks**:
   - Technical unknowns (need spike/prototype?)
   - External dependencies (third-party APIs, team coordination)
   - Data migration needs
   - Backward compatibility concerns

5. **Classify complexity**:
   - **S** — 1-2 files, clear change, < 1 day
   - **M** — 3-5 files, moderate logic, 1-3 days
   - **L** — Multiple modules, new patterns, 3-5 days
   - **XL** — Cross-cutting, architectural change, > 5 days → recommend splitting

6. **Post estimate** — `jira_add_comment` with:
   ```
   h3. Effort Estimate

   *Complexity:* {color:blue}*M (Medium)*{color}

   h4. Scope
   * Files affected: ~N
   * New code: yes/no
   * Schema changes: yes/no
   * API changes: additive, breaking, or none

   h4. Unknowns
   * Unknown 1 — suggested approach
   * Unknown 2 — needs spike

   h4. Risks
   * Risk 1 — mitigation
   * Risk 2 — mitigation

   h4. Recommendation
   Ready to implement / Needs spike / Should be split
   ```

7. **Report** — summarize in Slack thread
