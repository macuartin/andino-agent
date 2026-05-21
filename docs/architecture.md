# Architecture

## Overview

Each Andino agent runs as an independent unit: one process, one HTTP server, optional channels, and one or more worker coroutines. No shared state between agents. No central orchestrator required.

```
┌──────────────────────────────────────────────────────────┐
│                       Agent Unit                          │
│                                                          │
│  agent.yaml ──> AgentConfig ──> AgentService.run()       │
│                                                          │
│  ┌──────────────┐   ┌──────────────────────────────┐     │
│  │ HTTP Server   │   │  Channels (optional)          │    │
│  │ POST /task ───┤   │  SlackChannel ────────────────┤    │
│  │ POST /respond─┤   │  (future: Telegram, etc.) ────┤    │
│  │ Bearer auth ──┤   │                               │    │
│  └───────┬───────┘   └──────────────┬────────────────┘    │
│          │                          │                     │
│          └──────────┬───────────────┘                     │
│                     ▼                                     │
│          TaskExecutor (shared)                            │
│            asyncio.Queue (bounded)                        │
│                     │                                     │
│             N worker coroutines                           │
│                     │                                     │
│         AgentPool.get(session_id)                         │
│                     │                                     │
│     await agent.invoke_async(prompt)                      │
│         + asyncio.wait_for(timeout)                       │
│                     │                                     │
│          ┌──── interrupt? ────┐                           │
│          │ yes                │ no                        │
│          ▼                   ▼                            │
│   status=interrupted   status=completed                  │
│   wait for /respond    result=text                       │
│   resume agent                                           │
│                                                          │
│  GET /task/{id}  GET /tasks  GET /health  GET /info      │
└──────────────────────────────────────────────────────────┘
```

## Startup Flow

```
andino run researcher
         │
         ├── load_dotenv()               # ~/.andino/.env + agent/.env
         ├── configure_logging()         # stdout + optional file handler
         │
         ▼
  AgentService.from_yaml()
         │
         ├── AgentConfig.from_yaml()     # Parse YAML, expand ${VAR}, resolve paths
         ├── Set env vars                 # BYPASS_TOOL_CONSENT, etc.
         └── _run_async()
                  │
                  ├── Register SIGTERM/SIGINT handlers
                  │
                  ├── TaskExecutor(config)   # shared instance
                  │        │
                  │        ├── AgentPool(config)
                  │        │        └── build_agent(config)  # stateless base agent
                  │        └── asyncio.Queue(maxsize)
                  │
                  ├── create_app(config, executor)
                  │        └── Mount FastAPI routes + auth middleware
                  │
                  ├── load_channels(config, executor)
                  │        └── Instantiate enabled channels (Slack, etc.)
                  │
                  └── asyncio.wait([server, channels, shutdown_event])
```

## Task Lifecycle

```
1. POST /task arrives
   ├── TaskStatus created (status=queued)
   └── _TaskItem placed in asyncio.Queue
       └── If queue full → 429 Too Many Requests

2. Worker picks up item from queue
   ├── TaskStatus → running
   ├── AgentPool.acquire(session_id)
   │   ├── session_id=None → shared stateless agent
   │   └── session_id="x"  → dedicated agent with FileSessionManager
   │                          (created on first use, cached in LRU pool)
   └── await agent.invoke_async(prompt)
       wrapped in asyncio.wait_for(timeout)

3. Execution loop (may repeat on interrupts)
   ├── Interrupt (HITL) → status=interrupted, interrupts=[{id, name, reason}]
   │   ├── Notify channel callback (Slack buttons) if registered
   │   ├── Create asyncio.Future, wait for human response
   │   ├── POST /respond delivers response → future.set_result()
   │   └── Resume agent with interrupt responses → back to invoke_async
   ├── Success → status=completed, result=text
   ├── Timeout → status=timeout, error=message
   └── Error   → status=failed, error=message
   Lock released, completed_at set.
```

## Concurrency Model

The SDK uses **native async** throughout. No thread pools.

- **Strands `invoke_async()`** is a true async coroutine that streams LLM responses without blocking the event loop
- **Worker count** equals `max_concurrent_tasks` — each worker is an `asyncio.Task` that awaits the queue
- **Queue backpressure**: queue size = `max_concurrent_tasks * 2`. If full, new tasks get 429
- **Session locks**: one `asyncio.Lock` per `session_id` prevents concurrent writes to the same conversation

### Why not ThreadPoolExecutor?

Strands `Agent.__call__()` (sync) internally creates a thread + event loop via `run_async()`. Using `stream_async()` directly avoids this overhead:

