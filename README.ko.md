# k8s-agents-strands

> 🌐 **Language**: [English](./README.md) · **한국어**

Kubernetes 클러스터 장애의 **근본 원인 분석(RCA)** 을 자동화하는 AI Agent입니다.

[Strands Agents SDK](https://strandsagents.com)로 에이전트를 구성하고, 클러스터 데이터는 [Amazon EKS MCP Server](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-introduction.html)로 조회합니다. 운영 환경에는 [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html)에 Pattern 4 (full VPC isolation) 로 배포합니다.

> **운영 원칙**: AI 도구가 코드 작성을 도와주더라도, **사람이 line-by-line 이해하지 못한 코드는 운영에 올리지 않습니다.**
> 검증된 SDK 와 MCP 를 먼저 활용하고, 직접 구현은 정말 필요할 때만 합니다. 자세한 기준은 [05-code-style.md](./docs/05-code-style.md) 를 참고하세요.

---

## 빠른 시작 (로컬)

```bash
# 1) 클론과 설치
git clone <repository-url>
cd k8s-agents-strands
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2) 사전 점검
aws sts get-caller-identity                              # AWS 인증
aws bedrock list-foundation-models --region us-west-2    # Bedrock 모델 액세스
uvx awslabs.eks-mcp-server@latest --help                 # EKS MCP 부팅 확인

# 3) 첫 질의
python -m k8s_rca_agent.main --cluster <your-eks-cluster> \
  "default 네임스페이스의 nginx Pod 상태 확인해줘"
```

전체 단계는 [01-getting-started.md](./docs/01-getting-started.md) 에 있습니다.

---

## 아키텍처 한눈에

```
사용자 / AgentCore payload   { query, cluster }
        │
        ▼
   Orchestrator Agent
        │   (라우팅)
        ▼
   Specialist Agent
   (Pod / Network / ...)
        │   tools = [eks_mcp]
        ▼
   EKS MCP Server (AWS managed)
        │   SigV4 + EKS API
        ▼
   EKS 클러스터
```

소스 파일 11 개입니다. 핵심 패턴은 세 가지로 압축됩니다 — Strands MCP 통합, Multi-Agent (agents-as-tools), Bedrock AgentCore Runtime.

---

## 디렉토리 구조

```
k8s-agents-strands/
├── README.md
├── pyproject.toml
├── deploy/
│   └── agentcore/                 # AgentCore Pattern 4 배포 매니페스트
│       ├── Dockerfile
│       ├── cdk_stack.py
│       ├── iam-execution-policy.json
│       ├── eks-rbac.yaml
│       └── README.md
├── docs/
│   ├── 01-getting-started.md
│   ├── 02-architecture.md
│   ├── 03-development.md
│   ├── 04-deployment-agentcore.md
│   ├── 05-code-style.md
│   └── 06-security-and-load.md
├── src/k8s_rca_agent/
│   ├── domain/
│   │   ├── models.py              # Diagnosis 도메인 모델
│   │   └── validation.py          # 입력 sanity check
│   ├── infrastructure/
│   │   ├── mcp_client.py          # EKS MCP 클라이언트 팩토리
│   │   ├── container.py           # DI 컨테이너
│   │   └── redaction.py           # 민감 정보 마스킹 유틸
│   ├── agents/
│   │   ├── orchestrator.py        # 라우팅 + 종합
│   │   └── pod_diagnostic.py      # Pod 진단 specialist
│   ├── tools/                     # 자체 특화 도구 (현재 비어 있음)
│   ├── agentcore_app.py           # AgentCore Runtime 진입점
│   └── main.py                    # 로컬 CLI 진입점
└── tests/
```

---

## 문서 안내

| 문서 | 대상 독자 | 핵심 내용 |
|------|-----------|-----------|
| [00. References](./docs/00-references.md) | 모두 | Strands · Bedrock · AgentCore · MCP · K8s 자료 인덱스 |
| [01. 시작하기](./docs/01-getting-started.md) | 처음 접하는 사람 | 설치, 사전 점검, 4-tier 로컬 테스트 |
| [02. 아키텍처](./docs/02-architecture.md) | 구조를 이해하려는 사람 | MCP-first 설계, 데이터 흐름, invocation 라이프사이클 |
| [03. 개발 가이드](./docs/03-development.md) | 기능을 추가하려는 사람 | specialist / 도구 / MCP 추가 튜토리얼 |
| [04. AgentCore 배포](./docs/04-deployment-agentcore.md) | 배포·운영자 | Pattern 4, EKS MCP, 멀티 클러스터 매핑 |
| [05. 코드 스타일](./docs/05-code-style.md) | 모든 컨트리뷰터 | 가독성 원칙과 검토 기준 |
| [06. 보안 & 부하](./docs/06-security-and-load.md) | 보안·SRE 검토자 | layered defense 와 운영 체크리스트 |
| [07. 운영 Runbook](./docs/07-runbook.md) | on-call 엔지니어 | 알람별 5 단계 대응 절차 |

추천 학습 순서: **01 → 02 → 03 → 04 → 06 → 05**.
외부 자료(Strands · Bedrock AgentCore · EKS MCP 등)는 [00. References](./docs/00-references.md) 에 한곳에 모아두었습니다.

---

## 이 레포로 무엇을 배울 수 있나

이 레포는 **AWS 위에서 LLM 에이전트를 운영하기 위한 레퍼런스 프로젝트**입니다. RCA 자동화는 그 위에서 만들어 본 의미 있는 사용 시나리오일 뿐, 핵심 학습 가치는 그 옆에 있습니다.

| 관심사 | 어디서부터 | 코드에서 보고 갈 곳 |
|-------|-----------|------------------|
| Strands 로 에이전트 짜기 | [02. 아키텍처 §3](./docs/02-architecture.md) | `agents/orchestrator.py`, `agents/pod_diagnostic.py` |
| Bedrock AgentCore 운영 | [04. AgentCore 배포](./docs/04-deployment-agentcore.md) | `agentcore_app.py`, `deploy/agentcore/cdk_stack.py` |
| MCP 통합 패턴 | [02 §3.1](./docs/02-architecture.md) | `infrastructure/mcp_client.py` |
| K8s 진단 자동화 | [01 §6](./docs/01-getting-started.md) | `agents/pod_diagnostic.py` 의 system prompt |
| LLM 보안 모델 | [06. 보안 & 부하](./docs/06-security-and-load.md) | `deploy/agentcore/iam-execution-policy.json`, `eks-rbac.yaml` |
| 가독 가능한 AI-보조 코드 | [05. 코드 스타일](./docs/05-code-style.md) | 전체 — 코드는 의도적으로 짧고 평탄합니다 |

---

## 핵심 설계 원칙

1. **사람이 이해하지 못한 코드는 운영에 올리지 않습니다** — AI 도움을 받았어도 line-by-line 검토는 필수입니다.
2. **MCP 와 SDK 를 우선 사용합니다** — Strands 와 EKS MCP 가 처리할 수 있는 것은 직접 구현하지 않습니다.
3. **5초 안에 의도가 보이는 코드를 씁니다** — 6 개월 후 자신이 다시 봐도 즉시 읽힐 수 있어야 합니다.
4. **도메인은 외부 라이브러리에 의존하지 않습니다** — 비즈니스 모델을 SDK 변경에 묶지 않습니다.
5. **최소 권한 원칙을 지킵니다** — read-only RBAC 와 IAM Resource ARN 명시.
6. **네트워크는 격리합니다** — AgentCore Pattern 4, VPC endpoints 만 통신.
7. **방어선을 여러 겹 둡니다** — 한 layer 의 결함이 시스템 전체를 깨지 않도록 합니다.
8. **확장이 단순해야 합니다** — 새 specialist 또는 MCP 추가가 한 파일로 끝나야 합니다.

---

## 일반 LLM 챗봇과의 차이

| 항목 | 일반 LLM 챗봇 | 이 프로젝트 |
|------|---------------|-------------|
| K8s 데이터 접근 | 불가 | EKS MCP 로 실시간 조회 |
| 권한 관리 | 통제 어려움 | EKS RBAC + IAM 분리 |
| 보안 격리 | 노출 위험 | AgentCore Pattern 4 |
| 비용 관리 | 어려움 | invocation 단위 + Bedrock Guardrail |
| 확장성 | 단일 prompt 한계 | Specialist agent 와 MCP 조합 |

---

## 기여하기

오픈소스 프로젝트로 운영합니다. 기여를 환영합니다.

- 시작 전에 [CONTRIBUTING.md](./CONTRIBUTING.md) 를 읽어주세요.
- 모든 참여자는 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) 를 준수합니다.
- 처음이라면 `good first issue` 라벨이 붙은 이슈부터 살펴보세요.

## 라이선스

[Apache License 2.0](./LICENSE) 으로 배포합니다. 의존하는 서드파티 라이선스는 [NOTICE](./NOTICE) 에 정리되어 있습니다.
