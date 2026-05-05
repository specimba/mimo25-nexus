# NEXUS 25 — Agent Pack

Clean-room agent platform with free-tier provider routing, tool registry, governance, diagnostics, bridge contract, and deployment-ready scripts. Designed to complement the main NEXUS OS v3.0 codebase.

## Quick Start

```bash
cd nexus-os
pip install -e ".[dev]"
pytest tests/ -v          # 66 tests
nexus25 status            # system status
nexus25 doctor            # full diagnostics
nexus25 providers         # available LLMs
nexus25 interactive       # REPL
```

## One-Shot Gastown Deploy

```bash
bash deploy/gastown_quickstart.sh
```

## Architecture

```
nexus25/
├── bridge/                # Bridge contract (external API surface)
│   └── contract.py        # submit_task / status / audit_query
├── providers/             # 7 free-tier LLM providers
│   ├── catalog.py         # Groq, Cerebras, OpenRouter, Google, HF, GitHub, Mistral
│   ├── rate_limiter.py    # Sliding-window RPM + TPM tracking
│   └── router.py          # Quality/speed/cost/balanced scoring
├── tools/                 # Permission-aware tool registry
│   ├── permissions.py     # Trust levels (untrusted → red_team)
│   └── registry.py        # OpenAI function-calling schema, dispatch
├── governance/            # Archivist integrity + token lifecycle
│   ├── hooks.py           # Governor + TokenGuard reserve/commit/refund + cycle validation
│   ├── vap_chain.py       # SHA-256 immutable audit chain
│   └── archivist.py       # Mythos artifact validation + promotion pipeline
├── doctor/                # Report-only diagnostics
│   └── diagnostics.py     # Provider/token/tool/memory/runtime doctors
├── recovery/              # Crash resilience
│   └── boot.py            # State rebuild + COLD_HANDOFF generation
├── gateway/               # Multi-platform message dispatch
│   └── core.py            # Session management, command routing
├── orchestration/         # Agent workflows
│   ├── agent_loop.py      # Sequential tool-use loop
│   └── workflow.py        # DAG engine: edges, NodeType, checkpoints, HITL
├── harness/               # Session bootstrap
│   ├── execution_registry.py
│   └── runtime_session.py # One-call bootstrap wiring all subsystems
├── contracts/             # Task/evidence schemas
│   ├── task_envelope.py   # High-capability task dispatch
│   └── evidence_packet.py # Evidence with promotion tracking
└── cli/                   # nexus25 CLI
    └── main.py            # status, providers, audit, verify, task, doctor, interactive

deploy/
├── gastown_quickstart.sh  # One-shot Gastown deployment
├── zilliz_client.py       # Dual-cluster Zilliz vector memory
├── openshell_setup.sh     # NVIDIA OpenShell installer
├── mission_router.py      # Mission routing protocol parser
└── README.md
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `nexus25 status` | System status (providers, tokens, VAP chain) |
| `nexus25 providers` | List available LLM providers |
| `nexus25 audit` | Show governance audit log |
| `nexus25 verify` | Verify VAP chain integrity |
| `nexus25 task <brief>` | Submit a task envelope |
| `nexus25 doctor` | Full diagnostic report |
| `nexus25 doctor provider` | Provider health check |
| `nexus25 doctor token` | Token budget analysis |
| `nexus25 doctor tool` | Tool registry health |
| `nexus25 doctor memory` | Memory/vault status |
| `nexus25 doctor runtime` | Runtime/session health |
| `nexus25 interactive` | Interactive REPL |

## Bridge Contract

External systems integrate via three operations:

```python
from nexus25.bridge.contract import BridgeContract
bridge = BridgeContract()

# Submit a task
result = bridge.submit_task({"brief": "Review code"}, authority_scope="standard")
proposal_id = result["proposal_id"]

# Check status
status = bridge.status(proposal_id)
print(status["state"])  # "pending", "running", "completed", "failed"

# Query audit trail (redacted)
events = bridge.audit_query({"actor": "agent-1"})
```

## TokenGuard Lifecycle

```python
session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))

# Reserve tokens before work
reservation_id = session.governance.reserve_tokens("agent-1", 5000, "code_review")

# Do work...

# Commit with actual usage
session.governance.commit_reservation(reservation_id, actual_tokens=3200)

# Or refund if cancelled
session.governance.refund_reservation(reservation_id)

# Cycle validation
result = session.governance.check_cycle_validation({
    "files_changed": 3, "tests_passed": True, "memory_entries": 1, "errors": 0
})
print(result["should_continue"], result["trust_delta"])
```

## Recovery

```python
from nexus25.recovery.boot import RecoveryBoot
recovery = RecoveryBoot()

# Rebuild state after crash
state = recovery.rebuild_state()

# Generate cold handoff
handoff = recovery.generate_cold_handoff()
```

## Deployment

### Zilliz Memory (Dual-Cluster)

```bash
export ZILLIZ_SERVERLESS_URI=https://...
export ZILLIZ_SERVERLESS_TOKEN=...
export ZILLIZ_TOWN_URI=https://...
export ZILLIZ_TOWN_TOKEN=...
python -c "from deploy.zilliz_client import ZillizClient; ZillizClient().health_check()"
```

### OpenShell Sandbox

```bash
bash deploy/openshell_setup.sh
openshell --version
```

## Relationship to NEXUS OS v3.0

This pack (`nexus25`) is a **complementary** package to the main `nexus_os` v3.0:

- **v3.0** (`src/nexus_os/`): Production — KAIJU governor, GMR 50+ model relay, vault, swarm, A2A bridge
- **nexus25**: Clean architecture — free-tier providers, tool registry, bridge contract, doctor diagnostics, workflow checkpoints, CLI, deploy scripts

Both packages coexist. Bridge imports wire them together as needed.
