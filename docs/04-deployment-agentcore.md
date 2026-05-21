# 04. AgentCore Deployment

> 🌐 **Language**: **English** · [한국어](./04-deployment-agentcore.ko.md)

[← 03. Development Guide](./03-development.md) · [05. Code Style →](./05-code-style.md)

This document walks through deploying the RCA Agent to the [Bedrock AgentCore Runtime](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore) under **Pattern 4 (full VPC isolation)**. It also covers EKS MCP Server connectivity and multi-cluster operation.

---

## Why AgentCore + EKS MCP

| Topic | Direct K8s API operation | AgentCore + EKS MCP |
|-------|--------------------------|---------------------|
| Infrastructure | You manage it | AWS managed |
| Session isolation | Extra design needed | microVM by default |
| Observability | Build it yourself | OTel automatic |
| K8s SDK upkeep | You handle it | EKS MCP handles it |
| Multi-cluster auth | Custom ClusterRegistry | Automatic via IAM scope |
| Cost | Always-on | Pay per invocation |

---

## Deployment flow

```
[1] Provision isolated VPC + IAM via CDK
        ↓
[2] Choose EKS MCP access mode (managed vs self-hosted)
        ↓
[3] Push ARM64 container image to ECR
        ↓
[4] Create the AgentCore Runtime
        ↓
[5] Map IAM principal → K8s group on each diagnosed cluster
        ↓
[6] Verify a real invocation
```

---

## 1. Provision infrastructure with CDK

`deploy/agentcore/cdk_stack.py` provisions:

- An isolated VPC (NAT 0, no public subnets)
- VPC endpoints — STS, EKS, ECR, CloudWatch Logs, Bedrock, Bedrock AgentCore
- A security group for the AgentCore ENI
- An IAM execution role (based on `iam-execution-policy.json`)
- A CloudWatch Log Group

```bash
cd deploy/agentcore
pip install aws-cdk-lib constructs
cdk deploy RcaAgentCoreStack \
  -c clusters='[{"name":"prod-us","region":"us-east-1"},{"name":"prod-eu","region":"eu-west-1"}]'
```

Note `VpcId`, `SubnetIds`, `SecurityGroupId`, and `ExecutionRoleArn` from the stack outputs.

---

## 2. EKS MCP Server access mode

You have two options.

### Option A: Managed EKS MCP Server (preview, recommended)

Call the AWS-hosted EKS MCP server over Streamable HTTP + SigV4.

- Pros: zero install/upkeep, auto-updates, CloudTrail audit, automatic credential redaction in MCP responses (`HIDDEN_FOR_SECURITY_REASONS`)
- Endpoint format: `https://eks-mcp.{region}.api.aws/mcp` — region-specific
- AgentCore env (us-west-2 example)
  ```
  EKS_MCP_TRANSPORT=http
  AWS_REGION=us-west-2
  # Endpoint is auto-built from AWS_REGION. To override:
  # EKS_MCP_ENDPOINT=https://eks-mcp.us-west-2.api.aws/mcp
  ```
