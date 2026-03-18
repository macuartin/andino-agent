# Tools, MCP Servers & Skills

## Tools

Tools are executable functions the agent can call. Listed in `agent.yaml` using `module.path:attribute` format:

```yaml
tools:
  - strands_tools.http_request:http_request
  - strands_tools.shell:shell
  - strands_tools.file_read:file_read
  - mypackage.custom_tools:my_tool
```

Supports:
- `@tool`-decorated functions from `strands-agents-tools`
- Legacy tools with module-level `TOOL_SPEC`
- Custom tools from any installed package

Each tool is dynamically imported at startup.

## Sub-Agents (`use_agent`)

The `use_agent` tool lets an agent spawn temporary sub-agents with custom instructions and a filtered set of tools. The sub-agent runs in isolation, processes a single task, and returns the result.

```yaml
tools:
  - strands_tools.use_agent:use_agent
```

The agent decides when to delegate. When it calls `use_agent`, it provides:

- **`prompt`** — the task for the sub-agent
- **`system_prompt`** — custom instructions (role, constraints, output format)
- **`tools`** — which parent tools the sub-agent can use (default: all)
- **`model_provider`** — optional different model (`bedrock`, `anthropic`, `openai`, `ollama`)

### Use cases

**Plan-then-execute** — analyze before acting:

The parent agent spawns a read-only sub-agent (tools: `file_read`, `shell`) to explore the codebase and produce a plan, then implements it with full tools.

**Specialized review** — delegate to an expert:

Before delivering, the parent gives a sub-agent a security-focused system prompt and only `file_read` access to review the changes.

**Multi-perspective analysis** — get different viewpoints:

The parent spawns sub-agents with different system prompts (e.g. performance vs. cost) and synthesizes their outputs.

### Example

A coder agent that reviews its own work:

```yaml
tools:
  - strands_tools.use_agent:use_agent
  - strands_tools.file_read:file_read
  - strands_tools.file_write:file_write
  - strands_tools.shell:shell
```

The agent internally:
1. Writes code using `file_write` and `shell`
2. Calls `use_agent` with a code-review system prompt and only `file_read`
3. Receives feedback from the sub-agent
4. Fixes issues based on the review
5. Delivers the final result

The sub-agent is temporary — no memory of previous interactions, destroyed after returning.

## MCP Servers

[MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers provide tools via a client-server protocol. Three transports are supported:

**stdio** — runs as a subprocess:
```yaml
mcp_servers:
  - name: github
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}
```

**SSE** — connects to an HTTP SSE endpoint:
```yaml
mcp_servers:
  - name: my-server
    transport: sse
    server_url: http://localhost:3000/sse
```

**Streamable HTTP** — bidirectional HTTP:
```yaml
mcp_servers:
  - name: my-server
    transport: streamable_http
    server_url: http://localhost:3000/mcp
```

## Skills

Skills are modular instruction packages loaded on-demand via [Strands Skills](https://strandsagents.com/docs/user-guide/concepts/plugins/skills/). Instead of putting everything in the system prompt, skills use progressive disclosure — only their name and description are shown initially. Full instructions load when the agent activates a skill.

```yaml
skills:
  - ./skills/                    # directory with skill subdirectories
  - ./skills/code-review/        # single skill directory (must contain SKILL.md)
  - /shared/skills/deploy/       # absolute path
```

Each entry can be:
- A **skill directory** containing a `SKILL.md` file → loads one skill
- A **parent directory** with subdirectories containing `SKILL.md` → loads all skills found

Relative paths are resolved against the `agent.yaml` file's directory.

### Skill file format

Each skill is a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: code-review
description: "Reviews code for bugs, style, and security issues"
---
# Code Review Instructions

When reviewing code, follow these steps:
1. Check for bugs and logic errors
2. Verify error handling
3. Look for security vulnerabilities
...
```

The agent discovers available skills from their metadata and activates them by calling a built-in `skills` tool when needed.

## Tools vs. Skills vs. Sub-Agents

| | **Tools** | **Skills** | **Sub-Agents** |
|---|---|---|---|
| **What they are** | Executable functions | Instruction packages (markdown) | Temporary agent instances |
| **When loaded** | Always available | On-demand metadata | Created per invocation |
| **What they do** | Execute a single action | Guide step-by-step | Process a full task in isolation |
| **Defined as** | Python `@tool` functions | `SKILL.md` files | `use_agent` tool call with custom prompt |
| **Example** | `shell` runs a command | `code-review` methodology | Sub-agent reviews code with restricted tools |

**Use tools when** you need the agent to *execute* something — read files, make HTTP requests, run shell commands.

**Use skills when** you need the agent to follow a *process* or *methodology*. A skill tells the agent *how* to do something.

**Use sub-agents when** you need *delegation* — a separate agent with different instructions, restricted tools, or a different model to handle a subtask and return results.

**How they compose:**
- Tools provide *capabilities* (what the agent can do)
- Skills provide *knowledge* (how to approach a task)
- Sub-agents provide *delegation* (hand off a subtask to a specialist)
