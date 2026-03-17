# API Reference

Base URL: `http://{host}:{port}` (configured in `agent.yaml`).

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
| `completed` | Agent finished successfully, `result` contains output |
| `failed` | Agent threw an exception, `error` contains details |
| `timeout` | Task exceeded `task_timeout_seconds` |

**Error (404):**

```json
{
  "detail": "Task {task_id} not found"
}
```

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

Health check endpoint.

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
  -d '{"prompt": "Summarize the Python GIL"}' | jq -r .task_id)

# Poll until done
curl -s http://localhost:8101/task/$TASK_ID | jq .status
```

### Session-based conversation

```bash
# First message — establishes session
curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "My project uses FastAPI and PostgreSQL", "session_id": "project-ctx"}'

# Second message — agent remembers context
curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What database am I using?", "session_id": "project-ctx"}'
# Result: "You mentioned you are using PostgreSQL."
```

### Queue backpressure

```bash
# If max_concurrent_tasks=1 and queue is full:
curl -s -X POST http://localhost:8101/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Task 3"}'
# → 429 {"detail": "Task queue is full. Try again later."}
```
