"""Graph-based workflow engine — DAG orchestration with checkpoints.

Inspired by agent-framework's graph-based orchestration and nexusalpha's
Swarm layer (Foreman → Worker → Task → Bid).

Key concepts:
- NodeType: AGENT, FUNCTION, CHECKPOINT, FORK, JOIN
- WorkflowNode: A unit of work (agent call, function, or checkpoint)
- WorkflowEdge: Data flow connection between nodes with data_key
- Workflow: A DAG of nodes and edges with dependency/dependent queries
- WorkflowEngine: Executes workflows with checkpointing and human-in-the-loop

From agent-framework: DAG topology, streaming, checkpointing, time-travel
From nexusalpha Swarm: P2b auction allocation, Foreman coordination
From hermes-agent: delegate_tool sub-agent spawning pattern
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NodeStatus(str, Enum):
    """Status of a workflow node (backward-compatible string enum)."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    SKIPPED = "skipped"


# Alias for the remote's naming
WorkflowState = NodeStatus


class NodeType(str, Enum):
    """Classification of workflow nodes."""
    AGENT = "agent"            # LLM agent call (hermes-agent AIAgent)
    FUNCTION = "function"      # Deterministic function (agent-framework)
    CHECKPOINT = "checkpoint"  # Human-in-the-loop pause point
    FORK = "fork"              # Parallel branch (Swarm Foreman pattern)
    JOIN = "join"              # Merge parallel branches


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WorkflowNode:
    """A single unit of work in the workflow DAG."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    node_type: NodeType = NodeType.FUNCTION
    handler: Optional[Callable[..., Any]] = None
    depends_on: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def state(self) -> NodeStatus:
        """Alias for status (remote naming)."""
        return self.status

    @state.setter
    def state(self, value: NodeStatus) -> None:
        self.status = value

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000, 2)
        return None


@dataclass
class WorkflowEdge:
    """Data flow connection between nodes with optional data_key mapping."""
    source_id: str
    target_id: str
    data_key: Optional[str] = None  # Key to pass from source result to target input


@dataclass
class WorkflowCheckpoint:
    """State snapshot for time-travel."""
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    workflow_id: str = ""
    timestamp: float = field(default_factory=time.time)
    node_states: dict[str, NodeStatus] = field(default_factory=dict)
    node_results: dict[str, Any] = field(default_factory=dict)


# Alias for the remote's naming
Checkpoint = WorkflowCheckpoint


# ---------------------------------------------------------------------------
# Workflow (DAG container)
# ---------------------------------------------------------------------------

class Workflow:
    """A directed acyclic graph of nodes and edges."""

    def __init__(self, name: str = "") -> None:
        self.id: str = str(uuid.uuid4())[:8]
        self.name: str = name
        self._nodes: dict[str, WorkflowNode] = {}
        self._edges: list[WorkflowEdge] = []
        self._checkpoints: list[WorkflowCheckpoint] = []
        self._execution_context: dict[str, Any] = {}

    # --- Node management ---

    def add_node(self, node: WorkflowNode) -> None:
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> dict[str, WorkflowNode]:
        return self._nodes

    # --- Edge management ---

    def add_edge(self, source_id: str, target_id: str, data_key: Optional[str] = None) -> None:
        """Add a data-flow edge between two nodes."""
        self._edges.append(WorkflowEdge(source_id, target_id, data_key))
        # Also maintain depends_on for backward compatibility
        target = self._nodes.get(target_id)
        if target and source_id not in target.depends_on:
            target.depends_on.append(source_id)

    @property
    def edges(self) -> list[WorkflowEdge]:
        return self._edges

    # --- Dependency queries ---

    def get_dependencies(self, node_id: str) -> list[str]:
        """Return node IDs that this node depends on (via edges)."""
        edge_deps = [e.source_id for e in self._edges if e.target_id == node_id]
        if edge_deps:
            return edge_deps
        # Fallback to depends_on field for backward compatibility
        node = self._nodes.get(node_id)
        return list(node.depends_on) if node else []

    def get_dependents(self, node_id: str) -> list[str]:
        """Return node IDs that depend on this node (via edges)."""
        return [e.target_id for e in self._edges if e.source_id == node_id]

    def get_ready_nodes(self) -> list[WorkflowNode]:
        """Nodes whose dependencies are all completed (DAG scheduling)."""
        ready = []
        for node in self._nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = self.get_dependencies(node.id)
            if all(
                dep in self._nodes and self._nodes[dep].status == NodeStatus.COMPLETED
                for dep in deps
            ):
                ready.append(node)
        return ready

    # Backward-compatible alias
    def ready_nodes(self) -> list[WorkflowNode]:
        return self.get_ready_nodes()

    def is_complete(self) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.FAILED)
            for n in self._nodes.values()
        )

    # --- Checkpoints (time-travel) ---

    def save_checkpoint(self) -> WorkflowCheckpoint:
        cp = WorkflowCheckpoint(
            workflow_id=self.id,
            node_states={nid: n.status for nid, n in self._nodes.items()},
            node_results={nid: n.result for nid, n in self._nodes.items()},
        )
        self._checkpoints.append(cp)
        return cp

    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore workflow state to a previous checkpoint by id. Returns True if found."""
        for cp in reversed(self._checkpoints):
            if cp.checkpoint_id == checkpoint_id:
                for nid, status in cp.node_states.items():
                    if nid in self._nodes:
                        self._nodes[nid].status = status
                        self._nodes[nid].result = cp.node_results.get(nid)
                        if status == NodeStatus.PENDING:
                            self._nodes[nid].started_at = None
                            self._nodes[nid].completed_at = None
                            self._nodes[nid].error = None
                return True
        return False

    def restore_checkpoint_by_index(self, index: int = -1) -> None:
        """Time-travel: restore workflow to a checkpoint by index."""
        if not self._checkpoints:
            return
        cp = self._checkpoints[index]
        for nid, status in cp.node_states.items():
            if nid in self._nodes:
                self._nodes[nid].status = status
                self._nodes[nid].result = cp.node_results.get(nid)
                if status == NodeStatus.PENDING:
                    self._nodes[nid].started_at = None
                    self._nodes[nid].completed_at = None
                    self._nodes[nid].error = None


