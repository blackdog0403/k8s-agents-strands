# 01. 시작하기

> 🌐 **Language**: [English](./01-getting-started.md) · **한국어**

[← 00. References](./00-references.ko.md) · [02. 아키텍처 →](./02-architecture.ko.md)

이 문서는 처음 이 레포를 받았을 때 **로컬에서 RCA Agent 를 실제로 실행**하기까지의 모든 단계를 안내합니다.
Strands, EKS MCP Server, Bedrock 같은 처음 보는 이름이 등장하면 [00. References](./00-references.ko.md) 에서 한 줄 설명과 공식 문서 링크를 찾아볼 수 있습니다.

> 본 레포는 K8s API 를 직접 호출하지 않습니다.
> 모든 클러스터 데이터는 [Amazon EKS MCP Server](./00-references.ko.md#3-amazon-eks-mcp-server) 가 가져옵니다.

---

## 1. 전제 조건

| 항목 | 버전 또는 요건 | 확인 방법 |
|------|---------------|-----------|
| Python | 3.11 이상 | `python3 --version` |
| `uv` (uvx) | 최신 | `uvx --version` |
| AWS CLI | 2.x | `aws --version` |
| AWS 자격 증명 | Bedrock 와 EKS 접근 권한 | `aws sts get-caller-identity` |
| Bedrock 모델 액세스 | Claude 모델 활성화 | [Bedrock 콘솔](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore) |
| EKS 클러스터 | 본인 IAM 이 access entry 를 가진 클러스터 1 개 이상 | `aws eks list-clusters` |
| Docker (선택) | 20 이상 | 컨테이너 빌드·실행에 필요 |

### `uv` 설치

EKS MCP Server 를 stdio 모드로 띄울 때 `uvx` 가 필요합니다.

```bash
# macOS
brew install uv

# 또는 Python 패키지 매니저로
pip install uv
```

---

## 2. 설치

```bash
git clone <repository-url> k8s-agents-strands
cd k8s-agents-strands

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
```

설치 검증:

```bash
python -c "from k8s_rca_agent.agents import create_orchestrator; print('OK')"
pytest tests/ -q
```

---

## 3. EKS MCP Server 부팅 점검

stdio 모드로 EKS MCP Server 가 정상 부팅되는지 확인합니다.

```bash
uvx awslabs.eks-mcp-server@latest --help
```

명령이 헬프 메시지를 출력하면 OK 입니다. 실제 서버는 stdio 위에서 동작하므로 stdin 이 연결되어 있어야 응답합니다.

---

## 4. 로컬 테스트 4 단계

```
[일상 개발]                             [PR 직전]
   │                                       │
   ▼                                       ▼
1) Python CLI       →   2) AgentCore SDK 로컬   →   3) Docker 로컬   →   4) AgentCore CLI
   가장 빠른 반복         진입점 계약 검증              컨테이너 검증        가장 production-like
```

각 단계는 다음과 같이 사용합니다.

### 4.1 Python CLI — 일상 개발

```bash
# 단일 질의
python -m k8s_rca_agent.main --cluster <your-cluster-name> \
  "default 네임스페이스의 nginx Pod 상태 확인해줘"

# 인터랙티브 모드
python -m k8s_rca_agent.main --cluster <your-cluster-name>
```

`<your-cluster-name>` 은 본인 IAM 이 EKS access entry 로 매핑된 실제 클러스터 이름입니다.

기본값은 `EKS_MCP_TRANSPORT=stdio` 라서, `uvx` 가 자식 프로세스로 EKS MCP Server 를 실행합니다.

### 4.2 AgentCore SDK 로컬 모드 — 진입점 계약 검증

`agentcore_app.py` 가 AgentCore 의 `/invocations`, `/ping` 계약을 만족하는지 확인합니다.

```bash
pip install -e ".[dev,agentcore]"
python -m k8s_rca_agent.agentcore_app
```

다른 터미널에서 호출:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"query": "default 네임스페이스의 nginx 봐줘", "cluster": "<your-cluster-name>"}'
```

### 4.3 Docker 로컬 실행

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

> 컨테이너는 `--no-create-home` 으로 빌드되어 있어 사용자 홈이 없습니다.
> 자격 증명은 환경 변수나 위와 같이 명시적인 마운트로 전달하세요.

### 4.4 Managed EKS MCP Server 사용 (preview)

```bash
# region 은 AWS_REGION 으로 자동 결정됩니다 (us-west-2 기본).
export EKS_MCP_TRANSPORT=http
export AWS_REGION=us-west-2
# 명시적으로 endpoint 를 지정하려면:
# export EKS_MCP_ENDPOINT=https://eks-mcp.us-west-2.api.aws/mcp
python -m k8s_rca_agent.main --cluster <your-cluster-name> "..."
```

> 현재 `mcp_client.py` 의 http 모드는 SigV4 서명을 직접 수행하지 않습니다.
> Managed endpoint 호출에는 AWS 가 제공하는 공식 proxy [`aws/mcp-proxy-for-aws`](./00-references.ko.md#3-amazon-eks-mcp-server) 를 sidecar 또는 stdio 형태로 앞에 두어야 합니다.
> 로컬 dev 라면 stdio 모드(`EKS_MCP_TRANSPORT=stdio`)가 가장 단순합니다.

---

## 5. 첫 실행 — Hello World

진단 대상 클러스터가 있다고 가정합니다.

```bash
# Pod 띄우기
kubectl --context=<cluster> run hello-nginx --image=nginx --restart=Never
kubectl --context=<cluster> wait --for=condition=Ready pod/hello-nginx --timeout=60s

