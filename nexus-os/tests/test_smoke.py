"""Smoke tests — verify all NEXUS OS modules wire together correctly."""

import pytest

from nexus25.providers.catalog import ProviderCatalog, Provider, Model
from nexus25.providers.rate_limiter import RateLimiter
from nexus25.providers.router import ProviderRouter, RoutePreference
from nexus25.tools.registry import ToolRegistry, ToolDefinition
from nexus25.tools.permissions import PermissionContext, TrustLevel
from nexus25.governance.hooks import GovernanceHooks, DecisionType
from nexus25.governance.vap_chain import VAPChain
from nexus25.governance.archivist import (
    Archivist, ArtifactFrontmatter, AuthorityScope, PromotionState, CacheClass,
)
from nexus25.gateway.core import GatewayCore, GatewayEvent, Platform
from nexus25.orchestration.agent_loop import AgentLoop
from nexus25.orchestration.workflow import WorkflowGraph, WorkflowNode, WorkflowEngine
from nexus25.harness.execution_registry import ExecutionRegistry
from nexus25.harness.runtime_session import RuntimeSession, RuntimeConfig
from nexus25.contracts.task_envelope import TaskEnvelope, TaskOutputContract
from nexus25.contracts.evidence_packet import EvidencePacket, EvidenceClaim


class TestProviderCatalog:
    def test_seed_providers(self):
        cat = ProviderCatalog()
        assert len(cat.all_providers()) >= 5
        groq = cat.get("groq")
        assert groq is not None
        assert groq.base_url == "https://api.groq.com/openai/v1"
        assert len(groq.models) >= 2

    def test_all_models(self):
        cat = ProviderCatalog()
        models = cat.all_models()
        assert len(models) >= 10
        assert all(isinstance(m, tuple) for m in models)


class TestRateLimiter:
    def test_basic_limiting(self):
        rl = RateLimiter()
        rl.register("test", rpm=2, tpm=1000)
        assert rl.can_proceed("test")
        rl.record("test", 100)
        assert rl.can_proceed("test")
        rl.record("test", 100)
        assert not rl.can_proceed("test")  # RPM exceeded

    def test_unknown_provider(self):
        rl = RateLimiter()
        assert rl.can_proceed("unknown")  # unregistered = no limit


class TestProviderRouter:
    def test_select_quality(self):
        router = ProviderRouter()
        result = router.select(min_context=8192, prefer="quality")
        if result:
            assert result.score > 0
            assert result.provider.name

    def test_list_available(self):
        router = ProviderRouter()
        available = router.list_available()
        assert isinstance(available, list)


class TestToolRegistry:
    def test_register_and_dispatch(self):
        reg = ToolRegistry()
        reg.register_function(
            name="echo",
            description="Echo back the input",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            handler=lambda text="": f"echo: {text}",
        )
        assert "echo" in reg
        result = reg.dispatch("echo", {"text": "hello"})
        assert result.success
        assert result.output == "echo: hello"

    def test_permission_filtering(self):
        reg = ToolRegistry()
        reg.register_function("a", "A", {}, lambda: "a")
        reg.register_function("b", "B", {}, lambda: "b")
        reg.register_function("c", "C", {}, lambda: "c")
        ctx = PermissionContext(allowed_tools={"a", "c"})
        defs = reg.get_definitions(permission_ctx=ctx)
        names = {d.name for d in defs}
        assert names == {"a", "c"}

    def test_openai_schema(self):
        reg = ToolRegistry()
        reg.register_function("test", "desc", {"type": "object", "properties": {}}, lambda: None)
        schemas = reg.get_schemas()
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "test"


class TestPermissions:
    def test_blocked_tools(self):
        ctx = PermissionContext(blocked_tools={"dangerous"})
        assert not ctx.is_tool_allowed("dangerous")
        assert ctx.is_tool_allowed("safe")

    def test_untrusted_preset(self):
        ctx = PermissionContext.untrusted()
        assert ctx.trust_level == TrustLevel.UNTRUSTED
        assert ctx.is_tool_allowed("read_file")
        assert not ctx.is_tool_allowed("write_file")

    def test_filter(self):
        ctx = PermissionContext(allowed_tools={"x", "y"})
        assert ctx.filter_tools(["x", "y", "z"]) == ["x", "y"]


