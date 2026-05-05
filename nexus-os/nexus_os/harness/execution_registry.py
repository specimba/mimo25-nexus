"""Execution registry — session-aware command/tool dispatch tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class ExecutionRecord:
    name: str
    kind: str  # "command" or "tool"
    input_payload: str
    output: str
    success: bool
    timestamp: float
    duration_ms: float


@dataclass
class ExecutableEntry:
    name: str
    kind: str
    handler: Optional[Callable] = None
    source_hint: str = ""

    def execute(self, payload: str = "") -> ExecutionRecord:
        start = time.monotonic()
        try:
            if self.handler:
                result = self.handler(payload)
                output = str(result)
                success = True
            else:
                output = f"[{self.kind}] '{self.name}' from {self.source_hint} — no handler attached"
                success = True
        except Exception as e:
            output = f"Error: {e}"
            success = False
        duration = (time.monotonic() - start) * 1000
        return ExecutionRecord(
            name=self.name, kind=self.kind,
            input_payload=payload[:200], output=output[:500],
            success=success, timestamp=time.time(),
            duration_ms=round(duration, 2),
        )


class ExecutionRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, ExecutableEntry] = {}
        self._tools: dict[str, ExecutableEntry] = {}
        self._history: list[ExecutionRecord] = []

    def register_command(
        self, name: str, handler: Optional[Callable] = None, source_hint: str = "",
    ) -> None:
        self._commands[name] = ExecutableEntry(
            name=name, kind="command", handler=handler, source_hint=source_hint,
        )

    def register_tool(
        self, name: str, handler: Optional[Callable] = None, source_hint: str = "",
    ) -> None:
        self._tools[name] = ExecutableEntry(
            name=name, kind="tool", handler=handler, source_hint=source_hint,
        )

    def execute_command(self, name: str, payload: str = "") -> ExecutionRecord:
        entry = self._commands.get(name)
        if not entry:
            return ExecutionRecord(
                name=name, kind="command", input_payload=payload,
                output=f"Unknown command: {name}", success=False,
                timestamp=time.time(), duration_ms=0,
            )
        record = entry.execute(payload)
        self._history.append(record)
        return record

    def execute_tool(self, name: str, payload: str = "") -> ExecutionRecord:
        entry = self._tools.get(name)
        if not entry:
            return ExecutionRecord(
                name=name, kind="tool", input_payload=payload,
                output=f"Unknown tool: {name}", success=False,
                timestamp=time.time(), duration_ms=0,
            )
        record = entry.execute(payload)
        self._history.append(record)
        return record

    @property
    def history(self) -> list[ExecutionRecord]:
        return list(self._history)

    @property
    def command_count(self) -> int:
        return len(self._commands)

    @property
    def tool_count(self) -> int:
        return len(self._tools)
