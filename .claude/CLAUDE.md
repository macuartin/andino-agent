# CLAUDE.md

## Project Overview
Andino Agent — standalone autonomous agent runtime built on Strands Agents.
Each agent is defined in a YAML file and deployed as an independent HTTP server with async task processing. Agents can optionally connect to messaging platforms (Slack, etc.) via channels.

## Feedback loop — KEEP `.claude/learnings.md` FRESH

**This is a HARD requirement, not a suggestion.**

Every time you:

1. **Fix a bug** (yours or pre-existing) — record what broke, why, and what prevents recurrence
2. **Pick a non-obvious pattern** (or reject an alternative) — record the choice, the trigger for using it, and what was rejected
3. **Get bitten by a gotcha that took more than ~5 minutes to debug** — record symptom, root cause, watch-out

…you **MUST** append a short entry to `.claude/learnings.md` **in the same session, before declaring the work done**.

Use this shape (phrase as the problem the entry prevents, not as a story):

```
### <one-line problem description>
**Symptom:** What was visible / what failed.
**Cause:** Why it happened.
**Fix / Pattern:** What to do (or do differently) next time.
**Refs:** File paths, commits, links that prove it.
```

A change that fits the criteria above but **does not update `.claude/learnings.md` is INCOMPLETE.**

## Quick Reference
- **Language:** Python 3.11+
- **Package manager:** pip + hatchling
- **Run an agent:** `andino run <name>` or `andino run <agent.yaml>`
- **Install:** `pip install -e ".[bedrock]"` (or `anthropic`, `openai`, `slack`, `all`)
- **Create agent:** `andino init <name>` (scaffolds in `~/.andino/agents/<name>/`)
- **List agents:** `andino list`
- **Lint:** `ruff check src/`
- **Tests:** `pytest tests/ -v`
- **ANDINO_HOME:** `~/.andino/` (override with `ANDINO_HOME` env var)

## Project Structure
- `src/andino/` — core SDK code
- `src/andino/channels/` — channel integrations (Slack, etc.)
- `src/andino/tools/` — built-in tools (Jira, etc.)
- `src/andino/home.py` — ANDINO_HOME directory resolver
- `src/andino/hitl.py` — human-in-the-loop tool approval hook
- `deploy/` — systemd unit template
- `examples/` — sample agent configurations (researcher, architect, coder, reviewer)
- `tests/` — unit tests (pytest + pytest-asyncio)
- `docs/` — documentation (architecture, API, deployment, agent.yaml reference)

## Key Conventions
- Agent configuration lives in `agent.yaml`, NOT in environment variables
- Environment variables are only for secrets and provider credentials (AWS, Anthropic, OpenAI, Slack tokens, Jira tokens)
- Runtime flags (`BYPASS_TOOL_CONSENT`, `STRANDS_NON_INTERACTIVE`, etc.) are set programmatically in `service.py` — never require them from the user
- All concurrency is async-native (`asyncio`). No threads, no `ThreadPoolExecutor`
- Tools are loaded dynamically via `"module.path:attribute"` format
- Channels are loaded dynamically from `channels` section in `agent.yaml` via internal registry
- YAML config supports `${VAR}` syntax for environment variable expansion (secrets, tokens)
- `.env` files are loaded via python-dotenv: global (`~/.andino/.env`) + per-agent (`agents/<name>/.env`), system env vars always take precedence
- Relative paths in config (`session.storage_dir`, `workspace.base_dir`) resolve against ANDINO_HOME, not cwd
- HTTP endpoints (except `/health`) support optional Bearer token auth via `server.api_key`
- HITL tool approval uses Strands `BeforeToolCallEvent` interrupts — configured via the `access:` key pointing at an `access.yaml` (groups + rules with `require_approval`)
- Graceful shutdown via SIGTERM/SIGINT signal handlers cancels all tasks and stops channels cleanly

## Related Files

- `.claude/instructions.md` — step-by-step recipes for common development tasks
- `.claude/learnings.md` — accumulated gotchas and patterns discovered while working on this codebase
