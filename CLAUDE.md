# CLAUDE.md

## Project Overview
Andino Agent — standalone autonomous agent runtime built on Strands Agents.
Each agent is defined in a YAML file and deployed as an independent HTTP server with async task processing.

## Quick Reference
- **Language:** Python 3.11+
- **Package manager:** pip + hatchling
- **Run an agent:** `python -m andino_sdk <agent.yaml>`
- **Install:** `pip install -e ".[bedrock]"` (or `anthropic`, `openai`, `all`)
- **Lint:** `ruff check src/`

## Project Structure
- `src/andino_sdk/` — core SDK code
- `examples/` — sample agent configurations (researcher, architect, coder, reviewer)
- `docs/` — documentation (architecture, API, deployment, agent.yaml reference)

## Key Conventions
- Agent configuration lives in `agent.yaml`, NOT in environment variables
- Environment variables are only for provider credentials (AWS, Anthropic, OpenAI)
- Runtime flags (`BYPASS_TOOL_CONSENT`, `STRANDS_NON_INTERACTIVE`, etc.) are set programmatically in `service.py` — never require them from the user
- All concurrency is async-native (`asyncio`). No threads, no `ThreadPoolExecutor`
- Tools are loaded dynamically via `"module.path:attribute"` format

## Practices

> **Feedback loop:** Every pattern, correction, or improvement discovered while working on this codebase
> MUST be added to this section as a design-agnostic practice. Express rules in terms of
> the problem they solve, not the specific technology. This document is a living record.

- **Configuration over environment:** Prefer declarative config files over env vars. Use env vars only for secrets and provider credentials
- **No secrets in version control:** `.env` is gitignored. Use `.env.example` as template with empty values
- **Rename, don't duplicate:** When restructuring, update ALL references (docs, Dockerfiles, README) in the same change — never leave stale paths
- **Async all the way:** Never introduce synchronous blocking calls in the request path. Use `await` and native async APIs
- **Bounded resources:** Queues, pools, and caches must have explicit size limits to prevent unbounded growth
