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

### HITL in Slack

When [HITL](hitl.md) is configured, tool approval requests are sent as interactive Slack messages with Approve/Deny buttons. After a user responds, the buttons are replaced with a resolution status showing who approved or denied. See [HITL Guide](hitl.md) for details.
