"""nexusctl — NEXUS OS command-line interface."""

from __future__ import annotations

import sys
from typing import Optional

from ..harness.runtime_session import RuntimeSession, RuntimeConfig
from ..tools.permissions import TrustLevel
from ..contracts.task_envelope import TaskEnvelope


def _print(text: str) -> None:
    print(text)


def cmd_status(session: RuntimeSession) -> None:
    record = session.execution_registry.execute_command("status")
    _print(record.output)


def cmd_providers(session: RuntimeSession) -> None:
    record = session.execution_registry.execute_command("providers")
    _print(record.output)


def cmd_audit(session: RuntimeSession) -> None:
    record = session.execution_registry.execute_command("audit")
    _print(record.output)


def cmd_verify(session: RuntimeSession) -> None:
    valid = session.vap.verify()
    _print(f"VAP chain: {len(session.vap)} entries, valid={valid}")


def cmd_task_submit(session: RuntimeSession, args: list[str]) -> None:
    brief = " ".join(args) if args else "No brief provided"
    envelope = TaskEnvelope(brief=brief, lane=session.config.lane)
    violations = envelope.validate()
    _print(f"Task: {envelope.task_id}")
    _print(f"Lane: {envelope.lane}")
    _print(f"Brief: {envelope.brief}")
    if violations:
        _print(f"Violations: {violations}")
    else:
        _print("Envelope valid — ready for dispatch")


def cmd_doctor(session: RuntimeSession, args: list[str]) -> None:
    from ..doctor.diagnostics import (
        run_full_diagnostic, ProviderDoctor, TokenDoctor,
        ToolDoctor, MemoryDoctor, RuntimeDoctor,
    )

    subcmd = args[0] if args else "all"

    if subcmd == "all":
        report = run_full_diagnostic(session)
    elif subcmd == "provider":
        report = ProviderDoctor().diagnose(session.router)
    elif subcmd == "token":
        report = TokenDoctor().diagnose(session.governance)
    elif subcmd == "tool":
        report = ToolDoctor().diagnose(session.tools)
    elif subcmd == "memory":
        report = MemoryDoctor().diagnose(session.vap, session.archivist)
    elif subcmd == "runtime":
        report = RuntimeDoctor().diagnose(session)
    else:
        _print(f"Unknown doctor subcommand: {subcmd}")
        _print("Available: all, provider, token, tool, memory, runtime")
        return

    _print(report.summary())


def cmd_interactive(session: RuntimeSession) -> None:
    _print("NEXUS OS Interactive CLI")
    _print("Type 'help' for commands, 'quit' to exit.\n")
    while True:
        try:
            line = input("nexus> ").strip()
        except (EOFError, KeyboardInterrupt):
            _print("\nExiting.")
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        handlers = {
            "status": lambda: cmd_status(session),
            "providers": lambda: cmd_providers(session),
            "audit": lambda: cmd_audit(session),
            "verify": lambda: cmd_verify(session),
            "submit": lambda: cmd_task_submit(session, rest.split() if rest else []),
            "doctor": lambda: cmd_doctor(session, rest.split() if rest else []),
            "help": lambda: _print(
                "Commands: status, providers, audit, verify, submit <brief>, doctor [subcmd], help, quit"
            ),
        }
        handler = handlers.get(cmd)
        if handler:
            handler()
        else:
            record = session.execution_registry.execute_command(cmd, rest)
            _print(record.output)


def main(argv: Optional[list[str]] = None) -> None:
    args = argv or sys.argv[1:]

    trust = TrustLevel.STANDARD
    lane = "general"
    if "--governed" in args:
        trust = TrustLevel.GOVERNED
        args.remove("--governed")
    if "--red-team" in args:
        trust = TrustLevel.RED_TEAM
        args.remove("--red-team")
    if "--lane" in args:
        idx = args.index("--lane")
        if idx + 1 < len(args):
            lane = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    session = RuntimeSession.bootstrap(RuntimeConfig(trust_level=trust, lane=lane))

    if not args:
        cmd_interactive(session)
        return

    command = args[0].lower()
    rest = args[1:]

    commands = {
        "status": lambda: cmd_status(session),
        "providers": lambda: cmd_providers(session),
        "audit": lambda: cmd_audit(session),
        "verify": lambda: cmd_verify(session),
        "task": lambda: cmd_task_submit(session, rest),
        "doctor": lambda: cmd_doctor(session, rest),
        "interactive": lambda: cmd_interactive(session),
    }

    handler = commands.get(command)
    if handler:
        handler()
    else:
        _print(f"Unknown command: {command}")
        _print("Available: status, providers, audit, verify, task, doctor, interactive")
        sys.exit(1)