class TestGovernanceHooks:
    def test_strict_no_governor(self):
        gov = GovernanceHooks(strict=True)
        decision = gov.check_tool_access("test_tool")
        assert decision.decision == DecisionType.DENIED
        assert len(gov.audit_log) == 1

    def test_permissive_no_governor(self):
        gov = GovernanceHooks(strict=False)
        decision = gov.check_tool_access("test_tool")
        assert decision.decision == DecisionType.ALLOWED

    def test_token_budget(self):
        gov = GovernanceHooks(token_budget=1000)
        d1 = gov.check_token_budget(500)
        assert d1.decision == DecisionType.ALLOWED
        gov.track_tokens(600)
        assert gov.tokens_remaining == 400
        d2 = gov.check_token_budget(500)
        assert d2.decision == DecisionType.DENIED

    def test_audit_chain(self):
        gov = GovernanceHooks(strict=False)
        gov.check_tool_access("a")
        gov.check_tool_access("b")
        log = gov.audit_log
        assert len(log) == 2
        assert log[1].parent_hash == log[0].entry_hash


class TestVAPChain:
    def test_chain_integrity(self):
        chain = VAPChain()
        chain.append("action1", "agent", "allowed")
        chain.append("action2", "agent", "denied")
        chain.append("action3", "user", "allowed")
        assert len(chain) == 3
        assert chain.verify()

    def test_tamper_detection(self):
        chain = VAPChain()
        chain.append("action1", "agent", "allowed")
        chain.append("action2", "agent", "denied")
        assert chain.verify()
        chain._entries[0].action = "TAMPERED"
        assert not chain.verify()

    def test_export(self):
        chain = VAPChain()
        chain.append("test", "agent", "allowed")
        exported = chain.export()
        assert len(exported) == 1
        assert "entry_hash" in exported[0]


class TestArchivist:
    def test_register_valid(self):
        arch = Archivist()
        fm = ArtifactFrontmatter(id="test-001", type="Evidence_Packet")
        ok, violations = arch.register(fm)
        assert ok
        assert len(violations) == 0

    def test_reject_external_without_provider(self):
        arch = Archivist()
        fm = ArtifactFrontmatter(
            id="test-002", type="Evidence_Packet",
            authority_scope=AuthorityScope.EXTERNAL_EVIDENCE,
            provider_class="local",
        )
        ok, violations = arch.register(fm)
        assert not ok
        assert any("provider_class" in v.rule for v in violations)

    def test_reject_high_cap_without_approval(self):
        arch = Archivist()
        fm = ArtifactFrontmatter(
            id="test-003", type="Task_Result",
            provider_class="mythos_preview",
            policy_hash="sha256:abc",
            sandbox_profile="test-v1",
        )
        ok, violations = arch.register(fm)
        assert not ok
        assert any("approval_id" in v.rule for v in violations)

    def test_reject_cache_to_promoted(self):
        arch = Archivist()
        fm = ArtifactFrontmatter(
            id="test-004", type="Evidence_Packet",
            cache_class=CacheClass.RETRIEVAL,
            promotion_state=PromotionState.PROMOTED,
        )
        ok, violations = arch.register(fm)
        assert not ok
        assert any("illegal_promotion" in v.rule for v in violations)

    def test_promotion_lifecycle(self):
        arch = Archivist()
        fm = ArtifactFrontmatter(id="test-005", type="Evidence_Packet")
        arch.register(fm)
        ok, msg = arch.promote("test-005", PromotionState.PROPOSAL)
        assert ok
        ok, msg = arch.promote("test-005", PromotionState.REVIEWED)
        assert ok
        ok, msg = arch.promote("test-005", PromotionState.PROMOTED)
        assert ok
        ok, msg = arch.promote("test-005", PromotionState.RAW)
        assert not ok


class TestGateway:
    def test_event_processing(self):
        gw = GatewayCore()
        gw.register_platform(Platform.CLI)
        event = GatewayEvent(
            platform=Platform.CLI, user_id="user1",
            channel_id="cli", content="hello",
        )
        response = gw.process_event(event)
        assert "cli" in response
        assert gw.active_sessions == 1

    def test_command_dispatch(self):
        gw = GatewayCore()
        gw.register_command("ping", lambda e, s: "pong")
        event = GatewayEvent(
            platform=Platform.API, user_id="u",
            channel_id="c", is_command=True, command_name="ping",
        )
        assert gw.process_event(event) == "pong"

    def test_unknown_command(self):
        gw = GatewayCore()
        event = GatewayEvent(
            platform=Platform.API, user_id="u",
            channel_id="c", is_command=True, command_name="nope",
        )
        assert "Unknown command" in gw.process_event(event)


