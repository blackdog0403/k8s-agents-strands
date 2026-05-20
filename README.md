# k8s-agents-strands

> 🌐 **Language**: **English** · [한국어](./README.ko.md)

An AI agent that automates **root cause analysis (RCA)** for Kubernetes cluster incidents.

The agent is built with the [Strands Agents SDK](https://strandsagents.com), pulls cluster data through the [Amazon EKS MCP Server](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-introduction.html), and runs in production on the [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html) under Pattern 4 (full VPC isolation).

> **Operating principle**: even when AI tooling helps write the code, **we do not ship code that humans cannot read line by line.**
> Reach for proven SDKs and MCP servers first, and write our own implementation only when truly necessary. The full criteria are in [05-code-style.md](./docs/05-code-style.md).

---

## Quick start (local)

```bash
# 1) Clone & install
git clone <repository-url>
cd k8s-agents-strands
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2) Pre-flight checks
aws sts get-caller-identity                              # AWS auth
aws bedrock list-foundation-models --region us-west-2    # Bedrock model access
uvx awslabs.eks-mcp-server@latest --help                 # EKS MCP boots

# 3) First query
python -m k8s_rca_agent.main --cluster <your-eks-cluster> \
  "Check the status of the nginx pod in the default namespace"
```

For the full walkthrough, see [01-getting-started.md](./docs/01-getting-started.md).

---

## Architecture at a glance

```
User / AgentCore payload   { query, cluster }
        │
        ▼
   Orchestrator Agent
        │   (routing)
        ▼
   Specialist Agent
   (Pod / Network / ...)
        │   tools = [eks_mcp]
        ▼
   EKS MCP Server (AWS managed)
        │   SigV4 + EKS API
        ▼
   EKS cluster
```

11 source files. Three core patterns: Strands MCP integration, Multi-Agent (agents-as-tools), and the Bedrock AgentCore Runtime.

---

## Repository layout

```
k8s-agents-strands/
├── README.md                      # English (this file)
├── README.ko.md                   # Korean
├── pyproject.toml
├── deploy/
│   └── agentcore/                 # AgentCore Pattern 4 deployment manifests
│       ├── Dockerfile
│       ├── cdk_stack.py
│       ├── iam-execution-policy.json
│       ├── resource-policy.json
│       ├── eks-rbac.yaml
│       └── README.md
├── docs/
│   ├── 00-references.md
│   ├── 01-getting-started.md
│   ├── 02-architecture.md
│   ├── 03-development.md
│   ├── 04-deployment-agentcore.md
│   ├── 05-code-style.md
│   ├── 06-security-and-load.md
│   └── 07-runbook.md
├── src/k8s_rca_agent/
│   ├── domain/
│   │   ├── models.py              # Diagnosis domain model
│   │   └── validation.py          # Input sanity checks
│   ├── infrastructure/
│   │   ├── mcp_client.py          # EKS MCP client factory
│   │   ├── container.py           # DI container
│   │   ├── metrics.py             # CloudWatch EMF emitter
│   │   └── redaction.py           # Secret-pattern masking utility
│   ├── agents/
│   │   ├── orchestrator.py        # Routing + synthesis
│   │   └── pod_diagnostic.py      # Pod diagnosis specialist
│   ├── tools/                     # Custom tools (currently empty)
│   ├── agentcore_app.py           # AgentCore Runtime entrypoint
│   └── main.py                    # Local CLI entrypoint
└── tests/
```

---

## Documentation

| Doc | Audience | Contents |
|-----|----------|----------|
| [00. References](./docs/00-references.md) | Everyone | Index of Strands · Bedrock · AgentCore · MCP · K8s materials |
| [01. Getting Started](./docs/01-getting-started.md) | Newcomers | Install, pre-flight, 4-tier local testing |
| [02. Architecture](./docs/02-architecture.md) | Readers | MCP-first design, data flow, invocation lifecycle |
| [03. Development Guide](./docs/03-development.md) | Contributors | Tutorials for adding specialists / tools / MCP servers |
| [04. AgentCore Deployment](./docs/04-deployment-agentcore.md) | Operators | Pattern 4, EKS MCP, multi-cluster mapping |
| [05. Code Style](./docs/05-code-style.md) | All contributors | Readability principles and review criteria |
| [06. Security & Load](./docs/06-security-and-load.md) | Security / SRE reviewers | Layered defense and operations checklist |
| [07. Operations Runbook](./docs/07-runbook.md) | On-call engineers | 5-step response procedures per alarm scenario |

Recommended reading order: **01 → 02 → 03 → 04 → 06 → 05 → 07**.
External references (Strands, Bedrock AgentCore, EKS MCP, etc.) live in [00. References](./docs/00-references.md).

> Korean translations live next to each English document as `*.ko.md` (e.g. `README.ko.md`, `CONTRIBUTING.ko.md`). Doc-level Korean translations under `docs/` are being added in subsequent PRs — until then, the English versions under `docs/` are the source of truth.

---

## What you can learn from this repository

This repo is a **reference project for running LLM agents on AWS**. The Kubernetes RCA use case is a meaningful demonstration of the underlying capabilities; the deeper learning value is in the patterns themselves.

| Interest | Start here | Where to look in code |
|----------|-----------|----------------------|
| Building agents with Strands | [02. Architecture §3](./docs/02-architecture.md) | `agents/orchestrator.py`, `agents/pod_diagnostic.py` |
| Operating Bedrock AgentCore | [04. AgentCore Deployment](./docs/04-deployment-agentcore.md) | `agentcore_app.py`, `deploy/agentcore/cdk_stack.py` |
| MCP integration patterns | [02 §3.1](./docs/02-architecture.md) | `infrastructure/mcp_client.py` |
| K8s diagnostic automation | [01 §6](./docs/01-getting-started.md) | The system prompt in `agents/pod_diagnostic.py` |
| LLM security model | [06. Security & Load](./docs/06-security-and-load.md) | `deploy/agentcore/iam-execution-policy.json`, `eks-rbac.yaml` |
| Readable AI-assisted code | [05. Code Style](./docs/05-code-style.md) | The whole repo — code is intentionally short and flat |

---

## Core design principles

1. **We do not ship code we do not understand.** AI assistance is fine; line-by-line review is required.
2. **MCP and SDKs first.** Anything Strands or EKS MCP can do, we do not reimplement.
3. **Code that reveals intent in five seconds.** Six months from now, you must still be able to read it instantly.
4. **The domain layer has no external dependencies.** We do not couple business models to SDK changes.
5. **Least privilege everywhere.** Read-only RBAC, IAM resource ARNs explicitly listed.
6. **The network is isolated.** AgentCore Pattern 4, communicating only via VPC endpoints.
7. **Defense in depth.** A failure in one layer must not break the whole system.
8. **Extension must be simple.** Adding a new specialist or MCP server should be a one-file change.

---

## How this differs from a generic LLM chatbot

| Capability | Generic chatbot | This project |
|------------|----------------|--------------|
| K8s data access | None | Real-time via EKS MCP |
| Permission control | Hard | EKS RBAC + IAM separation |
| Security isolation | At risk of exposure | AgentCore Pattern 4 |
| Cost control | Hard | Per-invocation + Bedrock Guardrails |
| Extensibility | Single prompt | Specialist agents + MCP composition |

---

## Contributing

This is an open-source project and contributions are welcome.

- Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before starting (Korean: [CONTRIBUTING.ko.md](./CONTRIBUTING.ko.md)).
- All participants follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
- If this is your first contribution, look for issues labeled `good first issue`.

## License

Released under the [Apache License 2.0](./LICENSE). Third-party license attributions are in [NOTICE](./NOTICE).
