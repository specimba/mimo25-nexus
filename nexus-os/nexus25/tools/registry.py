"""Unified tool registry — merges hermes-agent's tools/registry.py with
claw-code-parity's tool dispatch patterns.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .permissions import PermissionContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    """A single tool registration."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    handler: Optional[Callable] = None
    check_fn: Optional[Callable[[], bool]] = None
    toolset: str = "core"
    requires_governance: bool = False

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class DispatchResult:
    tool_name: str
    success: bool
    output: Any
    duration_ms: float
    error: Optional[str] = None


class ToolRegistry:
    """Central tool registry with permission-aware dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        self._toolsets.setdefault(tool.toolset, []).append(tool.name)

    def register_function(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable,
        toolset: str = "core",
        requires_governance: bool = False,
    ) -> None:
        self.register(ToolDefinition(
            name=name, description=description, parameters=parameters,
            handler=handler, toolset=toolset, requires_governance=requires_governance,
        ))

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_definitions(
        self, permission_ctx: Optional[PermissionContext] = None,
    ) -> list[ToolDefinition]:
        tools = list(self._tools.values())
        tools = [t for t in tools if t.check_fn is None or t.check_fn()]
        if permission_ctx:
            names = permission_ctx.filter_tools([t.name for t in tools])
            tools = [t for t in tools if t.name in names]
        return tools

    def get_schemas(
        self, permission_ctx: Optional[PermissionContext] = None,
    ) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.get_definitions(permission_ctx)]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> DispatchResult:
        tool = self._tools.get(name)
        if not tool:
            return DispatchResult(
                tool_name=name, success=False, output=None,
                duration_ms=0, error=f"Unknown tool: {name}",
            )
        if not tool.handler:
            return DispatchResult(
                tool_name=name, success=False, output=None,
                duration_ms=0, error=f"Tool '{name}' has no handler",
            )
        start = time.monotonic()
        try:
            result = tool.handler(**arguments)
            duration = (time.monotonic() - start) * 1000
            return DispatchResult(
                tool_name=name, success=True, output=result,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            logger.exception("Tool '%s' failed", name)
            return DispatchResult(
                tool_name=name, success=False, output=None,
                duration_ms=round(duration, 2), error=str(e),
            )

    def toolset_names(self) -> list[str]:
        return sorted(self._toolsets.keys())

    def tools_in_toolset(self, toolset: str) -> list[str]:
        return list(self._toolsets.get(toolset, []))

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