class TestAgentLoop:
    def test_basic_run(self):
        loop = AgentLoop()
        result = loop.run("Hello")
        assert "AgentLoop ready" in result.final_response
        assert result.iterations == 0

    def test_with_provider_router(self):
        router = ProviderRouter()
        loop = AgentLoop(provider_router=router)
        result = loop.run("Hello")
        assert result.duration_ms > 0


class TestWorkflow:
    def test_simple_dag(self):
        graph = WorkflowGraph()
        results_collector = []
        n1 = WorkflowNode(name="step1", handler=lambda ctx: results_collector.append(1) or "a")
        n2 = WorkflowNode(name="step2", depends_on=[n1.id], handler=lambda ctx: results_collector.append(2) or "b")
        n3 = WorkflowNode(name="step3", depends_on=[n2.id], handler=lambda ctx: results_collector.append(3) or "c")
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n3)
        engine = WorkflowEngine(graph)
        results = engine.run()
        assert results_collector == [1, 2, 3]
        assert graph.is_complete()
        assert n1.result == "a"
        assert n3.result == "c"

    def test_human_in_the_loop(self):
        graph = WorkflowGraph()
        n1 = WorkflowNode(name="auto", handler=lambda ctx: "ok")
        n2 = WorkflowNode(name="needs_approval", requires_approval=True, handler=lambda ctx: "approved")
        n3 = WorkflowNode(name="final", depends_on=[n2.id], handler=lambda ctx: "done")
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n3)
        engine = WorkflowEngine(graph)
        engine.run()
        assert n1.status.value == "completed"
        assert n2.status.value == "paused"
        assert n3.status.value == "pending"
        assert engine.paused_nodes == [n2.id]
        engine.approve_node(n2.id)
        engine.run()
        assert n2.status.value == "completed"
        assert n3.status.value == "completed"

    def test_checkpoint(self):
        graph = WorkflowGraph()
        n1 = WorkflowNode(name="step1", handler=lambda ctx: "v1")
        graph.add_node(n1)
        engine = WorkflowEngine(graph)
        engine.run()
        cp = graph.save_checkpoint()
        n1.result = "corrupted"
        assert n1.result == "corrupted"
        assert graph.restore_checkpoint(cp.checkpoint_id)
        assert n1.result == "v1"


class TestExecutionRegistry:
    def test_command_execution(self):
        reg = ExecutionRegistry()
        reg.register_command("greet", lambda p: f"Hello, {p}!")
        record = reg.execute_command("greet", "world")
        assert record.success
        assert "Hello, world!" in record.output
        assert len(reg.history) == 1

    def test_unknown_command(self):
        reg = ExecutionRegistry()
        record = reg.execute_command("nope")
        assert not record.success
        assert "Unknown" in record.output


class TestContracts:
    def test_task_envelope_validation(self):
        env = TaskEnvelope(
            provider_class="mythos_preview",
            output=TaskOutputContract(canonical_write=True),
        )
        violations = env.validate()
        assert len(violations) >= 2
        assert any("approval_id" in v for v in violations)
        assert any("canonical_write" in v for v in violations)

    def test_task_envelope_serialization(self):
        env = TaskEnvelope(brief="Review code")
        d = env.to_dict()
        assert d["inputs"]["brief"] == "Review code"
        assert "task_id" in d

    def test_evidence_packet_frontmatter(self):
        packet = EvidencePacket(
            provider_class="mythos_preview",
            claims=[EvidenceClaim(text="Finding 1", confidence=0.9)],
        )
        fm = packet.to_frontmatter()
        assert fm.authority_scope == AuthorityScope.EXTERNAL_EVIDENCE
        assert fm.provider_class == "mythos_preview"
        assert fm.confidence == 0.9

    def test_evidence_content_hash(self):
        p1 = EvidencePacket(claims=[EvidenceClaim(text="A")])
        p2 = EvidencePacket(claims=[EvidenceClaim(text="B")])
        assert p1.content_hash() != p2.content_hash()


