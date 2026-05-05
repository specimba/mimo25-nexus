# NEXUS OS

Unified agent platform with governance, provider routing, and multi-platform gateway.

## Quick Start

```bash
cd nexus-os
pip install -e ".[dev]"
pytest tests/ -v
nexusctl status
nexusctl providers
nexusctl interactive
```

## Architecture

```
nexus_os/
├── providers/       # Smart LLM provider routing (7 free-tier providers)
│   ├── catalog.py   # Provider metadata (Groq, Cerebras, OpenRouter, Google, HF, GitHub, Mistral)
│   ├── rate_limiter.py  # Sliding-window rate tracking
│   └── router.py    # Quality/speed/cost-aware routing
├── tools/           # Permission-aware tool registry
│   ├── permissions.py   # Trust levels (untrusted → red_team)
│   └── registry.py      # OpenAI function-calling schema, dispatch with audit
├── governance/      # nexusalpha governance integration
│   ├── hooks.py     # Governor check + TokenGuard budget
│   ├── vap_chain.py # SHA-256 immutable audit chain
│   └── archivist.py # Mythos integrity gate + promotion pipeline
├── gateway/         # Multi-platform message dispatch
│   └── core.py      # Session management, command routing
├── orchestration/   # Agent workflows
│   ├── agent_loop.py    # Sequential tool-use loop
│   └── workflow.py      # DAG engine with checkpoints + human-in-the-loop
├── harness/         # Session bootstrap
│   ├── execution_registry.py  # Command/tool execution tracking
│   └── runtime_session.py     # One-call bootstrap wiring all subsystems
├── contracts/       # Structured task/evidence schemas
│   ├── task_envelope.py   # High-capability task dispatch contracts
│   └── evidence_packet.py # Evidence with promotion tracking
└── cli/             # nexusctl CLI
    └── main.py      # status, providers, audit, verify, task, interactive
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `nexusctl status` | System status (providers, tokens, VAP chain) |
| `nexusctl providers` | List available LLM providers |
| `nexusctl audit` | Show governance audit log |
| `nexusctl verify` | Verify VAP chain integrity |
| `nexusctl task <brief>` | Submit a task envelope |
| `nexusctl interactive` | Interactive REPL |

## Programmatic Usage

```python
from nexus_os.harness.runtime_session import RuntimeSession, RuntimeConfig
from nexus_os.tools.permissions import TrustLevel

# Bootstrap a full session
session = RuntimeSession.bootstrap(RuntimeConfig(
    trust_level=TrustLevel.STANDARD,
    lane="local",
    strict_governance=False,
))

# Register tools
session.tools.register_function("greet", "Greet someone", 
    {"type": "object", "properties": {"name": {"type": "string"}}},
    lambda name="": f"Hello, {name}!")

# Dispatch
result = session.tools.dispatch("greet", {"name": "NEXUS"})
print(result.output)  # "Hello, NEXUS!"

# Verify audit chain
print(session.vap.verify())  # True
```

## Provider Routing

```python
from nexus_os.providers.router import ProviderRouter

router = ProviderRouter()
result = router.select(min_context=32_000, prefer="quality")
if result:
    print(f"{result.provider.name}/{result.model.id} — {result.reason}")
```

## Governance

```python
from nexus_os.governance.hooks import GovernanceHooks

gov = GovernanceHooks(strict=False, token_budget=50_000)
decision = gov.check_tool_access("read_file")
print(decision.decision)  # DecisionType.ALLOWED

gov.track_tokens(1000)
print(gov.tokens_remaining)  # 49000
```