- IAM actions: `eks-mcp:InvokeMcp`, `eks-mcp:CallReadOnlyTool` (read-only), or use the managed policy `AmazonEKSMCPReadOnlyAccess`
- SigV4 signing is handled by [`aws/mcp-proxy-for-aws`](./00-references.md#3-amazon-eks-mcp-server) — run it as a stdio child or as a sidecar inside the agent container
- VPC endpoints are still in preview — confirm exact endpoint names against [AgentCore VPC docs](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore) and [EKS MCP getting started](./00-references.md#3-amazon-eks-mcp-server) at GA

> The http mode in this repo's `mcp_client.py` does not perform SigV4 itself.
> Calls to the managed endpoint must traverse the proxy above.

### Option B: Self-hosted EKS MCP Server (open source)

Use the `awslabs.eks-mcp-server` package in either of two configurations.

**B-1. Stdio mode** (child process inside the agent container):

```
EKS_MCP_TRANSPORT=stdio
```

The Dockerfile installs `uv` and runs the package inside the container.

**B-2. Separate container** (ECS/EKS task etc.):

```
EKS_MCP_TRANSPORT=http
EKS_MCP_ENDPOINT=http://eks-mcp.internal:8000/mcp
```

| Comparison | A (managed) | B-1 (stdio) | B-2 (separate) |
|------------|-------------|-------------|----------------|
| Operational burden | 0 | small | medium |
| Cold start | none | small (uvx boot) | none |
| AWS coupling | very high | low | medium |
| Pattern 4 fit | needs VPC endpoints | natural | within VPC |

---

## 3. Build and push the ARM64 image to ECR

```bash
aws ecr create-repository --repository-name rca-agent --region us-west-2

aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-west-2.amazonaws.com

docker buildx build \
  --platform linux/arm64 \
  -t <account>.dkr.ecr.us-west-2.amazonaws.com/rca-agent:0.1.0 \
  -f deploy/agentcore/Dockerfile \
  --push \
  .
```

---

## 4. Create the AgentCore Runtime

```bash
agentcore create rca-agent \
  --execution-role <ExecutionRoleArn-from-CDK> \
  --container-image <ecr-uri>:0.1.0 \
  --vpc-config "subnets=[<SubnetIds>],securityGroups=[<SecurityGroupId>]" \
  --network-mode VPC_ONLY \
  --environment "EKS_MCP_TRANSPORT=http,EKS_MCP_ENDPOINT=...,AWS_REGION=us-west-2,LOG_LEVEL=INFO"
```

---

## 5. Multi-cluster mapping

Apply the following to *each* diagnosed cluster.

### 5.1 Map IAM principal → K8s group

Option A (managed MCP) — register the AgentCore execution role as a K8s user.

```bash
for cluster in prod-us prod-eu; do
  aws eks create-access-entry \
    --cluster-name $cluster \
    --principal-arn <ExecutionRoleArn> \
    --kubernetes-groups rca-agent-readers \
    --type STANDARD
done
```

Option B (self-hosted MCP) — map the MCP server's task role.

### 5.2 Apply the ClusterRole and binding

```bash
for cluster in prod-us prod-eu; do
  kubectl --context=$cluster apply -f deploy/agentcore/eks-rbac.yaml
done
```

The manifest grants only read-only permissions and explicitly excludes `secrets`.

### 5.3 List the cluster ARNs in the IAM policy

In `iam-execution-policy.json`'s `EksClusterAccess` block, list every target cluster ARN.

```json
"Resource": [
  "arn:aws:eks:us-east-1:ACCOUNT:cluster/prod-us",
  "arn:aws:eks:eu-west-1:ACCOUNT:cluster/prod-eu"
]
```

**No `Resource: *`.** Adding a new cluster means updating IAM policy + Access Entry + RBAC together.

## 5.4 Apply the resource policy (caller restriction)

In production, attach a resource policy to the AgentCore Runtime to restrict who can invoke it. Skipping this step leaves every IAM principal in the same account able to call it.

```bash
# 1) Substitute the template
sed -e "s/ACCOUNT_ID/123456789012/g" \
    -e "s/REGION/us-west-2/g" \
    -e "s|AGENT_RUNTIME_ID|<agent-id-from-step-4>|g" \
    -e "s/VPCE_ID/vpce-0abc.../g" \
    deploy/agentcore/resource-policy.json > /tmp/resource-policy.rendered.json

# 2) Attach to the runtime
aws bedrock-agentcore-control put-agent-runtime-resource-policy \
  --agent-runtime-id <agent-id> \
  --policy file:///tmp/resource-policy.rendered.json
```

Two statements in the policy:

- `AllowInvocationFromApprovedPrincipals` — only listed caller IAM roles may invoke
- `DenyInvocationOutsideApprovedVpcEndpoint` — restrict the call path to listed VPC endpoints (Pattern 3+). If every caller is an IAM role in the same account, this deny statement is optional.

---

## 6. Verify a real invocation

```bash
aws bedrock-agentcore-control invoke-agent \
  --agent-id <agent-id> \
  --payload '{
    "query": "Look at the nginx pod in the default namespace",
    "cluster": "prod-us"
  }' \
  output.json

cat output.json
```

Expected response:

```json
{
  "response": "## Root cause\n...\n## Recommended actions\n...",
  "cluster": "prod-us"
}
```

---

## 7. Operating posture

### Cost monitoring

Set CloudWatch Billing Alerts.

- Bedrock tokens — daily ceiling
- AgentCore Runtime — invocation count
- EKS MCP Server (managed) — API call count
- VPC endpoints — small but worth tracking

### Metrics and alarm thresholds

`infrastructure/metrics.py` emits the following metrics over CloudWatch EMF (Embedded Metric Format) on stdout. AgentCore Runtime's log shipper auto-loads them into the `RcaAgent` namespace in CloudWatch Metrics.

| Metric | Unit | Dimensions | Meaning |
|--------|------|-----------|---------|
| `rca.invocation.count` | Count | cluster, status | Invocation count |
| `rca.invocation.latency_ms` | Milliseconds | cluster | Invocation latency |
| `rca.tool_call.count` | Count | specialist, tool, status | Tool calls (to be wired) |
| `rca.llm.tokens.input` | Count | model | LLM input tokens (to be wired) |
| `rca.llm.tokens.output` | Count | model | LLM output tokens (to be wired) |

Recommended alarm thresholds:

| Alarm | Metric and condition | Window | Action | Runbook |
|-------|---------------------|--------|--------|---------|
| `RcaAgent-InvocationErrorRate` | `rca.invocation.count{status=failure} / total` > 5% | 5 min | PagerDuty | [Runbook §1](./07-runbook.md#scenario-1-agentcore-invocation-5xx-error-rate-spike) |
| `RcaAgent-InvocationLatencyP95` | `rca.invocation.latency_ms` p95 > 60000 | 5 min | Slack | Latency review |
| `RcaAgent-BedrockThrottle` | `AWS/Bedrock` ThrottleException > 0 | 1 min | Slack | [Runbook §2](./07-runbook.md#scenario-2-bedrock-throttle-spike) |
| `RcaAgent-ToolCallFailureRate` | `rca.tool_call.count{status=failure} / total` > 10% | 10 min | Slack | [Runbook §3](./07-runbook.md#scenario-3-eks-mcp-timeout-spike) |
| `RcaAgent-DailyTokenBudget` | `rca.llm.tokens.input + output` > 80% of daily budget | 1 hr | Slack | [Runbook §4](./07-runbook.md#scenario-4-llm-token-cost-spike) |
| `RcaAgent-ClusterFailureRate` | `rca.invocation.count{cluster=X, status=failure} / total` > 30% | 10 min | PagerDuty | [Runbook §5](./07-runbook.md#scenario-5-single-eks-cluster-failure-spike) |

### Observability

AgentCore auto-ships OpenTelemetry traces to X-Ray. EKS MCP calls land in CloudTrail (managed). Other things to track:

- Tool-call traces and LLM token usage
- Tool failure rate
- Per-cluster request distribution

### Quarterly audit

- IAM execution role still has all Resources explicitly listed
- aws-auth or Access Entries have no unintended additions
- VPC endpoints are healthy
- CloudWatch Log Group retention policy

---

## 8. Operations checklist

- [ ] `pytest tests/` all pass
- [ ] Container image vulnerability scan
- [ ] IAM execution role has no `Resource: *`
- [ ] AgentCore VPC is Pattern 4 (NAT 0, no public subnets)
- [ ] All VPC endpoints (Bedrock, AgentCore, STS, EKS, ECR, Logs) healthy
- [ ] Each EKS cluster's ClusterRole is read-only and excludes secrets
- [ ] Access Entry / aws-auth maps only the intended IAM role
- [ ] CloudWatch alarms set (cost, error rate, throttle)
- [ ] Resource policy applied (`deploy/agentcore/resource-policy.json` template → `put-agent-runtime-resource-policy`)

---

## Next

- Skim the readability rules → [05. Code Style](./05-code-style.md)
- Threat-by-threat defense lines → [06. Security & Load](./06-security-and-load.md)

## Going deeper

- Topology rationale for Pattern 4 — [Network connectivity patterns for AgentCore](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore)
- AgentCore VPC mode differences — [AgentCore VPC config](./00-references.md#2-amazon-bedrock-and-bedrock-agentcore)
- EKS Access Entries usage — [EKS Access Entries](./00-references.md#3-amazon-eks-mcp-server)

---

[← 03. Development Guide](./03-development.md) · [05. Code Style →](./05-code-style.md)
