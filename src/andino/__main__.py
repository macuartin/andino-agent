"""Andino Agent CLI.

Usage::

    andino run <name-or-path> [--log-level info] [--log-file path]
    andino init <name>
    andino list
    andino validate <name-or-path>
    andino info <name-or-path>
    andino task <name-or-path> "prompt" [--session id] [--timeout secs] [--json]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from importlib.metadata import version as pkg_version
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from andino.home import get_andino_home, resolve_agent_dir
from andino.service import AgentService, configure_logging

app = typer.Typer(
    help="Andino Agent CLI — define, run, and manage autonomous agents.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()

# ── Templates ──────────────────────────────────────────────────────────────

_AGENT_YAML_TEMPLATE = """\
name: {name}
version: "1.0.0"
description: ""

model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-6
  max_tokens: 4096

system_prompt: ./system_prompt.md

tools:
  - strands_tools.http_request:http_request

server:
  port: 8100

skills:
  - ./skills/

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 600
"""

_SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful AI assistant.
"""

# ── Helpers ────────────────────────────────────────────────────────────────


def _get_version() -> str:
    try:
        return pkg_version("andino-agent")
    except Exception:
        return "dev"


def _resolve_config_path(name_or_path: str) -> Path:
    """Resolve a config argument to an actual file path.

    If the argument looks like a file path (contains ``/`` or ends with
    ``.yaml``/``.yml``), use it directly.  Otherwise treat it as an agent
    name and look it up under ``$ANDINO_HOME/agents/<name>/agent.yaml``.
    """
    if "/" in name_or_path or name_or_path.endswith((".yaml", ".yml")):
        return Path(name_or_path)
    return resolve_agent_dir(name_or_path) / "agent.yaml"


def _load_env_files(config_path: Path) -> None:
    """Load .env files in priority order (system env > per-agent > global)."""
    home = get_andino_home()
    global_env = home / ".env"
    agent_env = config_path.parent / ".env"

    if global_env.is_file():
        load_dotenv(global_env, override=False)
    if agent_env.is_file() and agent_env != global_env:
        load_dotenv(agent_env, override=False)


def _load_config(agent: str):
    """Resolve path, load env, parse config. Returns (config, path)."""
    from andino.config import AgentConfig

    path = _resolve_config_path(agent)
    if not path.is_file():
        console.print(f"[red]Error:[/] config not found: {path}")
        raise typer.Exit(1)
    _load_env_files(path)
    config = AgentConfig.from_yaml(str(path))
    return config, path


# ── Commands ───────────────────────────────────────────────────────────────


@app.command()
def run(
    agent: str = typer.Argument(help="Agent name or path to agent.yaml"),
    log_level: str = typer.Option("info", "--log-level", help="Log level (debug/info/warning/error)"),
    log_file: str | None = typer.Option(None, "--log-file", help="Log to file in addition to stdout"),
) -> None:
    """Start an agent HTTP server."""
    config_path = _resolve_config_path(agent)
    if not config_path.is_file():
        console.print(f"[red]Error:[/] config not found: {config_path}")
        raise typer.Exit(1)

    _load_env_files(config_path)
    configure_logging(log_level, log_file)
    AgentService.from_yaml(str(config_path)).run()


@app.command()
def init(name: str = typer.Argument(help="Agent name")) -> None:
    """Scaffold a new agent in ~/.andino/agents/<name>/."""
    agent_dir = resolve_agent_dir(name)
    if agent_dir.exists():
        console.print(f"[red]Error:[/] agent directory already exists: {agent_dir}")
        raise typer.Exit(1)

    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        _AGENT_YAML_TEMPLATE.format(name=name), encoding="utf-8"
    )
    (agent_dir / "system_prompt.md").write_text(_SYSTEM_PROMPT_TEMPLATE, encoding="utf-8")

    example_skill_dir = agent_dir / "skills" / "example"
    example_skill_dir.mkdir(parents=True)
    (example_skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: example\n"
        'description: "An example skill — replace with your own"\n'
        "---\n"
        "# Example Skill\n\n"
        "Replace this file with instructions for a real skill.\n"
        "Skills teach the agent *how* to perform complex tasks step by step.\n",
        encoding="utf-8",
    )

    console.print(f"[green]✓[/] Created agent [bold]{name}[/] at {agent_dir}")
    console.print(f"  Edit config:  [cyan]{agent_dir / 'agent.yaml'}[/]")
    console.print(f"  Edit prompt:  [cyan]{agent_dir / 'system_prompt.md'}[/]")
    console.print(f"  Add secrets:  [cyan]{agent_dir / '.env'}[/]")
    console.print(f"  Run:          [bold]andino run {name}[/]")


