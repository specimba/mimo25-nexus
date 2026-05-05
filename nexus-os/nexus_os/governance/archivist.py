"""Archivist integrity gate — Mythos-recommended artifact validation."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AuthorityScope(str, Enum):
    CANONICAL = "canonical"
    EXTERNAL_EVIDENCE = "external_evidence"
    CACHE_ONLY = "cache_only"


class PromotionState(str, Enum):
    RAW = "raw"
    PROPOSAL = "proposal"
    REVIEWED = "reviewed"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class CacheClass(str, Enum):
    AUTHORITATIVE = "authoritative"
    AUTHORITATIVE_EXTERNAL = "authoritative-external-evidence"
    RETRIEVAL = "retrieval-only"
    EPHEMERAL = "ephemeral"


@dataclass
class ArtifactFrontmatter:
    id: str
    type: str
    truth_layer: str = "EXTRACTED"
    authority_scope: AuthorityScope = AuthorityScope.CANONICAL
    provider_class: str = "local"
    source_uri: str = ""
    source_sha256: str = ""
    canonical_ref: str = ""
    created: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    verified: bool = False
    confidence: float = 0.0
    policy_hash: str = ""
    sandbox_profile: str = ""
    ocsf_log_ref: str = ""
    approval_id: str = ""
    cache_class: CacheClass = CacheClass.AUTHORITATIVE
    promotion_state: PromotionState = PromotionState.RAW


@dataclass
class ValidationViolation:
    rule: str
    message: str
    severity: str = "error"


class IntegrityGate:
    HIGH_CAPABILITY_PROVIDERS = {"mythos_preview", "claude_opus", "gpt4"}

    def validate(self, fm: ArtifactFrontmatter) -> list[ValidationViolation]:
        violations: list[ValidationViolation] = []
        if not isinstance(fm.authority_scope, AuthorityScope):
            violations.append(ValidationViolation(
                "authority_scope_required",
                "authority_scope must be a valid AuthorityScope enum value",
            ))
        if fm.authority_scope == AuthorityScope.EXTERNAL_EVIDENCE and fm.provider_class == "local":
            violations.append(ValidationViolation(
                "provider_class_required",
                "External evidence must specify a non-local provider_class",
            ))
        if fm.type in ("Execution_Result", "Task_Result", "Tool_Output"):
            if not fm.policy_hash:
                violations.append(ValidationViolation(
                    "policy_hash_required",
                    f"Execution artifacts of type '{fm.type}' require policy_hash",
                ))
            if not fm.sandbox_profile:
                violations.append(ValidationViolation(
                    "sandbox_profile_required",
                    f"Execution artifacts of type '{fm.type}' require sandbox_profile",
                ))
        if fm.provider_class in self.HIGH_CAPABILITY_PROVIDERS and not fm.approval_id:
            violations.append(ValidationViolation(
                "approval_id_required",
                f"High-capability provider '{fm.provider_class}' requires approval_id",
            ))
        if (fm.cache_class in (CacheClass.RETRIEVAL, CacheClass.EPHEMERAL)
                and fm.promotion_state == PromotionState.PROMOTED):
            violations.append(ValidationViolation(
                "illegal_promotion",
                "Cannot promote directly from cache/retrieval to promoted state",
                severity="error",
            ))
        return violations

    def is_valid(self, fm: ArtifactFrontmatter) -> bool:
        return len(self.validate(fm)) == 0


class Archivist:
    def __init__(self) -> None:
        self._gate = IntegrityGate()
        self._artifacts: dict[str, ArtifactFrontmatter] = {}

    def register(self, fm: ArtifactFrontmatter) -> tuple[bool, list[ValidationViolation]]:
        violations = self._gate.validate(fm)
        if any(v.severity == "error" for v in violations):
            return False, violations
        self._artifacts[fm.id] = fm
        return True, violations

    def promote(self, artifact_id: str, to_state: PromotionState) -> tuple[bool, str]:
        fm = self._artifacts.get(artifact_id)
        if not fm:
            return False, f"Unknown artifact: {artifact_id}"
        valid_transitions = {
            PromotionState.RAW: {PromotionState.PROPOSAL, PromotionState.REJECTED},
            PromotionState.PROPOSAL: {PromotionState.REVIEWED, PromotionState.REJECTED},
            PromotionState.REVIEWED: {PromotionState.PROMOTED, PromotionState.REJECTED},
            PromotionState.PROMOTED: set(),
            PromotionState.REJECTED: {PromotionState.RAW},
        }
        allowed = valid_transitions.get(fm.promotion_state, set())
        if to_state not in allowed:
            return False, f"Invalid transition: {fm.promotion_state.value} -> {to_state.value}"
        fm.promotion_state = to_state
        return True, f"Promoted to {to_state.value}"

    def get(self, artifact_id: str) -> Optional[ArtifactFrontmatter]:
        return self._artifacts.get(artifact_id)

    def list_by_state(self, state: PromotionState) -> list[ArtifactFrontmatter]:
        return [fm for fm in self._artifacts.values() if fm.promotion_state == state]

    def list_by_provider(self, provider_class: str) -> list[ArtifactFrontmatter]:
        return [fm for fm in self._artifacts.values() if fm.provider_class == provider_class]

    @property
    def gate(self) -> IntegrityGate:
        return self._gate
