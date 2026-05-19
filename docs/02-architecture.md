# 02. 아키텍처

[← 01. 시작하기](./01-getting-started.md) · [03. 개발 가이드 →](./03-development.md)

이 문서는 코드가 **왜 이렇게 구성되어 있는지** 를 설명합니다.
세 줄 요약:

1. [Strands Agents SDK](./00-references.md#1-strands-agents-sdk) 로 LLM 에이전트와 도구를 묶습니다.
2. K8s 데이터는 [EKS MCP Server](./00-references.md#3-amazon-eks-mcp-server) 가 가져옵니다 — 우리는 직접 K8s API 를 호출하지 않습니다.
3. 운영 환경에서는 [Bedrock AgentCore Runtime](./00-references.md#2-amazon-bedrock-와-bedrock-agentcore) 위에서 Pattern 4 (full VPC isolation) 로 실행합니다.

직접 구현하는 대신 검증된 컴포넌트에 책임을 위임합니다. 우리가 직접 짜는 코드는 **진단 워크플로우(어떤 도구를 어떤 순서로 부를지)** 와 **도메인 의미(에이전트의 system prompt 와 도메인 모델)** 에 집중되어 있습니다.

---

## 1. 한눈에 보기

```
              사용자 / AgentCore payload
                       │   { query, cluster }
                       ▼
              ┌──────────────────────┐
              │ Orchestrator Agent   │
              │  (라우팅과 종합)     │
              └──────────┬───────────┘
                         │  specialist 에 위임
                         ▼
              ┌──────────────────────┐
              │ Pod Diagnostic Agent │
              │  tools = [eks_mcp]   │
              └──────────┬───────────┘
                         │  MCP 도구 호출
                         ▼
              ┌──────────────────────┐
              │   EKS MCP Server     │
              │   (AWS managed)      │
              └──────────┬───────────┘
                         │  SigV4 + EKS API
                         ▼
                    EKS 클러스터
```

세 계층뿐입니다 — Agent, MCP Server, EKS.

---

## 2. 디렉토리 구조

```
src/k8s_rca_agent/
├── domain/
│   ├── models.py          # Diagnosis (출력 도메인 모델)
│   └── validation.py      # cluster, namespace, 리소스 이름 입력 검증
├── infrastructure/
│   ├── mcp_client.py      # EKS MCP 클라이언트 팩토리 (stdio | http)
│   ├── container.py       # DI 컨테이너 (싱글톤 MCP 클라이언트)
│   └── redaction.py       # 응답 민감 정보 마스킹 유틸
├── agents/
│   ├── orchestrator.py    # 사용자 → specialist 라우팅
│   └── pod_diagnostic.py  # Pod 진단 specialist
├── tools/                 # 자체 특화 도구 (현재 비어 있음)
├── agentcore_app.py       # AgentCore Runtime 진입점
└── main.py                # 로컬 CLI 진입점
```

소스 파일 11 개. EKS MCP 도입 전 17 개에서 절반 가까이 줄었습니다.

---

## 3. 적용된 패턴

### 3.1 Strands MCP 통합

`Agent(tools=[mcp_client])` 한 줄로 끝납니다. `MCPClient` 가 connect, list_tools, tool 호출, disconnect 라이프사이클을 자동으로 관리합니다 — [Strands MCP Tools 문서](./00-references.md#1-strands-agents-sdk).

```python
# infrastructure/mcp_client.py
def create_eks_mcp_client():
    transport = os.getenv("EKS_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        return _create_stdio_client()      # 로컬 dev: uvx 자식 프로세스
    return _create_http_client()           # managed: AWS 호스팅 endpoint
```

### 3.2 Multi-Agent — agents-as-tools

Orchestrator 가 specialist 자체를 도구처럼 호출합니다. Strands 가 권장하는 패턴입니다.

```python
# agents/orchestrator.py
return Agent(
    name="rca_orchestrator",
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[create_pod_diagnostic_agent()],   # specialist 가 곧 도구
)
```

### 3.3 입력 검증 (얕은 sanity check)

`domain/validation.py` 에서 cluster_name, namespace, 리소스 이름의 형식만 빠르게 검증합니다. 권한은 IAM 이, 리소스 존재는 EKS MCP 가 검증하므로 우리는 명백히 잘못된 입력만 거릅니다.

### 3.4 후처리 redaction (예비)

`infrastructure/redaction.py` 가 토큰·패스워드 패턴 마스킹 유틸을 제공합니다. 현재 1차 방어선은 specialist 의 system prompt 이고, `redact()` 는 layered defense 를 위한 예비 함수입니다 — 자세한 정책은 [06 §6](./06-security-and-load.md).

---

## 4. 의존성 방향

```
agents → tools → infrastructure → domain
                                    ▲
                                  외부에서
                                  의존하지 않음
```

- `domain` — 외부 라이브러리 import 없음
- `infrastructure` — `mcp`, `boto3` 같은 외부 라이브러리 사용
- `agents` — `infrastructure.container` 를 거쳐 MCP 클라이언트 획득
- `tools` — 우리만의 특화 도구가 생기면 여기에 두는 자리 (현재 비어 있음)

이 방향이 깨지지 않으면, 내부 구현을 자유롭게 바꾸면서도 도메인 코드가 안전합니다.

---

## 5. 애플리케이션 흐름

요청이 들어와 응답이 돌아가기까지의 전체 흐름입니다. 실전 디버깅과 운영에 도움이 되는 정보를 위주로 정리했습니다.

### 5.1 진입점별 흐름 비교

진입점은 두 가지 — 로컬 CLI 와 AgentCore Runtime. 두 경로 모두 같은 orchestrator 를 호출합니다.

```
[로컬 CLI]                              [AgentCore Runtime]
python -m k8s_rca_agent.main            POST /invocations
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
               (이후 동일 — §5.2 참고)
```

차이점은 진입과 응답 형식뿐입니다.

| 항목 | 로컬 CLI | AgentCore |
|------|---------|-----------|
| 입력 | argparse | JSON payload |
| 출력 | stdout 출력 | JSON 응답 |
| 라이프사이클 | 프로세스 1 개, 인터랙티브 가능 | invocation 마다 microVM |
| 실수 검증 | argparse 스키마 | `_build_query()` |

### 5.2 단일 invocation 라이프사이클

AgentCore 에 한 번 호출이 들어왔을 때:

```
1. AgentCore Runtime 이 microVM 부팅 (cold) 또는 재사용 (warm)
   │
   ├─ cold: microVM 생성 → 이미지 로드 → BedrockAgentCoreApp 시작
   └─ warm: 기존 microVM 에 요청 라우팅
   │
   ▼
2. /invocations POST 도착 → @app.entrypoint(handler) 호출
   │
   ▼
3. invoke(payload) 실행
   ├─ _build_query: query, cluster 추출과 검증
   └─ orchestrator = create_orchestrator()    ← 매 invocation 마다 새로
   │
   ▼
4. orchestrator(user_message) — Strands Agent loop 시작
   │
   ├─ LLM 호출 1: "어느 specialist 에게 위임할까?"
   │            → pod_diagnostic
   │
   ▼
5. pod_diagnostic_agent(<연결된 message>)
   │
   ├─ MCP 클라이언트가 lazy connect
   │   └─ stdio: uvx 자식 프로세스 시작 (cold 일 때만)
   │       또는
   │   └─ http: streamable_http 연결 + (proxy 가) SigV4 서명
   │
   ├─ MCP 에서 list_tools() 받아 LLM 에 노출
   │
   ├─ LLM 호출 2: "어떤 도구를 부를까?"
   │            → get_pod
   │
   ├─ MCP tool 실행: get_pod(cluster=..., namespace=..., name=...)
   │   └─ EKS MCP server → eks:DescribeCluster → K8s API → 응답
   │
   ├─ LLM 호출 3: 응답 보고 다음 단계 결정
   │            "이벤트도 봐야겠다" → get_pod_events 호출
   │
   ├─ ... (필요한 만큼 도구 호출 반복)
   │
   └─ LLM 호출 N: 충분한 정보 모임 → 최종 응답 작성
   │
   ▼
6. orchestrator 의 LLM 이 specialist 결과를 종합해 답변
   │
   ▼
7. invoke() 반환: {"response": "...", "cluster": "..."}
   │
   ▼
8. AgentCore 가 JSON 응답 반환
   │
   ▼
9. microVM 은 재사용을 위해 보관 또는 폐기 (AgentCore 가 결정)
```

핵심 세 가지:

- **매 invocation 마다 fresh orchestrator** — 상태가 invocation 사이에 새지 않습니다.
- **MCP 는 lazy 연결** — 첫 도구 호출 시점에 연결되고 invocation 끝나면 해제됩니다.
- **LLM 은 도구를 여러 번 호출** — 한 invocation 에서 5 ~ 10 회도 흔합니다.

### 5.3 도구 호출 한 사이클 상세

도구 한 번 호출이 어떻게 일어나는지:

```
LLM 이 tool_use 결정
    │  {"tool": "get_pod", "args": {...}}
    ▼
Strands SDK 가 args 검증 (도구의 type hint 기반 schema)
    │
    ▼
MCPClient 가 MCP 서버에 RPC 요청
    │  JSON-RPC over stdio 또는 streamable HTTP
    ▼
EKS MCP Server 가 SigV4 로 EKS API 호출
    │
    ▼
응답이 역방향으로 돌아옴
    EKS API → MCP server → MCPClient → Strands → LLM context
    │
    ▼
LLM 이 응답을 보고 다음 액션 결정
```

우리 코드가 직접 관여하는 곳은 거의 없습니다. Strands SDK 와 MCP 가 처리합니다.

### 5.4 에러 흐름

| 에러 발생 위치 | 결과 | 사용자 경험 |
|--------------|------|-----------|
| `_build_query` 에서 query 또는 cluster 누락 | `ValueError` → AgentCore 4xx | "필드가 비어 있습니다" 메시지 |
| LLM 이 잘못된 형식의 도구 args | Strands schema 검증 실패 | LLM 이 자동으로 재시도 |
| MCP 일시 오류 (5xx, throttle) | MCP 클라이언트 retry | invocation 시간 약간 길어짐 |
| MCP 영구 오류 (4xx 권한 없음) | 도구가 에러 메시지 반환 | LLM 이 사용자에게 권한 문제 안내 |
| EKS RBAC 차단 (예: secrets 조회) | 403 → MCP 도구 에러 메시지 | LLM 이 "권한이 없어 못 봅니다" 응답 |
| LLM 환각 (없는 도구 호출) | Strands 가 거부 → LLM 재시도 | 사용자 영향 없음 |
| Bedrock throttling | Strands retry | invocation 시간 길어짐 |
| AgentCore timeout | invocation 종료 | "분석이 길어집니다, 좁혀서 다시 질의" |

핵심: **에러도 LLM 에게 자연어로 전달되어 자동 회복을 시도**합니다. 우리가 try/except 로 처리할 일이 거의 없는 이유입니다.

### 5.5 콜드·웜 스타트 비용

```
[Cold start — 첫 invocation 또는 microVM 갱신 후]

  microVM 부팅, 컨테이너 시작, Python import, BedrockAgentCoreApp 시작이
  순서대로 일어납니다. 사용자 체감 추가 지연이 있을 수 있습니다.

  [첫 도구 호출 시]
  MCP stdio: uvx 부팅 비용
  MCP http: streamable_http 연결 + list_tools()

[Warm — microVM 재사용]
  거의 즉시 invocation 시작
  MCP 는 invocation 단위로 새로 연결
```

운영 팁:

- 평소 트래픽이 있으면 warm 상태가 유지되어 cold start 영향이 작습니다.
- MCP 는 매 invocation 마다 새로 연결됩니다 (microVM 격리 때문). http transport 가 stdio 보다 일관되게 빠릅니다.
- 진단 자체가 LLM 다회 호출이라 5 ~ 30 초가 걸립니다. 1 ~ 2 초 cold start 는 큰 부담이 아닙니다.

---

## 6. 자주 묻는 질문

### Q. 왜 `kubernetes` Python SDK 를 직접 사용하지 않나요?

EKS MCP Server 가 이미 잘 처리합니다. 우리가 직접 사용하면 다음을 모두 직접 구현해야 합니다.

- 인증, 토큰 갱신, 캐시, retry, 멀티 클러스터
- K8s API 변경 대응
- MCP 표준의 이점(다른 MCP 서버와 통합) 상실

### Q. `ClusterRegistry` 같은 매핑은 왜 없나요?

직접 호출 시에는 cluster_name → endpoint 매핑이 필요했지만, EKS MCP 가 IAM scope 로 처리합니다. AgentCore execution role 이 접근 권한을 가진 클러스터만 호출됩니다.

### Q. `PodSnapshot` 같은 도메인 모델은 왜 없앴나요?

MCP 응답을 LLM 에게 dict 그대로 넘기면 충분합니다. `is_healthy` 같은 도메인 의미는 LLM 이 system prompt 를 보고 판단합니다. 진짜 비즈니스 로직(예: 진단 결과 종합)이 생기면 그때 도메인 모델을 추가합니다.

### Q. Specialist Agent 는 왜 분리했나요?

Strands 의 권장 패턴이고, 도메인별 system prompt 를 좁게 유지할 수 있습니다. 향후 Network 또는 Resource Diagnostic Agent 를 추가해도 Orchestrator 만 수정하면 됩니다.

---

## 7. 향후 확장 시점

- **새 specialist** (Network, Resource 등) → `agents/<domain>_diagnostic.py` 추가, Orchestrator 의 `tools` 에 등록 ([03 §1](./03-development.md))
- **자체 특화 도구** (MCP 가 못 하는 것) → `tools/` 에 `@tool` 함수 추가, specialist 의 `tools=[mcp, our_tool]` ([03 §2](./03-development.md))
- **다른 MCP 서버 통합** (예: Prometheus MCP) → 같은 패턴으로 `Agent(tools=[eks_mcp, prom_mcp, ...])` ([03 §3](./03-development.md))
- **Bedrock Guardrails** → `BedrockModel` 에 `guardrailConfig` 추가

---

## 다음 단계

- 실제로 새 기능을 추가해보기 → [03. 개발 가이드](./03-development.md)
- 운영 환경에 올리기 → [04. AgentCore 배포](./04-deployment-agentcore.md)
- 보안 모델 한 번에 확인하기 → [06. 보안 & 부하](./06-security-and-load.md)

## 더 깊이 알아보기

- Strands 의 agents-as-tools 패턴 — [Strands MCP Tools 통합](./00-references.md#1-strands-agents-sdk)
- Bedrock AgentCore Runtime 의 microVM 격리 모델 — [AgentCore VPC 설정](./00-references.md#2-amazon-bedrock-와-bedrock-agentcore)
- EKS MCP Server 가 호출하는 K8s API 의 범위 — [Amazon EKS MCP Server 소개](./00-references.md#3-amazon-eks-mcp-server)

---

[← 01. 시작하기](./01-getting-started.md) · [03. 개발 가이드 →](./03-development.md)
