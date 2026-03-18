# Human-in-the-Loop (HITL)

HITL allows you to require human approval before the agent executes specific tools. This is useful for dangerous operations (shell commands, file writes, API calls) where you want a human to review before execution.

## Configuration

```yaml
hitl:
  require_approval:
    - shell
    - file_write
  approvers:
    - U12345678
    - U87654321
```

| Field | Type | Default | Description |
|---|---|---|---|
| `require_approval` | list[string] | `[]` | Tool runtime names that require human approval before execution |
| `approvers` | list[string] | `[]` | Slack user IDs authorized to approve/deny. Empty = anyone can approve |

**Important:** Use the tool's **runtime name** (e.g. `shell`, `http_request`), not the import reference (`strands_tools.shell:shell`). The runtime name is the function name registered with Strands.

## How it works

1. Agent calls a tool in the `require_approval` list
2. Execution pauses — task status becomes `interrupted`
3. The `interrupts` field in `TaskStatus` shows the pending approval with tool name and input
4. A human responds via HTTP or Slack
5. If approved, execution continues. If denied, the tool is cancelled with a denial message

## HTTP workflow

Poll the task status until it becomes `interrupted`, then respond:

```bash
# 1. Submit a task
TASK_ID=$(curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "Run ls -la in the workspace"}' | jq -r .task_id)

# 2. Poll — status becomes "interrupted"
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8101/task/$TASK_ID | jq '{status, interrupts}'
# {"status": "interrupted", "interrupts": [{"interrupt_id": "approve:shell", ...}]}

# 3. Approve
curl -s -X POST http://localhost:8101/task/$TASK_ID/respond \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"interrupt_id": "approve:shell", "response": "approved"}'

# 4. Task resumes and completes
```

See [API Reference](api.md#post-tasktask_idrespond) for endpoint details.

## Slack workflow

When a [Slack channel](channels.md) is configured, HITL requests are sent as interactive messages with **Approve** and **Deny** buttons:

- The message shows the tool name and input for review
- After clicking, buttons are replaced with a resolution status (`✅ approved by @user` or `❌ denied by @user`)
- If `approvers` is configured, only listed users can click the buttons — others see an ephemeral "not authorized" message

### Finding Slack user IDs

Open a user's profile → click the three dots menu → "Copy member ID".
