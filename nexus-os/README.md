# NEXUS 25 — Agent Pack

Clean-room agent platform with free-tier provider routing, tool registry, governance, and deployment-ready scripts. Designed to complement the main NEXUS OS v3.0 codebase.

## Quick Start

```bash
cd nexus-os
pip install -e ".[dev]"
pytest tests/ -v
nexus25 status
nexus25 providers
nexus25 interactive
```

## One-Shot Gastown Deploy

```bash
bash deploy/gastown_quickstart.sh
```

## Architecture

```
nexus25/
├── providers/             # 7 free-tier LLM providers + rate limiter + smart router
│   ├── catalog.py         # Groq, Cerebras, OpenRouter, Google, HF, GitHub, Mistral
│   ├── rate_limiter.py    # Sliding-window RPM + TPM tracking
│   └── router.py          # Quality/speed/cost/balanced scoring
├── tools/                 # Permission-aware tool registry
│   ├── permissions.py     # Trust levels (untrusted → red_team)
│   └── registry.py        # OpenAI function-calling schema, dispatch with audit
├── governance/            # Archivist integrity gate
│   ├── hooks.py           # Governor check + token budget + audit chain
│   ├── vap_chain.py       # SHA-256 immutable audit chain
│   └── archivist.py       # Mythos artifact validation + promotion pipeline
├── gateway/               # Multi-platform message dispatch
│   └── core.py            # Session management, command routing
├── orchestration/         # Agent workflows
│   ├── agent_loop.py      # Sequential tool-use loop with provider routing
│   └── workflow.py        # DAG engine: edges, NodeType, checkpoints, HITL
├── harness/               # Session bootstrap
│   ├── execution_registry.py  # Command/tool execution tracking
│   └── runtime_session.py     # One-call bootstrap wiring all subsystems
├── contracts/             # Structured task/evidence schemas
│   ├── task_envelope.py   # High-capability task dispatch contracts
│   └── evidence_packet.py # Evidence with promotion tracking
└── cli/                   # nexus25 CLI
    └── main.py            # status, providers, audit, verify, task, interactive

deploy/
├── gastown_quickstart.sh  # One-shot Gastown deployment
├── zilliz_client.py       # Dual-cluster Zilliz vector memory client
├── openshell_setup.sh     # NVIDIA OpenShell CLI installer
├── mission_router.py      # Mission routing protocol parser
└── README.md              # Deploy quick reference
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `nexus25 status` | System status (providers, tokens, VAP chain) |
| `nexus25 providers` | List available LLM providers |
| `nexus25 audit` | Show governance audit log |
| `nexus25 verify` | Verify VAP chain integrity |
| `nexus25 task <brief>` | Submit a task envelope |
| `nexus25 interactive` | Interactive REPL |

## Programmatic Usage

```python
from nexus25.harness.runtime_session import RuntimeSession, RuntimeConfig

session = RuntimeSession.bootstrap(RuntimeConfig(strict_governance=False))

session.tools.register_function("greet", "Greet someone",
    {"type": "object", "properties": {"name": {"type": "string"}}},
    lambda name="": f"Hello, {name}!")

result = session.tools.dispatch("greet", {"name": "NEXUS"})
print(result.output)  # "Hello, NEXUS!"
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

### Mission Routing

```python
from deploy.mission_router import MissionRouter
router = MissionRouter()
result = router.parse(mission_text)
print(result["mode"], result["agents"])
```

## Relationship to NEXUS OS v3.0

This pack (`nexus25`) is a **complementary** package to the main `nexus_os` v3.0 codebase:

- **v3.0** (`src/nexus_os/`): Production infrastructure — KAIJU governor, GMR 50+ model relay, vault/5-track memory, swarm, A2A bridge
- **nexus25**: Clean architecture — free-tier providers, tool registry, contracts, workflow checkpoints, CLI, deployment scripts

Both packages coexist. Bridge imports wire them together as needed.
