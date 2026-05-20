# 01. Getting Started

> 🌐 **Language**: **English** · [한국어](./01-getting-started.ko.md)

[← 00. References](./00-references.md) · [02. Architecture →](./02-architecture.md)

This document walks you through everything from picking up the repo for the first time to **actually running the RCA Agent locally**.
When you encounter unfamiliar names like Strands, EKS MCP Server, or Bedrock, see [00. References](./00-references.md) for one-line summaries and links to the official docs.

> This repo never calls the K8s API directly.
> All cluster data is fetched through the [Amazon EKS MCP Server](./00-references.md#3-amazon-eks-mcp-server).

---

## 1. Prerequisites

| Item | Version / Requirement | How to check |
|------|----------------------|--------------|
| Python | 3.11+ | `python3 --version` |
| `uv` (uvx) | latest | `uvx --version` |
| AWS CLI | 2.x | `aws --version` |
| AWS credentials | Bedrock + EKS access | `aws sts get-caller-identity` |
| Bedrock model access | Claude enabled | [Bedrock console](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore) |
| EKS cluster | At least one cluster you have access entry on | `aws eks list-clusters` |
| Docker (optional) | 20+ | Needed only for container build/run |

### Install `uv`

`uvx` is required to launch the EKS MCP Server in stdio mode.

```bash
# macOS
brew install uv

# Or via pip
pip install uv
```

---

## 2. Install

```bash
git clone <repository-url> k8s-agents-strands
cd k8s-agents-strands

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
```

Verify the install:

```bash
python -c "from k8s_rca_agent.agents import create_orchestrator; print('OK')"
pytest tests/ -q
```

---

## 3. Verify the EKS MCP Server boots

Confirm that the EKS MCP Server starts cleanly in stdio mode.

```bash
uvx awslabs.eks-mcp-server@latest --help
```

If the help text appears, you are good. The actual server runs over stdio, so it expects stdin to be connected to respond to real requests.

---

## 4. The four local-test tiers

```
[Daily dev]                              [Just before PR]
   │                                          │
   ▼                                          ▼
1) Python CLI       →   2) AgentCore SDK local   →   3) Local Docker   →   4) AgentCore CLI
   Fastest iteration       Entrypoint-contract test       Container test         Most production-like
```

Use each tier as follows.

### 4.1 Python CLI — daily development

```bash
# Single query
python -m k8s_rca_agent.main --cluster <your-cluster-name> \
  "Check the status of the nginx pod in the default namespace"

# Interactive
python -m k8s_rca_agent.main --cluster <your-cluster-name>
```

`<your-cluster-name>` is the actual cluster your IAM principal has an EKS access entry on.

The default is `EKS_MCP_TRANSPORT=stdio`, which spawns the EKS MCP Server as a child process via `uvx`.

### 4.2 AgentCore SDK local mode — entrypoint contract

Verify that `agentcore_app.py` satisfies the AgentCore `/invocations` and `/ping` contract.

```bash
pip install -e ".[dev,agentcore]"
python -m k8s_rca_agent.agentcore_app
```

In a separate terminal:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"query": "Look at the nginx pod in the default namespace", "cluster": "<your-cluster-name>"}'
```

### 4.3 Local Docker

```bash
docker buildx build --platform linux/arm64 \
  -t rca-agent:local \
  -f deploy/agentcore/Dockerfile .

docker run --rm -p 8080:8080 \
  -e AWS_REGION=us-west-2 \
  -e EKS_MCP_TRANSPORT=stdio \
  -e AWS_PROFILE=$AWS_PROFILE \
  -v $HOME/.aws:/.aws:ro \
  -e AWS_SHARED_CREDENTIALS_FILE=/.aws/credentials \
  rca-agent:local
```

> The container is built with `--no-create-home`, so there is no user home directory.
> Pass credentials through environment variables or an explicit mount as shown above.

### 4.4 Managed EKS MCP Server (preview)

```bash
# Region is auto-derived from AWS_REGION (default us-west-2).
export EKS_MCP_TRANSPORT=http
export AWS_REGION=us-west-2
# To override the endpoint explicitly:
# export EKS_MCP_ENDPOINT=https://eks-mcp.us-west-2.api.aws/mcp
python -m k8s_rca_agent.main --cluster <your-cluster-name> "..."
```

> The current `mcp_client.py` http mode does not perform SigV4 signing itself.
> Calls to the managed endpoint must go through the official [`aws/mcp-proxy-for-aws`](./00-references.md#3-amazon-eks-mcp-server) proxy, either as a sidecar or via stdio.
> For local dev, stdio mode (`EKS_MCP_TRANSPORT=stdio`) is the simplest option.

---

## 5. First run — Hello World

Assuming you have an accessible cluster:

```bash
# Launch a pod
kubectl --context=<cluster> run hello-nginx --image=nginx --restart=Never
kubectl --context=<cluster> wait --for=condition=Ready pod/hello-nginx --timeout=60s

# Ask the agent
python -m k8s_rca_agent.main --cluster <cluster> \
  "Check the status of the hello-nginx pod in the default namespace"

# Cleanup
kubectl --context=<cluster> delete pod hello-nginx
```

What happens, in one line:

1. The orchestrator analyzes the question, decides it is pod-related, and delegates to `pod_diagnostic`
2. The specialist invokes EKS MCP tools (`get_pod`, etc.)
3. EKS MCP calls the EKS API with SigV4
4. The response goes back to the LLM
5. The LLM produces a Korean / English RCA report

For the detailed lifecycle, see [02. Architecture §5](./02-architecture.md).

---

## 6. CrashLoopBackOff scenario

```bash
kubectl --context=<cluster> run crash-test --image=busybox --restart=Never \
  -- sh -c "echo starting; sleep 2; exit 1"

sleep 30
kubectl --context=<cluster> get pod crash-test

python -m k8s_rca_agent.main --cluster <cluster> \
  "Analyze the crash-test pod in the default namespace"

kubectl --context=<cluster> delete pod crash-test
```

The agent uses EKS MCP to gather pod state and Warning events, then produces a synthesis.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'k8s_rca_agent'` | venv not active | `source .venv/bin/activate && pip install -e ".[dev]"` |
| `uvx: command not found` | uv not installed | `brew install uv` or `pip install uv` |
| `NoCredentialsError` | AWS credentials unset | `aws configure` or `export AWS_PROFILE=...` |
| `AccessDeniedException` (Bedrock) | Model access not enabled | Enable Claude in the [Bedrock console](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore) |
| EKS MCP cannot find the cluster | Missing IAM access entry or RBAC | Check `aws eks list-clusters` and confirm `deploy/agentcore/eks-rbac.yaml` is applied |
| AgentCore SDK not installed | Extras missing | `pip install -e ".[agentcore]"` |

---

## Next

- Understand why the code is shaped this way → [02. Architecture](./02-architecture.md)
- Add a new specialist or tool → [03. Development Guide](./03-development.md)
- Deploy to production → [04. AgentCore Deployment](./04-deployment-agentcore.md)
- Skim the security model → [06. Security & Load](./06-security-and-load.md)

## Going deeper

- How Strands lets agents call tools — [Strands MCP Tools integration](./00-references.md#1-strands-agents-sdk)
- Enabling Claude models on Bedrock — [Bedrock console](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore)
- What the EKS MCP Server actually does — [Amazon EKS MCP Server introduction](./00-references.md#3-amazon-eks-mcp-server)

---

[← 00. References](./00-references.md) · [02. Architecture →](./02-architecture.md)
