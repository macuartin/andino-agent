# CLAUDE.md

## Project Overview
Andino Agent — standalone autonomous agent runtime built on Strands Agents.
Each agent is defined in a YAML file and deployed as an independent HTTP server with async task processing. Agents can optionally connect to messaging platforms (Slack, etc.) via channels.

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
- HITL tool approval uses Strands `BeforeToolCallEvent` interrupts — configured via `hitl.require_approval` list
- Graceful shutdown via SIGTERM/SIGINT signal handlers cancels all tasks and stops channels cleanly

## Practices

> **Feedback loop:** Every pattern, correction, or improvement discovered while working on this codebase
> MUST be added to this section as a design-agnostic practice. Express rules in terms of
> the problem they solve, not the specific technology. This document is a living record.

- **Configuration over environment:** Prefer declarative config files over env vars. Use env vars only for secrets and provider credentials
- **No secrets in version control:** `.env` is gitignored. Use `.env.example` as template with empty values
- **Rename, don't duplicate:** When restructuring, update ALL references (docs, Dockerfiles, README) in the same change — never leave stale paths
- **Async all the way:** Never introduce synchronous blocking calls in the request path. Use `await` and native async APIs
- **Bounded resources:** Queues, pools, and caches must have explicit size limits to prevent unbounded growth
- **Shared executor, multiple entry points:** Channels and HTTP server share one `TaskExecutor` — never create parallel execution paths with separate queues
- **Self-message filtering:** Any channel that sends responses must filter its own bot messages to prevent infinite loops
- **Docker COPY preserves structure:** When copying directories in Dockerfiles, use separate COPY commands to preserve directory hierarchy (e.g., `COPY src/ /sdk/src/` not `COPY pyproject.toml src/ /sdk/`)
