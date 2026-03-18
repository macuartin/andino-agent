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

skills:
  - ./skills/

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 1200

conversation:
  manager: summarizing
  summary_ratio: 0.3
  preserve_recent_messages: 10

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

List of tool references. See [Tools, MCP & Skills](tools-and-skills.md) for format, supported types, and examples.

### `mcp_servers`

List of MCP server configurations. See [Tools, MCP & Skills](tools-and-skills.md#mcp-servers) for transports and examples.

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

Human-in-the-loop tool approval. See [HITL Guide](hitl.md) for configuration, workflow, and Slack integration.

### `limits`

| Field | Type | Default | Description |
|---|---|---|---|
| `max_concurrent_tasks` | int | `1` | Max tasks running simultaneously (= number of worker coroutines) |
| `task_timeout_seconds` | int | `600` | Per-task timeout before cancellation |

### `channels`

Messaging platform integrations. See [Channels](channels.md) for configuration and Slack setup.

### `conversation`

Controls how the agent manages conversation history to stay within model context limits.

```yaml
# SlidingWindow (default) — keeps last N messages
conversation:
  manager: sliding_window
  window_size: 40
  should_truncate_results: true
  per_turn: false

# Summarizing — condenses older messages instead of dropping them
conversation:
  manager: summarizing
  summary_ratio: 0.3
  preserve_recent_messages: 10

# Null — no management, full history preserved
conversation:
  manager: "null"
```

| Field | Type | Default | Applies to | Description |
|---|---|---|---|---|
| `manager` | string | `"sliding_window"` | all | `sliding_window`, `summarizing`, or `null` |
| `window_size` | int | `40` | sliding_window | Max messages to keep in history |
| `should_truncate_results` | bool | `true` | sliding_window | Truncate large tool results to save context |
| `per_turn` | bool \| int | `false` | sliding_window | `true` = manage before every model call; int N = every N calls |
| `summary_ratio` | float | `0.3` | summarizing | Ratio of messages to summarize (0.1–0.8) |
| `preserve_recent_messages` | int | `10` | summarizing | Minimum recent messages to always keep |

If omitted, defaults to `SlidingWindowConversationManager` with Strands defaults.

### `skills`

Modular instruction packages loaded on-demand. See [Tools, MCP & Skills](tools-and-skills.md#skills) for format, file structure, and comparison with tools.

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
