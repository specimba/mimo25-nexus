"""Permission context — from claw-code-parity's filter_tools_by_permission_context().

Controls which tools are available to an agent based on lane, trust level,
and explicit allow/block lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    STANDARD = "standard"
    ELEVATED = "elevated"
    GOVERNED = "governed"        # behind Governor approval
    RED_TEAM = "red_team"        # full access, audited


@dataclass
class PermissionContext:
    """Controls tool visibility and execution permissions for an agent session."""
    trust_level: TrustLevel = TrustLevel.STANDARD
    lane: str = "general"
    blocked_tools: set[str] = field(default_factory=set)
    allowed_tools: set[str] | None = None  # None = allow all (minus blocked)
    requires_governor: bool = False
    actor: str = "agent"

    def is_tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.blocked_tools:
            return False
        if self.allowed_tools is not None:
            return tool_name in self.allowed_tools
        return True

    def filter_tools(self, tool_names: list[str]) -> list[str]:
        return [t for t in tool_names if self.is_tool_allowed(t)]

    @classmethod
    def untrusted(cls) -> "PermissionContext":
        return cls(
            trust_level=TrustLevel.UNTRUSTED,
            allowed_tools={"read_file", "list_files", "search", "web_search"},
        )

    @classmethod
    def standard(cls) -> "PermissionContext":
        return cls(trust_level=TrustLevel.STANDARD)

    @classmethod
    def governed(cls, lane: str = "general") -> "PermissionContext":
        return cls(trust_level=TrustLevel.GOVERNED, lane=lane, requires_governor=True)

    @classmethod
    def red_team(cls) -> "PermissionContext":
        return cls(trust_level=TrustLevel.RED_TEAM, requires_governor=True)
