# Nexus OS — MiMo v2.5 Pro Agent Guide

## What This Repo Is

**Nexus OS** is a unified agent platform with governance, provider routing, multi-platform gateway, and diagnostic tooling. It's a Python package (`nexus25`) that manages the full lifecycle of AI agent operations.

**Repository:** `specimba/mimo25-nexus` (branch: `mimo25-nexus-branch`)  
**Package:** `nexus25` (v0.1.0)  
**Python:** ≥3.11  
**Dependencies:** `pydantic>=2.0` (core), `pytest` (dev)

---

## Architecture Overview

```
nexus25/
├── cli/          → CLI interface (nexus25 command)
├── contracts/    → Task envelopes, evidence packets
├── doctor/       → Diagnostic system (5 pillars)
├── gateway/      → Multi-platform message dispatch
├── governance/   → Hooks, VAP chain, archivist
├── harness/      → Execution registry, runtime session
├── orchestration/ → Agent loop, workflow engine
├── providers/    → Provider catalog, rate limiter, router
├── recovery/     → Boot/recovery procedures
├── tools/        → Tool registry, permissions
└── bridge/       → External system contracts
```

---

## Key Concepts

### 1. Provider Routing
The `ProviderRouter` selects the best LLM provider+model based on:
- **Quality score** (0-100, from live testing)
- **Speed** (tokens/sec)
- **Context window** size
- **Tier** (free > freemium > paid)
- **Rate limits** (per-provider RPM/TPM)

**Route preferences:** `quality`, `speed`, `cost`, `balanced`

**Fallback chain:** `router.select_chain()` returns ordered candidates. Try each on 402/429/error.

### 2. Current Providers (8 total)

| Provider | Key Env Var | Models |
|---|---|---|
| **Kilo** | `KILO_API_KEY` (JWT) | 8 free models (best: ling-2.6-1t, step-3.5-flash) |
| **Groq** | `GROQ_API_KEY` | llama-3.3-70b, llama-3.1-8b, gemma2-9b |
| **Cerebras** | `CEREBRAS_API_KEY` | llama3.1-8b, llama3.1-70b |
| **OpenRouter** | `OPENROUTER_API_KEY` | llama-3.1-8b, mistral-7b, gemma-2-9b (free) |
| **Google** | `GOOGLE_API_KEY` | gemini-2.0-flash, gemini-1.5-flash |
| **HuggingFace** | `HF_TOKEN` | llama-3.1-70b HF |
| **GitHub** | `GITHUB_TOKEN` | gpt-4o-mini, llama-3.1-405b |
| **Mistral** | `MISTRAL_API_KEY` | mistral-small, codestral |

### 3. Governance
- **GovernanceHooks** — tool access control, token budget tracking, audit logging
- **VAPChain** — immutable SHA-256 hash chain for audit trail
- **Archivist** — artifact validation, promotion lifecycle (raw→proposal→reviewed→promoted)
- **TokenGuard** — reserve/commit/refund token lifecycle

### 4. Doctor Diagnostics
5 diagnostic pillars:
- **ProviderDoctor** — API key health, model availability
- **TokenDoctor** — budget usage, exhaustion warnings
- **ToolDoctor** — registry health, toolset breakdown
- **MemoryDoctor** — VAP chain integrity, artifact status
- **RuntimeDoctor** — session config, permission context, router state

### 5. CLI Commands
```
nexus25 status        → Provider count, tokens remaining, VAP validity
nexus25 providers     → List available models with scores
nexus25 doctor        → Full diagnostic report (all 5 pillars)
nexus25 doctor provider  → Provider-only diagnostics
nexus25 doctor token     → Token budget analysis
nexus25 task "brief"  → Create and validate a task envelope
nexus25 audit         → Show audit log
nexus25 verify        → Verify VAP chain integrity
nexus25 interactive   → REPL mode
```

---

## How to Run

```bash
cd nexus-os
pip install -e ".[dev]"
export KILO_API_KEY="your-jwt-token"
nexus25 status
nexus25 doctor
pytest tests/ -v
```

---

## How to Extend

### Add a New Provider
Edit `nexus25/providers/catalog.py`, add a `Provider(...)` with `Model(...)` entries to `_seed_defaults()`.

### Add a New Tool
```python
from nexus25.tools.registry import ToolRegistry, ToolDefinition

registry = ToolRegistry()
registry.register_function(
    name="my_tool",
    description="Does something",
    parameters={"type": "object", "properties": {...}},
    handler=my_function,
    toolset="custom",
)
```

### Add a New CLI Command
Edit `nexus25/cli/main.py`, add a `cmd_*` function and register it in `main()`.

### Custom Workflow
Use `WorkflowEngine` from `nexus25.orchestration.workflow` to build DAG-based agent workflows with checkpointing.

---

## Testing

66 smoke tests covering all modules:
```bash
pytest tests/ -v
```

**Note:** One test (`test_finds_no_available_when_no_keys`) assumes no API keys are set. Set keys after running tests, or expect this one to fail when keys are in the environment.

---

## File Count: 44 files, ~5,800 lines, ~208K characters
