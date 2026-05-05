"""NEXUS 25 Doctor — Report-only diagnostics.

Subcommands:
  nexus25 doctor           Run all diagnostics
  nexus25 doctor provider  Provider health check
  nexus25 doctor token     Token budget analysis
  nexus25 doctor tool      Tool registry health
  nexus25 doctor memory    Memory/vault status
  nexus25 doctor runtime   Runtime/session health
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..governance.hooks import GovernanceHooks, DecisionType
from ..governance.vap_chain import VAPChain
from ..governance.archivist import Archivist, PromotionState
from ..providers.router import ProviderRouter
from ..providers.catalog import ProviderCatalog
from ..providers.rate_limiter import RateLimiter
from ..tools.registry import ToolRegistry
from ..harness.execution_registry import ExecutionRegistry


# ---------------------------------------------------------------------------
# Severity & Finding
# ---------------------------------------------------------------------------

class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


_SEVERITY_ICON = {
    Severity.INFO: "ℹ️ ",
    Severity.WARNING: "⚠️ ",
    Severity.CRITICAL: "🔴",
}


@dataclass
class Finding:
    category: str
    severity: Severity
    title: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""


# ---------------------------------------------------------------------------
# DoctorReport
# ---------------------------------------------------------------------------

class DoctorReport:
    """Aggregated findings from one or more diagnostic pillars."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def summary(self) -> str:
        """Return a formatted report with counts by severity."""
        counts = {s: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity] += 1

        lines: list[str] = []
        lines.append("═══════════════════════════════════════════════")
        lines.append("  NEXUS 25 — Doctor Diagnostic Report")
        lines.append("═══════════════════════════════════════════════")
        lines.append("")
        lines.append(
            f"  Summary: {counts[Severity.CRITICAL]} critical, "
            f"{counts[Severity.WARNING]} warning, "
            f"{counts[Severity.INFO]} info  "
            f"({len(self.findings)} total)"
        )
        lines.append("")

        if not self.findings:
            lines.append("  ✅ All checks passed — no findings.")
            lines.append("")
            lines.append("═══════════════════════════════════════════════")
            return "\n".join(lines)

        # Group by category
        categories: dict[str, list[Finding]] = {}
        for f in self.findings:
            categories.setdefault(f.category, []).append(f)

        for cat_name, cat_findings in categories.items():
            lines.append(f"  ── {cat_name} ──")
            for f in cat_findings:
                icon = _SEVERITY_ICON[f.severity]
                lines.append(f"    {icon} [{f.severity.value.upper():8s}] {f.title}")
                if f.detail:
                    lines.append(f"             {f.detail}")
                if f.evidence:
                    for k, v in f.evidence.items():
                        lines.append(f"             {k}: {v}")
                if f.suggested_action:
                    lines.append(f"             → {f.suggested_action}")
            lines.append("")

        lines.append("═══════════════════════════════════════════════")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ProviderDoctor
# ---------------------------------------------------------------------------

