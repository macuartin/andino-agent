"""Andino Agent CLI.

Usage::

    andino run <name-or-path> [--log-level info] [--log-file path]
    andino init <name>
    andino list
"""
from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from dotenv import load_dotenv

from andino.home import get_andino_home, resolve_agent_dir
from andino.service import AgentService, configure_logging

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

limits:
  max_concurrent_tasks: 1
  task_timeout_seconds: 600
"""

_SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful AI assistant.
"""


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

    # Load global first, then per-agent — neither overrides already-set vars
    if global_env.is_file():
        load_dotenv(global_env, override=False)
    if agent_env.is_file() and agent_env != global_env:
        load_dotenv(agent_env, override=False)


def _cmd_run(args: argparse.Namespace) -> None:
    config_path = _resolve_config_path(args.agent)
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        raise SystemExit(1)

    _load_env_files(config_path)
    configure_logging(args.log_level, args.log_file)

    AgentService.from_yaml(str(config_path)).run()


def _cmd_init(args: argparse.Namespace) -> None:
    agent_dir = resolve_agent_dir(args.name)
    if agent_dir.exists():
        print(f"Error: agent directory already exists: {agent_dir}", file=sys.stderr)
        raise SystemExit(1)

    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        _AGENT_YAML_TEMPLATE.format(name=args.name), encoding="utf-8"
    )
    (agent_dir / "system_prompt.md").write_text(_SYSTEM_PROMPT_TEMPLATE, encoding="utf-8")

    print(f"Created agent '{args.name}' at {agent_dir}")
    print(f"  Edit config:  {agent_dir / 'agent.yaml'}")
    print(f"  Edit prompt:  {agent_dir / 'system_prompt.md'}")
    print(f"  Add secrets:  {agent_dir / '.env'}")
    print(f"  Run:          andino run {args.name}")


def _cmd_list(_args: argparse.Namespace) -> None:
    agents_dir = get_andino_home() / "agents"
    if not agents_dir.is_dir():
        print("No agents found. Create one with: andino init <name>")
        return

    agents = sorted(
        d.name for d in agents_dir.iterdir() if d.is_dir() and (d / "agent.yaml").is_file()
    )
    if not agents:
        print("No agents found. Create one with: andino init <name>")
        return

    for name in agents:
        print(f"  {name}")


def _build_parser() -> argparse.ArgumentParser:
    try:
        ver = pkg_version("andino-agent")
    except Exception:
        ver = "dev"

    parser = argparse.ArgumentParser(prog="andino", description="Andino Agent CLI")
    parser.add_argument("--version", action="version", version=f"andino {ver}")

    subparsers = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Run an agent")
    run_parser.add_argument(
        "agent",
        help="Agent name (looked up in ~/.andino/agents/<name>/) or path to agent.yaml",
    )
    run_parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Log level (default: info)",
    )
    run_parser.add_argument("--log-file", default=None, help="Log to file (in addition to stdout)")
    run_parser.set_defaults(func=_cmd_run)

    # --- init ---
    init_parser = subparsers.add_parser("init", help="Create a new agent")
    init_parser.add_argument("name", help="Agent name")
    init_parser.set_defaults(func=_cmd_init)

    # --- list ---
    list_parser = subparsers.add_parser("list", help="List agents in ~/.andino/agents/")
    list_parser.set_defaults(func=_cmd_list)

    return parser


def main() -> None:
    # Backward compatibility: `andino agent.yaml` (no subcommand)
    # Intercept before argparse to avoid "invalid choice" error
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-") and sys.argv[1] not in ("run", "init", "list"):
        sys.argv = [sys.argv[0], "run", sys.argv[1]]

    parser = _build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(1)

    args.func(args)


if __name__ == "__main__":
    main()