class TestRuntimeSession:
    def test_bootstrap(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        assert session.tools is not None
        assert session.governance is not None
        assert session.vap is not None

    def test_status_command(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        record = session.execution_registry.execute_command("status")
        assert record.success
        assert "Providers" in record.output

    def test_full_flow(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        session.tools.register_function("ping", "Ping", {}, lambda: "pong")
        assert "ping" in session.tools
        result = session.tools.dispatch("ping", {})
        assert result.success
        assert result.output == "pong"
        assert session.vap.verify()


# ---------------------------------------------------------------------------
# Doctor diagnostics
# ---------------------------------------------------------------------------

from nexus25.doctor.diagnostics import (
    Severity, Finding, DoctorReport,
    ProviderDoctor, TokenDoctor, ToolDoctor, MemoryDoctor, RuntimeDoctor,
    run_full_diagnostic,
)


class TestDoctorReport:
    def test_empty_report(self):
        report = DoctorReport()
        text = report.summary()
        assert "All checks passed" in text
        assert "0 total" in text

    def test_report_with_findings(self):
        report = DoctorReport()
        report.add(Finding(category="Test", severity=Severity.INFO, title="info finding", detail="detail"))
        report.add(Finding(category="Test", severity=Severity.WARNING, title="warn finding", detail=""))
        report.add(Finding(category="Test", severity=Severity.CRITICAL, title="crit finding", detail="oh no"))
        text = report.summary()
        assert "1 critical" in text
        assert "1 warning" in text
        assert "1 info" in text
        assert "3 total" in text
        assert "Test" in text

    def test_report_grouping(self):
        report = DoctorReport()
        report.add(Finding(category="Alpha", severity=Severity.INFO, title="a1", detail=""))
        report.add(Finding(category="Beta", severity=Severity.WARNING, title="b1", detail=""))
        report.add(Finding(category="Alpha", severity=Severity.INFO, title="a2", detail=""))
        text = report.summary()
        # Alpha section should appear
        assert "Alpha" in text
        assert "Beta" in text

    def test_report_with_evidence_and_action(self):
        report = DoctorReport()
        report.add(Finding(
            category="Test", severity=Severity.WARNING,
            title="issue", detail="something broke",
            evidence={"key": "val"},
            suggested_action="fix it",
        ))
        text = report.summary()
        assert "something broke" in text
        assert "key: val" in text
        assert "fix it" in text


class TestProviderDoctor:
    def test_diagnose_returns_report(self):
        router = ProviderRouter()
        report = ProviderDoctor().diagnose(router)
        assert isinstance(report, DoctorReport)
        assert len(report.findings) > 0

    def test_finds_missing_keys(self):
        router = ProviderRouter()
        report = ProviderDoctor().diagnose(router)
        # All providers require keys and none are set in test env
        missing = [f for f in report.findings if "missing API keys" in f.title.lower() or "missing" in f.title.lower()]
        # Should flag missing keys
        assert any("missing" in f.title.lower() or "api key" in f.title.lower() for f in report.findings)

    def test_finds_no_available_when_no_keys(self):
        router = ProviderRouter()
        report = ProviderDoctor().diagnose(router)
        critical = [f for f in report.findings if f.severity == Severity.CRITICAL]
        # Should be critical since no keys are set
        assert len(critical) >= 1


class TestTokenDoctor:
    def test_diagnose_returns_report(self):
        gov = GovernanceHooks(strict=False, token_budget=10000)
        report = TokenDoctor().diagnose(gov)
        assert isinstance(report, DoctorReport)
        assert len(report.findings) >= 2  # budget overview + governance mode

    def test_reports_budget_usage(self):
        gov = GovernanceHooks(strict=False, token_budget=1000)
        gov.track_tokens(500)
        report = TokenDoctor().diagnose(gov)
        budget_finding = [f for f in report.findings if "budget" in f.title.lower()]
        assert len(budget_finding) >= 1

    def test_reports_exhausted(self):
        gov = GovernanceHooks(strict=False, token_budget=100)
        gov.track_tokens(100)
        report = TokenDoctor().diagnose(gov)
        exhausted = [f for f in report.findings if "exhausted" in f.title.lower()]
        assert len(exhausted) >= 1

    def test_reports_high_usage_warning(self):
        gov = GovernanceHooks(strict=False, token_budget=1000)
        gov.track_tokens(800)  # 80% used
        report = TokenDoctor().diagnose(gov)
        warnings = [f for f in report.findings if f.severity == Severity.WARNING]
        assert len(warnings) >= 1


class TestToolDoctor:
    def test_empty_registry(self):
        reg = ToolRegistry()
        report = ToolDoctor().diagnose(reg)
        assert isinstance(report, DoctorReport)
        warnings = [f for f in report.findings if "no tools" in f.title.lower() or "empty" in f.title.lower()]
        assert len(warnings) >= 1

    def test_with_tools(self):
        reg = ToolRegistry()
        reg.register_function("echo", "Echo", {}, lambda: "echo")
        reg.register_function("ping", "Ping", {}, lambda: "pong")
        report = ToolDoctor().diagnose(reg)
        assert any("2 tool" in f.title for f in report.findings)

    def test_toolset_breakdown(self):
        reg = ToolRegistry()
        reg.register_function("a", "A", {}, lambda: "a", toolset="alpha")
        reg.register_function("b", "B", {}, lambda: "b", toolset="beta")
        report = ToolDoctor().diagnose(reg)
        toolsets = [f for f in report.findings if "toolset" in f.title.lower()]
        assert len(toolsets) >= 2


class TestMemoryDoctor:
    def test_empty_chain(self):
        vap = VAPChain()
        archivist = Archivist()
        report = MemoryDoctor().diagnose(vap, archivist)
        assert isinstance(report, DoctorReport)
        assert any("empty" in f.title.lower() for f in report.findings)

    def test_valid_chain(self):
        vap = VAPChain()
        vap.append("test", "agent", "allowed")
        archivist = Archivist()
        report = MemoryDoctor().diagnose(vap, archivist)
        assert any("valid" in f.title.lower() for f in report.findings)

    def test_broken_chain(self):
        vap = VAPChain()
        vap.append("test", "agent", "allowed")
        vap._entries[0].action = "TAMPERED"
        archivist = Archivist()
        report = MemoryDoctor().diagnose(vap, archivist)
        critical = [f for f in report.findings if f.severity == Severity.CRITICAL]
        assert len(critical) >= 1

    def test_with_artifacts(self):
        from nexus25.governance.archivist import ArtifactFrontmatter
        vap = VAPChain()
        archivist = Archivist()
        archivist.register(ArtifactFrontmatter(id="a1", type="Evidence_Packet"))
        archivist.register(ArtifactFrontmatter(id="a2", type="Evidence_Packet"))
        report = MemoryDoctor().diagnose(vap, archivist)
        assert any("2 artifact" in f.title for f in report.findings)


class TestRuntimeDoctor:
    def test_fresh_session(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        report = RuntimeDoctor().diagnose(session)
        assert isinstance(report, DoctorReport)
        assert any("trust level" in f.title.lower() for f in report.findings)

    def test_reports_failures(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        # Register a command that raises an exception to create a failure record
        session.execution_registry.register_command(
            "boom", lambda _: (_ for _ in ()).throw(RuntimeError("kaboom")),
        )
        session.execution_registry.execute_command("boom")
        report = RuntimeDoctor().diagnose(session)
        failure_findings = [f for f in report.findings if "failed" in f.title.lower() or "fail" in f.title.lower()]
        assert len(failure_findings) >= 1

    def test_reports_config(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(
            trust_level=TrustLevel.GOVERNED, lane="security", strict_governance=True,
        ))
        report = RuntimeDoctor().diagnose(session)
        assert any("governed" in f.title.lower() or "governed" in f.detail.lower() for f in report.findings)


class TestFullDiagnostic:
    def test_run_all(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        report = run_full_diagnostic(session)
        assert isinstance(report, DoctorReport)
        # Should have findings from all 5 pillars
        categories = {f.category for f in report.findings}
        assert "Provider" in categories
        assert "Token Budget" in categories
        assert "Tool Registry" in categories
        assert "Memory/Vault" in categories
        assert "Runtime" in categories

    def test_summary_output(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        report = run_full_diagnostic(session)
        text = report.summary()
        assert "NEXUS 25" in text
        assert "Doctor Diagnostic Report" in text
        assert "Summary:" in text


class TestCLIDoctor:
    def test_doctor_command(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        record = session.execution_registry.execute_command("status")
        assert record.success

    def test_doctor_subcommands(self):
        session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))
        # Test each subcommand produces output without crashing
        from nexus25.doctor.diagnostics import (
            ProviderDoctor, TokenDoctor, ToolDoctor, MemoryDoctor, RuntimeDoctor,
        )
        r1 = ProviderDoctor().diagnose(session.router)
        assert len(r1.findings) > 0
        r2 = TokenDoctor().diagnose(session.governance)
        assert len(r2.findings) > 0
        r3 = ToolDoctor().diagnose(session.tools)
        assert len(r3.findings) > 0
        r4 = MemoryDoctor().diagnose(session.vap, session.archivist)
        assert len(r4.findings) > 0
        r5 = RuntimeDoctor().diagnose(session)
        assert len(r5.findings) > 0
