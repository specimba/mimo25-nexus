"""Agent conversation loop — sequential tool-use with provider routing."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..tools.registry import ToolRegistry
from ..tools.permissions import PermissionContext
from ..providers.router import ProviderRouter, RouteResult
from ..governance.hooks import GovernanceHooks

logger = logging.getLogger(__name__)


@dataclass
class ConversationResult:
    final_response: str
    messages: list[dict[str, Any]]
    tool_calls_count: int
    iterations: int
    provider_used: Optional[RouteResult] = None
    duration_ms: float = 0.0


class AgentLoop:
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        provider_router: Optional[ProviderRouter] = None,
        permission_ctx: Optional[PermissionContext] = None,
        governance: Optional[GovernanceHooks] = None,
        max_iterations: int = 90,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.provider_router = provider_router
        self.permission_ctx = permission_ctx
        self.governance = governance
        self.max_iterations = max_iterations

    def run(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[list[dict]] = None,
    ) -> ConversationResult:
        start = time.monotonic()
        messages: list[dict[str, Any]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        tool_schemas = self.tool_registry.get_definitions(permission_ctx=self.permission_ctx)

        if self.governance:
            decision = self.governance.check_tool_access("agent_loop:run", actor="agent")
            if decision.decision.value == "denied":
                return ConversationResult(
                    final_response=f"Blocked by governance: {decision.reason}",
                    messages=messages, tool_calls_count=0, iterations=0,
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                )

        route_result = None
        if self.provider_router:
            route_result = self.provider_router.select(
                min_context=32_000, prefer="quality", fallback_chain=True,
            )

        if self.governance and route_result:
            token_decision = self.governance.check_token_budget(4096)
            if token_decision.decision.value == "denied":
                return ConversationResult(
                    final_response=f"Token budget exceeded: {token_decision.reason}",
                    messages=messages, tool_calls_count=0, iterations=0,
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                )

        duration = (time.monotonic() - start) * 1000
        return ConversationResult(
            final_response=(
                f"[AgentLoop ready — {len(tool_schemas)} tools available, "
                f"provider={route_result.provider.name if route_result else 'none'}, "
                f"model={route_result.model.name if route_result else 'none'}]"
            ),
            messages=messages, tool_calls_count=0, iterations=0,
            provider_used=route_result,
            duration_ms=round(duration, 2),
        )
