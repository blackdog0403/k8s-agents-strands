# 00. References — Learning and Operations Materials

> 🌐 **Language**: **English** · [한국어](./00-references.ko.md)

This document indexes every reference, internal and external, in one place.
If you are new, work top to bottom.
Other documents inline-link to this page rather than to external URLs directly.

> This repo is a **reference project for running LLM agents on AWS.**
> The goal is to learn Strands, Bedrock AgentCore, EKS MCP, and related technologies through working code.
> Kubernetes RCA is the meaningful use case we built on top of those building blocks.

---

## Documents in this repo

| # | Document | One-line summary |
|---|----------|------------------|
| 00 | [References](./00-references.md) | This page — index of every external and internal material |
| 01 | [Getting Started](./01-getting-started.md) | Install, pre-flight, first run |
| 02 | [Architecture](./02-architecture.md) | Why the code is shaped this way |
| 03 | [Development Guide](./03-development.md) | Tutorials for adding new specialists / tools / MCP servers |
| 04 | [AgentCore Deployment](./04-deployment-agentcore.md) | Pattern 4, multi-cluster, operations |
| 05 | [Code Style](./05-code-style.md) | Readability principles and review criteria |
| 06 | [Security & Load](./06-security-and-load.md) | Layered defense and operations checklist |
| 07 | [Operations Runbook](./07-runbook.md) | 5-step on-call response procedures |

Recommended reading order: **01 → 02 → 03 → 04 → 06 → 05 → 07** (read the runbook once just before going to production).

---

## 1. Strands Agents SDK

The SDK that wires LLM agents to tools. In this project, `Agent`, `MCPClient`, and the `agents-as-tools` pattern all come from Strands.

