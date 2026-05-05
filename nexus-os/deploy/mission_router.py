"""
mission_router.py — Nexus Mission Routing Protocol

Parses nexus-mission blocks and routes them to appropriate handlers
based on mode, task shape, and agent capabilities.

Format:
  /--- nexus-mission
  name: <mission name>
  mode: research|design|implementation|verification|hygiene
  scope: <description>
  evidence: <what we know>
  skills: <required skills>
  agents: <target agents>
  deliverable: <expected output>
  safety: <safety constraints>
  constraints: <additional constraints>
  verification: <how to verify>
  /---
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────
class MissionMode(str, Enum):
    RESEARCH = "research"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    HYGIENE = "hygiene"


class TaskShape(str, Enum):
    OPEN_ENDED = "open_ended"        # research, exploration
    STRUCTURED = "structured"         # clear spec, implementation
    CREATIVE = "creative"             # design, brainstorming
    ANALYTICAL = "analytical"         # audit, review, verification
    MAINTENANCE = "maintenance"       # cleanup, hygiene, refactoring


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class MissionBlock:
    """Parsed nexus-mission block."""
    name: str = ""
    mode: str = ""
    scope: str = ""
    evidence: str = ""
    skills: str = ""
    agents: str = ""
    deliverable: str = ""
    safety: str = ""
    constraints: str = ""
    verification: str = ""
    raw: str = ""

    @property
    def mode_enum(self) -> Optional[MissionMode]:
        try:
            return MissionMode(self.mode.lower().strip())
        except ValueError:
            return None

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "mode": self.mode,
            "scope": self.scope,
            "evidence": self.evidence,
            "skills": self.skills,
            "agents": self.agents,
            "deliverable": self.deliverable,
            "safety": self.safety,
            "constraints": self.constraints,
            "verification": self.verification,
        }


@dataclass
class RoutingDecision:
    """Result of routing a mission."""
    mode: MissionMode
    handler: str
    agents: List[str]
    verification_method: str
    priority: int  # 1=highest
    notes: str = ""


@dataclass
class HandlerResult:
    """Result returned by a handler."""
    success: bool
    output: str
    artifacts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ── Parser ───────────────────────────────────────────────────────────────────
MISSION_BLOCK_RE = re.compile(
    r"/---\s*nexus-mission\s*\n(.*?)/---",
    re.DOTALL | re.IGNORECASE,
)

FIELD_RE = re.compile(r"^\s*(\w+)\s*:\s*(.+)$", re.MULTILINE)


def parse_mission_blocks(text: str) -> List[MissionBlock]:
    """Extract all nexus-mission blocks from text."""
    blocks: List[MissionBlock] = []

    for match in MISSION_BLOCK_RE.finditer(text):
        raw_block = match.group(1)
        block = MissionBlock(raw=match.group(0))

        for field_match in FIELD_RE.finditer(raw_block):
            key = field_match.group(1).lower().strip()
            value = field_match.group(2).strip()
            if hasattr(block, key):
                setattr(block, key, value)

        blocks.append(block)

    return blocks


# ── Selection Matrix ─────────────────────────────────────────────────────────
# Maps task shape → preferred mode → agents → verification
SELECTION_MATRIX: Dict[TaskShape, Dict[str, Any]] = {
    TaskShape.OPEN_ENDED: {
        "mode": MissionMode.RESEARCH,
        "agents": ["researcher", "analyst"],
        "verification": "peer_review",
        "priority": 3,
    },
    TaskShape.STRUCTURED: {
        "mode": MissionMode.IMPLEMENTATION,
        "agents": ["engineer", "coder"],
        "verification": "test_suite",
        "priority": 2,
    },
    TaskShape.CREATIVE: {
        "mode": MissionMode.DESIGN,
        "agents": ["designer", "architect"],
        "verification": "design_review",
        "priority": 2,
    },
    TaskShape.ANALYTICAL: {
        "mode": MissionMode.VERIFICATION,
        "agents": ["auditor", "reviewer"],
        "verification": "checklist",
        "priority": 1,
    },
    TaskShape.MAINTENANCE: {
        "mode": MissionMode.HYGIENE,
        "agents": ["maintainer", "engineer"],
        "verification": "ci_pipeline",
        "priority": 4,
    },
}

# Mode → default handler function name
MODE_HANDLERS: Dict[MissionMode, str] = {
    MissionMode.RESEARCH: "handle_research",
    MissionMode.DESIGN: "handle_design",
    MissionMode.IMPLEMENTATION: "handle_implementation",
    MissionMode.VERIFICATION: "handle_verification",
    MissionMode.HYGIENE: "handle_hygiene",
}


# ── Router ───────────────────────────────────────────────────────────────────
def infer_task_shape(mission: MissionBlock) -> TaskShape:
    """Infer task shape from mission fields."""
    mode = mission.mode.lower()

    if mode in ("research", "explore", "investigate"):
        return TaskShape.OPEN_ENDED
    if mode in ("design", "architect", "plan"):
        return TaskShape.CREATIVE
    if mode in ("implementation", "build", "code", "deploy"):
        return TaskShape.STRUCTURED
    if mode in ("verification", "audit", "review", "test"):
        return TaskShape.ANALYTICAL
    if mode in ("hygiene", "cleanup", "refactor", "maintenance"):
        return TaskShape.MAINTENANCE

    # Fallback: infer from scope/deliverable keywords
    scope = (mission.scope + " " + mission.deliverable).lower()
    if any(w in scope for w in ("research", "analyze", "investigate", "compare")):
        return TaskShape.OPEN_ENDED
    if any(w in scope for w in ("design", "mockup", "wireframe", "architecture")):
        return TaskShape.CREATIVE
    if any(w in scope for w in ("build", "implement", "code", "deploy", "fix")):
        return TaskShape.STRUCTURED
    if any(w in scope for w in ("audit", "review", "verify", "test", "check")):
        return TaskShape.ANALYTICAL
    if any(w in scope for w in ("clean", "refactor", "migrate", "update")):
        return TaskShape.MAINTENANCE

    return TaskShape.STRUCTURED  # safe default


def route_mission(mission: MissionBlock) -> RoutingDecision:
    """Route a mission to appropriate handler based on mode/shape."""
    mode = mission.mode_enum

    if mode is not None:
        # Direct mode match
        shape = infer_task_shape(mission)
        matrix = SELECTION_MATRIX[shape]
        handler = MODE_HANDLERS.get(mode, "handle_generic")

        # Use agents from mission if specified, else from matrix
        agents = (
            [a.strip() for a in mission.agents.split(",")]
            if mission.agents
            else matrix["agents"]
        )

        return RoutingDecision(
            mode=mode,
            handler=handler,
            agents=agents,
            verification_method=mission.verification or matrix["verification"],
            priority=matrix["priority"],
            notes=f"Direct mode match: {mode.value}",
        )

    # No explicit mode — infer from shape
    shape = infer_task_shape(mission)
    matrix = SELECTION_MATRIX[shape]

    agents = (
        [a.strip() for a in mission.agents.split(",")]
        if mission.agents
        else matrix["agents"]
    )

    return RoutingDecision(
        mode=matrix["mode"],
        handler=MODE_HANDLERS[matrix["mode"]],
        agents=agents,
        verification_method=mission.verification or matrix["verification"],
        priority=matrix["priority"],
        notes=f"Inferred from task shape: {shape.value}",
    )


# ── Handler stubs ────────────────────────────────────────────────────────────
def handle_research(mission: MissionBlock) -> HandlerResult:
    """Handler for research-mode missions."""
    return HandlerResult(
        success=True,
        output=f"Research mission '{mission.name}': investigating {mission.scope}",
    )


def handle_design(mission: MissionBlock) -> HandlerResult:
    """Handler for design-mode missions."""
    return HandlerResult(
        success=True,
        output=f"Design mission '{mission.name}': creating {mission.deliverable}",
    )


def handle_implementation(mission: MissionBlock) -> HandlerResult:
    """Handler for implementation-mode missions."""
    return HandlerResult(
        success=True,
        output=f"Implementation mission '{mission.name}': building {mission.scope}",
    )


def handle_verification(mission: MissionBlock) -> HandlerResult:
    """Handler for verification-mode missions."""
    return HandlerResult(
        success=True,
        output=f"Verification mission '{mission.name}': verifying {mission.scope}",
    )


def handle_hygiene(mission: MissionBlock) -> HandlerResult:
    """Handler for hygiene-mode missions."""
    return HandlerResult(
        success=True,
        output=f"Hygiene mission '{mission.name}': cleaning up {mission.scope}",
    )


def handle_generic(mission: MissionBlock) -> HandlerResult:
    """Fallback handler."""
    return HandlerResult(
        success=True,
        output=f"Generic handler for '{mission.name}' (mode={mission.mode})",
    )


HANDLER_MAP: Dict[str, Callable[[MissionBlock], HandlerResult]] = {
    "handle_research": handle_research,
    "handle_design": handle_design,
    "handle_implementation": handle_implementation,
    "handle_verification": handle_verification,
    "handle_hygiene": handle_hygiene,
    "handle_generic": handle_generic,
}


def execute_mission(mission: MissionBlock) -> HandlerResult:
    """Route and execute a mission."""
    decision = route_mission(mission)
    handler_fn = HANDLER_MAP.get(decision.handler, handle_generic)
    result = handler_fn(mission)
    result.output += f"\n  [routing: {decision.notes}, agents: {decision.agents}]"
    return result


# ── CLI demo ─────────────────────────────────────────────────────────────────
def main() -> None:
    demo_text = """
    /--- nexus-mission
    name: Audit Zilliz Integration
    mode: verification
    scope: Check dual-cluster connectivity and embedding storage
    evidence: zilliz_client.py exists, env vars documented
    skills: python, milvus, zilliz
    agents: auditor, engineer
    deliverable: Health report with pass/fail per cluster
    safety: Read-only, no destructive operations
    constraints: Must complete within 5 minutes
    verification: Run health_check() and similar_search() smoke test
    /---

    /--- nexus-mission
    name: Design Mission Router
    mode: design
    scope: Create routing protocol for nexus missions
    evidence: Mission format spec exists
    skills: python, architecture
    deliverable: mission_router.py with selection matrix
    safety: No external dependencies beyond stdlib
    verification: Parse test blocks and verify routing decisions
    /---
    """

    blocks = parse_mission_blocks(demo_text)
    print(f"Found {len(blocks)} mission block(s)\n")

    for block in blocks:
        decision = route_mission(block)
        result = execute_mission(block)

        print(f"═══ {block.name} ═══")
        print(f"  Mode       : {decision.mode.value}")
        print(f"  Handler    : {decision.handler}")
        print(f"  Agents     : {decision.agents}")
        print(f"  Verify     : {decision.verification_method}")
        print(f"  Priority   : {decision.priority}")
        print(f"  Result     : {result.output}")
        print()


if __name__ == "__main__":
    main()
