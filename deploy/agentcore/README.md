# AgentCore 배포 매니페스트

이 디렉토리는 RCA Agent를 **Amazon Bedrock AgentCore Runtime**에 **Pattern 4 (Full VPC Isolation)** 으로 배포하기 위한 자료를 담는다.

## 파일

| 파일 | 설명 |
|------|------|
| `Dockerfile` | ARM64 컨테이너 이미지 (AgentCore 계약 준수) |
| `iam-execution-policy.json` | AgentCore execution role 의 IAM 정책 (Bedrock + EKS + EKS MCP + ECR) |
| `resource-policy.json` | AgentCore Runtime resource policy 템플릿 (호출자 제한) |
| `eks-rbac.yaml` | 진단 대상 EKS 클러스터에 적용할 read-only RBAC + access mapping 가이드 |
| `cdk_stack.py` | 격리 VPC + VPC endpoints + IAM role 을 만드는 CDK 스택 템플릿 |

## 배포 흐름

```
[1] CDK로 VPC + IAM 만들기
        │
        ▼
[2] ECR에 ARM64 이미지 푸시
        │
        ▼
[3] AgentCore Runtime 생성 (CLI 또는 콘솔)
    - VPC: CDK output VpcId
    - Subnets: CDK output SubnetIds
    - SG: CDK output SecurityGroupId
    - ExecutionRole: CDK output ExecutionRoleArn
    - Image: ECR URI
    - Env: K8S_MODE=eks, K8S_CLUSTERS=<JSON>
        │
        ▼
[4] 각 EKS 클러스터에:
    - kubectl apply -f eks-rbac.yaml
    - aws eks create-access-entry로 IAM role을 group에 매핑
        │
        ▼
[5] 호출 검증
    aws bedrock-agentcore-control invoke-agent \\
        --agent-id <id> \\
        --payload '{"query": "...", "cluster": "prod-us"}'
```

## 단계별 상세

### 1. CDK 배포

```bash
cd deploy/agentcore
pip install aws-cdk-lib constructs
cdk synth
cdk deploy RcaAgentCoreStack
```

스택이 출력하는 값을 다음 단계에서 사용한다.

### 2. ARM64 이미지 빌드 + 푸시

```bash
# ECR 로그인
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-west-2.amazonaws.com

# 빌드 (Apple Silicon 외 환경에서는 buildx 필요)
docker buildx build \
  --platform linux/arm64 \
  -t <account>.dkr.ecr.us-west-2.amazonaws.com/rca-agent:0.1.0 \
  -f deploy/agentcore/Dockerfile \
  --push \
  .
```

### 3. AgentCore Runtime 생성

`agentcore` CLI 또는 AWS 콘솔로:

```bash
agentcore create rca-agent \
  --execution-role <arn-from-cdk> \
  --container-image <ecr-uri> \
  --vpc-config "subnets=[<subnet-ids>],securityGroups=[<sg-id>]" \
  --environment "K8S_MODE=eks,K8S_CLUSTERS=<json-from-cdk>,AWS_REGION=us-west-2"
```

### 4. EKS 클러스터에 RBAC 적용

진단할 각 클러스터에 대해:

```bash
# context 변경
kubectl config use-context prod-us

# RBAC 매니페스트 적용
kubectl apply -f deploy/agentcore/eks-rbac.yaml

# IAM role을 그룹에 매핑 (Access Entries 권장)
aws eks create-access-entry \
  --cluster-name prod-us \
  --principal-arn <execution-role-arn> \
  --kubernetes-groups rca-agent-readers \
  --type STANDARD
```

### 5. 호출 테스트

```bash
aws bedrock-agentcore-control invoke-agent \
  --agent-id <agent-id> \
  --payload '{"query": "default 네임스페이스의 nginx Pod 봐줘", "cluster": "prod-us"}' \
  output.json

cat output.json
```

## 보안 체크리스트

배포 전 확인:

- [ ] IAM 정책에 `Resource: *` 없음 (`bedrock:InvokeModel`은 모델 ARN 명시, `eks:DescribeCluster`는 클러스터 ARN 명시)
- [ ] VPC가 `nat_gateways=0`으로 격리됨
- [ ] VPC endpoints가 모든 사용 AWS 서비스에 대해 생성됨
- [ ] EKS RBAC는 read-only이고 `secrets` 미포함
- [ ] CloudWatch Log Group의 KMS 암호화 적용 (선택)
- [ ] AgentCore에 inbound resource policy로 호출자 제한 (Pattern 3+)
- [ ] aws-auth 또는 Access Entries에 매핑된 IAM role이 우리 execution role 외에는 추가되지 않음

## 로컬 테스트는?

이 디렉토리의 자료는 **운영 배포용**이다. 로컬 개발은:

- 빠른 반복: `python -m k8s_rca_agent.main --cluster default "..."` (kind/minikube)
- 진입점 검증: `python -m k8s_rca_agent.agentcore_app` + `curl http://localhost:8080/invocations`

자세한 내용은 [docs/01-getting-started.md](../../docs/01-getting-started.md) 참고.

## 참고

- [docs/04-deployment-agentcore.md](../../docs/04-deployment-agentcore.md) — 본 디렉토리의 상세 가이드
- [Bedrock AgentCore VPC 설정](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html)
- [Network connectivity patterns blog](https://aws.amazon.com/blogs/networking-and-content-delivery/network-connectivity-patterns-for-agents-deployed-on-amazon-bedrock-agentcore-runtime/)
