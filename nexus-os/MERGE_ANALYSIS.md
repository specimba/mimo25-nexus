# NEXUS OS — Merge Analysis Report
## Remote (v3.0) vs New (v0.1.0) — Detailed Code & Workflow Comparison

Generated: 2026-05-06

---

## Executive Summary

The remote `mimo25-nexus-branch` has **287 files** with a mature v3.0 codebase (`src/nexus_os/`). Our new code has **32 files** with a clean v0.1.0 architecture. These are **complementary, not competing** codebases — the remote is production infrastructure, ours is a clean-room reimplementation of core patterns with some unique additions.

**Verdict: Merge ours into theirs as a parallel package. Zero breakage, both sides benefit.**

---

## 1. GOVERNANCE — Deep Comparison

### Remote: `src/nexus_os/governor/` (6 files)
- `base.py` — NexusGovernor: 3-layer pipeline (KAIJU → CVA → Compliance)
- `kaiju_auth.py` — KAIJU 4-variable authorization (scope × clearance, impact × clearance, intent × action)
- `compliance.py` — OWASP/CSA/IMDA compliance engine
- `proof_chain.py` — VAP 4-layer proof chain (L1+L2+L3+L4)
- `trust_scoring.py` — Trust Scoring v2.1 with lane-scoped Bayesian reputation
- `autoharness.py` — 6-step governance pipeline
- `constitution.yaml` — Policy rules

### Ours: `nexus_os/governance/` (3 files)
- `hooks.py` — GovernanceHooks: check_tool_access + token budget + audit chain
- `vap_chain.py` — VAP chain (SHA-256, genesis hash, verify/export)
- `archivist.py` — Integrity gate with Mythos frontmatter validation

### Comparison

| Aspect | Remote (v3.0) | Ours (v0.1.0) | Winner |
|--------|--------------|---------------|--------|
| Authorization model | KAIJU 4-variable (scope/intent/impact/clearance) | Simple allow/deny/hold | **Remote** |
| VAP chain | 4-layer (L1 proposal + L2 merge + L3 signature + L4 integrity) | 2-layer (SHA-256 hash chain) | **Remote** |
| Trust scoring | Bayesian lane-scoped with 15+ reason codes, MemoryTracks | None (just trust_level enum) | **Remote** |
| Compliance | OWASP/CSA/IMDA post-checks | None | **Remote** |
| Token guard integration | TokenGuard with per-agent budgets, warning/hardstop | Simple token counter | **Remote** |
| Artifact validation | None | Archivist integrity gate (authority_scope, promotion_state, cache_class) | **Ours** |
| Promotion pipeline | None | RAW→PROPOSAL→REVIEWED→PROMOTED state machine | **Ours** |
| Frontmatter schema | None | Mythos-recommended fields (policy_hash, sandbox_profile, approval_id) | **Ours** |

**Merge strategy:** Keep remote's governor as primary. Our `archivist.py` and promotion pipeline are **unique additions** worth integrating.

---

## 2. MODEL ROUTING — Deep Comparison

### Remote: `src/nexus_os/gmr/` + `engine/hermes.py` (10 files)
- `rotator.py` — GeniusModelRotator v3.0: dual-pool (FAST/PREMIUM), intent classification, circuit breaker, zero-context-loss handoff
- `domain_mapping.py` — Static model-to-domain mapping
- `circuit_breaker.py` — Adaptive circuit breaker
- `context_packet.py` — Zero-context-loss handoff packet
- `savings.py` — Token savings tracker
- `scheduler.py` — Telemetry refresh scheduler
- `telemetry.py` — Live telemetry ingest
- `trust_adapter.py` — Trust integration for GMR
- `hermes.py` — HermesRouter: intent classification + experience scoring + cost optimization

### Ours: `nexus_os/providers/` (3 files)
- `catalog.py` — Static provider catalog (7 free-tier providers, 15+ models)
- `rate_limiter.py` — Sliding-window rate tracking (RPM + TPM)
- `router.py` — ProviderRouter: quality/speed/cost/balanced scoring

### Comparison

