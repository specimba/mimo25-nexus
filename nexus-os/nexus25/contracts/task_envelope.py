"""Task envelope contract — Mythos-recommended high-capability task schema."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskOutputContract:
    artifacts: list[str] = field(default_factory=lambda: ["output"])
    canonical_write: bool = False
    requires_verification: bool = True
    max_tokens: int = 32_000
    timeout_seconds: int = 600


@dataclass
class TaskEnvelope:
    task_id: str = field(default_factory=lambda: f"TASK-{uuid.uuid4().hex[:12]}")
    project_id: str = "nexus-unified"
    lane: str = "general"
    provider_class: str = "local"
    sandbox_profile: str = ""
    approval_id: str = ""
    trust_min: str = "standard"
    requires_open_shell: bool = False
    a2a_agent_card_url: str = ""
    brief: str = ""
    input_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    output: TaskOutputContract = field(default_factory=TaskOutputContract)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_high_capability(self) -> bool:
        high_cap = {"mythos_preview", "claude_opus", "gpt4"}
        return self.provider_class in high_cap

    def validate(self) -> list[str]:
        violations = []
        if self.is_high_capability():
            if not self.approval_id:
                violations.append("High-capability task requires approval_id")
            if not self.sandbox_profile:
                violations.append("High-capability task requires sandbox_profile")
            if self.output.canonical_write:
                violations.append("High-capability tasks cannot have canonical_write=True")
        return violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "lane": self.lane,
            "provider_class": self.provider_class,
            "sandbox_profile": self.sandbox_profile,
            "approval_id": self.approval_id,
            "trust_min": self.trust_min,
            "requires_open_shell": self.requires_open_shell,
            "inputs": {
                "brief": self.brief,
                "input_refs": self.input_refs,
                "evidence_refs": self.evidence_refs,
            },
            "output_contract": {
                "artifacts": self.output.artifacts,
                "canonical_write": self.output.canonical_write,
                "requires_verification": self.output.requires_verification,
                "max_tokens": self.output.max_tokens,
            },
            "metadata": self.metadata,
        }
