# 04. AgentCore 배포

> 🌐 **Language**: [English](./04-deployment-agentcore.md) · **한국어**

[← 03. 개발 가이드](./03-development.ko.md) · [05. 코드 스타일 →](./05-code-style.ko.md)

이 문서는 RCA Agent 를 [Bedrock AgentCore Runtime](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore) 에 **Pattern 4 (full VPC isolation)** 로 배포하는 절차를 단계별로 안내합니다. EKS MCP Server 연결 설정과 다중 EKS 클러스터 운영 방안도 다룹니다.

---

## 왜 AgentCore + EKS MCP 인가

| 항목 | 직접 K8s API 운영 | AgentCore + EKS MCP |
|------|-----------------|---------------------|
| 인프라 관리 | 직접 | AWS 가 관리 |
| 세션 격리 | 추가 설계 필요 | microVM 기본 제공 |
| 관측성 | 직접 구성 | OTel 자동 |
| K8s SDK 유지보수 | 직접 | EKS MCP 가 처리 |
| 다중 클러스터 인증 | ClusterRegistry 등 직접 | IAM scope 로 자동 |
| 비용 | 항상 켜져 있음 | pay-per-invocation |

---

## 전체 배포 흐름

```
[1] CDK 로 격리 VPC + IAM 생성
        ↓
[2] EKS MCP Server 접근 방식 선택 (managed vs self-hosted)
        ↓
[3] ECR 에 ARM64 컨테이너 이미지 푸시
        ↓
[4] AgentCore Runtime 생성
        ↓
[5] 진단 대상 EKS 클러스터에 IAM principal → K8s group 매핑
        ↓
[6] 호출 검증
```

---

## 1. CDK 로 인프라 만들기

`deploy/agentcore/cdk_stack.py` 가 다음을 만듭니다.

- 격리 VPC (NAT 0, public subnet 0)
- VPC Endpoints — STS, EKS, ECR, CloudWatch Logs, Bedrock, Bedrock AgentCore
- AgentCore ENI 용 Security Group
- IAM Execution Role (`iam-execution-policy.json` 기반)
- CloudWatch Log Group

```bash
cd deploy/agentcore
pip install aws-cdk-lib constructs
cdk deploy RcaAgentCoreStack \
  -c clusters='[{"name":"prod-us","region":"us-east-1"},{"name":"prod-eu","region":"eu-west-1"}]'
```

스택 출력에서 `VpcId`, `SubnetIds`, `SecurityGroupId`, `ExecutionRoleArn` 을 확인합니다.

---

## 2. EKS MCP Server 접근 방식

두 가지 옵션이 있습니다.

### 옵션 A: Managed EKS MCP Server (preview, 권장)

AWS 가 호스팅하는 EKS MCP server 를 Streamable HTTP + SigV4 로 호출합니다.

- 장점: 설치·유지보수 부담 0, 자동 업데이트, CloudTrail 감사, MCP 응답 자체에 자격 증명 패턴 redaction 내장 (`HIDDEN_FOR_SECURITY_REASONS`)
- Endpoint 형식: `https://eks-mcp.{region}.api.aws/mcp` — region 가변
- AgentCore 환경 변수 예시 (us-west-2)
  ```
  EKS_MCP_TRANSPORT=http
  AWS_REGION=us-west-2
  # endpoint 는 AWS_REGION 으로 자동 구성됨. 명시 시:
  # EKS_MCP_ENDPOINT=https://eks-mcp.us-west-2.api.aws/mcp
  ```
