# API Reference

Base URL: `http://{host}:{port}` (configured in `agent.yaml`).

## Authentication

When `server.api_key` is configured in `agent.yaml`, all endpoints except `/health` require a Bearer token:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8101/tasks
```

Without the header (or with a wrong key), the server returns `401 Unauthorized`.

The `/health` endpoint is always unauthenticated — safe for load balancer health checks.

## POST /task

Submit a task for asynchronous execution.

**Request:**

```json
{
  "task_id": "optional-custom-id",
  "prompt": "Investigate the feasibility of...",
  "session_id": "jira-AD-123"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | yes | — | The task instruction for the agent |
| `task_id` | string | no | UUID v4 | Custom task identifier |
| `session_id` | string | no | `null` | Session for conversation persistence |

**Response (202 Accepted):**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

**Error (429 Too Many Requests):**

```json
{
  "detail": "Task queue is full. Try again later."
}
```

## GET /task/{task_id}

Get the status and result of a task.

**Response (200):**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "prompt": "Investigate the feasibility of...",
  "session_id": "jira-AD-123",
  "result": "Based on my analysis...",
  "error": null,
  "interrupts": null,
  "workspace_dir": "/home/user/.andino/.workspaces/jira-AD-123",
  "created_at": "2026-03-17T16:51:32.229697+00:00",
  "started_at": "2026-03-17T16:51:32.231773+00:00",
  "completed_at": "2026-03-17T16:51:35.899529+00:00"
}
```

**Status values:**

| Status | Description |
|---|---|
| `queued` | Task is in the queue, waiting for a worker |
| `running` | Worker picked up the task, agent is executing |
| `interrupted` | Agent paused, waiting for human approval (HITL) |
| `completed` | Agent finished successfully, `result` contains output |
| `failed` | Agent threw an exception, `error` contains details |
| `timeout` | Task exceeded `task_timeout_seconds` |

**Additional fields:**

| Field | Present when | Description |
|---|---|---|
| `interrupts` | `status=interrupted` | List of pending tool approvals (see HITL section) |
| `workspace_dir` | workspace enabled + session_id set | Absolute path to the session's workspace directory |

**Error (404):**

```json
{
  "detail": "Task {task_id} not found"
}
```

## POST /task/{task_id}/respond

Respond to a human-in-the-loop (HITL) interrupt. Only valid when a task's status is `interrupted`.

**Request:**

```json
{
  "interrupt_id": "approve:shell",
  "response": "approved"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `interrupt_id` | string | yes | The interrupt ID from the `interrupts` array |
| `response` | string | yes | `"approved"` to allow, any other value to deny |

**Response (200):**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "resumed"
}
```

**Errors:**

| Code | Detail |
|---|---|
| 404 | Task not found |
| 409 | Task is not interrupted (wrong status) |
| 409 | No pending interrupt for this task |

## GET /tasks

List all tasks (up to last 100, oldest completed tasks are evicted).

**Response (200):**

```json
[
  {"task_id": "...", "status": "completed", "prompt": "...", ...},
  {"task_id": "...", "status": "running", "prompt": "...", ...}
]
```

## GET /health

Health check endpoint. **No authentication required.**

**Response (200):**

```json
{
  "status": "ok",
  "agent_name": "researcher",
  "running_tasks": 1,
  "uptime_seconds": 3600.5
}
```

## GET /info

Agent metadata from config.

**Response (200):**

```json
{
  "name": "researcher",
  "version": "1.0.0",
  "description": "Investigates topics, analyzes feasibility, produces technical briefs",
  "model": {
    "provider": "bedrock",
    "model_id": "us.anthropic.claude-sonnet-4-6"
  },
  "tools": [
    "strands_tools.http_request:http_request",
    "strands_tools.file_read:file_read"
  ],
  "max_concurrent_tasks": 1,
  "task_timeout_seconds": 600
}
```

## Usage Examples

### Stateless task (fire and forget)

```bash
# Submit
TASK_ID=$(curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "Summarize the Python GIL"}' | jq -r .task_id)

# Poll until done
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8101/task/$TASK_ID | jq .status
```

### Session-based conversation

```bash
# First message — establishes session
curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "My project uses FastAPI and PostgreSQL", "session_id": "project-ctx"}'

# Second message — agent remembers context
curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "What database am I using?", "session_id": "project-ctx"}'
# Result: "You mentioned you are using PostgreSQL."
```

### HITL workflow (tool approval)

```bash
# 1. Submit a task that uses a tool requiring approval
TASK_ID=$(curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "Run ls -la in the workspace"}' | jq -r .task_id)

# 2. Poll — status will become "interrupted"
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8101/task/$TASK_ID | jq '{status, interrupts}'
# {"status": "interrupted", "interrupts": [{"interrupt_id": "approve:shell", ...}]}

# 3. Approve the tool execution
curl -s -X POST http://localhost:8101/task/$TASK_ID/respond \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"interrupt_id": "approve:shell", "response": "approved"}'

# 4. Task resumes and completes
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8101/task/$TASK_ID | jq .status
# "completed"
```
