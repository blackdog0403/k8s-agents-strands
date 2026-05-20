# 02. Architecture

> 🌐 **Language**: **English** · [한국어](./02-architecture.ko.md)

[← 01. Getting Started](./01-getting-started.md) · [03. Development Guide →](./03-development.md)

This document explains **why the code is shaped this way.**
Three-line summary:

1. We use [Strands Agents SDK](./00-references.md#1-strands-agents-sdk) to wire LLM agents to tools.
2. K8s data is fetched by the [EKS MCP Server](./00-references.md#3-amazon-eks-mcp-server) — we never call the K8s API directly.
3. In production, we run on [Bedrock AgentCore Runtime](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore) under Pattern 4 (full VPC isolation).

Rather than implementing things ourselves, we delegate responsibility to vetted components. The code we write focuses on **the diagnostic workflow (which tools to call in what order)** and **the domain semantics (system prompts and the diagnosis model)**.

---

## 1. At a glance

```
              User / AgentCore payload
                       │   { query, cluster }
                       ▼
              ┌──────────────────────┐
              │ Orchestrator Agent   │
              │ (routing + synthesis)│
              └──────────┬───────────┘
                         │  delegates to specialist
                         ▼
              ┌──────────────────────┐
              │ Pod Diagnostic Agent │
              │  tools = [eks_mcp]   │
              └──────────┬───────────┘
                         │  MCP tool calls
                         ▼
              ┌──────────────────────┐
              │   EKS MCP Server     │
              │   (AWS managed)      │
              └──────────┬───────────┘
                         │  SigV4 + EKS API
                         ▼
                    EKS cluster
```

Three layers — Agent, MCP Server, EKS.

---

## 2. Layout

```
src/k8s_rca_agent/
├── domain/
│   ├── models.py          # Diagnosis (output domain model)
│   └── validation.py      # cluster, namespace, resource name input checks
├── infrastructure/
│   ├── mcp_client.py      # EKS MCP client factory (stdio | http)
│   ├── container.py       # DI container (singleton MCP client)
│   ├── metrics.py         # CloudWatch EMF metrics emitter
│   └── redaction.py       # Secret-pattern masking utility
├── agents/
│   ├── orchestrator.py    # User → specialist routing
│   └── pod_diagnostic.py  # Pod diagnosis specialist
├── tools/                 # Custom @tool functions (currently empty)
├── agentcore_app.py       # AgentCore Runtime entrypoint
└── main.py                # Local CLI entrypoint
```

11 source files. Down from 17 before the EKS MCP migration — almost half.

---

## 3. Patterns applied

### 3.1 Strands MCP integration

`Agent(tools=[mcp_client])` is the entire integration. `MCPClient` handles connect, list_tools, tool calls, and disconnect automatically — see [Strands MCP Tools docs](./00-references.md#1-strands-agents-sdk).

```python
# infrastructure/mcp_client.py
def create_eks_mcp_client():
    transport = os.getenv("EKS_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        return _create_stdio_client()      # Local dev: uvx child process
    return _create_http_client()           # Managed: AWS-hosted endpoint
```

### 3.2 Multi-Agent — agents-as-tools

The orchestrator calls specialist agents as if they were tools. This is the recommended Strands pattern.

```python
# agents/orchestrator.py
return Agent(
    name="rca_orchestrator",
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[create_pod_diagnostic_agent()],   # the specialist itself becomes a tool
)
```

### 3.3 Input validation (shallow sanity check)

`domain/validation.py` validates only the *format* of cluster_name, namespace, and resource names. Permission checks belong to IAM, and resource existence belongs to EKS MCP — we just reject obviously malformed inputs early.

### 3.4 Post-processing redaction (reserved)

`infrastructure/redaction.py` provides a token/password pattern masking utility. The current first line of defense is the specialist's system prompt; `redact()` is reserved for layered defense — see [06 §6](./06-security-and-load.md) for the policy.

---

## 4. Dependency direction

```
agents → tools → infrastructure → domain
                                    ▲
                                  no outward
                                  dependencies
```

- `domain` — no third-party imports
- `infrastructure` — uses `mcp`, `boto3`, etc.
- `agents` — gets the MCP client through `infrastructure.container`
- `tools` — for our specialized tools when they exist (currently empty)

Keep this direction intact and the domain code stays safe even when internal implementations change.

---

## 5. Application flow

This section traces a request from arrival to response. The focus is on what is useful for real-world debugging and operations.

### 5.1 Per-entrypoint comparison

There are two entrypoints — local CLI and AgentCore Runtime. Both call the same orchestrator.

```
[Local CLI]                              [AgentCore Runtime]
python -m k8s_rca_agent.main             POST /invocations
        │                                       │
        ▼                                       ▼
  argparse(--cluster, query)            BedrockAgentCoreApp
        │                                       │
        ▼                                       ▼
  run_once / run_interactive            @app.entrypoint(invoke)
        │                                       │
        └──────────┐               ┌────────────┘
                   ▼               ▼
               create_orchestrator()
                       │
                       ▼
               orchestrator(f"[cluster={c}] {query}")
                       │
                       ▼
               (continues — see §5.2)
```

The differences are entry and response format only.

| Item | Local CLI | AgentCore |
|------|-----------|-----------|
| Input | argparse | JSON payload |
| Output | stdout | JSON response |
| Lifecycle | One process, interactive | One microVM per invocation |
| Mistake validation | argparse schema | `_build_query()` |

### 5.2 A single invocation lifecycle

When AgentCore receives one call:

```
1. AgentCore Runtime boots a microVM (cold) or reuses one (warm)
   │
   ├─ cold: create microVM → load image → start BedrockAgentCoreApp
   └─ warm: route to an existing microVM
   │
   ▼
2. /invocations POST arrives → @app.entrypoint(handler) is invoked
   │
   ▼
3. invoke(payload) runs
   ├─ _build_query: extract and validate query, cluster
   └─ orchestrator = create_orchestrator()    ← fresh per invocation
   │
   ▼
4. orchestrator(user_message) — Strands Agent loop starts
   │
   ├─ LLM call 1: "Which specialist should I delegate to?"
   │            → pod_diagnostic
   │
   ▼
5. pod_diagnostic_agent(<routed message>)
   │
   ├─ MCP client lazily connects
   │   └─ stdio: spawn uvx child process (cold only)
   │       or
   │   └─ http: open streamable_http connection + (proxy) SigV4 sign
   │
   ├─ Receive list_tools() from MCP, expose to LLM
   │
   ├─ LLM call 2: "Which tool should I use?"
   │            → get_pod
   │
   ├─ MCP tool execution: get_pod(cluster=..., namespace=..., name=...)
   │   └─ EKS MCP server → eks:DescribeCluster → K8s API → response
   │
   ├─ LLM call 3: see response, decide next step
   │            "I need events too" → get_pod_events
   │
   ├─ ... (tool calls repeat as needed)
   │
   └─ LLM call N: enough info gathered → final response
   │
   ▼
6. The orchestrator's LLM synthesizes the specialist's result into the final answer
   │
   ▼
7. invoke() returns: {"response": "...", "cluster": "..."}
   │
   ▼
8. AgentCore returns the JSON response
   │
   ▼
9. The microVM is retained for reuse or discarded (AgentCore decides)
```

Three things to remember:

- **Fresh orchestrator every invocation** — state never leaks between invocations.
- **Lazy MCP connect** — the connection is established on first tool call and torn down at end of invocation.
- **The LLM calls tools many times** — 5 to 10 times in one invocation is common.

### 5.3 One tool-call cycle in detail

```
LLM decides to call a tool
    │  {"tool": "get_pod", "args": {...}}
    ▼
Strands SDK validates args (schema derived from the tool's type hints)
    │
    ▼
MCPClient sends an RPC request to the MCP server
    │  JSON-RPC over stdio or streamable HTTP
    ▼
EKS MCP Server calls the EKS API with SigV4
    │
    ▼
The response flows back
    EKS API → MCP server → MCPClient → Strands → LLM context
    │
    ▼
The LLM looks at the response and decides the next action
```

Almost none of this is our code. Strands SDK and MCP handle it.

### 5.4 Error flow

| Where the error originates | What happens | User experience |
|---------------------------|--------------|----------------|
| Missing query/cluster in `_build_query` | `ValueError` → AgentCore 4xx | "Field is empty" message |
| LLM produced malformed tool args | Strands schema validation fails | LLM retries automatically |
| MCP transient failure (5xx, throttle) | MCP client retries | Slightly longer invocation |
| MCP permanent failure (4xx no permission) | Tool returns an error message | LLM tells the user about the permission issue |
| EKS RBAC blocks (e.g., secrets read) | 403 → MCP tool error message | LLM responds "I do not have permission to view that" |
| LLM hallucinates a non-existent tool | Strands rejects → LLM retries | No user impact |
| Bedrock throttling | Strands retries | Slightly longer invocation |
| AgentCore timeout | Invocation ends | "Analysis is taking too long, narrow your question and retry" |

The key idea: **errors are also delivered to the LLM in natural language, so the LLM can attempt to recover automatically.** That is why we rarely need try/except in our code.

### 5.5 Cold and warm start cost

```
[Cold start — first invocation, or after microVM refresh]

  microVM boot, container start, Python import, BedrockAgentCoreApp boot
  happen in sequence. The user feels some additional latency.

  [On the first tool call]
  MCP stdio: cost of booting uvx
  MCP http: cost of opening streamable_http + list_tools()

[Warm — microVM reuse]
  Invocation starts almost immediately
  MCP reconnects per invocation (microVM isolation)
```

Operational tips:

- With steady traffic, warm state is preserved and cold start barely shows.
- MCP reconnects every invocation (microVM isolation). HTTP transport is consistently faster than stdio.
- The diagnosis itself takes 5–30 seconds because of multiple LLM calls — a 1–2 second cold start is not the bottleneck.

---

## 6. FAQ

### Q. Why not use the `kubernetes` Python SDK directly?

EKS MCP Server already does this well. If we rolled our own, we would have to implement all of:

- Auth, token refresh, caching, retry, multi-cluster routing
- Reactions to K8s API changes
- Loss of the MCP standard's benefits (compose with other MCP servers)

### Q. Where did `ClusterRegistry` go?

When we called K8s directly, we needed `cluster_name → endpoint` mapping. EKS MCP handles that within IAM scope — only clusters that the AgentCore execution role has access to are reachable.

### Q. Why drop the `PodSnapshot` domain model?

Passing the MCP response to the LLM as a dict is enough. Domain semantics like `is_healthy` come from the system prompt. When real business logic appears (e.g., synthesizing a diagnosis), we will reintroduce a domain model.

### Q. Why split off specialist agents?

It is the recommended Strands pattern, and it keeps each domain's system prompt narrow. Adding a Network or Resource Diagnostic Agent later only requires updating the orchestrator.

---

## 7. When to extend

- **New specialist** (Network, Resource, etc.) → add `agents/<domain>_diagnostic.py`, register in the orchestrator's `tools` ([03 §1](./03-development.md))
- **Custom tool** (something MCP cannot do) → add `@tool` in `tools/`, attach to specialist `tools=[mcp, our_tool]` ([03 §2](./03-development.md))
- **Another MCP server** (e.g., Prometheus MCP) → same pattern: `Agent(tools=[eks_mcp, prom_mcp, ...])` ([03 §3](./03-development.md))
- **Bedrock Guardrails** → add `guardrailConfig` to `BedrockModel`

---

## Next

- Actually add a feature → [03. Development Guide](./03-development.md)
- Ship to production → [04. AgentCore Deployment](./04-deployment-agentcore.md)
- Quick security overview → [06. Security & Load](./06-security-and-load.md)

## Going deeper

- The agents-as-tools pattern in Strands — [Strands MCP Tools](./00-references.md#1-strands-agents-sdk)
- AgentCore's microVM isolation model — [AgentCore VPC config](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore)
- What the EKS MCP Server actually exposes — [EKS MCP Server introduction](./00-references.md#3-amazon-eks-mcp-server)

---

[← 01. Getting Started](./01-getting-started.md) · [03. Development Guide →](./03-development.md)
