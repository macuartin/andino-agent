# Andino Agent

Standalone autonomous agent runtime built on [Strands Agents](https://strandsagents.com/). Define an agent in a YAML file, deploy it as an independent unit with its own HTTP API.

Licensed under [Apache 2.0](LICENSE).

## Quick Start

```bash
pip install andino-agent[bedrock]
andino init researcher
vim ~/.andino/agents/researcher/agent.yaml
andino run researcher
```

See [Getting Started](docs/getting-started.md) for detailed setup.

## agent.yaml

```yaml
name: researcher
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-6
system_prompt: ./system_prompt.md
tools:
  - strands_tools.http_request:http_request
server:
  port: 8101
```

See [agent.yaml Reference](docs/agent-yaml.md) for all options.

## Features

- **Async-native** — No threads, uses Strands `invoke_async()` with `asyncio`
- **Session persistence** — Conversation state via `FileSessionManager`
- **Workspace isolation** — Per-session directories for artifacts
- **Human-in-the-loop** — Tool approval via HTTP or Slack interactive buttons
- **API key auth** — Optional Bearer token for securing endpoints
- **Skills** — On-demand instruction packages for complex tasks
- **Channels** — Slack Socket Mode with thread-scoped sessions
- **MCP support** — Stdio, SSE, and Streamable HTTP transports

## Documentation

- [Getting Started](docs/getting-started.md) — installation, CLI, ANDINO_HOME, first agent
- [agent.yaml Reference](docs/agent-yaml.md) — configuration specification
- [Tools, MCP & Skills](docs/tools-and-skills.md) — tools, MCP servers, skills, comparison
- [Channels](docs/channels.md) — Slack integration
- [Human-in-the-Loop](docs/hitl.md) — tool approval workflow
- [API Reference](docs/api.md) — HTTP endpoints and examples
- [Architecture](docs/architecture.md) — concurrency model, task lifecycle
- [Deployment](docs/deployment.md) — host, Docker, systemd
