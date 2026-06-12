# Learnings

> Every pattern, correction, or improvement discovered while working on this codebase
> MUST be added here. Express rules in terms of the problem they solve. This is a living record.

## Design Principles

- **Configuration over environment:** Prefer declarative config files over env vars. Use env vars only for secrets and provider credentials.
- **No secrets in version control:** `.env` is gitignored. Use `.env.example` as template with empty values.
- **Rename, don't duplicate:** When restructuring, update ALL references (docs, Dockerfiles, README) in the same change — never leave stale paths.
- **Async all the way:** Never introduce synchronous blocking calls in the request path. Use `await` and native async APIs.
- **Bounded resources:** Queues, pools, and caches must have explicit size limits to prevent unbounded growth.
- **Shared executor, multiple entry points:** Channels and HTTP server share one `TaskExecutor` — never create parallel execution paths with separate queues.
- **Self-message filtering:** Any channel that sends responses must filter its own bot messages to prevent infinite loops.
- **Docker COPY preserves structure:** When copying directories in Dockerfiles, use separate COPY commands to preserve directory hierarchy (e.g., `COPY src/ /sdk/src/` not `COPY pyproject.toml src/ /sdk/`).

## Implementation Gotchas

- Tool functions must follow the `_ok()` / `_err()` pattern returning `{"status": "...", "content": [{"text": "..."}]}` for Strands tool compatibility.
- Slack buttons after HITL approval must be replaced via `chat_update` to prevent duplicate clicks — otherwise users can click approve/deny multiple times.
- `os.chdir()` is process-global — never use it for workspace isolation with concurrent workers. Inject workspace paths via system_prompt instead so the LLM passes explicit paths to tools.
- Models like Amazon Nova embed `<thinking>` tags as plain text instead of using native reasoning content blocks. `_strip_thinking()` in `_extract_text()` handles this automatically.
- `Depends(_bearer_scheme)` in FastAPI function defaults triggers ruff B008 — use `# noqa: B008` (this is a standard FastAPI pattern, not a real issue).
- The `additional_request_fields` key in BedrockModel kwargs enables extended thinking. Pass via `model.extras` in agent.yaml to keep it declarative.
- Strands `invoke_async()` is true async — never wrap in `ThreadPoolExecutor`. Use `await agent.invoke_async(prompt)` directly.
- `gitleaks` flags example API keys in docs (e.g., `YOUR_API_KEY`). Use `$API_KEY` variable syntax instead to avoid false positives.
- Strands tools (`shell`, `python_repl`, `journal`, `diagram`) all use `os.getcwd()` / `Path.cwd()` as their base directory — this is why workspace path injection via system_prompt works.
- The Slack upload context pattern (module-level dict keyed by workspace_dir) is a proven way to pass context from channels to tools without coupling.

## Singular backports (2026-06)

### Audit claims must be verified against code before planning
**Symptom:** A first-pass code audit reported tools as "sync blocking I/O without the _ok/_err envelope" — both wrong (they were already async httpx + envelope). Two backlog items evaporated on closer reading.
**Cause:** Surface-level greps misread `_jira_request`'s internal helpers as the tool surface.
**Fix / Pattern:** Before planning refactors from an audit, open ONE representative file per claim and confirm the finding with the actual code. Plans built on unverified audits waste scope.
**Refs:** `src/andino/tools/jira.py:34` (already async + envelope since inception)

### HITL replay semantics: decisions are single-shot, keyed by (session, tool)
**Symptom:** A persisted approval decision could match a LATER invocation of the same gated tool in the same session, silently skipping a fresh approval.
**Fix / Pattern:** `lookup_decision` + `consume_decision` — the stored decision is removed the moment the hook applies it. A second gated call re-interrupts. Also: replay re-executes the turn from the original prompt, so non-gated tools that ran before the interrupt run again (same trade-off as Singular's resume_after_hitl; documented, not hidden).
**Refs:** `src/andino/approvals.py`, `src/andino/hitl.py:_prior_decision`

### Don't retry the task budget timeout
**Symptom:** Naive retry-on-Exception would have retried `asyncio.wait_for`'s TimeoutError — doubling or tripling the wall-clock of an already-over-budget task.
**Fix / Pattern:** Catch `TimeoutError` FIRST and re-raise (budget exhausted is terminal); retry only classified transients (httpx network errors, throttling string-match). httpx's ReadTimeout is `httpx.TimeoutException`, NOT the builtin TimeoutError — order of except blocks matters.
**Refs:** `src/andino/task_executor.py:_is_transient` + the retry loop
