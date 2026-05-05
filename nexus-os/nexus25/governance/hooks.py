"""Governance hooks for NEXUS OS integration."""

from __future__ import annotations

import hashlib
import json as _json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DecisionType(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    HOLD = "hold"


@dataclass(frozen=True)
class GovernanceDecision:
    decision: DecisionType
    reason: str
    trust_score: float = 1.0
    lane: str = "general"
    token_budget_remaining: Optional[int] = None


@dataclass
class AuditEntry:
    """VAP-chain-compatible audit entry."""
    timestamp: float
    action: str
    actor: str
    decision: DecisionType
    details: dict[str, Any] = field(default_factory=dict)
    parent_hash: str = ""

    @property
    def entry_hash(self) -> str:
        details_str = _json.dumps(self.details, sort_keys=True, default=str)
        content = (
            f"{self.timestamp}:{self.action}:{self.actor}:"
            f"{self.decision.value}:{self.parent_hash}:{details_str}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class GovernanceHooks:
    """Integration hooks for nexusalpha governance."""

    def __init__(self, strict: bool = True, token_budget: int = 100_000) -> None:
        self.strict = strict
        self._audit_log: list[AuditEntry] = []
        self._token_budget: int = token_budget
        self._tokens_used: int = 0
        self._governor = None
        self._lock = threading.Lock()

        try:
            from nexus25._governor_bridge import load_governor
            self._governor = load_governor()
        except (ImportError, Exception):
            pass

    def check_tool_access(self, tool_name: str, actor: str = "agent") -> GovernanceDecision:
        if self._governor:
            try:
                result = self._governor.check_access(
                    agent_id=actor, project_id="nexus-unified", action=tool_name,
                )
                decision_map = {
                    "allow": DecisionType.ALLOWED,
                    "deny": DecisionType.DENIED,
                    "hold": DecisionType.HOLD,
                }
                mapped = decision_map.get(result.decision.value, DecisionType.DENIED)
                decision = GovernanceDecision(
                    decision=mapped, reason=f"Governor: {result.decision.value}",
                )
                self._record(tool_name, actor, decision.decision)
                return decision
            except Exception:
                if self.strict:
                    d = GovernanceDecision(decision=DecisionType.DENIED,
                                           reason="Governor error; strict mode denies by default")
                else:
                    d = GovernanceDecision(decision=DecisionType.ALLOWED,
                                           reason="Governor error; fail-open (non-strict)")
                self._record(tool_name, actor, d.decision)
                return d

        if self.strict:
            d = GovernanceDecision(decision=DecisionType.DENIED,
                                   reason="No governor available; strict mode denies by default")
        else:
            d = GovernanceDecision(decision=DecisionType.ALLOWED,
                                   reason="No governor available; default permissive (non-strict)")
        self._record(tool_name, actor, d.decision)
        return d

    def check_token_budget(self, tokens_requested: int) -> GovernanceDecision:
        with self._lock:
            remaining = self._token_budget - self._tokens_used
        if remaining <= 0:
            return GovernanceDecision(
                decision=DecisionType.DENIED,
                reason="Token budget exhausted (hard stop)",
                token_budget_remaining=0,
            )
        if tokens_requested > remaining:
            return GovernanceDecision(
                decision=DecisionType.DENIED,
                reason=f"Request ({tokens_requested}) exceeds remaining budget ({remaining})",
                token_budget_remaining=remaining,
            )
        return GovernanceDecision(
            decision=DecisionType.ALLOWED,
            reason="Within budget",
            token_budget_remaining=remaining,
        )

    def track_tokens(self, tokens_used: int, model: str = "", actor: str = "agent") -> None:
        if tokens_used < 0:
            raise ValueError(f"tokens_used must be non-negative, got {tokens_used}")
        with self._lock:
            self._tokens_used += tokens_used
        self._record(
            action=f"token_usage:{tokens_used}:{model}",
            actor=actor, decision=DecisionType.ALLOWED,
        )

    def _record(self, action: str, actor: str, decision: DecisionType) -> None:
        with self._lock:
            parent = self._audit_log[-1].entry_hash if self._audit_log else ""
            entry = AuditEntry(
                timestamp=time.time(), action=action, actor=actor,
                decision=decision, parent_hash=parent,
            )
            self._audit_log.append(entry)

    @property
    def audit_log(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._audit_log)

    @property
    def tokens_remaining(self) -> int:
        with self._lock:
            return max(0, self._token_budget - self._tokens_used)

    def set_token_budget(self, budget: int) -> None:
        with self._lock:
            self._token_budget = budget

    def close(self) -> None:
        pass

    def __enter__(self) -> "GovernanceHooks":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
