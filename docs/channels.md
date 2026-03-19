# Channels

Channels connect agents to messaging platforms. Each channel runs alongside the HTTP server and shares the same `TaskExecutor`.

## Slack (Socket Mode)

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

String values matching `${VAR}` are expanded from environment variables.

### Session ID derivation

All conversations are scoped by thread. The bot always replies inside a thread.

- Format: `slack:{channel_id}:{thread_ts}`
- New messages use their own `ts` as thread root
- Replies inside an existing thread use its `thread_ts`
- Works identically for DMs, channels, and group messages

### Processing indicator

When the agent starts working on a message, an ⏳ reaction is added to the user's message. The reaction is automatically removed when the agent finishes (success or error). This provides immediate visual feedback that the bot received the message and is processing it.

> **Note:** Requires `reactions:write` scope in the Slack App configuration.

### File uploads

Agents can upload files from their workspace to the Slack thread using the `slack_upload_file` tool. This requires workspace to be enabled.

**Setup:**

```yaml
workspace:
  enabled: true

tools:
  - andino.channels.slack_upload:slack_upload_file
  - strands_tools.file_write:file_write    # so the agent can create files
```

**How it works:**

1. The Slack channel registers upload context (client, channel, thread) before each task
2. The agent creates a file in its workspace (e.g. via `file_write` or `shell`)
3. The agent calls `slack_upload_file(file_path="/workspace/report.csv", comment="Here's the report")`
4. The file appears as an attachment in the Slack thread

The tool supports:
- Absolute paths within the workspace directory
- Relative paths (resolved against the workspace root)
- Optional comment attached to the upload
- Size limit of 50 MB per file
- Graceful error handling (file not found, empty file, upload failure)

### HITL in Slack

When [HITL](hitl.md) is configured, tool approval requests are sent as interactive Slack messages with Approve/Deny buttons. After a user responds, the buttons are replaced with a resolution status showing who approved or denied. See [HITL Guide](hitl.md) for details.