class ProviderDoctor:
    """Check provider catalog health."""

    def diagnose(self, router: ProviderRouter) -> DoctorReport:
        report = DoctorReport()
        catalog = router.catalog
        all_providers = catalog.all_providers()
        enabled = catalog.enabled_providers()

        # --- Provider count ---
        report.add(Finding(
            category="Provider",
            severity=Severity.INFO,
            title=f"{len(all_providers)} providers in catalog ({len(enabled)} enabled)",
            detail=f"Disabled: {len(all_providers) - len(enabled)}",
            evidence={"total": len(all_providers), "enabled": len(enabled)},
        ))

        # --- Providers with no models ---
        for p in all_providers:
            if not p.models:
                report.add(Finding(
                    category="Provider",
                    severity=Severity.WARNING,
                    title=f"Provider '{p.name}' has no models registered",
                    detail=f"base_url={p.base_url}",
                    suggested_action="Add models to this provider or disable it",
                ))

        # --- API key availability ---
        missing_keys: list[str] = []
        available_keys: list[str] = []
        for p in enabled:
            if p.requires_key:
                if os.environ.get(p.api_key_env):
                    available_keys.append(p.name)
                else:
                    missing_keys.append(p.name)

        if missing_keys:
            report.add(Finding(
                category="Provider",
                severity=Severity.WARNING,
                title=f"{len(missing_keys)} provider(s) missing API keys",
                detail=f"Missing: {', '.join(missing_keys)}",
                evidence={"missing_keys": missing_keys},
                suggested_action="Set the required environment variables to enable these providers",
            ))

        if available_keys:
            report.add(Finding(
                category="Provider",
                severity=Severity.INFO,
                title=f"{len(available_keys)} provider(s) have API keys configured",
                detail=f"Available: {', '.join(available_keys)}",
            ))

        # --- Rate limiter state ---
        snapshot = router.rate_limiter.snapshot()
        throttled = [
            name for name, info in snapshot.items()
            if info["requests"] >= info["rpm_limit"]
            or info["tokens"] >= info["tpm_limit"]
        ]
        if throttled:
            report.add(Finding(
                category="Provider",
                severity=Severity.WARNING,
                title=f"{len(throttled)} provider(s) currently throttled",
                detail=f"Throttled: {', '.join(throttled)}",
                evidence={"throttled": throttled},
                suggested_action="Wait for rate limit windows to reset or increase limits",
            ))
        else:
            report.add(Finding(
                category="Provider",
                severity=Severity.INFO,
                title="No providers currently throttled",
                detail=f"Tracking {len(snapshot)} provider(s) in rate limiter",
            ))

        # --- Available models via router ---
        available = router.list_available()
        if not available:
            report.add(Finding(
                category="Provider",
                severity=Severity.CRITICAL,
                title="No models available for routing",
                detail="The router cannot select any provider+model pair",
                suggested_action="Check API keys and rate limits",
            ))
        else:
            report.add(Finding(
                category="Provider",
                severity=Severity.INFO,
                title=f"{len(available)} model(s) available for routing",
                detail=f"Top: {available[0].provider.name}/{available[0].model.id} (score={available[0].score})",
            ))

        return report


# ---------------------------------------------------------------------------
# TokenDoctor
# ---------------------------------------------------------------------------

class TokenDoctor:
    """Check token budget health."""

    def diagnose(self, governance: GovernanceHooks) -> DoctorReport:
        report = DoctorReport()

        remaining = governance.tokens_remaining

        # Access private budget fields for diagnostics
        budget = governance._token_budget  # type: ignore[attr-defined]
        used = governance._tokens_used  # type: ignore[attr-defined]

        # --- Budget overview ---
        pct_used = (used / budget * 100) if budget > 0 else 0
        if pct_used >= 90:
            sev = Severity.CRITICAL
        elif pct_used >= 70:
            sev = Severity.WARNING
        else:
            sev = Severity.INFO

        report.add(Finding(
            category="Token Budget",
            severity=sev,
            title=f"Budget: {used:,} / {budget:,} tokens used ({pct_used:.1f}%)",
            detail=f"Remaining: {remaining:,} tokens",
            evidence={"budget": budget, "used": used, "remaining": remaining, "pct_used": round(pct_used, 1)},
            suggested_action="Increase budget or reduce token consumption" if sev != Severity.INFO else "",
        ))

        # --- Exhausted check ---
        if remaining <= 0:
            report.add(Finding(
                category="Token Budget",
                severity=Severity.CRITICAL,
                title="Token budget exhausted",
                detail="All further requests will be denied",
                suggested_action="Increase token budget via governance.set_token_budget()",
            ))

        # --- Audit log stats ---
        log = governance.audit_log
        denied_count = sum(1 for e in log if e.decision == DecisionType.DENIED)
        allowed_count = sum(1 for e in log if e.decision == DecisionType.ALLOWED)
        hold_count = sum(1 for e in log if e.decision == DecisionType.HOLD)

        report.add(Finding(
            category="Token Budget",
            severity=Severity.INFO,
            title=f"Audit log: {len(log)} entries",
            detail=f"Allowed: {allowed_count}, Denied: {denied_count}, Hold: {hold_count}",
            evidence={"total": len(log), "allowed": allowed_count, "denied": denied_count, "hold": hold_count},
        ))

        if denied_count > 0:
            denial_rate = denied_count / len(log) * 100 if log else 0
            sev = Severity.WARNING if denial_rate > 20 else Severity.INFO
            report.add(Finding(
                category="Token Budget",
                severity=sev,
                title=f"Denial rate: {denial_rate:.1f}%",
                detail=f"{denied_count} of {len(log)} requests denied",
                suggested_action="Review denied requests in audit log" if sev == Severity.WARNING else "",
            ))

        # --- Governance mode ---
        report.add(Finding(
            category="Token Budget",
            severity=Severity.INFO,
            title=f"Governance mode: {'strict' if governance.strict else 'permissive'}",
            detail="Strict mode denies by default when no governor is available",
        ))

        return report