# Agent 에게 질의
python -m k8s_rca_agent.main --cluster <cluster> \
  "default 네임스페이스의 hello-nginx Pod 상태 확인해줘"

# 정리
kubectl --context=<cluster> delete pod hello-nginx
```

흐름 한 줄 요약:

1. Orchestrator 가 질문을 분석해 Pod 관련임을 인식 → `pod_diagnostic` 으로 위임
2. Specialist 가 EKS MCP 도구를 호출 (`get_pod` 등)
3. EKS MCP 가 SigV4 로 EKS API 호출
4. 응답이 LLM 에 전달
5. LLM 이 한국어 RCA 리포트로 재구성

자세한 라이프사이클은 [02. 아키텍처 §5](./02-architecture.ko.md) 참고.

---

## 6. CrashLoopBackOff 시나리오

```bash
kubectl --context=<cluster> run crash-test --image=busybox --restart=Never \
  -- sh -c "echo starting; sleep 2; exit 1"

sleep 30
kubectl --context=<cluster> get pod crash-test

python -m k8s_rca_agent.main --cluster <cluster> \
  "default 네임스페이스의 crash-test Pod 분석해줘"

kubectl --context=<cluster> delete pod crash-test
```

Agent 가 EKS MCP 를 통해 Pod 상태와 Warning 이벤트를 수집하고 종합 분석합니다.

---

## 7. 트러블슈팅

| 증상 | 원인 후보 | 해결 |
|------|---------|------|
| `ModuleNotFoundError: No module named 'k8s_rca_agent'` | venv 활성화 안 됨 | `source .venv/bin/activate && pip install -e ".[dev]"` |
| `uvx: command not found` | uv 미설치 | `brew install uv` 또는 `pip install uv` |
| `NoCredentialsError` | AWS 자격 증명 미설정 | `aws configure` 또는 `export AWS_PROFILE=...` |
| `AccessDeniedException` (Bedrock) | 모델 액세스 미활성 | [Bedrock 콘솔](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore) 에서 Claude 활성화 |
| EKS MCP 가 클러스터를 못 찾음 | IAM access entry 또는 RBAC 누락 | `aws eks list-clusters` 결과와 `deploy/agentcore/eks-rbac.yaml` 적용 여부 확인 |
| AgentCore SDK 미설치 | extras 미설치 | `pip install -e ".[agentcore]"` |

---

## 다음 단계

- 코드가 왜 이렇게 짜여 있는지 이해하기 → [02. 아키텍처](./02-architecture.ko.md)
- 새 specialist 또는 도구 추가하기 → [03. 개발 가이드](./03-development.ko.md)
- 운영에 배포하기 → [04. AgentCore 배포](./04-deployment-agentcore.ko.md)
- 보안 모델 한 번에 훑기 → [06. 보안 & 부하](./06-security-and-load.ko.md)

## 더 깊이 알아보기

- Strands 로 에이전트가 어떻게 도구를 호출하는지 — [Strands MCP Tools 통합](./00-references.ko.md#1-strands-agents-sdk)
- Bedrock 에 Claude 모델을 활성화하는 방법 — [Bedrock 콘솔](./00-references.ko.md#2-amazon-bedrock-와-bedrock-agentcore)
- EKS MCP Server 가 무엇을 하는지 — [Amazon EKS MCP Server 소개](./00-references.ko.md#3-amazon-eks-mcp-server)

---

[← 00. References](./00-references.ko.md) · [02. 아키텍처 →](./02-architecture.ko.md)
