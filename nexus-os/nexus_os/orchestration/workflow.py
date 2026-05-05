"""Graph-based workflow engine — DAG orchestration with checkpoints."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    SKIPPED = "skipped"


@dataclass
class WorkflowNode:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    handler: Optional[Callable[..., Any]] = None
    depends_on: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowCheckpoint:
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    node_states: dict[str, NodeStatus] = field(default_factory=dict)
    node_results: dict[str, Any] = field(default_factory=dict)


class WorkflowGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, WorkflowNode] = {}
        self._checkpoints: list[WorkflowCheckpoint] = []

    def add_node(self, node: WorkflowNode) -> None:
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        return self._nodes.get(node_id)

    def ready_nodes(self) -> list[WorkflowNode]:
        ready = []
        for node in self._nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps_met = all(
                self._nodes[dep].status == NodeStatus.COMPLETED
                for dep in node.depends_on
                if dep in self._nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.FAILED)
            for n in self._nodes.values()
        )

    def save_checkpoint(self) -> WorkflowCheckpoint:
        cp = WorkflowCheckpoint(
            node_states={nid: n.status for nid, n in self._nodes.items()},
            node_results={nid: n.result for nid, n in self._nodes.items()},
        )
        self._checkpoints.append(cp)
        return cp

    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        for cp in reversed(self._checkpoints):
            if cp.checkpoint_id == checkpoint_id:
                for nid, status in cp.node_states.items():
                    if nid in self._nodes:
                        self._nodes[nid].status = status
                        self._nodes[nid].result = cp.node_results.get(nid)
                return True
        return False


class WorkflowEngine:
    def __init__(self, graph: WorkflowGraph) -> None:
        self.graph = graph
        self._paused_nodes: list[str] = []

    def run(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
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
                        node.result = node.handler(context)
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

    def approve_node(self, node_id: str) -> bool:
        node = self.graph.get_node(node_id)
        if node and node.status == NodeStatus.PAUSED:
            node.status = NodeStatus.PENDING
            node.requires_approval = False  # already approved
            self._paused_nodes.remove(node_id)
            return True
        return False

    @property
    def paused_nodes(self) -> list[str]:
        return list(self._paused_nodes)
