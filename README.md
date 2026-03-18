# Andino Agent

Standalone autonomous agent runtime built on [Strands Agents](https://strandsagents.com/). Define an agent in a YAML file, deploy it as an independent unit with its own HTTP API.

Licensed under [Apache 2.0](LICENSE).

## Quick Start

```bash
pip install andino-agent[bedrock]

# Create a new agent
andino init researcher

# Edit config and add credentials
vim ~/.andino/agents/researcher/agent.yaml
echo "AWS_REGION=us-east-1" >> ~/.andino/agents/researcher/.env

# Run
andino run researcher
```

## CLI

```bash
andino run <name>              # Run agent by name
andino run ./path/agent.yaml   # Run from a path
andino init <name>             # Scaffold a new agent
andino list                    # List agents
andino --version               # Show version
```

Options for `andino run`:
- `--log-level debug|info|warning|error` (default: `info`)
- `--log-file /path/to/file.log` (log to file in addition to stdout)

## ANDINO_HOME

All data lives under `~/.andino/` (override with `ANDINO_HOME` env var):

```
~/.andino/
├── .env                        # global secrets
├── agents/                     # agent configurations
│   ├── researcher/
│   │   ├── agent.yaml
│   │   ├── system_prompt.md
│   │   └── .env                # agent-specific secrets
│   └── coder/
├── sessions/                   # conversation state
├── workspaces/                 # agent artifacts
└── logs/                       # log files
```

## agent.yaml

```yaml
name: researcher
version: "1.0.0"
description: "Investigates topics and produces technical briefs"

model:
  provider: bedrock            # bedrock | anthropic | openai
  model_id: us.anthropic.claude-sonnet-4-6
  max_tokens: 4096

system_prompt: ./system_prompt.md   # inline string or path to .md file

tools:
  - strands_tools.http_request:http_request
  - strands_tools.file_read:file_read

server:
  host: "0.0.0.0"
  port: 8101
  api_key: ${ANDINO_API_KEY}   # optional, enables Bearer token auth

hitl:
  require_approval:            # tools that need human approval before execution
    - strands_tools.shell:shell

workspace:
  enabled: true
  base_dir: .workspaces        # resolved against ANDINO_HOME

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 600

session:
  storage_dir: .sessions       # resolved against ANDINO_HOME
  max_pool_size: 20
```

## API

All endpoints (except `/health`) require a Bearer token when `server.api_key` is configured:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8101/tasks
```

### POST /task

Submit a task for async execution.

```bash
curl -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "What is Python?", "session_id": "optional-session"}'
```

Response (202): `{"task_id": "uuid", "status": "queued"}`

### GET /task/{task_id}

Returns task status: `queued`, `running`, `interrupted`, `completed`, `failed`, `timeout`.

### POST /task/{task_id}/respond

Respond to a human-in-the-loop (HITL) interrupt:

```bash
curl -X POST http://localhost:8101/task/$TASK_ID/respond \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"interrupt_id": "approve:shell", "response": "approved"}'
```

### GET /tasks | GET /health | GET /info

List tasks, health check (no auth), agent metadata.

## Features

- **Async-native**: No threads — uses Strands `invoke_async()` with `asyncio`
- **Session persistence**: Conversation state via `FileSessionManager`, keyed by `session_id`
- **Workspace isolation**: Per-session directories for artifacts, downloads, scripts
- **Human-in-the-loop**: Tool approval via HTTP `/respond` or Slack interactive buttons
- **API key auth**: Optional Bearer token for securing endpoints
- **Channels**: Slack Socket Mode with thread-scoped sessions (extensible to other platforms)
- **MCP support**: Stdio, SSE, and Streamable HTTP transports

## Providers

```bash
pip install andino-agent[bedrock]      # AWS Bedrock (boto3)
pip install andino-agent[anthropic]    # Anthropic API
pip install andino-agent[openai]       # OpenAI API
pip install andino-agent[all]          # All providers + Slack
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | bedrock | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | bedrock | AWS credentials |
| `AWS_SESSION_TOKEN` | bedrock (SSO) | Temporary session token |
| `AWS_REGION` | bedrock | AWS region |
| `ANTHROPIC_API_KEY` | anthropic | Anthropic API key |
| `OPENAI_API_KEY` | openai | OpenAI API key |
| `ANDINO_API_KEY` | optional | API key for HTTP endpoint auth |
| `ANDINO_HOME` | optional | Override home directory (default: `~/.andino`) |

## Project Structure

```
andino-agent/
  pyproject.toml
  src/andino/
    __main__.py          # CLI (run, init, list)
    config.py            # Pydantic models for agent.yaml
    home.py              # ANDINO_HOME directory resolver
    service.py           # Entry point (logging, signals, uvicorn)
    server.py            # FastAPI app factory + auth
    task_executor.py     # Queue, AgentPool, workers, HITL interrupts
    agent_builder.py     # Build Strands Agent from config + workspace
    model_registry.py    # Build BedrockModel / AnthropicModel / OpenAIModel
    tool_loader.py       # Dynamic import of tool callables
    mcp_loader.py        # MCP server client setup
    hitl.py              # Human-in-the-loop hook (ToolApprovalHook)
    channels/
      __init__.py        # BaseChannel, loader
      slack.py           # Slack Socket Mode integration
  deploy/
    andino@.service      # systemd user unit template
  docs/                  # architecture, API, deployment, agent.yaml reference
  examples/              # sample agents (researcher, architect, coder, reviewer)
  tests/                 # pytest + pytest-asyncio
```

## Documentation

- [Architecture](docs/architecture.md) — concurrency model, task lifecycle, module graph
- [API Reference](docs/api.md) — endpoints, auth, HITL, examples
- [Deployment](docs/deployment.md) — host, Docker, systemd, ANDINO_HOME
- [agent.yaml Reference](docs/agent-yaml.md) — full config specification