| Approach | Threads | Event loops | Complexity |
|---|---|---|---|
| `run_in_executor(pool, agent, prompt)` | N+1 per task | 2 per task | High |
| `agent.stream_async(prompt)` | 0 | 1 (shared) | Low |

The worker iterates `stream_async` via `_consume_stream`, forwarding each `data` delta to an optional ``on_progress`` callback before returning the final `AgentResult`. ``invoke_async`` internally does the same thing, so semantics — including interrupt handling — are identical whether or not a callback is registered.

### Progressive responses in channels

Channels can register an ``on_progress`` callback when calling
``submit_and_wait``. The callback is awaited with each text delta as the
model produces tokens. The Slack channel uses this to post a placeholder
message immediately and update it via ``chat_update`` on a throttle
(``stream_update_interval``, default 1.5 s), so the user sees the
response build up rather than wait for the whole turn. Set
``streaming: false`` in the Slack config to fall back to the final-only
behavior.

## Session Management

Sessions are **opt-in**. Behavior depends on whether `session_id` is provided in `POST /task`:

| `session_id` | Agent Instance | Session Manager | Conversation |
|---|---|---|---|
| `null` / absent | Shared (stateless) | None | Each task is independent |
| `"jira-AD-123"` | Dedicated (cached) | `FileSessionManager` | Tasks in same session share context |

The **AgentPool** manages the cache:
- LRU eviction when `max_pool_size` is exceeded
- One `asyncio.Lock` per session prevents race conditions
- The stateless agent (key=`None`) is never evicted

## Graceful Shutdown

Signal handlers are registered on the event loop for `SIGTERM` and `SIGINT`:

1. Signal received → `shutdown_event.set()`
2. `asyncio.wait()` returns (FIRST_COMPLETED)
3. All pending tasks (server, channels) are cancelled
4. Channel `stop()` methods are called for cleanup
5. Process exits cleanly

This ensures in-flight tasks complete before shutdown and channels (Slack Socket Mode, etc.) disconnect properly.

## Observability (OpenTelemetry)

Opt-in via `agent.yaml`. Requires the `andino-agent[otel]` extra.

```yaml
observability:
  enabled: true
  otlp: true              # default — export traces to OTLP endpoint
  console: false          # also print spans to stdout (debug)
  metrics: false          # set up MeterProvider
  service_name: ""        # defaults to agent name
  lifecycle_logging: true # log invocation start/end + duration
```

### Lifecycle hooks

When `lifecycle_logging: true`, andino attaches a `LifecycleHook` that subscribes to Strands' `BeforeInvocationEvent`, `AfterInvocationEvent`, and `MessageAddedEvent` and emits structured log lines:

```
invocation_started input_messages=3
message_added role=assistant         # DEBUG level
invocation_completed duration_ms=2417 stop_reason=end_turn
```

Channels can subscribe to `MessageAddedEvent` programmatically by passing an `on_message` callback to `LifecycleHook(on_message=...)` — used to mirror partial assistant messages to Slack/etc. as they are produced.

Standard OTEL env vars are honored by the underlying SDK:

- `OTEL_EXPORTER_OTLP_ENDPOINT` — collector URL (default `http://localhost:4318`)
- `OTEL_EXPORTER_OTLP_HEADERS` — auth headers (`api-key=...`)
- `OTEL_SERVICE_NAME` — overrides agent name

Strands emits GenAI semantic-convention spans (`gen_ai.system`, `gen_ai.request.model`, tool calls, etc.) — readable in Jaeger, Datadog, Honeycomb, or any OTLP-compatible backend.

Quick local test with Jaeger:

```bash
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 andino run my-agent
# open http://localhost:16686
```

## Module Dependency Graph

```
__main__.py (CLI: run, init, list)
    ├── home.py (ANDINO_HOME resolver)
    └── service.py (configure_logging, signal handling)
            ├── config.py (AgentConfig)
            │       └── home.py (resolve_data_path)
            ├── server.py (create_app + Bearer auth)
            │       └── task_executor.py (TaskExecutor)
            │               ├── agent_builder.py (build_agent + workspace)
            │               │       ├── model_registry.py
            │               │       ├── tool_loader.py
            │               │       ├── mcp_loader.py
            │               │       └── hitl.py (ToolApprovalHook)
            │               └── config.py (AgentConfig)
            └── channels/ (load_channels)
                    ├── __init__.py (BaseChannel, loader)
                    └── slack.py (SlackChannel + HITL buttons)
```

No circular dependencies. Each module has a single responsibility.