@app.command(name="list")
def list_agents() -> None:
    """List agents in ~/.andino/agents/."""
    agents_dir = get_andino_home() / "agents"
    if not agents_dir.is_dir():
        console.print("No agents found. Create one with: [bold]andino init <name>[/]")
        return

    agents = sorted(
        d.name for d in agents_dir.iterdir() if d.is_dir() and (d / "agent.yaml").is_file()
    )
    if not agents:
        console.print("No agents found. Create one with: [bold]andino init <name>[/]")
        return

    for name in agents:
        console.print(f"  {name}")


@app.command()
def validate(agent: str = typer.Argument(help="Agent name or path to agent.yaml")) -> None:
    """Validate agent configuration without running."""
    from andino.config import AgentConfig
    from andino.tool_loader import _import_tool

    path = _resolve_config_path(agent)
    if not path.is_file():
        console.print(f"[red]✗[/] Config file not found: {path}")
        raise typer.Exit(1)

    _load_env_files(path)
    errors = 0

    # 1. Parse config
    try:
        config = AgentConfig.from_yaml(str(path))
        console.print(f"[green]✓[/] Config: valid ({path.name})")
    except Exception as exc:
        console.print(f"[red]✗[/] Config: {exc}")
        raise typer.Exit(1) from None

    # 2. System prompt
    if config.system_prompt:
        lines = config.system_prompt.count("\n") + 1
        console.print(f"[green]✓[/] System prompt: {lines} lines")
    else:
        console.print("[yellow]⚠[/] System prompt: empty")

    # 3. Tools
    bad_tools: list[str] = []
    for ref in config.tools:
        try:
            _import_tool(ref)
        except Exception:
            bad_tools.append(ref)
    ok = len(config.tools) - len(bad_tools)
    if bad_tools:
        console.print(f"[red]✗[/] Tools: {ok}/{len(config.tools)} importable")
        for b in bad_tools:
            console.print(f"    [red]✗ {b}[/]")
        errors += len(bad_tools)
    elif config.tools:
        console.print(f"[green]✓[/] Tools: {ok}/{len(config.tools)} importable")
    else:
        console.print("[dim]  Tools: none configured[/]")

    # 4. Skills
    bad_skills: list[str] = []
    for skill_path in config.skills:
        p = Path(skill_path)
        if not p.is_dir():
            bad_skills.append(skill_path)
        elif not (p / "SKILL.md").is_file():
            bad_skills.append(f"{skill_path} (missing SKILL.md)")
    ok_skills = len(config.skills) - len(bad_skills)
    if bad_skills:
        console.print(f"[red]✗[/] Skills: {ok_skills}/{len(config.skills)} valid")
        for b in bad_skills:
            console.print(f"    [red]✗ {b}[/]")
        errors += len(bad_skills)
    elif config.skills:
        console.print(f"[green]✓[/] Skills: {ok_skills}/{len(config.skills)} valid")

    # 5. Environment variables — scan raw YAML for ${VAR}
    raw_text = path.read_text(encoding="utf-8")
    env_refs = set(re.findall(r"\$\{([^}]+)}", raw_text))
    missing_env = [v for v in sorted(env_refs) if not os.environ.get(v)]
    if missing_env:
        for v in missing_env:
            console.print(f"[yellow]⚠[/] Environment: {v} not set")

    # 6. Server
    auth_label = "[green]Bearer token[/]" if config.server.api_key else "[yellow]none[/]"
    console.print(f"[green]✓[/] Server: {config.server.host}:{config.server.port} (auth: {auth_label})")

    if errors:
        console.print(f"\n[red]Validation failed with {errors} error(s)[/]")
        raise typer.Exit(1)
    else:
        console.print("\n[green]Validation passed[/]")