# ---------------------------------------------------------------------------
# ToolDoctor
# ---------------------------------------------------------------------------

class ToolDoctor:
    """Check tool registry health."""

    def diagnose(self, tool_registry: ToolRegistry) -> DoctorReport:
        report = DoctorReport()

        total = len(tool_registry)

        # --- Tool count ---
        report.add(Finding(
            category="Tool Registry",
            severity=Severity.INFO,
            title=f"{total} tool(s) registered",
            detail=f"Toolsets: {', '.join(tool_registry.toolset_names()) or 'none'}",
        ))

        if total == 0:
            report.add(Finding(
                category="Tool Registry",
                severity=Severity.WARNING,
                title="No tools registered",
                detail="The tool registry is empty — no tools available for dispatch",
                suggested_action="Register tools before running agent workflows",
            ))

        # --- Tools with no handlers ---
        no_handler: list[str] = []
        for name, tool_def in tool_registry._tools.items():  # type: ignore[attr-defined]
            if tool_def.handler is None:
                no_handler.append(name)

        if no_handler:
            report.add(Finding(
                category="Tool Registry",
                severity=Severity.WARNING,
                title=f"{len(no_handler)} tool(s) have no handler",
                detail=f"Tools: {', '.join(no_handler)}",
                evidence={"tools_without_handlers": no_handler},
                suggested_action="Attach handlers to these tools for them to be dispatchable",
            ))

        # --- Tools requiring governance ---
        gov_tools: list[str] = []
        for name, tool_def in tool_registry._tools.items():  # type: ignore[attr-defined]
            if tool_def.requires_governance:
                gov_tools.append(name)

        if gov_tools:
            report.add(Finding(
                category="Tool Registry",
                severity=Severity.INFO,
                title=f"{len(gov_tools)} tool(s) require governance approval",
                detail=f"Tools: {', '.join(gov_tools)}",
            ))

        # --- Toolset breakdown ---
        for ts_name in tool_registry.toolset_names():
            ts_tools = tool_registry.tools_in_toolset(ts_name)
            report.add(Finding(
                category="Tool Registry",
                severity=Severity.INFO,
                title=f"Toolset '{ts_name}': {len(ts_tools)} tool(s)",
                detail=", ".join(ts_tools),
            ))

        return report


# ---------------------------------------------------------------------------
# MemoryDoctor
# ---------------------------------------------------------------------------

class MemoryDoctor:
    """Check memory/vault status (VAP chain + Archivist)."""

    def diagnose(self, vap: VAPChain, archivist: Archivist) -> DoctorReport:
        report = DoctorReport()

        # --- VAP chain ---
        chain_len = len(vap)
        chain_valid = vap.verify()

        if chain_len == 0:
            report.add(Finding(
                category="Memory/Vault",
                severity=Severity.INFO,
                title="VAP chain is empty",
                detail="No audit entries recorded yet",
            ))
        elif chain_valid:
            report.add(Finding(
                category="Memory/Vault",
                severity=Severity.INFO,
                title=f"VAP chain integrity: VALID ({chain_len} entries)",
                detail="All hash links verified successfully",
            ))
        else:
            report.add(Finding(
                category="Memory/Vault",
                severity=Severity.CRITICAL,
                title=f"VAP chain integrity: BROKEN ({chain_len} entries)",
                detail="Hash chain verification failed — possible tampering detected",
                suggested_action="Investigate chain corruption; consider rebuilding from trusted checkpoint",
            ))

        # --- Archivist artifacts ---
        artifacts = archivist._artifacts  # type: ignore[attr-defined]
        total_artifacts = len(artifacts)

        report.add(Finding(
            category="Memory/Vault",
            severity=Severity.INFO,
            title=f"Archivist: {total_artifacts} artifact(s) tracked",
            detail="Artifacts managed by integrity gate",
        ))

        # --- Promotion state distribution ---
        from ..governance.archivist import PromotionState as PS
        state_counts: dict[str, int] = {}
        for state in PS:
            count = len(archivist.list_by_state(state))
            if count > 0:
                state_counts[state.value] = count

        if state_counts:
            detail_parts = [f"{k}: {v}" for k, v in state_counts.items()]
            report.add(Finding(
                category="Memory/Vault",
                severity=Severity.INFO,
                title="Artifact promotion distribution",
                detail=", ".join(detail_parts),
                evidence=state_counts,
            ))

            # Stuck artifacts (RAW for too long could be an issue)
            raw_count = state_counts.get("raw", 0)
            if raw_count > 10:
                report.add(Finding(
                    category="Memory/Vault",
                    severity=Severity.WARNING,
                    title=f"{raw_count} artifacts in RAW state",
                    detail="Consider reviewing and promoting or rejecting stale artifacts",
                    suggested_action="Run artifact review pipeline",
                ))

        return report


