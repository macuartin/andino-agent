from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_tools(tool_refs: str) -> list[Any]:
    """Load tool callables from a comma-separated string of import references.

    Each reference uses the format ``module.path:attribute``.
    Example: ``"strands_tools.calculator:calculator,strands_tools.http:http_request"``
    """
    if not tool_refs or not tool_refs.strip():
        return []

    tools: list[Any] = []
    for ref in tool_refs.split(","):
        ref = ref.strip()
        if not ref:
            continue
        tool = _import_tool(ref)
        tools.append(tool)
        logger.info("loaded_tool ref=%s", ref)
    return tools


def _import_tool(ref: str) -> Any:
    if ":" in ref:
        module_name, attr = ref.split(":", 1)
    elif "." in ref:
        module_name, attr = ref.rsplit(".", 1)
    else:
        raise ValueError(f"Invalid tool reference '{ref}'. Expected 'module.path:attribute' format.")

    module = importlib.import_module(module_name)
    if not hasattr(module, attr):
        raise ValueError(f"Attribute '{attr}' not found in module '{module_name}'")

    obj = getattr(module, attr)

    # Old-style tools (plain functions with module-level TOOL_SPEC) must be
    # passed as the module so the SDK can discover the spec via load_tools_from_module.
    if callable(obj) and not hasattr(obj, "tool_name") and hasattr(module, "TOOL_SPEC"):
        return module

    return obj
