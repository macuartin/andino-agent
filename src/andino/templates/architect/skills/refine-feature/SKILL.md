---
name: refine-feature
description: "Full workflow — read Jira task, analyze codebase, produce technical refinement, post back to Jira"
---
# Refine Feature

## Arguments
- `$0` (required): Jira issue key (e.g. PROJ-123) or feature description
- `repo` (optional): GitHub repository (e.g. org/repo). If not provided, infer from Jira task or ask.

## Steps

1. **Read the Jira task** — `jira_get_issue` to get summary, description, acceptance criteria, labels, linked issues

2. **Search for related work** — `jira_search_issues` with keywords from the task to find:
   - Related features or dependencies
   - Previous attempts or discussions
   - Blocked or blocking tasks

3. **Search existing documentation** — `confluence_search` for architecture docs, ADRs, or design docs related to the feature area

4. **Clone the repository** — `shell` to run `gh repo clone {org/repo} {workspace_dir}/repo`
   - If repo is not specified, look for repo references in the Jira description or linked PRs

5. **Analyze affected code** — identify the modules impacted by this feature:
   - `shell` → `find . -type f -name "*.py" | head -50` to understand structure
   - `shell` → `grep -rn "relevant_keyword" src/` to find related code
   - `file_read` on key files to understand current implementation
   - `shell` → `git log --oneline -10 -- path/to/module` for recent changes

6. **Identify dependencies and risks**:
   - What does this module depend on?
   - What other modules depend on it?
   - Are there existing tests? What's the test coverage pattern?
   - Any ongoing PRs that might conflict?

7. **Write the technical refinement** — `jira_add_comment` with the structured refinement format:
   - Summary, affected modules, proposed approach
   - Acceptance criteria (technical), dependencies, risks
   - Estimated complexity (S/M/L/XL)
   - Open questions for the team

8. **Transition task** (if applicable) — `jira_transition_issue` to move to refined status

9. **Report** — summarize findings in Slack thread

## Important Notes
- Always read the full Jira description before starting — it may contain links, context, or constraints
- If the task is vague, list open questions in the refinement and flag it
- For large features (XL), recommend splitting into smaller tasks as part of the refinement
- Never modify code — this agent analyzes and documents, it does not implement
