# agent.yaml Reference

Complete specification for the agent configuration file.

## Full Example

```yaml
name: coder
version: "1.0.0"
description: "Implements code and tests from architecture specs"

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-6
  max_tokens: 4096
  temperature: 0.7

system_prompt: ./system_prompt.md

tools:
  - strands_tools.http_request:http_request
  - strands_tools.file_read:file_read
  - strands_tools.file_write:file_write
  - strands_tools.editor:editor
  - strands_tools.shell:shell

mcp_servers:
  - name: github
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."

server:
  host: "0.0.0.0"
  port: 8103

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 1200

session:
  storage_dir: /data/sessions
  max_pool_size: 20
```

## Fields

### `name` (required)

Agent identifier. Used in logs, `/health`, and `/info` responses.

### `version`

Semver string. Default: `"1.0.0"`.

### `description`

Human-readable description. Shown in `/info`.

### `model`

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `"bedrock"` | `bedrock`, `anthropic`, or `openai` |
| `model_id` | string | `"us.anthropic.claude-sonnet-4-6"` | Model identifier for the provider |
| `max_tokens` | int | `4096` | Max output tokens per invocation |
| `temperature` | float \| null | `null` | Sampling temperature (provider default if null) |

### `system_prompt`

Either an inline string or a relative path to a `.md` file:

```yaml
# Inline
system_prompt: "You are a helpful researcher."

# File reference (resolved relative to agent.yaml directory)
system_prompt: ./system_prompt.md
```

### `tools`

List of tool references in `module.path:attribute` format. Each tool is dynamically imported at startup.

```yaml
tools:
  - strands_tools.http_request:http_request
  - strands_tools.shell:shell
  - mypackage.custom_tools:my_tool
```

Supports:
- `@tool`-decorated functions from `strands-agents-tools`
- Legacy tools with module-level `TOOL_SPEC`
- Custom tools from any installed package

### `mcp_servers`

List of MCP (Model Context Protocol) server configurations. Each entry creates an `MCPClient` that the agent can use as a tool.

**stdio transport:**
```yaml
mcp_servers:
  - name: github
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."
```

**SSE transport:**
```yaml
mcp_servers:
  - name: my-server
    transport: sse
    server_url: http://localhost:3000/sse
```

**Streamable HTTP transport:**
```yaml
mcp_servers:
  - name: my-server
    transport: streamable_http
    server_url: http://localhost:3000/mcp
```

### `server`

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | string | `"0.0.0.0"` | Bind address |
| `port` | int | `8100` | HTTP port |

### `limits`

| Field | Type | Default | Description |
|---|---|---|---|
| `max_concurrent_tasks` | int | `1` | Max tasks running simultaneously (= number of worker coroutines) |
| `task_timeout_seconds` | int | `600` | Per-task timeout before cancellation |

### `channels`

Optional communication channels that connect the agent to messaging platforms. Each channel runs alongside the HTTP server and shares the same `TaskExecutor`.

String values matching `${VAR}` are expanded from environment variables.

**Slack (Socket Mode):**
```yaml
channels:
  slack:
    enabled: true
    mode: socket
    app_token: ${SLACK_APP_TOKEN}
    bot_token: ${SLACK_BOT_TOKEN}
    require_mention: true
    allowed_channels: []        # empty = all channels
    max_message_length: 3900
```

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable/disable this channel |
| `mode` | string | `"socket"` | Connection mode (`socket`) |
| `app_token` | string | required | Slack app-level token (`xapp-...`) |
| `bot_token` | string | required | Slack bot token (`xoxb-...`) |
| `require_mention` | bool | `true` | In channels, only respond to `@bot` mentions |
| `allowed_channels` | list | `[]` | Restrict to specific Slack channel IDs (empty = all) |
| `max_message_length` | int | `3900` | Max chars per message chunk (Slack limit is 4000) |

**Session ID derivation:**
- DMs: `slack:dm:{user_id}`
- Channel messages: `slack:channel:{channel_id}`
- Threaded messages: `slack:channel:{channel_id}:thread:{thread_ts}`

### `session`

| Field | Type | Default | Description |
|---|---|---|---|
| `storage_dir` | string | `".sessions"` | Directory where `FileSessionManager` persists conversation state |
| `max_pool_size` | int | `20` | Max agent instances cached in the AgentPool (LRU eviction) |
