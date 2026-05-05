"""Governance hooks for NEXUS OS integration."""

from __future__ import annotations

import hashlib
import json as _json
import threading
import time
import uuid
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


# ---------------------------------------------------------------------------
# Token reservation record
# ---------------------------------------------------------------------------

@dataclass
class _TokenReservation:
    reservation_id: str
    agent_id: str
    reserved: int
    actual: int = 0
    operation: str = ""
    created_at: float = field(default_factory=time.time)
    committed: bool = False
    refunded: bool = False


# ---------------------------------------------------------------------------
# Cycle validation result
# ---------------------------------------------------------------------------

@dataclass
class CycleValidation:
    should_continue: bool
    trust_delta: float
    reason: str


# ---------------------------------------------------------------------------
# Main governance hooks
# ---------------------------------------------------------------------------

class GovernanceHooks:
    """Integration hooks for nexusalpha governance."""

    def __init__(self, strict: bool = True, token_budget: int = 100_000) -> None:
        self.strict = strict
        self._audit_log: list[AuditEntry] = []
        self._token_budget: int = token_budget
        self._tokens_used: int = 0
        self._governor = None
        self._lock = threading.Lock()

        # Reservation lifecycle
        self._reservations: dict[str, _TokenReservation] = {}
        self._reserved_total: int = 0  # sum of active (not committed/refunded) reservations

        # Per-agent budgets
        self._agent_budgets: dict[str, dict[str, int]] = {}  # agent_id -> {total, used}

        try:
            from nexus25._governor_bridge import load_governor
            self._governor = load_governor()
        except (ImportError, Exception):
            pass

    # -----------------------------------------------------------------------
    # Tool access
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Token budget (legacy API — still works)
    # -----------------------------------------------------------------------

    def check_token_budget(self, tokens_requested: int) -> GovernanceDecision:
        with self._lock:
            remaining = self._token_budget - self._tokens_used - self._reserved_total
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

    # -----------------------------------------------------------------------
    # Token reservation lifecycle
    # -----------------------------------------------------------------------

    def reserve_tokens(self, agent_id: str, tokens: int, operation: str = "") -> str:
        """Reserve tokens before execution. Returns reservation_id.

        Raises ``ValueError`` if insufficient budget.
        """
        if tokens <= 0:
            raise ValueError(f"tokens must be positive, got {tokens}")

        with self._lock:
            remaining = self._token_budget - self._tokens_used - self._reserved_total
            if tokens > remaining:
                raise ValueError(
                    f"Cannot reserve {tokens} tokens — only {remaining} remaining "
                    f"(budget={self._token_budget}, used={self._tokens_used}, "
                    f"reserved={self._reserved_total})"
                )
            reservation_id = f"RSV-{uuid.uuid4().hex[:12]}"
            rec = _TokenReservation(
                reservation_id=reservation_id,
                agent_id=agent_id,
                reserved=tokens,
                operation=operation,
            )
            self._reservations[reservation_id] = rec
            self._reserved_total += tokens

        self._record(
            action=f"token_reserve:{tokens}",
            actor=agent_id,
            decision=DecisionType.ALLOWED,
            details={"reservation_id": reservation_id, "tokens": tokens, "operation": operation},
        )
        return reservation_id

    def commit_reservation(self, reservation_id: str, actual_tokens: int = 0) -> bool:
        """Commit a reservation after execution.

        If ``actual_tokens`` is provided and less than reserved, the difference is refunded.
        If ``actual_tokens`` is 0, the full reserved amount is treated as used.
        """
        with self._lock:
            rec = self._reservations.get(reservation_id)
            if rec is None:
                return False
            if rec.committed or rec.refunded:
                return False

            actual = actual_tokens if actual_tokens > 0 else rec.reserved
            rec.actual = min(actual, rec.reserved)
            rec.committed = True

            # Move reserved tokens to used
            self._tokens_used += rec.actual
            self._reserved_total -= rec.reserved

            # Refund the difference
            refund = rec.reserved - rec.actual
            # (refund is implicit — reserved_total decreased by full amount,
            #  but tokens_used only increased by actual)

        self._record(
            action=f"token_commit:{rec.actual}",
            actor=rec.agent_id,
            decision=DecisionType.ALLOWED,
            details={
                "reservation_id": reservation_id,
                "reserved": rec.reserved,
                "actual": rec.actual,
                "refunded": refund,
            },
        )

        # Also update agent-level budget tracking
        with self._lock:
            ab = self._agent_budgets.get(rec.agent_id)
            if ab is None:
                ab = {"total": self._token_budget, "used": rec.actual}
                self._agent_budgets[rec.agent_id] = ab
            else:
                ab["used"] += rec.actual

        return True

    def refund_reservation(self, reservation_id: str) -> bool:
        """Cancel a reservation and refund the full reserved amount."""
        with self._lock:
            rec = self._reservations.get(reservation_id)
            if rec is None:
                return False
            if rec.committed or rec.refunded:
                return False

            rec.refunded = True
            self._reserved_total -= rec.reserved

        self._record(
            action=f"token_refund:{rec.reserved}",
            actor=rec.agent_id,
            decision=DecisionType.ALLOWED,
            details={"reservation_id": reservation_id, "refunded": rec.reserved},
        )
        return True

    def get_agent_budget_status(self, agent_id: str) -> dict[str, Any]:
        """Get budget status for a specific agent.

        Returns ``{total, used, remaining, reservations_active, percentage}``.
        """
        with self._lock:
            ab = self._agent_budgets.get(agent_id)
            if ab is None:
                total = self._token_budget
                used = 0
            else:
                total = ab.get("total", self._token_budget)
                used = ab.get("used", 0)

            # Count active reservations for this agent
            active_reservations = sum(
                r.reserved for r in self._reservations.values()
                if r.agent_id == agent_id and not r.committed and not r.refunded
            )

            remaining = max(0, total - used - active_reservations)
            pct = round((used / total * 100), 2) if total > 0 else 0.0

        return {
            "total": total,
            "used": used,
            "remaining": remaining,
            "reservations_active": active_reservations,
            "percentage": pct,
        }

    def set_agent_budget(self, agent_id: str, budget: int) -> None:
        """Set a per-agent token budget."""
        with self._lock:
            existing = self._agent_budgets.get(agent_id, {"total": 0, "used": 0})
            existing["total"] = budget
            self._agent_budgets[agent_id] = existing

    # -----------------------------------------------------------------------
    # Cycle validation
    # -----------------------------------------------------------------------

    def check_cycle_validation(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Check if an agent's work cycle was productive.

        Args:
            metrics: Expected keys (all optional, default False/0):
                - files_changed (bool): did files change?
                - tests_passed (bool): did tests pass?
                - memory_entries_created (int): how many memory entries were created?
                - errors_encountered (int): how many errors occurred?
                - trust_score (float): current agent trust score (0-1)

        Returns:
            ``{should_continue: bool, trust_delta: float, reason: str}``
        """
        files_changed = metrics.get("files_changed", False)
        tests_passed = metrics.get("tests_passed", False)
        memory_entries = metrics.get("memory_entries_created", 0)
        errors = metrics.get("errors_encountered", 0)
        trust_score = metrics.get("trust_score", 0.5)

        reasons: list[str] = []
        should_continue = True
        trust_delta = 0.0

        # Positive signals
        positive = 0
        if files_changed:
            positive += 1
            reasons.append("files changed")
        if tests_passed:
            positive += 2
            reasons.append("tests passed")
        if memory_entries > 0:
            positive += 1
            reasons.append(f"{memory_entries} memory entries created")

        # Negative signals
        negative = 0
        if errors > 0:
            negative += errors
            reasons.append(f"{errors} errors encountered")
        if not files_changed and memory_entries == 0:
            negative += 1
            reasons.append("no observable output")

        # Compute trust delta
        trust_delta = (positive * 0.05) - (negative * 0.08)
        trust_delta = max(-0.3, min(0.3, trust_delta))

        # Decision logic
        if negative >= 3 and positive == 0:
            should_continue = False
            reasons.append("too many failures with no productive output")
        elif trust_score + trust_delta < 0.1:
            should_continue = False
            reasons.append("trust score would drop below minimum threshold")
        elif positive == 0 and negative == 0:
            # No signal at all — cautious continue but negative delta
            trust_delta = -0.02
            reasons.append("no observable activity (mild penalty)")

        self._record(
            action="cycle_validation",
            actor=metrics.get("agent_id", "agent"),
            decision=DecisionType.ALLOWED if should_continue else DecisionType.DENIED,
            details={"trust_delta": trust_delta, "reasons": reasons},
        )

        return {
            "should_continue": should_continue,
            "trust_delta": round(trust_delta, 4),
            "reason": "; ".join(reasons) if reasons else "no signals",
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _record(self, action: str, actor: str, decision: DecisionType,
                details: dict[str, Any] | None = None) -> None:
        with self._lock:
            parent = self._audit_log[-1].entry_hash if self._audit_log else ""
            entry = AuditEntry(
                timestamp=time.time(), action=action, actor=actor,
                decision=decision, details=details or {}, parent_hash=parent,
            )
            self._audit_log.append(entry)

    @property
    def audit_log(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._audit_log)

    @property
    def tokens_remaining(self) -> int:
        with self._lock:
            return max(0, self._token_budget - self._tokens_used - self._reserved_total)

    def set_token_budget(self, budget: int) -> None:
        with self._lock:
            self._token_budget = budget

    def close(self) -> None:
        pass

    def __enter__(self) -> "GovernanceHooks":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
