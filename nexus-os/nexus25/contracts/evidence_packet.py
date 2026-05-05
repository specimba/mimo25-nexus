"""Evidence packet contract — Mythos-recommended evidence schema."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..governance.archivist import ArtifactFrontmatter, AuthorityScope, PromotionState, CacheClass


@dataclass
class EvidenceClaim:
    claim_id: str = field(default_factory=lambda: f"CLM-{uuid.uuid4().hex[:6]}")
    text: str = ""
    claim_type: str = "general"
    confidence: float = 0.0
    requires_human_review: bool = False


@dataclass
class EvidenceSource:
    kind: str = "unknown"
    uri: str = ""
    sha256: str = ""


@dataclass
class EvidencePacket:
    evidence_id: str = field(default_factory=lambda: f"EVID-{uuid.uuid4().hex[:12]}")
    source_kind: str = "external_model_run"
    provider_class: str = "local"
    sandbox_profile: str = ""
    policy_hash: str = ""
    ocsf_log_uri: str = ""
    approval_id: str = ""
    claims: list[EvidenceClaim] = field(default_factory=list)
    sources: list[EvidenceSource] = field(default_factory=list)
    promotion_state: PromotionState = PromotionState.PROPOSAL
    canonical_ref: str = ""

    def to_frontmatter(self) -> ArtifactFrontmatter:
        return ArtifactFrontmatter(
            id=self.evidence_id,
            type="Evidence_Packet",
            truth_layer="EXTRACTED",
            authority_scope=(
                AuthorityScope.EXTERNAL_EVIDENCE
                if self.provider_class != "local"
                else AuthorityScope.CANONICAL
            ),
            provider_class=self.provider_class,
            source_uri=self.sources[0].uri if self.sources else "",
            source_sha256=self.sources[0].sha256 if self.sources else "",
            canonical_ref=self.canonical_ref,
            verified=False,
            confidence=max((c.confidence for c in self.claims), default=0.0),
            policy_hash=self.policy_hash,
            sandbox_profile=self.sandbox_profile,
            ocsf_log_ref=self.ocsf_log_uri,
            approval_id=self.approval_id,
            cache_class=(
                CacheClass.AUTHORITATIVE_EXTERNAL
                if self.provider_class != "local"
                else CacheClass.AUTHORITATIVE
            ),
            promotion_state=self.promotion_state,
        )

    def content_hash(self) -> str:
        content = json.dumps({
            "evidence_id": self.evidence_id,
            "claims": [{"text": c.text, "type": c.claim_type} for c in self.claims],
            "sources": [{"kind": s.kind, "uri": s.uri} for s in self.sources],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