| Aspect | Remote (v3.0) | Ours (v0.1.0) | Winner |
|--------|--------------|---------------|--------|
| Model pools | Dual-pool (FAST/PREMIUM) with budget-aware selection | Single pool with quality/speed/cost scoring | **Remote** |
| Intent classification | Keyword + heuristic classifier (code/research/reasoning/speed/security) | task_type string matching | **Remote** |
| Circuit breaker | Per-model failure tracking with cooldown | None | **Remote** |
| Zero-context-loss | ContextPacket with handoff state | None | **Remote** |
| Experience scoring | Bayesian-smoothed from model_performance DB | Static quality_score in catalog | **Remote** |
| Provider catalog | Hardcoded in DOMAIN_MAPPING | 7 real free-tier providers (Groq, Cerebras, Google, HF, GitHub, Mistral, OpenRouter) | **Ours** |
| Rate limiting | None (relies on circuit breaker) | Sliding-window RPM + TPM per provider | **Ours** |
| Free-tier awareness | None (assumes paid models) | Tier scoring (free > freemium > paid), API key detection | **Ours** |
| Provider diversity | ~10 models, 2-3 providers | 15+ models, 7 providers | **Ours** |

**Merge strategy:** Our `providers/catalog.py` with real free-tier data + `rate_limiter.py` are **unique and valuable**. Wire them into GMR as an additional provider source.

---

## 3. TOKEN MANAGEMENT — Deep Comparison

### Remote: `src/nexus_os/monitoring/token_guard.py`
- Per-agent/per-skill/per-swarm budgets
- Semantic cache (warm path)
- Model routing (warm path)
- VAP-compliant audit trail with SHA-256 signatures
- Trend analysis (cold path)
- Fallback model recommendation

### Ours: `nexus_os/governance/hooks.py` (token budget section)
- Simple token counter with budget check
- Audit chain integration

### Comparison

| Aspect | Remote | Ours | Winner |
|--------|--------|------|--------|
| Budget granularity | Per-agent/per-skill/per-swarm/per-session | Single global budget | **Remote** |
| Semantic caching | Built-in | None | **Remote** |
| Trend analysis | Built-in | None | **Remote** |
| Audit integration | Standalone + VAP signatures | Integrated with VAP chain | **Tie** |

**Merge strategy:** Remote's TokenGuard is strictly superior. Ours adds nothing here.

---

## 4. ORCHESTRATION — Deep Comparison

### Remote: `src/nexus_os/engine/` (10 files)
- `executor.py` — Real task executor (pluggable backends)
- `router.py` — EngineRouter: task lifecycle + DAG dependencies
- `hermes.py` — HermesRouter (see above)
- `forge.py` — Qualixar-style declarative team design
- `heartbeat.py` — Stalled agent detection + task reclamation
- `skill_adapter.py` — Skill platform bridge
- `skill_smith.py` — Auto-discovery system v2.1
- `tool_discipline.py` — Tool usage tracking + enforcement

### Ours: `nexus_os/orchestration/` (2 files)
- `agent_loop.py` — Sequential tool-use conversation loop
- `workflow.py` — DAG engine with checkpoints + human-in-the-loop

### Comparison

| Aspect | Remote | Ours | Winner |
|--------|--------|------|--------|
| Agent loop | executor.py (pluggable backends) | agent_loop.py (sequential tool-use with provider routing) | **Different focus** |
| DAG workflow | router.py (task lifecycle + deps) | workflow.py (DAG + checkpoints + human-in-the-loop) | **Ours** (checkpoints + approval gates) |
| Team orchestration | forge.py (declarative team design) | None | **Remote** |
| Heartbeat/health | heartbeat.py (stalled agent detection) | None | **Remote** |
| Skill discovery | skill_smith.py (auto-discovery) | None | **Remote** |
| Tool discipline | tool_discipline.py (usage tracking) | None | **Remote** |
| Checkpoint/restore | None | save_checkpoint() + restore_checkpoint() | **Ours** |
| Human-in-the-loop | None | requires_approval → PAUSED → approve_node() | **Ours** |

**Merge strategy:** Our `workflow.py` with checkpoints + human-in-the-loop is **unique**. The rest is remote's domain.

---

## 5. UNIQUE TO OURS (No Remote Equivalent)

| Module | What it does | Value |
|--------|-------------|-------|
| `tools/registry.py` | Unified tool registry with OpenAI function-calling schema, permission-aware dispatch | **High** — clean API for tool management |
| `tools/permissions.py` | TrustLevel enum + PermissionContext (untrusted/standard/governed/red_team) | **High** — clean permission model |
| `contracts/task_envelope.py` | Task dispatch contracts with high-capability validation | **Medium** — Mythos integration pattern |
| `contracts/evidence_packet.py` | Evidence packets with frontmatter conversion | **Medium** — Archivist integration |
| `harness/runtime_session.py` | One-call bootstrap wiring all subsystems | **High** — instant dev experience |
| `harness/execution_registry.py` | Command/tool execution tracking | **Medium** — session-level dispatch |
| `cli/main.py` | nexusctl CLI | **High** — quick start |
| `boot.sh` | Quick boot script | **Medium** — developer experience |

