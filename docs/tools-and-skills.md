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

## Tools vs. Skills

| | **Tools** | **Skills** |
|---|---|---|
| **What they are** | Executable functions (`file_read`, `shell`, `http_request`) | Instruction packages (markdown) |
| **When loaded** | Always available in the agent's context | On-demand — only metadata shown initially |
| **What they do** | Execute a specific action | Guide the agent step-by-step through complex tasks |
| **Defined as** | Python functions with `@tool` decorator or `TOOL_SPEC` | `SKILL.md` files with YAML frontmatter |
| **Example** | `shell` runs a command | `code-review` teaches the agent how to review code |

**Use tools when** you need the agent to *execute* something — read files, make HTTP requests, run shell commands, interact with APIs.

**Use skills when** you need the agent to follow a *process* or *methodology*. A skill tells the agent *how* to do something; tools give it *what* to do it with.

**Example:**
- Tools: `shell` + `file_write` → the agent *can* run commands and write files
- Skill: `deploy-to-staging` → step-by-step instructions for *how* to use those tools to deploy

Skills **use** tools. They don't replace them.
