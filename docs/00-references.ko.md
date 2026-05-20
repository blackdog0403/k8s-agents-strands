# 00. References — 학습과 운영 자료 모음

> 🌐 **Language**: [English](./00-references.md) · **한국어**

이 문서는 프로젝트 안과 밖의 모든 참고 자료를 한곳에 모아둔 인덱스입니다.
처음 보는 개발자는 위에서 아래로 차근히 따라가면 됩니다.
다른 문서들은 본문 안에서 이 페이지의 링크를 인라인으로 참조합니다.

> 이 레포는 **AWS 위에서 LLM 에이전트를 운영하기 위한 레퍼런스 프로젝트**입니다.
> Strands, Bedrock AgentCore, EKS MCP 같은 새 기술을 손에 잡히는 코드로 배우는 것이 목적이고,
> Kubernetes RCA 는 그 위에서 의미 있는 사용 시나리오를 보여주기 위한 도메인입니다.

---

## 본 레포 문서

| # | 문서 | 한 줄 안내 |
|---|------|-----------|
| 00 | [References](./00-references.ko.md) | 지금 이 페이지 — 모든 외부·내부 자료의 인덱스 |
| 01 | [시작하기](./01-getting-started.ko.md) | 설치, 사전 점검, 첫 실행까지 |
| 02 | [아키텍처](./02-architecture.ko.md) | 코드가 왜 이렇게 짜여 있는지 |
| 03 | [개발 가이드](./03-development.ko.md) | 새 specialist / 도구 / MCP 추가 튜토리얼 |
| 04 | [AgentCore 배포](./04-deployment-agentcore.ko.md) | Pattern 4, 멀티 클러스터, 운영 |
| 05 | [코드 스타일](./05-code-style.ko.md) | 가독성 원칙과 검토 기준 |
| 06 | [보안 & 부하](./06-security-and-load.ko.md) | layered defense 와 운영 체크리스트 |
| 07 | [운영 Runbook](./07-runbook.ko.md) | on-call 이 알람 받았을 때 따라가는 5 단계 절차 |

추천 학습 순서: **01 → 02 → 03 → 04 → 06 → 05 → 07** (Runbook 은 운영 시작 직전 한 번 정독)

---

## 1. Strands Agents SDK

LLM 에이전트와 도구를 묶는 SDK 입니다. 본 프로젝트에서 `Agent`, `MCPClient`, `agents-as-tools` 패턴을 모두 Strands 가 제공합니다.