---

## 6. UNIQUE TO REMOTE (No Equivalent in Ours)

| Module | What it does |
|--------|-------------|
| `bridge/` | A2A JSON-RPC server, SDK, MCP-Auth |
| `swarm/` | Foreman/Worker/OpenClaw spawner |
| `vault/` | 5-track memory, S-P-E-W hierarchy, mem0 adapter, poisoning detection |
| `db/` | SQLite database manager |
| `api/` | FastAPI surface + dashboard |
| `observability/` | Squeez pruner, trace context |
| `relay/` | Model relay proxy |
| `stresslab/` | ISC-bench runner |
| `cron/` | Agent cycle runner |
| `team/` | Agentic team coordinator |

---

## 7. RECOMMENDED MERGE ROUTE

### Step 1: Namespace Ours as `nexus25/`
```
nexus25/
├── __init__.py
├── providers/          ← Our free-tier catalog + rate limiter
├── tools/              ← Our permission-aware registry
├── governance/         ← Archivist + promotion pipeline ONLY
├── orchestration/      ← Workflow engine with checkpoints
├── contracts/          ← Task envelope + evidence packet
├── harness/            ← RuntimeSession bootstrap
└── cli/                ← nexusctl
```

### Step 2: Add Bridge Imports
Create `src/nexus_os/bridge/nexus25_bridge.py` that imports from `nexus25`:
```python
from nexus25.providers.router import ProviderRouter
from nexus25.tools.registry import ToolRegistry
from nexus25.harness.runtime_session import RuntimeSession
```

### Step 3: Integrate Unique Pieces
- Our `providers/catalog.py` → feed into GMR as additional provider source
- Our `tools/registry.py` → use as clean tool API layer
- Our `workflow.py` → add checkpoint + human-in-the-loop to engine
- Our `archivist.py` → add artifact validation to governor pipeline
- Our `contracts/` → use for task dispatch validation

### Step 4: Keep Remote Untouched
- `src/nexus_os/` stays as-is (v3.0 production)
- `pyproject.toml` stays as-is (setuptools v3.0.0)
- `README.md` stays as-is
- `.gitignore` merge (theirs is more comprehensive, keep theirs)

### File-Level Merge Map

```
OURS                          → DESTINATION
─────────────────────────────────────────────
nexus_os/providers/           → nexus25/providers/
nexus_os/tools/               → nexus25/tools/
nexus_os/governance/archivist.py → nexus25/governance/archivist.py
nexus_os/governance/hooks.py  → SKIP (remote's governor is better)
nexus_os/governance/vap_chain.py → SKIP (remote's proof_chain is better)
nexus_os/orchestration/workflow.py → nexus25/orchestration/workflow.py
nexus_os/orchestration/agent_loop.py → SKIP (remote's executor is better)
nexus_os/gateway/core.py      → SKIP (remote's bridge is better)
nexus_os/harness/             → nexus25/harness/
nexus_os/contracts/           → nexus25/contracts/
nexus_os/cli/                 → nexus25/cli/
tests/test_smoke.py           → tests/test_nexus25_smoke.py
boot.sh                       → boot.sh (root level)
pyproject.toml                → SKIP (theirs)
README.md                     → SKIP (theirs)
.gitignore                    → SKIP (theirs)
```

---

## 8. RISK ASSESSMENT

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Package name collision | **Eliminated** | Using `nexus25` namespace |
| Test interference | **Eliminated** | `tests/test_nexus25_smoke.py` separate file |
| Import conflicts | **Eliminated** | Different package names |
| Breaking remote code | **None** | No changes to `src/nexus_os/` |
| Merge conflicts | **Minimal** | Only `.gitignore` overlaps, keep theirs |

---

## 9. CONCLUSION

The two codebases are **complementary**:
- **Remote (v3.0):** Production infrastructure — governor, GMR, vault, swarm, bridge
- **Ours (v0.1.0):** Clean architecture — free-tier providers, tool registry, contracts, workflow checkpoints, CLI

**Best merge: `nexus25/` namespace, bridge imports, zero breakage.**