| Resource | What it covers | Where it appears in this repo |
|----------|---------------|-------------------------------|
| [Strands home](https://strandsagents.com) | SDK overview and quickstart | README entry link |
| [Strands MCP Tools integration](https://strandsagents.com/docs/user-guide/concepts/tools/mcp-tools/index.md) | How `Agent(tools=[mcp_client])` works | `infrastructure/mcp_client.py`, `agents/pod_diagnostic.py` |
| [Strands → AgentCore deployment](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/index.md) | Pattern for moving a Strands app onto AgentCore Runtime | `agentcore_app.py`, [docs/04](./04-deployment-agentcore.md) |

A suggested first-time path:
1. Skim "Quick start" on the Strands home (5 minutes), then follow [01](./01-getting-started.md) here.
2. Read the MCP Tools page, then [02 §3.1](./02-architecture.md) "Strands MCP integration".
3. Read the AgentCore deployment page, then [04](./04-deployment-agentcore.md).

---

## 2. Amazon Bedrock and Bedrock AgentCore

| Resource | What it covers | Where it appears in this repo |
|----------|---------------|-------------------------------|
| [Bedrock console — model access](https://console.aws.amazon.com/bedrock/home#/modelaccess) | Enable Claude models | [01 §1, §7](./01-getting-started.md) |
| [Bedrock AgentCore VPC configuration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html) | VPC modes, endpoint requirements, ENI behavior, supported AZs | [04 §1](./04-deployment-agentcore.md), [06 §1](./06-security-and-load.md) |
| [Network connectivity patterns for AgentCore (blog)](https://aws.amazon.com/blogs/networking-and-content-delivery/network-connectivity-patterns-for-agents-deployed-on-amazon-bedrock-agentcore-runtime/) | **The source for the Pattern 1–4 naming** — Pattern 4 is the full VPC isolation topology | `deploy/agentcore/cdk_stack.py`, [04 §1](./04-deployment-agentcore.md), [06 §1](./06-security-and-load.md) |

> **The "Pattern 4 (full VPC isolation)" naming comes from the blog above**, not from the AgentCore VPC reference page. To be precise, this repo cites both sources together.

What this repo uses from Bedrock and AgentCore:

- **Bedrock** — Strands `Agent` calls Claude models (`bedrock:InvokeModel`)
- **Bedrock Guardrails** (optional) — Response filtering (`bedrock:ApplyGuardrail`); remove from policy if unused
- **AgentCore Runtime** — Containerized isolated execution; per-invocation microVM isolation
- **AgentCore Pattern 4** — Isolated VPC with no NAT, only VPC endpoints

---

## 3. Amazon EKS MCP Server

The path through which this repo retrieves K8s data.

| Resource | What it covers | Where it appears in this repo |
|----------|---------------|-------------------------------|
| [Amazon EKS MCP Server introduction](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-introduction.html) | Service overview, preview status, redaction behavior | [02 §3.1](./02-architecture.md), [04 §2](./04-deployment-agentcore.md), [06 §3](./06-security-and-load.md) |
| [Getting Started with Amazon EKS MCP Server](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html) | Endpoint URL format, IAM action names, `mcp-proxy-for-aws` usage | `deploy/agentcore/iam-execution-policy.json`, `infrastructure/mcp_client.py` |
| [aws/mcp-proxy-for-aws](https://github.com/aws/mcp-proxy-for-aws) | Official proxy that handles SigV4 signing for the managed MCP endpoint | [04 §2](./04-deployment-agentcore.md) |
| [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html) | Mapping IAM principals to K8s groups | `deploy/agentcore/eks-rbac.yaml` |

How EKS MCP is used here, in one sentence:

> The EKS MCP Server calls the K8s API on our behalf using our IAM credentials, and returns results to the LLM in the standard MCP tool-response format.
> That is why we do not import the `kubernetes` Python SDK directly.

For the detailed data flow, see the invocation lifecycle diagram in [02 §5](./02-architecture.md).

---

## 4. Model Context Protocol (MCP)

| Resource | What it covers |
|----------|---------------|
| [MCP official site](https://modelcontextprotocol.io/) | Protocol specification and client/server architecture |
| [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) | The Python SDK we depend on |

In one sentence:

> MCP is "a standardized RPC protocol for letting LLMs invoke tools safely."
> It runs JSON-RPC over stdio or HTTP.

---

## 5. Kubernetes Security

| Resource | What it covers |
|----------|---------------|
| [Kubernetes RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/) | Rationale for read-only ClusterRole design |
| [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) | Definition of the `restricted` profile |

This repo grants only a `read-only ClusterRole` to diagnosed clusters and explicitly excludes `secrets` (`deploy/agentcore/eks-rbac.yaml`).

---

## 6. LLM Security

| Resource | What it covers |
|----------|---------------|
| [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | Common threat taxonomy for LLM applications |

[06 §5](./06-security-and-load.md) maps OWASP LLM Top 10 categories to the layered defense in this project.

---

## 7. Python code style

| Resource | What it covers |
|----------|---------------|
| [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/) | Standard style guide |
| [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/) | Docstring rules |
| [Clean Code (Robert C. Martin)](https://www.oreilly.com/library/view/clean-code-a/9780136083238/) | Chapters 2 and 3 — names and functions |
| [The Art of Readable Code](https://www.oreilly.com/library/view/the-art-of/9781449318482/) | Practical examples of readability principles |

[05](./05-code-style.md) restates these for our domain (agents + MCP).

---

## 8. Learning paths — what you can take from this repo

| Interest | Start here | Follow with |
|----------|-----------|-------------|
| Building agents with Strands | [02 §3](./02-architecture.md) | Strands MCP Tools page |
| Operating Bedrock AgentCore | [04](./04-deployment-agentcore.md) | AgentCore VPC configuration page |
| MCP integration patterns | [02 §3.1](./02-architecture.md), [03 §3](./03-development.md) | MCP official site |
| K8s diagnostic automation | [01 §6](./01-getting-started.md), [03 §1](./03-development.md) | EKS MCP Server introduction |
| LLM security model | [06](./06-security-and-load.md) | OWASP LLM Top 10 |
| Readable AI-assisted code | [05](./05-code-style.md) | Clean Code chapters 2-3 |

---

[← README](../README.md) · [01. Getting Started →](./01-getting-started.md)