- IAM 액션은 `eks-mcp:InvokeMcp`, `eks-mcp:CallReadOnlyTool` (read-only) — 또는 managed policy `AmazonEKSMCPReadOnlyAccess`
- SigV4 서명은 [`aws/mcp-proxy-for-aws`](./00-references.ko.md#3-amazon-eks-mcp-server) 가 담당 — Agent 컨테이너 안에서 stdio 로 띄우거나 sidecar 컨테이너로 운영
- VPC endpoint 는 preview 단계 — 정확한 endpoint 이름은 [AgentCore VPC docs](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore) 와 [EKS MCP getting started](./00-references.ko.md#3-amazon-eks-mcp-server) 에서 GA 시점에 확인

> 본 레포의 `mcp_client.py` http 모드는 자체 SigV4 서명을 수행하지 않습니다.
> Managed endpoint 사용 시 위 proxy 를 거쳐야 합니다.

### 옵션 B: Self-hosted EKS MCP Server (open-source)

`awslabs.eks-mcp-server` 패키지를 두 가지 방식으로 사용할 수 있습니다.

**B-1. Stdio 모드** (Agent 컨테이너 안에서 자식 프로세스):

```
EKS_MCP_TRANSPORT=stdio
```

Dockerfile 에 `uv` 가 설치되어 있고, 패키지가 컨테이너 내부에서 실행됩니다.

**B-2. 별도 컨테이너로 분리** (ECS/EKS task 등):

```
EKS_MCP_TRANSPORT=http
EKS_MCP_ENDPOINT=http://eks-mcp.internal:8000/mcp
```

| 비교 | A (managed) | B-1 (stdio) | B-2 (분리) |
|------|-------------|-------------|------------|
| 운영 부담 | 0 | 작음 | 중간 |
| 콜드 스타트 | 없음 | 약간 (uvx 부팅) | 없음 |
| AWS 의존도 | 매우 높음 | 낮음 | 중간 |
| Pattern 4 호환 | VPC endpoint 필요 | 자연스러움 | VPC 내부 |

---

## 3. ARM64 이미지 빌드와 ECR 푸시

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

## 4. AgentCore Runtime 생성

```bash
agentcore create rca-agent \
  --execution-role <ExecutionRoleArn-from-CDK> \
  --container-image <ecr-uri>:0.1.0 \
  --vpc-config "subnets=[<SubnetIds>],securityGroups=[<SecurityGroupId>]" \
  --network-mode VPC_ONLY \
  --environment "EKS_MCP_TRANSPORT=http,EKS_MCP_ENDPOINT=...,AWS_REGION=us-west-2,LOG_LEVEL=INFO"
```

---

## 5. 다중 EKS 클러스터 매핑

진단 대상 클러스터마다 다음을 적용합니다.

### 5.1 IAM principal → K8s group 매핑

옵션 A (Managed MCP) — AgentCore execution role 을 K8s 사용자로 인식시킵니다.

```bash
for cluster in prod-us prod-eu; do
  aws eks create-access-entry \
    --cluster-name $cluster \
    --principal-arn <ExecutionRoleArn> \
    --kubernetes-groups rca-agent-readers \
    --type STANDARD
done
```

옵션 B (self-hosted MCP) — MCP server 의 task role 을 매핑합니다.

### 5.2 ClusterRole 과 Binding 적용

```bash
for cluster in prod-us prod-eu; do
  kubectl --context=$cluster apply -f deploy/agentcore/eks-rbac.yaml
done
```

이 매니페스트는 read-only 권한만 부여하고 `secrets` 를 명시적으로 제외합니다.

### 5.3 IAM 정책에 클러스터 ARN 명시

`iam-execution-policy.json` 의 `EksClusterAccess` 블록에 모든 대상 클러스터 ARN 을 나열합니다.

```json
"Resource": [
  "arn:aws:eks:us-east-1:ACCOUNT:cluster/prod-us",
  "arn:aws:eks:eu-west-1:ACCOUNT:cluster/prod-eu"
]
```

**`Resource: *` 금지.** 새 클러스터마다 IAM 정책 + Access Entry + RBAC 세 가지를 함께 추가합니다.

---

## 5.4 Resource Policy 적용 (호출자 제한)

운영 환경에서는 AgentCore Runtime 에 resource policy 를 적용해 invoke 호출자를 제한합니다. 이 단계를 빠뜨리면 같은 계정의 모든 IAM principal 이 호출할 수 있습니다.

```bash
# 1) 템플릿을 환경에 맞게 치환
sed -e "s/ACCOUNT_ID/123456789012/g" \
    -e "s/REGION/us-west-2/g" \
    -e "s|AGENT_RUNTIME_ID|<agent-id-from-step-4>|g" \
    -e "s/VPCE_ID/vpce-0abc.../g" \
    deploy/agentcore/resource-policy.json > /tmp/resource-policy.rendered.json

# 2) AgentCore Runtime 에 적용
aws bedrock-agentcore-control put-agent-runtime-resource-policy \
  --agent-runtime-id <agent-id> \
  --policy file:///tmp/resource-policy.rendered.json
```

정책의 두 statement:

- `AllowInvocationFromApprovedPrincipals` — 명시된 caller IAM role 만 호출 허용
- `DenyInvocationOutsideApprovedVpcEndpoint` — 호출 경로를 명시된 VPC endpoint 로 강제 (Pattern 3 이상). 모든 caller 가 같은 계정의 IAM role 이라면 이 deny 는 생략 가능

## 6. 호출 검증

```bash
aws bedrock-agentcore-control invoke-agent \
  --agent-id <agent-id> \
  --payload '{
    "query": "default 네임스페이스의 nginx Pod 봐줘",
    "cluster": "prod-us"
  }' \
  output.json

cat output.json
```

기대 응답:

```json
{
  "response": "## 근본 원인\n...\n## 권장 조치\n...",
  "cluster": "prod-us"
}
```

---

## 7. 운영 점검

### 비용 모니터링

CloudWatch Billing Alert 에 임계값을 설정합니다.

- Bedrock 토큰 — 일일 한도
- AgentCore Runtime — invocation 수
- EKS MCP Server (managed) — API 호출 수
- VPC Endpoints — 일반적으로 작지만 추적

### 메트릭과 Alarm 임계값

`infrastructure/metrics.py` 가 CloudWatch EMF (Embedded Metric Format) 로 다음 메트릭을 stdout 에 emit 합니다. AgentCore Runtime 의 log shipper 가 자동으로 CloudWatch Metrics 의 `RcaAgent` namespace 에 적재합니다.

| 메트릭 | Unit | Dimensions | 의미 |
|--------|------|-----------|------|
| `rca.invocation.count` | Count | cluster, status | invocation 횟수 |
| `rca.invocation.latency_ms` | Milliseconds | cluster | invocation 지연 |
| `rca.tool_call.count` | Count | specialist, tool, status | 도구 호출 횟수 (향후 wiring) |
| `rca.llm.tokens.input` | Count | model | LLM 입력 토큰 (향후 wiring) |
| `rca.llm.tokens.output` | Count | model | LLM 출력 토큰 (향후 wiring) |

권장 alarm 임계값:

| Alarm 이름 | 메트릭과 조건 | 평가 윈도우 | 액션 | 대응 시나리오 |
|-----------|--------------|-----------|------|------------|
| `RcaAgent-InvocationErrorRate` | `rca.invocation.count{status=failure} / rca.invocation.count` > 5% | 5 분 | PagerDuty | [Runbook §1](./07-runbook.ko.md#시나리오-1-agentcore-invocation-5xx-에러율-폭증) |
| `RcaAgent-InvocationLatencyP95` | `rca.invocation.latency_ms` p95 > 60000 | 5 분 | Slack | latency 추세 검토 |
| `RcaAgent-BedrockThrottle` | `AWS/Bedrock` ThrottleException > 0 | 1 분 | Slack | [Runbook §2](./07-runbook.ko.md#시나리오-2-bedrock-throttle-폭증) |
| `RcaAgent-ToolCallFailureRate` | `rca.tool_call.count{status=failure} / total` > 10% | 10 분 | Slack | [Runbook §3](./07-runbook.ko.md#시나리오-3-eks-mcp-timeout-폭증) |
| `RcaAgent-DailyTokenBudget` | `rca.llm.tokens.input + output` > 일일 한도 80% | 1 시간 | Slack | [Runbook §4](./07-runbook.ko.md#시나리오-4-llm-토큰-비용-급증) |
| `RcaAgent-ClusterFailureRate` | `rca.invocation.count{cluster=X, status=failure} / total` > 30% | 10 분 | PagerDuty | [Runbook §5](./07-runbook.ko.md#시나리오-5-단일-eks-cluster-진단-실패-폭증) |

### 관측성

AgentCore 가 OpenTelemetry trace 를 X-Ray 로 자동 전송합니다. CloudTrail 에는 EKS MCP 호출이 기록됩니다 (managed). 추가로 추적할 항목:

- 도구 호출 trace 와 LLM 토큰 사용량
- 도구 실패율
- 클러스터별 요청 분포

### 정기 감사 (분기 1 회)

- IAM execution role 의 Resource 명시 여부
- aws-auth 또는 Access Entries 에 의도하지 않은 항목 추가 여부
- VPC endpoints 정상 동작
- CloudWatch Log Group 의 retention 정책

---

## 8. 운영 체크리스트

- [ ] `pytest tests/` 모두 통과
- [ ] 컨테이너 이미지 취약점 스캔
- [ ] IAM execution role 에 `Resource: *` 없음
- [ ] AgentCore VPC 가 Pattern 4 (NAT 0, public subnet 0)
- [ ] VPC endpoints (Bedrock, AgentCore, STS, EKS, ECR, Logs) 모두 healthy
- [ ] 각 EKS 클러스터의 ClusterRole 이 read-only 이고 secrets 미포함
- [ ] Access Entry 또는 aws-auth 가 의도한 IAM role 만 매핑
- [ ] CloudWatch alarm 설정 (비용, error rate, throttle)
- [ ] AgentCore Resource Policy 적용 (`deploy/agentcore/resource-policy.json` 템플릿 → `put-agent-runtime-resource-policy`)

---

## 다음 단계

- 코드 가독성 원칙 한 번에 보기 → [05. 코드 스타일](./05-code-style.ko.md)
- 보안 모델과 위협별 방어선 → [06. 보안 & 부하](./06-security-and-load.ko.md)

## 더 깊이 알아보기

- Pattern 4 토폴로지 설계 근거 — [Network connectivity patterns for AgentCore](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore)
- AgentCore VPC 모드별 차이 — [AgentCore VPC 설정](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore)
- EKS Access Entries 사용법 — [EKS Access Entries](./00-references.ko.md#3-amazon-eks-mcp-server)

---

[← 03. 개발 가이드](./03-development.ko.md) · [05. 코드 스타일 →](./05-code-style.ko.md)
