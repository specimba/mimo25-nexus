"""Gateway core — message dispatch across platforms."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..governance.hooks import GovernanceHooks, DecisionType


class Platform(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    HOMEASSISTANT = "homeassistant"
    CLI = "cli"
    API = "api"


@dataclass
class GatewayEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform = Platform.API
    user_id: str = ""
    channel_id: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    is_command: bool = False
    command_name: Optional[str] = None
    command_args: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewaySession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform = Platform.API
    user_id: str = ""
    channel_id: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    tokens_used: int = 0


class GatewayCore:
    def __init__(self, governance: Optional[GovernanceHooks] = None) -> None:
        self._sessions: dict[str, GatewaySession] = {}
        self._platforms: set[Platform] = set()
        self._command_handlers: dict[str, Any] = {}
        self._governance = governance

    def register_platform(self, platform: Platform) -> None:
        self._platforms.add(platform)

    def register_command(self, name: str, handler: Any) -> None:
        self._command_handlers[name] = handler

    def get_or_create_session(
        self, platform: Platform, user_id: str, channel_id: str,
    ) -> GatewaySession:
        key = f"{platform.value}:{user_id}:{channel_id}"
        if key not in self._sessions:
            self._sessions[key] = GatewaySession(
                platform=platform, user_id=user_id, channel_id=channel_id,
            )
        session = self._sessions[key]
        session.last_active = time.time()
        return session

    def process_event(self, event: GatewayEvent) -> str:
        session = self.get_or_create_session(event.platform, event.user_id, event.channel_id)
        if self._governance:
            decision = self._governance.check_tool_access(
                f"gateway:{event.platform.value}", actor=event.user_id,
            )
            if decision.decision == DecisionType.DENIED:
                return f"Access denied: {decision.reason}"
        if event.is_command and event.command_name:
            handler = self._command_handlers.get(event.command_name)
            if handler:
                return handler(event, session)
            return f"Unknown command: /{event.command_name}"
        session.messages.append({"role": "user", "content": event.content})
        response = f"[Gateway: received on {event.platform.value}, session {session.session_id[:8]}]"
        session.messages.append({"role": "assistant", "content": response})
        if self._governance:
            token_estimate = len(event.content.split()) * 2 + len(response.split()) * 2
            self._governance.track_tokens(token_estimate, actor=event.user_id)
            session.tokens_used += token_estimate
        return response

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    @property
    def registered_platforms(self) -> list[str]:
        return sorted(p.value for p in self._platforms)
