# Andino Agent

Standalone autonomous agent runtime built on [Strands Agents](https://strandsagents.com/). Define an agent in a YAML file, deploy it as an independent unit with its own HTTP API.

## Quick Start

```bash
pip install -e ".[bedrock]"
python -m andino_sdk agent.yaml
```

The agent starts an HTTP server and accepts tasks via `POST /task`.

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

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 600

session:
  storage_dir: .sessions       # directory for FileSessionManager
  max_pool_size: 20            # max cached agent instances
```

## API

### POST /task

Submit a task for async execution.

```bash
curl -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?", "session_id": "optional-session"}'
```

Response (202):
```json
{"task_id": "uuid", "status": "queued"}
```

- `task_id` is auto-generated if not provided
- `session_id` is optional — if present, conversation state persists across tasks for that session

### GET /task/{task_id}

```json
{
  "task_id": "uuid",
  "status": "completed",
  "prompt": "What is Python?",
  "session_id": null,
  "result": "Python is a programming language...",
  "error": null,
  "created_at": "2026-03-17T16:51:32Z",
  "started_at": "2026-03-17T16:51:32Z",
  "completed_at": "2026-03-17T16:51:35Z"
}
```

Status values: `queued`, `running`, `completed`, `failed`, `timeout`.

### GET /tasks

List all tasks (last 100).

### GET /health

```json
{"status": "ok", "agent_name": "researcher", "running_tasks": 0, "uptime_seconds": 120.5}
```

### GET /info

Returns agent config metadata (name, version, model, tools, limits).

## Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY andino-agent/ /sdk/
RUN pip install --no-cache-dir /sdk[bedrock] && rm -rf /sdk
COPY examples/researcher/ .
CMD ["python", "-m", "andino_sdk", "agent.yaml"]
```

```bash
docker compose -f docker-compose.agents.yml up researcher
```

## Architecture

```
POST /task ──> asyncio.Queue (bounded)
                    |
             N worker coroutines
                    |
          AgentPool.get(session_id)
                    |
        await agent.invoke_async(prompt)
            + asyncio.wait_for(timeout)
                    |
              TaskStatus updated
```

- **Queue**: Bounded `asyncio.Queue` provides backpressure. Returns 429 when full.
- **Workers**: N async coroutines (N = `max_concurrent_tasks`) consume from the queue.
- **invoke_async**: Strands native async — no ThreadPoolExecutor, no threads.
- **AgentPool**: LRU cache of Agent instances keyed by `session_id`. Stateless tasks share one agent. Session tasks get dedicated agents with `FileSessionManager`.
- **Locks**: One `asyncio.Lock` per session prevents concurrent writes to the same conversation.

## Providers

Install the extra for your model provider:

```bash
pip install -e ".[bedrock]"      # AWS Bedrock (boto3)
pip install -e ".[anthropic]"    # Anthropic API
pip install -e ".[openai]"       # OpenAI API
pip install -e ".[all]"          # All providers
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | bedrock | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | bedrock | AWS credentials |
| `AWS_SESSION_TOKEN` | bedrock (SSO) | Temporary session token |
| `AWS_REGION` | bedrock | AWS region (e.g. `us-east-1`) |
| `ANTHROPIC_API_KEY` | anthropic | Anthropic API key |
| `OPENAI_API_KEY` | openai | OpenAI API key |

## Project Structure

```
andino-agent/
  pyproject.toml
  src/andino_sdk/
    __init__.py          # Exports: AgentConfig, AgentService
    __main__.py          # CLI entry point
    config.py            # Pydantic models for agent.yaml
    model_registry.py    # Build BedrockModel / AnthropicModel / OpenAIModel
    tool_loader.py       # Dynamic import of tool callables
    mcp_loader.py        # MCP server client setup (stdio, sse, streamable_http)
    agent_builder.py     # Build Strands Agent from config + optional session
    task_executor.py     # Queue, AgentPool, workers, task lifecycle
    server.py            # FastAPI app factory
    service.py           # Top-level entry point (env setup + uvicorn)
```
