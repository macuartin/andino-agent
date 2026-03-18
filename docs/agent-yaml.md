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
  api_key: ${ANDINO_API_KEY}

hitl:
  require_approval:
    - shell

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 1200

workspace:
  enabled: true
  base_dir: /data/workspaces

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
| `extras` | dict | `{}` | Additional keyword arguments passed to the model constructor (provider-specific) |

**Model extras example** — enable extended thinking on Bedrock:

```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-6
  extras:
    additional_request_fields:
      thinking:
        type: enabled
        budget_tokens: 10000
```

Any key in `extras` is forwarded as-is to the Strands model constructor (`BedrockModel`, `AnthropicModel`, or `OpenAIModel`). See each provider's documentation for supported parameters.

> **Note:** Models that emit `<thinking>` tags as plain text (e.g. Amazon Nova without native thinking) are automatically cleaned — the tags are stripped before the response reaches the user.

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
| `api_key` | string | `""` | API key for Bearer token auth. When set, all endpoints except `/health` require `Authorization: Bearer <key>` |

Use `${VAR}` syntax to load the key from an environment variable:

```yaml
server:
  api_key: ${ANDINO_API_KEY}
```

### `hitl`

Human-in-the-loop (HITL) tool approval. When configured, the agent pauses before executing listed tools and waits for human approval.

```yaml
hitl:
  require_approval:
    - shell
    - file_write
  approvers:
    - U12345678
    - U87654321
```

**Important:** Use the tool's **runtime name** (e.g. `shell`, `http_request`), not the import reference (`strands_tools.shell:shell`). The runtime name is the function name registered with Strands.

| Field | Type | Default | Description |
|---|---|---|---|
| `require_approval` | list[string] | `[]` | Tool runtime names that require human approval before execution |
| `approvers` | list[string] | `[]` | User IDs authorized to approve/deny. Empty = anyone can approve |

**How it works:**

1. Agent calls a tool in the `require_approval` list
2. Execution pauses — task status becomes `interrupted`
3. The `interrupts` field in `TaskStatus` shows the pending approval with tool name and input
4. A human responds via `POST /task/{task_id}/respond` (HTTP) or interactive buttons (Slack)
5. If approved, execution continues. If denied, the tool is cancelled with a denial message
6. On Slack, the approval buttons are replaced with a resolution status showing who approved/denied

> **Finding Slack user IDs:** Open a user's profile → click the three dots menu → "Copy member ID".

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

All conversations are scoped by thread. The bot always replies inside a thread.
- Format: `slack:{channel_id}:{thread_ts}`
- New messages use their own `ts` as thread root
- Replies inside an existing thread use its `thread_ts`
- Works identically for DMs, channels, and group messages

### `workspace`

Provides an isolated working directory per session where the agent creates artifacts, downloads files, and executes scripts.

```yaml
workspace:
  enabled: true
  base_dir: /data/.workspaces
```

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable workspace-per-session isolation |
| `base_dir` | string | `".workspaces"` | Base directory for workspaces. Each session gets `{base_dir}/{session_id}/` |

**How it works:**

When enabled and a `session_id` is provided, Andino:
1. Creates a directory at `{base_dir}/{session_id}/` if it doesn't exist
2. Appends a workspace note to the system prompt so the LLM knows the path
3. The LLM passes absolute paths within the workspace to tools (`shell` → `work_dir`, `file_write` → `path`, etc.)
4. `TaskStatus` responses include a `workspace_dir` field pointing to the session's workspace

**Separation from sessions:**
- `.sessions/` = conversation state (managed by Strands `FileSessionManager`)
- `.workspaces/` = agent artifacts (files, downloads, scripts created during tasks)

### `session`

| Field | Type | Default | Description |
|---|---|---|---|
| `storage_dir` | string | `".sessions"` | Directory where `FileSessionManager` persists conversation state |
| `max_pool_size` | int | `20` | Max agent instances cached in the AgentPool (LRU eviction) |

## Path Resolution

Relative paths for `session.storage_dir` and `workspace.base_dir` are resolved against `ANDINO_HOME` (default: `~/.andino/`), not the current working directory. Absolute paths are used as-is.

For example, with default ANDINO_HOME:
- `storage_dir: .sessions` → `~/.andino/.sessions/`
- `storage_dir: /data/sessions` → `/data/sessions/` (unchanged)

Override ANDINO_HOME with the `ANDINO_HOME` environment variable.
