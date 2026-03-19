# Getting Started

## Installation

```bash
pip install andino-agent[bedrock]      # AWS Bedrock
pip install andino-agent[anthropic]    # Anthropic API
pip install andino-agent[openai]       # OpenAI API
pip install andino-agent[all]          # All providers + Slack
```

## CLI

```bash
andino run <name>                         # Run agent by name
andino run ./path/agent.yaml              # Run from a path (backward compatible)
andino init <name>                        # Scaffold a new agent
andino list                               # List agents in ~/.andino/agents/
andino validate <name>                    # Validate config without running
andino info <name>                        # Show agent config details
andino task <name> "prompt"               # Send task to a running agent
andino --version                          # Show version
```

Options for `andino run`:
- `--log-level debug|info|warning|error` (default: `info`)
- `--log-file /path/to/file.log` (log to file in addition to stdout)

Options for `andino task`:
- `--session <id>` — session ID for conversation persistence
- `--timeout <secs>` — max wait time (default: from agent config)
- `--json` — output raw JSON instead of text

## ANDINO_HOME

All persistent data lives under `~/.andino/` (override with `ANDINO_HOME` env var):

```
~/.andino/
├── .env                        # global secrets (AWS keys, API tokens)
├── agents/                     # agent configurations
│   ├── researcher/
│   │   ├── agent.yaml
│   │   ├── system_prompt.md
│   │   ├── skills/             # agent-specific skills
│   │   └── .env                # agent-specific secrets
│   └── coder/
│       └── ...
├── sessions/                   # conversation state
├── workspaces/                 # agent artifacts
└── logs/                       # log files
```

### Environment variable loading

Variables are loaded in this order (earlier values take precedence):

1. System environment variables (always win)
2. `~/.andino/agents/<name>/.env` (per-agent secrets)
3. `~/.andino/.env` (global secrets)

### Path resolution

Relative paths in `agent.yaml` for `session.storage_dir` and `workspace.base_dir` are resolved against `ANDINO_HOME`, not the current working directory. Absolute paths are used as-is.

## Your First Agent

```bash
# 1. Create
andino init researcher

# 2. Configure
vim ~/.andino/agents/researcher/agent.yaml
vim ~/.andino/agents/researcher/system_prompt.md

# 3. Add credentials
cat >> ~/.andino/agents/researcher/.env << 'EOF'
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
EOF

# 4. Run
andino run researcher
```

The agent starts an HTTP server on the configured port. Submit tasks via `POST /task`. See [API Reference](api.md).

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
| `SLACK_APP_TOKEN` | slack | Slack app-level token (`xapp-...`) |
| `SLACK_BOT_TOKEN` | slack | Slack bot token (`xoxb-...`) |
