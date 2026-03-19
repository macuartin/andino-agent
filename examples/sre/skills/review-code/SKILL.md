---
name: review-code
description: "Review a GitHub pull request or repository code using gh CLI — analyze for correctness, security, performance, and testing gaps"
---
# Review Code

## Arguments

- `$0` (required): PR reference — `org/repo#123`, or just a repo `org/repo` for general review
- `focus` (optional): Specific focus area — "security", "performance", "tests", "all" (default: all)

## Prerequisites

The `gh` CLI must be installed and authenticated on the host (`gh auth status`).
All shell commands require HITL approval since the `shell` tool has approval enabled.

## Steps

1. **Parse the reference**
   - If format is `org/repo#123` → PR review mode
   - If format is `org/repo` → general repo review (latest commits)
   - Extract repo owner/name and PR number if applicable

2. **Get PR metadata** (PR mode)
   - Run: `gh pr view <number> --repo <repo> --json title,body,author,baseRefName,headRefName,files,additions,deletions,changedFiles`
   - Note: title, description, base/head branches, number of files changed
   - Run: `gh pr checks <number> --repo <repo>` to see CI status

3. **Get the diff**
   - Run: `gh pr diff <number> --repo <repo>`
   - If diff is small (< 500 lines), analyze directly from the output
   - If diff is large (> 500 lines), proceed to step 4 to clone and read files

4. **Clone to workspace** (for large diffs or repo review)
   - Run: `gh repo clone <repo> <workspace_path>/<repo_name>`
   - For PR: `cd <workspace_path>/<repo_name> && gh pr checkout <number>`
   - Use `file_read` to read specific changed files with full context

5. **Analyze the code**
   - **Correctness:** Logic errors, missing edge cases, incorrect return values, race conditions
   - **Security:** Injection vulnerabilities (SQL, XSS, command), hardcoded secrets, insecure defaults, missing auth checks
   - **Performance:** O(N²) patterns, unnecessary allocations in loops, missing indexes, N+1 queries, unbounded growth
   - **Error handling:** Unhandled exceptions, missing try/catch, swallowed errors, unclear error messages
   - **Testing:** Are new code paths covered? Missing edge case tests? Are existing tests modified/removed?
   - **Dependencies:** New dependencies introduced? Are they maintained? License compatible?

6. **Write review report**
   - Use `file_write` to save the review to workspace as `review_{repo}_{pr_number}.md`
   - Format:

   ```
   # Code Review: {repo}#{pr_number}

   ## Summary
   {One paragraph: what the PR does and overall assessment}

   ## Findings

   ### Critical
   - [file:line] Description of issue and suggested fix

   ### Major
   - [file:line] Description and recommendation

   ### Minor
   - [file:line] Suggestion

   ## Tests
   {Assessment of test coverage — what's missing?}

   ## Verdict
   ✅ Approve / ⚠️ Request Changes / ❌ Block
   {Required actions before merge, if any}
   ```

7. **Post review on GitHub** (optional, ask first)
   - If the user wants feedback posted directly on the PR:
   - Run: `gh pr review <number> --repo <repo> --comment --body "<review_summary>"`
   - For specific file comments, use: `gh api repos/<repo>/pulls/<number>/comments -f body="..." -f path="<file>" -f line=<line> -f side=RIGHT`

8. **Report findings**
   - Summarize the review in the conversation
   - Highlight critical findings first
   - Reference the full report saved in workspace

## Important Notes

- Every `shell` command requires HITL approval — the on-call engineer must confirm each command
- Never run `git push`, `git commit`, or destructive operations during review
- If the repo is private, ensure `gh auth status` shows the correct account with access
- For monorepos, focus on the changed files only — don't try to understand the entire codebase
- If CI checks are failing, note them in the review but don't attempt to fix them
