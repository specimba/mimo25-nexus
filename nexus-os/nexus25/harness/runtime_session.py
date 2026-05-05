"""Runtime session bootstrap — ties everything together."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..providers.catalog import ProviderCatalog
from ..providers.rate_limiter import RateLimiter
from ..providers.router import ProviderRouter
from ..tools.registry import ToolRegistry
from ..tools.permissions import PermissionContext, TrustLevel
from ..governance.hooks import GovernanceHooks
from ..governance.vap_chain import VAPChain
from ..governance.archivist import Archivist
from .execution_registry import ExecutionRegistry


@dataclass
class RuntimeConfig:
    trust_level: TrustLevel = TrustLevel.STANDARD
    lane: str = "general"
    token_budget: int = 100_000
    strict_governance: bool = True
    actor: str = "agent"


class RuntimeSession:
    """Fully wired NEXUS OS runtime session."""

    def __init__(
        self,
        config: RuntimeConfig,
        catalog: ProviderCatalog,
        rate_limiter: RateLimiter,
        router: ProviderRouter,
        tool_registry: ToolRegistry,
        permissions: PermissionContext,
        governance: GovernanceHooks,
        vap: VAPChain,
        archivist: Archivist,
        execution_registry: ExecutionRegistry,
    ) -> None:
        self.config = config
        self.catalog = catalog
        self.rate_limiter = rate_limiter
        self.router = router
        self.tools = tool_registry
        self.permissions = permissions
        self.governance = governance
        self.vap = vap
        self.archivist = archivist
        self.execution_registry = execution_registry

    @classmethod
    def bootstrap(cls, config: RuntimeConfig | None = None) -> "RuntimeSession":
        config = config or RuntimeConfig()

        catalog = ProviderCatalog()
        rate_limiter = RateLimiter()
        router = ProviderRouter(catalog=catalog, rate_limiter=rate_limiter)
        tool_registry = ToolRegistry()
        permissions = PermissionContext(
            trust_level=config.trust_level,
            lane=config.lane,
            actor=config.actor,
        )
        governance = GovernanceHooks(
            strict=config.strict_governance,
            token_budget=config.token_budget,
        )
        vap = VAPChain()
        archivist = Archivist()
        execution_registry = ExecutionRegistry()

        from ..gateway.core import GatewayCore, Platform
        gateway = GatewayCore(governance=governance)
        gateway.register_platform(Platform.CLI)
        gateway.register_platform(Platform.API)

        execution_registry.register_command(
            "status", lambda _: cls._status(router, governance, vap),
            source_hint="builtin",
        )
        execution_registry.register_command(
            "providers", lambda _: cls._list_providers(router),
            source_hint="builtin",
        )
        execution_registry.register_command(
            "audit", lambda _: cls._show_audit(governance),
            source_hint="builtin",
        )

        return cls(
            config=config, catalog=catalog, rate_limiter=rate_limiter,
            router=router, tool_registry=tool_registry, permissions=permissions,
            governance=governance, vap=vap, archivist=archivist,
            execution_registry=execution_registry,
        )

    @staticmethod
    def _status(router: ProviderRouter, gov: GovernanceHooks, vap: VAPChain) -> str:
        available = router.list_available()
        return (
            f"Providers: {len(available)} models available\n"
            f"Tokens remaining: {gov.tokens_remaining}\n"
            f"VAP chain length: {len(vap)}\n"
            f"VAP chain valid: {vap.verify()}"
        )

    @staticmethod
    def _list_providers(router: ProviderRouter) -> str:
        available = router.list_available()
        lines = [f"  {r.provider.name}/{r.model.id}  (score={r.score})" for r in available]
        return "Available models:\n" + "\n".join(lines) if lines else "No providers available"

    @staticmethod
    def _show_audit(gov: GovernanceHooks) -> str:
        log = gov.audit_log
        if not log:
            return "Audit log empty"
        lines = [
            f"  [{entry.decision.value:8s}] {entry.action}  (actor={entry.actor})"
            for entry in log[-20:]
        ]
        return f"Last {len(lines)} audit entries:\n" + "\n".join(lines)
