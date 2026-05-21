# 03. Development Guide

> 🌐 **Language**: **English** · [한국어](./03-development.ko.md)

[← 02. Architecture](./02-architecture.md) · [04. AgentCore Deployment →](./04-deployment-agentcore.md)

This document is written as a **step-by-step tutorial that developers can follow to add new features**. Each section is self-contained, with code that actually runs.

| Task | Difficulty | Time | Section |
|------|-----------|------|---------|
| Add a new specialist agent | Medium | 30 min | [§1](#1-tutorial-adding-a-network-diagnostic-specialist) |
| Add a custom tool | Easy | 15 min | [§2](#2-tutorial-adding-a-custom-tool) |
| Integrate another MCP server | Medium | 30 min | [§3](#3-tutorial-integrating-another-mcp-server) |
| Extend the domain model | Hard | 1 hr | [§4](#4-extending-the-domain-model) |
| Write tests | Easy | as needed | [§5](#5-writing-tests) |

Each tutorial follows the same structure:

- **Goal** — what you will build
- **Steps** — 1, 2, 3 ...
- **Verification** — how to confirm it works
- **Common pitfalls**

---

## 1. Tutorial: Adding a Network Diagnostic Specialist

### Goal

Add a new specialist agent that diagnoses network-related incidents (Service connection failures, DNS, NetworkPolicy, etc.) and have the orchestrator route to it.

### Steps

#### Step 1. Create the specialist file

Create `src/k8s_rca_agent/agents/network_diagnostic.py`:

```python
"""Network-incident specialist agent."""
from __future__ import annotations

from strands import Agent

from k8s_rca_agent.infrastructure.container import container

NETWORK_DIAGNOSTIC_PROMPT = """\
You are a Kubernetes network-incident expert.
Use the K8s tools provided by the EKS MCP Server to investigate the following.

## Diagnostic procedure

Pass the ``cluster`` name from the invocation context to every MCP tool call.

1. **Service state** — check the Service's endpoints and selector match
2. **NetworkPolicy review** — look for blocking rules
3. **DNS** — CoreDNS state and resolution behavior
4. **Ingress** (if needed) — Ingress controller and routing rules

## Common symptoms and likely causes

| Symptom | Likely cause |
|---------|-------------|
| Connection refused | Service selector ≠ Pod label, Pod down |
| DNS resolution failure | CoreDNS issue, NetworkPolicy block |
| Timeout | NetworkPolicy deny, Pod CIDR routing issue |
| Ingress 503 | Backend Service unhealthy, TLS misconfiguration |

## Output format

Root cause → cluster/resources → evidence → recommended actions → confidence.
Mask any sensitive data you observe.
"""


def create_network_diagnostic_agent() -> Agent:
    return Agent(
        name="network_diagnostic",
        description=(
            "Diagnoses network-related incidents "
            "(Service connectivity, DNS, NetworkPolicy, Ingress). "
            "Caller must specify cluster, namespace, and resource name."
        ),
        system_prompt=NETWORK_DIAGNOSTIC_PROMPT,
        tools=[container.eks_mcp],
    )
```

#### Step 2. Export from `agents/__init__.py`

```python
from .network_diagnostic import create_network_diagnostic_agent
from .orchestrator import create_orchestrator
from .pod_diagnostic import create_pod_diagnostic_agent

__all__ = [
    "create_network_diagnostic_agent",
    "create_orchestrator",
    "create_pod_diagnostic_agent",
]
```

#### Step 3. Update orchestrator routing

`src/k8s_rca_agent/agents/orchestrator.py`:

```python
from .network_diagnostic import create_network_diagnostic_agent
from .pod_diagnostic import create_pod_diagnostic_agent

ORCHESTRATOR_PROMPT = """\
...
## Routing criteria

- **Pod symptoms** → `pod_diagnostic`
- **Network symptoms** (connection failures, DNS, Service, Ingress) → `network_diagnostic`
...
"""


def create_orchestrator() -> Agent:
    return Agent(
        name="rca_orchestrator",
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            create_pod_diagnostic_agent(),
            create_network_diagnostic_agent(),  # added
        ],
    )
```

#### Step 4. Smoke-test the import

```bash
python -c "from k8s_rca_agent.agents import create_network_diagnostic_agent; \
           agent = create_network_diagnostic_agent(); \
           print(f'OK: {agent.name}')"
```

Expected output: `OK: network_diagnostic`.

### Verification

#### 4.1 Single-import check

```bash
PYTHONPATH=src python -c "from k8s_rca_agent.agents import create_orchestrator; print('OK')"
```

#### 4.2 Routing check (real LLM call)

```bash
python -m k8s_rca_agent.main --cluster <your-cluster> \
  "I'm seeing connection refused for my-service in the default namespace, please investigate"
```

You should see a trace where the orchestrator calls `network_diagnostic`.

#### 4.3 Static checks

```bash
ruff check src/k8s_rca_agent/agents/
mypy src/k8s_rca_agent/agents/
```

### Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ImportError: cannot import name 'create_network_diagnostic_agent'` | `agents/__init__.py` not updated | Apply Step 2 |
| LLM never calls the new specialist, always pod_diagnostic | Routing criteria missing from orchestrator prompt | Verify the prompt update from Step 3 |
| The new specialist calls the wrong tool | System prompt is too vague | Make the symptom table more specific |

---

## 2. Tutorial: Adding a Custom Tool

### Goal

Add a single tool to one specialist for an action EKS MCP cannot perform (e.g., querying an external cost system).

### Steps

#### Step 1. Create the tool file

Create `src/k8s_rca_agent/tools/cost_tools.py`:

```python
"""Cost estimation tool — fetches data from an external system."""
from __future__ import annotations

import logging

from strands import tool

from k8s_rca_agent.domain.validation import (
    validate_cluster_name,
    validate_namespace,
    validate_resource_name,
)

logger = logging.getLogger(__name__)


@tool
def get_pod_cost_estimate(cluster: str, namespace: str, pod_name: str) -> dict:
    """Return the monthly cost estimate for a specific pod.

    Used to retrieve data from an external cost system that EKS MCP does
    not expose. Useful when an OOMKilled diagnosis recommends increasing
    memory and you want to surface the cost impact alongside the change.

    Args:
        cluster: Registered cluster name (e.g., "prod-us")
        namespace: Namespace
        pod_name: Pod name

    Returns:
        {
            "monthly_usd": float,
            "compute_usd": float,
            "memory_usd": float,
            "currency": "USD",
        }
    """
    cluster = validate_cluster_name(cluster)
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name)

    logger.info("cost lookup: cluster=%s ns=%s pod=%s", cluster, namespace, pod_name)

    # TODO: call the actual cost system (e.g., internal FinOps API)
    # Stub for now
    return {
        "monthly_usd": 12.34,
        "compute_usd": 8.00,
        "memory_usd": 4.34,
        "currency": "USD",
    }
```

#### Step 2. Export from `tools/__init__.py`

```python
from .cost_tools import get_pod_cost_estimate

__all__ = ["get_pod_cost_estimate"]
```

#### Step 3. Add to the specialist's tools

`src/k8s_rca_agent/agents/pod_diagnostic.py`:

```python
from k8s_rca_agent.infrastructure.container import container
from k8s_rca_agent.tools import get_pod_cost_estimate


def create_pod_diagnostic_agent() -> Agent:
    return Agent(
        ...,
        tools=[container.eks_mcp, get_pod_cost_estimate],  # both
    )
```

#### Step 4. Mention in the system prompt

```python
POD_DIAGNOSTIC_PROMPT = """\
...
## Cost-impact analysis (optional)

Before recommending an OOMKilled fix or memory limit increase, call the
``get_pod_cost_estimate`` tool to retrieve current cost and surface the
cost impact of the recommendation.
...
"""
```

### Verification

```bash
# 1) Tool registered?
python -c "from k8s_rca_agent.tools import get_pod_cost_estimate; \
           print(get_pod_cost_estimate.__doc__[:80])"

# 2) Validation works?
python -c "
from k8s_rca_agent.tools.cost_tools import get_pod_cost_estimate
result = get_pod_cost_estimate.func('prod-us', 'default', 'nginx')
assert result['currency'] == 'USD'
print('OK')
"
```

### Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| LLM never calls the tool | Vague docstring | Spell out *when* to use this tool |
| `AttributeError: 'function' object has no attribute 'func'` | `@tool` decorator not applied | Check the import path |
| Validation errors invisible to the LLM | Vague exception message | Make `ValueError` messages explicit |

### Tool-author checklist

- [ ] Docstring is clear enough for the LLM to pick the tool
- [ ] All parameters have type hints
- [ ] Inputs go through `validate_*`
- [ ] Side-effecting (write) operations are separated from read-only ones
- [ ] Errors carry messages an LLM can act on

---

## 3. Tutorial: Integrating Another MCP Server

### Goal

Add a Prometheus MCP server alongside EKS MCP so the LLM can also reason about metrics.

### Steps

#### Step 1. Add a factory in `mcp_client.py`

`src/k8s_rca_agent/infrastructure/mcp_client.py`:

```python
def create_prometheus_mcp_client():
    """Prometheus MCP client.

    Requires the ``PROMETHEUS_MCP_ENDPOINT`` environment variable (HTTP transport).
    """
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    endpoint = os.getenv("PROMETHEUS_MCP_ENDPOINT")
    if not endpoint:
        raise ValueError("PROMETHEUS_MCP_ENDPOINT is not set")

    logger.info("Prometheus MCP starting — endpoint=%s", endpoint)
    return MCPClient(lambda: streamablehttp_client(endpoint))
```

#### Step 2. Register on the container

`src/k8s_rca_agent/infrastructure/container.py`:

```python
from .mcp_client import create_eks_mcp_client, create_prometheus_mcp_client


class Container:
    @cached_property
    def eks_mcp(self):
        return create_eks_mcp_client()

    @cached_property
    def prometheus_mcp(self):
        return create_prometheus_mcp_client()
```

#### Step 3. Add to the specialist that needs it

If you create a `resource_diagnostic` specialist:

```python
# agents/resource_diagnostic.py
return Agent(
    name="resource_diagnostic",
    ...,
    tools=[container.eks_mcp, container.prometheus_mcp],  # both
)
```

Strands automatically exposes tools from both MCP servers to the LLM.

#### Step 4. If tool names collide

Should two MCP servers expose tools with the same name (rare), use Strands `MCPClient`'s prefix option — see [Strands MCP integration](./00-references.md#1-strands-agents-sdk).

### Verification

```bash
PROMETHEUS_MCP_ENDPOINT=http://localhost:9090/mcp \
python -c "from k8s_rca_agent.infrastructure.container import container; \
           print(container.prometheus_mcp)"
```

### Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ValueError: PROMETHEUS_MCP_ENDPOINT is not set` | Env var missing | `export PROMETHEUS_MCP_ENDPOINT=...` |
| MCP server auth failure | Missing SigV4 or token | Use the right transport for the server type |
| Tool name collision | Same names as EKS MCP | Apply a prefix |

---

## 4. Extending the Domain Model

### Goal

Extend `Diagnosis` to include cost information.

### Steps

#### Step 1. Update the domain model

`src/k8s_rca_agent/domain/models.py`:

```python
@dataclass(frozen=True)
class CostImpact:
    monthly_usd: float
    description: str  # e.g., "Memory limit 1Gi → 2Gi adds +$8/mo"


@dataclass(frozen=True)
class Diagnosis:
    root_cause: str
    affected_resources: list[str]
    confidence: float
    recommended_actions: list[str]
    evidence: list[str]
    summary: str = ""
    cost_impact: CostImpact | None = None  # added

    def to_dict(self) -> dict:
        result = {
            "root_cause": self.root_cause,
            "affected_resources": self.affected_resources,
            "confidence": self.confidence,
            "recommended_actions": self.recommended_actions,
            "evidence": self.evidence,
            "summary": self.summary,
        }
        if self.cost_impact:
            result["cost_impact"] = {
                "monthly_usd": self.cost_impact.monthly_usd,
                "description": self.cost_impact.description,
            }
        return result
```

#### Step 2. Add tests

`tests/domain/test_models.py`:

```python
def test_diagnosis_with_cost_impact():
    cost = CostImpact(monthly_usd=8.0, description="memory increase")
    d = Diagnosis(
        root_cause="OOMKilled", affected_resources=["pod/api"], confidence=0.85,
        recommended_actions=["bump memory limit to 2Gi"], evidence=[], summary="",
        cost_impact=cost,
    )
    out = d.to_dict()
    assert out["cost_impact"]["monthly_usd"] == 8.0


def test_diagnosis_without_cost_impact_omits_field():
    d = Diagnosis(
        root_cause="x", affected_resources=[], confidence=0.5,
        recommended_actions=[], evidence=[],
    )
    assert "cost_impact" not in d.to_dict()
```

### Verification

```bash
pytest tests/domain/test_models.py -v
```

### Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TypeError: __init__() missing 1 required positional argument` | Added a required field to a dataclass | Use `= None` for the new field |
| Existing tests fail | dict format changed | Be careful with tests that compare with `==` |

---

## 5. Writing Tests

| Layer | Approach | Notes |
|-------|----------|-------|
| `domain/` (models, validation) | Pure unit tests | No external deps, fast |
| `infrastructure/redaction.py` | Unit tests | I/O assertions |
| `infrastructure/mcp_client.py` | Unit tests with mocks; integration when needed | Real MCP server when integration |
| `agents/` | Integration tests | Real LLM or mock LLM |

### Quick unit test — no external deps

```python
# tests/domain/test_validation.py
def test_validate_cluster_name_rejects_path_traversal():
    with pytest.raises(InvalidResourceName):
        validate_cluster_name("../etc/passwd")
```

### Mock-based unit test

```python
# tests/agents/test_pod_diagnostic.py
def test_pod_diagnostic_uses_mcp(mocker):
    mock_mcp = mocker.MagicMock()
    mocker.patch(
        "k8s_rca_agent.infrastructure.container.container.eks_mcp",
        mock_mcp,
    )
    agent = create_pod_diagnostic_agent()
    assert mock_mcp in agent.tools
```

### Run

```bash
pytest tests/ -v
pytest tests/domain/ -v        # domain only
pytest -k cluster              # by keyword
pytest --cov=k8s_rca_agent     # coverage
```

---

## 6. Quality automation

### Ruff (lint and format)

```bash
ruff check src tests           # check
ruff check src tests --fix     # auto-fix
ruff format src tests          # format
```

### mypy

```bash
mypy src
```

### pre-commit (recommended — runs on commit)

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
```

```bash
pip install pre-commit
pre-commit install
```

---

## 7. General development workflow

```
[1] Starting work — what kind of change?

  Tool only           → §2 (15 min)
  New specialist      → §1 (30 min)
  Add an MCP server   → §3 (30 min)
  Domain change       → §4 (1 hr)

[2] Write the code

  - Tests first (TDD), or
  - Code → tests (faster path)

[3] Verify (every change)

  pytest tests/
  ruff check src tests
  mypy src

[4] Local integration check (optional)

  python -m k8s_rca_agent.main --cluster <c> "relevant scenario"

[5] Entrypoint check (just before deploy)

  python -m k8s_rca_agent.agentcore_app
  curl localhost:8080/invocations -d '{...}'

[6] PR
  - Is the intent visible in 5 seconds?
  - Is the abstraction justified?
  - Did a human read the AI-assisted lines line by line?
```

---

## Next

- Production deployment → [04. AgentCore Deployment](./04-deployment-agentcore.md)
- Readability principles and review criteria → [05. Code Style](./05-code-style.md)
- Security model and operations checklist → [06. Security & Load](./06-security-and-load.md)

## Going deeper

- Schema extraction by Strands `@tool` — [Strands MCP Tools](./00-references.md#1-strands-agents-sdk)
- How to write your own domain MCP server — [MCP official site](./00-references.md#4-model-context-protocol-mcp)

---

[← 02. Architecture](./02-architecture.md) · [04. AgentCore Deployment →](./04-deployment-agentcore.md)