@app.command()
def info(agent: str = typer.Argument(help="Agent name or path to agent.yaml")) -> None:
    """Show agent configuration details."""
    config, _path = _load_config(agent)

    console.print(f"\n[bold]{config.name}[/] v{config.version}")
    if config.description:
        console.print(f"  [dim]{config.description}[/]")
    console.print()

    # Config table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Model", f"{config.model.provider} / {config.model.model_id} (max_tokens: {config.model.max_tokens})")
    if config.model.extras:
        table.add_row("Extras", str(config.model.extras))
    table.add_row("Server", f"{config.server.host}:{config.server.port}")
    auth = "[green]Bearer token[/]" if config.server.api_key else "[yellow]none[/]"
    table.add_row("Auth", auth)
    ws = f"[green]enabled[/] ({config.workspace.base_dir})" if config.workspace.enabled else "[dim]disabled[/]"
    table.add_row("Workspace", ws)
    conc = f"{config.limits.max_concurrent_tasks} tasks, {config.limits.task_timeout_seconds}s timeout"
    table.add_row("Concurrency", conc)
    table.add_row("Session", f"{config.session.storage_dir} (pool: {config.session.max_pool_size})")
    if config.hitl.require_approval:
        table.add_row("HITL", ", ".join(config.hitl.require_approval))
    console.print(table)

    # Tools
    if config.tools:
        console.print(f"\n[bold]Tools ({len(config.tools)}):[/]")
        for t in config.tools:
            console.print(f"  [cyan]{t}[/]")

    # Skills
    if config.skills:
        console.print(f"\n[bold]Skills ({len(config.skills)}):[/]")
        for s in config.skills:
            name = Path(s).name
            console.print(f"  [cyan]{name}[/]")

    # Channels
    if config.channels:
        console.print("\n[bold]Channels:[/]")
        for ch_name, ch_cfg in config.channels.items():
            enabled = ch_cfg.get("enabled", True)
            status = "[green]enabled[/]" if enabled else "[dim]disabled[/]"
            mode = ch_cfg.get("mode", "")
            console.print(f"  {ch_name}: {status} ({mode})" if mode else f"  {ch_name}: {status}")

    console.print()


@app.command()
def task(
    agent: str = typer.Argument(help="Agent name or path to agent.yaml"),
    prompt: str = typer.Argument(help="Task prompt"),
    session: str | None = typer.Option(None, "--session", "-s", help="Session ID for conversation persistence"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="Max wait time in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Send a task to a running agent and wait for the result."""
    asyncio.run(_task_async(agent, prompt, session, timeout, json_output))


async def _task_async(
    agent: str,
    prompt: str,
    session: str | None,
    timeout_secs: int | None,
    json_output: bool,
) -> None:
    import httpx

    config, _path = _load_config(agent)
    base = f"http://{config.server.host}:{config.server.port}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.server.api_key:
        headers["Authorization"] = f"Bearer {config.server.api_key}"

    body: dict = {"prompt": prompt}
    if session:
        body["session_id"] = session

    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
        # Submit
        try:
            resp = await client.post(f"{base}/task", json=body, headers=headers)
        except httpx.ConnectError:
            console.print(f"[red]Error:[/] cannot connect to agent at {base}. Is it running?")
            raise typer.Exit(1) from None

        if resp.status_code != 202:
            console.print(f"[red]Error {resp.status_code}:[/] {resp.text[:300]}")
            raise typer.Exit(1)

        task_id = resp.json()["task_id"]
        console.print(f"[dim]Task {task_id} submitted[/]", highlight=False)

        # Poll
        max_wait = timeout_secs or config.limits.task_timeout_seconds
        deadline = time.monotonic() + max_wait

        from rich.live import Live
        from rich.spinner import Spinner

        with Live(Spinner("dots", text="Running..."), console=console, transient=True):
            while time.monotonic() < deadline:
                resp = await client.get(f"{base}/task/{task_id}", headers=headers)
                data = resp.json()
                status = data["status"]

                if status == "completed":
                    if json_output:
                        console.print_json(json.dumps(data))
                    else:
                        result = data.get("result", "")
                        if result:
                            console.print(result)
                    return

                if status in ("failed", "timeout"):
                    console.print(f"[red]{status}:[/] {data.get('error', '')}")
                    raise typer.Exit(1)

                if status == "interrupted":
                    for intr in data.get("interrupts", []):
                        name = intr.get("name", "unknown")
                        reason = intr.get("reason", {})
                        tool_name = reason.get("tool_name", name) if isinstance(reason, dict) else name
                        console.print(f"\n[yellow]⚠ Tool approval required:[/] [bold]{tool_name}[/]")
                        if isinstance(reason, dict) and reason.get("tool_input"):
                            console.print(f"  Input: {str(reason['tool_input'])[:200]}")
                        approved = typer.confirm("  Approve?", default=False)
                        response = "approved" if approved else "denied"
                        await client.post(
                            f"{base}/task/{task_id}/respond",
                            json={"interrupt_id": intr["interrupt_id"], "response": response},
                            headers=headers,
                        )

                await asyncio.sleep(2)

        console.print("[red]Timed out waiting for task completion[/]")
        raise typer.Exit(1)


# ── Version callback ───────────────────────────────────────────────────────

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"andino {_get_version()}")
        raise typer.Exit()


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version"),
) -> None:
    """Andino Agent CLI — define, run, and manage autonomous agents."""


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    # Backward compatibility: `andino agent.yaml` (no subcommand)
    if (
        len(sys.argv) == 2
        and not sys.argv[1].startswith("-")
        and sys.argv[1] not in ("run", "init", "list", "validate", "info", "task")
    ):
        sys.argv = [sys.argv[0], "run", sys.argv[1]]

    app()


if __name__ == "__main__":
    main()
