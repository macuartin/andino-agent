from __future__ import annotations

import logging
import os
from typing import Any

from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


def _build_transport(config: dict[str, Any]):
    """Create a transport callable from a server config dict."""
    transport = config.get("transport", "stdio")

    if transport == "stdio":
        command = config["command"]
        args = config.get("args", [])
        env = config.get("env")
        full_env = {**os.environ, **env} if env else None
        devnull = open(os.devnull, "w")  # noqa: SIM115
        return lambda: stdio_client(
            StdioServerParameters(command=command, args=args, env=full_env),
            errlog=devnull,
        )

    if transport == "sse":
        from mcp.client.sse import sse_client

        server_url = config["server_url"]
        return lambda: sse_client(server_url)

    if transport == "streamable_http":
        from mcp.client.streamable_http import streamablehttp_client

        server_url = config["server_url"]
        return lambda: streamablehttp_client(url=server_url)

    raise ValueError(f"Unsupported MCP transport: {transport}")


def load_mcp_servers(configs: list[dict[str, Any]]) -> list[MCPClient]:
    """Load MCP servers from inline config dicts.

    Each dict should have at minimum a ``transport`` key (stdio, sse, or
    streamable_http) plus transport-specific fields (command/args/env for
    stdio, server_url for sse/streamable_http).
    """
    clients: list[MCPClient] = []
    for cfg in configs:
        name = cfg.get("name", "unnamed")
        try:
            transport = _build_transport(cfg)
            client = MCPClient(transport)
            logger.info("mcp_server_configured name=%s", name)
            clients.append(client)
        except Exception as exc:
            logger.error("Failed to configure MCP server '%s': %s", name, exc)
    return clients
