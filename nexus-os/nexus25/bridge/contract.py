"""NEXUS Bridge Contract — Thin API surface for external integration.

Three stable operations:
  nexus.submit_task(task_packet, sandbox_identity, authority_scope) -> proposal_id
  nexus.status(proposal_id) -> state, runtime, audit_refs
  nexus.audit_query(filters) -> redacted audit events

All requests carry authority scope. Governor/KAIJU can deny before runtime execution.
Tool and runtime outputs get redacted before external display.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from nexus25.contracts.task_envelope import TaskEnvelope, TaskOutputContract
from nexus25.governance.vap_chain import VAPChain
from nexus25.governance.archivist import (
    Archivist,
    ArtifactFrontmatter,
    AuthorityScope,
    PromotionState,
)


# ---------------------------------------------------------------------------
# Authority scope validation
# ---------------------------------------------------------------------------

VALID_AUTHORITY_SCOPES = {"standard", "elevated", "governed"}


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


# ---------------------------------------------------------------------------
# Proposal record stored in-memory
# ---------------------------------------------------------------------------

@dataclass
class _ProposalRecord:
    proposal_id: str
    task_envelope: TaskEnvelope
    sandbox_identity: str
    authority_scope: str
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: str = ""
    vap_refs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

# Patterns that look like secrets, tokens, API keys, or sensitive paths
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|auth)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(sk|pk|rk)[-_][A-Za-z0-9]{20,}"),
    re.compile(r"/home/\w+|/Users/\w+|/root/\w+"),
    re.compile(r"(?i)ssh-rsa\s+[A-Za-z0-9+/=]+"),
]


def _redact_value(value: Any) -> Any:
    """Redact a single value if it looks sensitive."""
    if not isinstance(value, str):
        return value
    for pat in _SENSITIVE_PATTERNS:
        value = pat.sub("[REDACTED]", value)
    return value


def _redact_dict(obj: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive fields in a dict."""
    redacted: dict[str, Any] = {}
    for k, v in obj.items():
        kl = k.lower()
        # Entirely drop fields whose key names are inherently sensitive
        if kl in {"api_key", "apikey", "token", "secret", "password", "auth_token",
                   "private_key", "access_token", "refresh_token"}:
            redacted[k] = "[REDACTED]"
            continue
        if isinstance(v, dict):
            redacted[k] = _redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [_redact_value(i) if isinstance(i, str) else i for i in v]
        else:
            redacted[k] = _redact_value(v)
    return redacted


# ---------------------------------------------------------------------------
# Bridge contract
# ---------------------------------------------------------------------------

