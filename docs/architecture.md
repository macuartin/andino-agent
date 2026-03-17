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
│  │               │   │  (future: Telegram, etc.) ────┤    │
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
│            TaskStatus updated                             │
│                                                          │
│  GET /task/{id}  GET /tasks  GET /health  GET /info      │
└──────────────────────────────────────────────────────────┘
```

## Startup Flow

```
python -m andino agent.yaml
         │
         ▼
  AgentService.from_yaml()
         │
         ├── AgentConfig.from_yaml()     # Parse YAML, expand ${VAR}, resolve system_prompt
         ├── Set env vars                 # BYPASS_TOOL_CONSENT, etc.
         └── _run_async()
                  │
                  ├── TaskExecutor(config)   # shared instance
                  │        │
                  │        ├── AgentPool(config)
                  │        │        └── build_agent(config)  # stateless base agent
                  │        └── asyncio.Queue(maxsize)
                  │
                  ├── create_app(config, executor)
                  │        └── Mount FastAPI routes
                  │
                  ├── load_channels(config, executor)
                  │        └── Instantiate enabled channels (Slack, etc.)
                  │
                  └── asyncio.gather(server.serve(), *channels)
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

3. Execution completes
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

Strands `Agent.__call__()` (sync) internally creates a thread + event loop via `run_async()`. Using `invoke_async()` directly avoids this overhead:

| Approach | Threads | Event loops | Complexity |
|---|---|---|---|
| `run_in_executor(pool, agent, prompt)` | N+1 per task | 2 per task | High |
| `await agent.invoke_async(prompt)` | 0 | 1 (shared) | Low |

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

## Module Dependency Graph

```
__main__.py
    └── service.py
            ├── config.py (AgentConfig)
            ├── server.py (create_app)
            │       └── task_executor.py (TaskExecutor)
            │               ├── agent_builder.py (build_agent)
            │               │       ├── model_registry.py
            │               │       ├── tool_loader.py
            │               │       └── mcp_loader.py
            │               └── config.py (AgentConfig)
            └── channels/ (load_channels)
                    ├── __init__.py (BaseChannel, loader)
                    └── slack.py (SlackChannel)
```

No circular dependencies. Each module has a single responsibility.