# ---------------------------------------------------------------------------
# RuntimeDoctor
# ---------------------------------------------------------------------------

class RuntimeDoctor:
    """Check runtime/session health."""

    def diagnose(self, session: Any) -> DoctorReport:
        report = DoctorReport()

        # --- Execution registry ---
        exec_reg: ExecutionRegistry = session.execution_registry
        history = exec_reg.history
        total_executions = len(history)

        report.add(Finding(
            category="Runtime",
            severity=Severity.INFO,
            title=f"Execution history: {total_executions} record(s)",
            detail=f"Registered commands: {exec_reg.command_count}, tools: {exec_reg.tool_count}",
        ))

        # --- Success/failure rate ---
        if total_executions > 0:
            failures = sum(1 for r in history if not r.success)
            fail_rate = failures / total_executions * 100
            sev = Severity.CRITICAL if fail_rate > 50 else (Severity.WARNING if fail_rate > 10 else Severity.INFO)
            report.add(Finding(
                category="Runtime",
                severity=sev,
                title=f"Execution success rate: {100 - fail_rate:.1f}%",
                detail=f"{failures} failure(s) in {total_executions} execution(s)",
                evidence={"total": total_executions, "failures": failures, "fail_rate": round(fail_rate, 1)},
                suggested_action="Review failed executions in history" if sev != Severity.INFO else "",
            ))

            # --- Recent failures ---
            recent_failures = [r for r in history[-10:] if not r.success]
            if recent_failures:
                for rf in recent_failures[-3:]:  # Show last 3
                    report.add(Finding(
                        category="Runtime",
                        severity=Severity.WARNING,
                        title=f"Failed: {rf.kind}/{rf.name}",
                        detail=rf.output[:120],
                        evidence={"duration_ms": rf.duration_ms},
                    ))

        # --- Permission context ---
        perms = session.permissions
        report.add(Finding(
            category="Runtime",
            severity=Severity.INFO,
            title=f"Trust level: {perms.trust_level.value}",
            detail=f"Lane: {perms.lane}, Actor: {perms.actor}",
            evidence={"trust_level": perms.trust_level.value, "lane": perms.lane},
        ))

        if perms.blocked_tools:
            report.add(Finding(
                category="Runtime",
                severity=Severity.INFO,
                title=f"{len(perms.blocked_tools)} tool(s) blocked by permissions",
                detail=f"Blocked: {', '.join(sorted(perms.blocked_tools))}",
            ))

        # --- Session config ---
        cfg = session.config
        report.add(Finding(
            category="Runtime",
            severity=Severity.INFO,
            title="Session configuration",
            detail=f"Lane: {cfg.lane}, Strict governance: {cfg.strict_governance}, Actor: {cfg.actor}",
        ))

        return report


# ---------------------------------------------------------------------------
# Full diagnostic
# ---------------------------------------------------------------------------

def run_full_diagnostic(session: Any) -> DoctorReport:
    """Run all doctor checks and return combined report."""
    report = DoctorReport()

    # Provider
    provider_report = ProviderDoctor().diagnose(session.router)
    report.findings.extend(provider_report.findings)

    # Token
    token_report = TokenDoctor().diagnose(session.governance)
    report.findings.extend(token_report.findings)

    # Tool
    tool_report = ToolDoctor().diagnose(session.tools)
    report.findings.extend(tool_report.findings)

    # Memory
    memory_report = MemoryDoctor().diagnose(session.vap, session.archivist)
    report.findings.extend(memory_report.findings)

    # Runtime
    runtime_report = RuntimeDoctor().diagnose(session)
    report.findings.extend(runtime_report.findings)

    return report