class BridgeContract:
    """Thin API surface for external systems (Hermes, swarm pack) to interact with NEXUS."""

    def __init__(
        self,
        vap_chain: Optional[VAPChain] = None,
        archivist: Optional[Archivist] = None,
    ) -> None:
        self._vap = vap_chain or VAPChain()
        self._archivist = archivist or Archivist()
        self._proposals: dict[str, _ProposalRecord] = {}

    # -----------------------------------------------------------------------
    # submit_task
    # -----------------------------------------------------------------------

    def submit_task(
        self,
        task_packet: dict[str, Any],
        sandbox_identity: str = "",
        authority_scope: str = "standard",
    ) -> dict[str, Any]:
        """Submit a task for governed execution.

        Returns ``{"proposal_id": ..., "state": ...}`` on success.
        Raises ``ValueError`` on validation failures.
        """
        # 1. Validate authority scope
        if authority_scope not in VALID_AUTHORITY_SCOPES:
            raise ValueError(
                f"Invalid authority_scope '{authority_scope}'. "
                f"Must be one of: {', '.join(sorted(VALID_AUTHORITY_SCOPES))}"
            )

        # 2. Build TaskEnvelope from the packet
        output_cfg = task_packet.get("output", {})
        envelope = TaskEnvelope(
            project_id=task_packet.get("project_id", "nexus-unified"),
            lane=task_packet.get("lane", "general"),
            provider_class=task_packet.get("provider_class", "local"),
            sandbox_profile=task_packet.get("sandbox_profile", sandbox_identity),
            approval_id=task_packet.get("approval_id", ""),
            trust_min=task_packet.get("trust_min", authority_scope),
            requires_open_shell=task_packet.get("requires_open_shell", False),
            brief=task_packet.get("brief", ""),
            input_refs=task_packet.get("input_refs", []),
            evidence_refs=task_packet.get("evidence_refs", []),
            output=TaskOutputContract(
                artifacts=output_cfg.get("artifacts", ["output"]),
                canonical_write=output_cfg.get("canonical_write", False),
                requires_verification=output_cfg.get("requires_verification", True),
                max_tokens=output_cfg.get("max_tokens", 32_000),
                timeout_seconds=output_cfg.get("timeout_seconds", 600),
            ),
            metadata=task_packet.get("metadata", {}),
        )

        # Validate envelope (high-cap checks, etc.)
        violations = envelope.validate()
        if violations:
            raise ValueError(f"TaskEnvelope validation failed: {'; '.join(violations)}")

        # 3. Register artifact with Archivist
        import hashlib
        policy_hash = hashlib.sha256(
            f"{envelope.task_id}:{authority_scope}:{sandbox_identity}".encode()
        ).hexdigest()[:32]
        fm = ArtifactFrontmatter(
            id=envelope.task_id,
            type="Task_Result",
            sandbox_profile=sandbox_identity or "bridge-default",
            provider_class=envelope.provider_class,
            approval_id=envelope.approval_id,
            policy_hash=policy_hash,
            promotion_state=PromotionState.RAW,
        )
        ok, arch_violations = self._archivist.register(fm)
        if not ok:
            msgs = "; ".join(v.message for v in arch_violations)
            raise ValueError(f"Archivist rejected task: {msgs}")

        # 4. Record proposal
        proposal_id = f"PROP-{uuid.uuid4().hex[:12]}"
        record = _ProposalRecord(
            proposal_id=proposal_id,
            task_envelope=envelope,
            sandbox_identity=sandbox_identity,
            authority_scope=authority_scope,
        )
        self._proposals[proposal_id] = record

        # 5. Audit log
        vap_entry = self._vap.append(
            action="submit_task",
            actor=sandbox_identity or "bridge",
            decision="allowed",
            details={
                "proposal_id": proposal_id,
                "task_id": envelope.task_id,
                "authority_scope": authority_scope,
                "lane": envelope.lane,
            },
        )
        record.vap_refs.append(vap_entry.entry_hash)

        return {"proposal_id": proposal_id, "state": record.state.value}

    # -----------------------------------------------------------------------
    # status
    # -----------------------------------------------------------------------

    def status(self, proposal_id: str) -> dict[str, Any]:
        """Check task status.

        Returns ``{state, runtime, audit_refs}`` on success.
        Raises ``KeyError`` if the proposal does not exist.
        """
        record = self._proposals.get(proposal_id)
        if record is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")

        runtime_info: dict[str, Any] = {
            "task_id": record.task_envelope.task_id,
            "lane": record.task_envelope.lane,
            "provider_class": record.task_envelope.provider_class,
            "sandbox_identity": record.sandbox_identity,
            "authority_scope": record.authority_scope,
            "created_at": record.created_at,
        }
        if record.completed_at is not None:
            runtime_info["completed_at"] = record.completed_at
        if record.error:
            runtime_info["error"] = record.error

        return {
            "proposal_id": proposal_id,
            "state": record.state.value,
            "runtime": runtime_info,
            "audit_refs": list(record.vap_refs),
        }

    # -----------------------------------------------------------------------
    # audit_query
    # -----------------------------------------------------------------------

    def audit_query(self, filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Query the VAP audit trail with automatic redaction of sensitive fields.

        Supported filters (all optional):
          - ``actor``: exact match on actor
          - ``action``: substring match on action
          - ``since``: only entries with timestamp >= since
          - ``proposal_id``: match proposal_id in details
        """
        entries = self._vap.export()

        if filters:
            if "actor" in filters:
                entries = [e for e in entries if e["actor"] == filters["actor"]]
            if "action" in filters:
                entries = [e for e in entries if filters["action"] in e["action"]]
            if "since" in filters:
                entries = [e for e in entries if e["timestamp"] >= filters["since"]]
            if "proposal_id" in filters:
                pid = filters["proposal_id"]
                entries = [e for e in entries if e.get("details", {}).get("proposal_id") == pid]

        return [_redact_dict(e) for e in entries]

    # -----------------------------------------------------------------------
    # Helpers for state management (used by orchestration layer)
    # -----------------------------------------------------------------------

    def update_state(self, proposal_id: str, state: TaskState, error: str = "") -> None:
        """Update the state of a proposal. Used by the orchestration layer."""
        record = self._proposals.get(proposal_id)
        if record is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")
        record.state = state
        if state in (TaskState.COMPLETED, TaskState.FAILED):
            record.completed_at = time.time()
        if error:
            record.error = error
        # Audit the transition
        vap_entry = self._vap.append(
            action=f"state_change:{state.value}",
            actor="bridge",
            decision="allowed",
            details={"proposal_id": proposal_id, "error": error} if error else {"proposal_id": proposal_id},
        )
        record.vap_refs.append(vap_entry.entry_hash)

    @property
    def vap_chain(self) -> VAPChain:
        return self._vap

    @property
    def archivist(self) -> Archivist:
        return self._archivist
