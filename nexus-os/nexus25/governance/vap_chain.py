"""VAP (Verified Audit Proof) chain — immutable SHA-256 hash chain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VAPEntry:
    index: int
    timestamp: float
    action: str
    actor: str
    decision: str
    details: dict[str, Any] = field(default_factory=dict)
    parent_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self) -> str:
        content = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "actor": self.actor,
            "decision": self.decision,
            "details": self.details,
            "parent_hash": self.parent_hash,
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


class VAPChain:
    """Append-only verified audit proof chain."""

    def __init__(self) -> None:
        self._entries: list[VAPEntry] = []
        self._genesis_hash = hashlib.sha256(b"nexus-vap-genesis").hexdigest()

    def append(
        self, action: str, actor: str, decision: str,
        details: dict[str, Any] | None = None,
    ) -> VAPEntry:
        parent = self._entries[-1].entry_hash if self._entries else self._genesis_hash
        entry = VAPEntry(
            index=len(self._entries),
            timestamp=time.time(),
            action=action, actor=actor, decision=decision,
            details=details or {},
            parent_hash=parent,
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        expected_parent = self._genesis_hash
        for entry in self._entries:
            if entry.parent_hash != expected_parent:
                return False
            if entry.entry_hash != entry.compute_hash():
                return False
            expected_parent = entry.entry_hash
        return True

    def __len__(self) -> int:
        return len(self._entries)

    def export(self) -> list[dict[str, Any]]:
        return [
            {
                "index": e.index, "timestamp": e.timestamp,
                "action": e.action, "actor": e.actor, "decision": e.decision,
                "details": e.details, "parent_hash": e.parent_hash, "entry_hash": e.entry_hash,
            }
            for e in self._entries
        ]