| 자료 | 무엇이 들어 있나 | 본 레포 어디서 사용? |
|------|-----------------|-------------------|
| [Strands 홈](https://strandsagents.com) | SDK 개요와 빠른 시작 | README 진입 링크 |
| [Strands MCP Tools 통합](https://strandsagents.com/docs/user-guide/concepts/tools/mcp-tools/index.md) | `Agent(tools=[mcp_client])` 동작 방식 | `infrastructure/mcp_client.py`, `agents/pod_diagnostic.py` |
| [Strands → AgentCore 배포](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/index.md) | Strands 앱을 AgentCore Runtime 으로 옮기는 패턴 | `agentcore_app.py`, [docs/04](./04-deployment-agentcore.ko.md) |

처음 보는 분께 권하는 순서:
1. Strands 홈에서 "Quick start" 5 분 훑기 → 본 레포 [01](./01-getting-started.ko.md) 따라가기
2. MCP Tools 페이지 → 본 레포 [02 §3.1](./02-architecture.ko.md) 의 "Strands MCP 통합"
3. AgentCore 배포 페이지 → 본 레포 [04](./04-deployment-agentcore.ko.md)

---

## 2. Amazon Bedrock 와 Bedrock AgentCore

| 자료 | 무엇이 들어 있나 | 본 레포 어디서 사용? |
|------|-----------------|-------------------|
| [Bedrock 콘솔 - 모델 액세스](https://console.aws.amazon.com/bedrock/home#/modelaccess) | Claude 모델 활성화 | [01 §1, §7](./01-getting-started.ko.md) |
| [Bedrock AgentCore VPC 설정](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html) | VPC 모드와 endpoint 요구사항, ENI 동작, 지원 AZ | [04 §1](./04-deployment-agentcore.ko.md), [06 §1](./06-security-and-load.ko.md) |
| [Network connectivity patterns for AgentCore (블로그)](https://aws.amazon.com/blogs/networking-and-content-delivery/network-connectivity-patterns-for-agents-deployed-on-amazon-bedrock-agentcore-runtime/) | **Pattern 1 ~ 4 명명 출처** — Pattern 4 = full VPC isolation 토폴로지의 정의 | `deploy/agentcore/cdk_stack.py`, [04 §1](./04-deployment-agentcore.ko.md), [06 §1](./06-security-and-load.ko.md) |

> **"Pattern 4 (full VPC isolation)" 라는 명명은 위 블로그에서 정의된 분류**이며, AgentCore VPC 공식 docs 페이지에는 등장하지 않습니다. 본 레포는 두 출처를 함께 인용해야 정확합니다.

본 레포에서 Bedrock 와 AgentCore 의 어떤 부분을 사용하는지:

- **Bedrock**: Strands `Agent` 가 Claude 모델을 호출 (`bedrock:InvokeModel`)
- **Bedrock Guardrails (선택)**: 응답 필터링 (`bedrock:ApplyGuardrail`) — 활성화 안 하면 정책에서 제거 가능
- **AgentCore Runtime**: 컨테이너 격리 실행 환경. invocation 마다 microVM 격리 제공
- **AgentCore Pattern 4**: NAT 없는 격리 VPC + VPC endpoints

---

## 3. Amazon EKS MCP Server

본 레포가 K8s 데이터를 가져오는 통로입니다.

| 자료 | 무엇이 들어 있나 | 본 레포 어디서 사용? |
|------|-----------------|-------------------|
| [Amazon EKS MCP Server 소개](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-introduction.html) | 서비스 개요, preview 표기, redaction 동작 | [02 §3.1](./02-architecture.ko.md), [04 §2](./04-deployment-agentcore.ko.md), [06 §3](./06-security-and-load.ko.md) |
| [Getting Started with Amazon EKS MCP Server](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html) | endpoint URL 형식, IAM 액션명, mcp-proxy-for-aws 사용법 | `deploy/agentcore/iam-execution-policy.json`, `infrastructure/mcp_client.py` |
| [aws/mcp-proxy-for-aws](https://github.com/aws/mcp-proxy-for-aws) | managed MCP endpoint 호출 시 SigV4 서명을 담당하는 공식 proxy | [04 §2](./04-deployment-agentcore.ko.md) |
| [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html) | IAM principal → K8s group 매핑 | `deploy/agentcore/eks-rbac.yaml` |

본 레포에서 EKS MCP 가 어떻게 쓰이는지 한 줄로:

> EKS MCP Server 가 우리 IAM 자격 증명으로 K8s API 를 호출하고, 결과를 MCP 표준 도구 응답으로 LLM 에 돌려줍니다.
> 우리가 직접 `kubernetes` Python SDK 를 사용하지 않는 이유입니다.

자세한 데이터 흐름은 [02 §5](./02-architecture.ko.md) 의 invocation 라이프사이클 그림 참고.

---

## 4. Model Context Protocol (MCP)

| 자료 | 무엇이 들어 있나 |
|------|-----------------|
| [MCP 공식 사이트](https://modelcontextprotocol.io/) | 프로토콜 사양과 클라이언트/서버 구조 |
| [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) | 본 레포가 의존하는 Python SDK |

핵심 개념 한 줄:

> MCP 는 "LLM 이 도구를 안전하게 호출하도록 표준화한 RPC 프로토콜"입니다.
> stdio 또는 HTTP 위에서 JSON-RPC 형태로 동작합니다.

---

## 5. Kubernetes 보안

| 자료 | 무엇이 들어 있나 |
|------|-----------------|
| [Kubernetes RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/) | read-only ClusterRole 설계 근거 |
| [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) | `restricted` 프로파일 정의 |

본 레포는 진단 대상 클러스터에 `read-only ClusterRole` 만 부여하고 `secrets` 를 명시적으로 제외합니다 (`deploy/agentcore/eks-rbac.yaml`).

---

## 6. LLM 보안

| 자료 | 무엇이 들어 있나 |
|------|-----------------|
| [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | LLM 애플리케이션의 대표 위협 분류 |

본 레포의 [06 §5](./06-security-and-load.ko.md) 가 OWASP LLM Top 10 항목을 본 프로젝트의 layered defense 와 매핑합니다.

---

## 7. Python 코드 스타일

| 자료 | 무엇이 들어 있나 |
|------|-----------------|
| [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/) | 표준 스타일 가이드 |
| [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/) | docstring 작성 규칙 |
| [Clean Code (Robert C. Martin)](https://www.oreilly.com/library/view/clean-code-a/9780136083238/) | 챕터 2, 3 — 이름과 함수 |
| [The Art of Readable Code](https://www.oreilly.com/library/view/the-art-of/9781449318482/) | 가독성 원칙의 실전 예시 |

본 레포의 [05](./05-code-style.ko.md) 는 위 자료를 우리 도메인(에이전트 + MCP) 에 맞게 재구성한 것입니다.

---

## 8. 학습 경로 — 이 레포로 무엇을 배울 수 있나

| 관심사 | 추천 진입점 | 이어볼 자료 |
|-------|------------|-----------|
| Strands 로 에이전트 짜기 | [02 §3](./02-architecture.ko.md) | Strands MCP Tools 페이지 |
| Bedrock AgentCore 운영 | [04](./04-deployment-agentcore.ko.md) | AgentCore VPC 설정 페이지 |
| MCP 통합 패턴 | [02 §3.1](./02-architecture.ko.md), [03 §3](./03-development.ko.md) | MCP 공식 사이트 |
| K8s 진단 자동화 | [01 §6](./01-getting-started.ko.md), [03 §1](./03-development.ko.md) | EKS MCP Server 소개 |
| LLM 보안 모델 | [06](./06-security-and-load.ko.md) | OWASP LLM Top 10 |
| 가독 가능한 AI-보조 코드 | [05](./05-code-style.ko.md) | Clean Code 챕터 2-3 |

---

[← README 로](../README.ko.md) · [01. 시작하기 →](./01-getting-started.ko.md)
