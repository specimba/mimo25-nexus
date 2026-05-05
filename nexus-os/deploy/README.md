# Gastown / Zilliz / OpenShell — Deployment Scripts

Quick reference for the Nexus OS deployment toolkit.

---

## Scripts

| Script | Purpose |
|---|---|
| `gastown_quickstart.sh` | One-shot deploy: deps, .env, health check, boot |
| `zilliz_client.py` | Dual-cluster Zilliz vector client (serverless + town) |
| `openshell_setup.sh` | Install NVIDIA OpenShell CLI with Podman fallback |
| `mission_router.py` | Parse and route nexus-mission blocks |

---

## gastown_quickstart.sh

```bash
bash deploy/gastown_quickstart.sh [repo_path]
```

**What it does:**
1. Verifies/initializes git repo
2. Installs `pymilvus`, `python-dotenv`, `pydantic` via pip
3. Creates `.env` template with Zilliz cluster vars
4. Runs Zilliz client health check
5. Loads mission router module

**After running:** Edit `.env` with your actual Zilliz credentials.

---

## zilliz_client.py

```python
from zilliz_client import ZillizClient, TrackType

client = ZillizClient()

# Health check
status = client.health_check()

# Store an embedding
client.store_embedding(
    agent_id="nexus-01",
    lane="analysis",
    track_type=TrackType.EVENT,
    key="task:2024-001",
    value="Initial event embedding",
    embedding=[0.1, 0.2, ...],  # 768-dim float vector
)

# Search similar
results = client.similar_search(
    query_embedding=[0.1, 0.2, ...],
    track_type=TrackType.EVENT,
    top_k=5,
)
```

**Cluster mapping:**
- **Serverless** → EVENT, FAILURE_PATTERN tracks
- **Town** → TRUST, GOVERNANCE, CAPABILITY tracks

**Env vars required:**
```
ZILLIZ_SERVERLESS_URI
ZILLIZ_SERVERLESS_TOKEN
ZILLIZ_TOWN_URI
ZILLIZ_TOWN_TOKEN
```

**Features:** Thread-safe, auto-creates collections with COSINE metric, graceful degradation when pymilvus is missing.

---

## openshell_setup.sh

```bash
bash deploy/openshell_setup.sh
```

**What it does:**
1. Checks if OpenShell is already installed
2. Detects Docker or Podman; installs Podman if neither exists
3. Downloads and installs OpenShell CLI
4. Adds to PATH in shell RC file
5. Verifies with `openshell --version`

**Container runtime fallback:** Docker → Podman → auto-install Podman (apt/dnf/yum/brew).

---

## mission_router.py

```python
from mission_router import parse_mission_blocks, route_mission, execute_mission

text = """
/--- nexus-mission
name: Fix bug in auth module
mode: implementation
scope: Authentication flow
skills: python, security
deliverable: Patched auth.py
verification: Unit tests pass
/---
"""

blocks = parse_mission_blocks(text)
for block in blocks:
    decision = route_mission(block)
    result = execute_mission(block)
    print(result.output)
```

**Mission modes:** `research`, `design`, `implementation`, `verification`, `hygiene`

**Selection matrix (task shape → mode → agents → verification):**

| Shape | Mode | Default Agents | Verification |
|---|---|---|---|
| Open-ended | research | researcher, analyst | peer_review |
| Structured | implementation | engineer, coder | test_suite |
| Creative | design | designer, architect | design_review |
| Analytical | verification | auditor, reviewer | checklist |
| Maintenance | hygiene | maintainer, engineer | ci_pipeline |

---

## Verification

```bash
cd nexus-os
python -c "import ast; ast.parse(open('deploy/zilliz_client.py').read()); print('OK')"
python -c "import ast; ast.parse(open('deploy/mission_router.py').read()); print('OK')"
```