# Backward-compatible alias
WorkflowGraph = Workflow


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """Executes workflows with DAG scheduling, checkpointing, and HITL.

    Supports two construction styles for backward compatibility:
        WorkflowEngine(graph)        — old API (pass a WorkflowGraph)
        WorkflowEngine()             — new API (use create_workflow / execute)
    """

    def __init__(self, graph: Optional[Workflow] = None) -> None:
        self.graph: Optional[Workflow] = graph
        self._paused_nodes: list[str] = []
        self._workflows: dict[str, Workflow] = {}
        if graph:
            self._workflows[graph.id] = graph

    # --- Factory ---

    def create_workflow(self, name: str = "") -> Workflow:
        wf = Workflow(name=name)
        self._workflows[wf.id] = wf
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    # --- Execution (new API) ---

    def execute(self, workflow: Optional[Workflow] = None, context: Optional[dict] = None) -> Workflow:
        """Run workflow to completion with DAG scheduling and edge-based data flow."""
        wf = workflow or self.graph
        if wf is None:
            raise ValueError("No workflow provided")

        context = context or {}
        wf._execution_context = context

        while True:
            ready = wf.get_ready_nodes()
            if not ready:
                break

            for node in ready:
                # CHECKPOINT nodes auto-pause
                if node.node_type == NodeType.CHECKPOINT or node.requires_approval:
                    node.status = NodeStatus.PAUSED
                    self._paused_nodes.append(node.id)
                    wf.save_checkpoint()
                    continue

                node.status = NodeStatus.RUNNING
                node.started_at = time.monotonic()

                try:
                    if node.handler:
                        # Gather data from dependency edges
                        deps_data: dict[str, Any] = {}
                        for edge in wf.edges:
                            if edge.target_id == node.id and edge.source_id in wf._nodes:
                                src = wf._nodes[edge.source_id]
                                if src.result is not None:
                                    key = edge.data_key or edge.source_id
                                    deps_data[key] = src.result
                        # Also gather from depends_on (backward compat)
                        for dep_id in node.depends_on:
                            if dep_id in wf._nodes and dep_id not in deps_data:
                                dep_node = wf._nodes[dep_id]
                                if dep_node.result is not None:
                                    deps_data[dep_id] = dep_node.result
                        node.result = node.handler({**context, **deps_data, **node.config})
                    else:
                        node.result = f"[{node.name}] no handler — skipped"
                    node.status = NodeStatus.COMPLETED
                except Exception as e:
                    node.error = str(e)
                    node.status = NodeStatus.FAILED
                finally:
                    node.completed_at = time.monotonic()

            wf.save_checkpoint()

        # Check if we're paused (any paused nodes means we stop and wait)
        if any(n.status == NodeStatus.PAUSED for n in wf._nodes.values()):
            return wf

        all_done = all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.FAILED)
            for n in wf._nodes.values()
        )
        return wf

    # --- Resume (human-in-the-loop) ---

    def resume(self, workflow: Optional[Workflow] = None, approval: bool = True) -> Workflow:
        """Resume a paused workflow after human-in-the-loop checkpoint."""
        wf = workflow or self.graph
        if wf is None:
            raise ValueError("No workflow provided")

        if not approval:
            return wf

        for node in wf._nodes.values():
            if node.status == NodeStatus.PAUSED:
                node.status = NodeStatus.PENDING
                node.requires_approval = False
                if node.id in self._paused_nodes:
                    self._paused_nodes.remove(node.id)

        return self.execute(wf, context=wf._execution_context)

    # --- Backward-compatible run() ---

    def run(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Backward-compatible run method. Returns dict of node_id → result."""
        if self.graph is None:
            raise ValueError("No graph provided")

        context = context or {}
        results: dict[str, Any] = {}
        max_passes = 100

        for _ in range(max_passes):
            ready = self.graph.ready_nodes()
            if not ready:
                break
            for node in ready:
                if node.requires_approval:
                    node.status = NodeStatus.PAUSED
                    self._paused_nodes.append(node.id)
                    continue
                node.status = NodeStatus.RUNNING
                try:
                    if node.handler:
                        # Gather edge-based data
                        deps_data: dict[str, Any] = {}
                        for edge in self.graph.edges:
                            if edge.target_id == node.id and edge.source_id in self.graph._nodes:
                                src = self.graph._nodes[edge.source_id]
                                if src.result is not None:
                                    key = edge.data_key or edge.source_id
                                    deps_data[key] = src.result
                        for dep_id in node.depends_on:
                            if dep_id in self.graph._nodes and dep_id not in deps_data:
                                dep_node = self.graph._nodes[dep_id]
                                if dep_node.result is not None:
                                    deps_data[dep_id] = dep_node.result
                        node.result = node.handler({**context, **deps_data, **node.config})
                    else:
                        node.result = f"[{node.name}] no handler — skipped"
                    node.status = NodeStatus.COMPLETED
                    results[node.id] = node.result
                except Exception as e:
                    node.error = str(e)
                    node.status = NodeStatus.FAILED
                    results[node.id] = f"ERROR: {e}"
            self.graph.save_checkpoint()
        return results

    # --- Approval ---

    def approve_node(self, node_id: str) -> bool:
        """Approve a paused node and reset it to pending for re-execution."""
        node = self.graph.get_node(node_id) if self.graph else None
        if node and node.status == NodeStatus.PAUSED:
            node.status = NodeStatus.PENDING
            node.requires_approval = False
            if node_id in self._paused_nodes:
                self._paused_nodes.remove(node_id)
            return True
        return False

    @property
    def paused_nodes(self) -> list[str]:
        return list(self._paused_nodes)
