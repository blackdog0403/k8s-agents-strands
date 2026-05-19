# 03. 개발 가이드

[← 02. 아키텍처](./02-architecture.md) · [04. AgentCore 배포 →](./04-deployment-agentcore.md)

이 문서는 **개발자가 따라하면서 새 기능을 추가할 수 있도록** 단계별 튜토리얼 형식으로 작성되었습니다. 각 섹션은 독립적이고, 실제 동작하는 코드를 제공합니다.

| 작업 | 난이도 | 소요 시간 | 섹션 |
|------|-------|---------|------|
| 새 specialist agent 추가 | 중 | 30 분 | [§1](#1-튜토리얼-network-diagnostic-specialist-추가) |
| 자체 특화 도구 추가 | 하 | 15 분 | [§2](#2-튜토리얼-자체-도구-추가) |
| 다른 MCP 서버 통합 | 중 | 30 분 | [§3](#3-튜토리얼-다른-mcp-서버-통합) |
| 도메인 모델 확장 | 상 | 1 시간 | [§4](#4-도메인-모델-확장) |
| 테스트 작성 | 하 | 자유 | [§5](#5-테스트-작성) |

각 튜토리얼의 구성은 다음과 같습니다.

- **목표** — 무엇을 만들 것인가
- **단계별 작업** — 1, 2, 3 ...
- **검증** — 잘 됐는지 어떻게 확인할까
- **자주 만나는 문제**

---

## 1. 튜토리얼: Network Diagnostic Specialist 추가

### 목표

네트워크 관련 장애(Service 연결 실패, DNS, NetworkPolicy 등) 를 진단하는 새 specialist agent 를 추가하고, orchestrator 가 그것을 라우팅하도록 만듭니다.

### 단계별 작업

#### Step 1. specialist agent 파일 생성

`src/k8s_rca_agent/agents/network_diagnostic.py` 를 새로 만듭니다.

```python
"""Network 단위 장애를 진단하는 specialist agent."""
from __future__ import annotations

from strands import Agent

from k8s_rca_agent.infrastructure.container import container

NETWORK_DIAGNOSTIC_PROMPT = """\
당신은 Kubernetes 네트워크 장애 진단 전문가입니다.
EKS MCP Server 가 제공하는 K8s 도구를 사용해 다음을 조사합니다.

## 진단 절차

호출 시 invocation context 의 ``cluster`` 이름을 모든 MCP 도구 호출에 전달합니다.

1. **Service 상태 확인** — Service 의 endpoint 와 selector 일치
2. **NetworkPolicy 검토** — 차단 규칙 여부
3. **DNS 동작 확인** — CoreDNS 상태와 응답
4. **Ingress 확인** (필요시) — Ingress controller 와 라우팅 규칙

## 자주 보는 증상과 가능한 원인

| 증상 | 가능한 원인 |
|------|------------|
| Connection refused | Service selector ≠ Pod label, Pod down |
| DNS 해석 실패 | CoreDNS 장애, NetworkPolicy 차단 |
| Timeout | NetworkPolicy 거부, Pod CIDR 라우팅 문제 |
| Ingress 503 | Backend Service unhealthy, TLS 설정 |

## 출력 형식

근본 원인 → 클러스터·리소스 → 증거 → 권장 조치 → 신뢰도 순으로 적습니다.
민감 정보가 보이면 마스킹합니다.
"""


def create_network_diagnostic_agent() -> Agent:
    return Agent(
        name="network_diagnostic",
        description=(
            "네트워크 관련 장애를 진단합니다 "
            "(Service 연결, DNS, NetworkPolicy, Ingress). "
            "호출 시 cluster, namespace, 리소스 이름을 명시해야 합니다."
        ),
        system_prompt=NETWORK_DIAGNOSTIC_PROMPT,
        tools=[container.eks_mcp],
    )
```

#### Step 2. `agents/__init__.py` 에 export 추가

```python
from .network_diagnostic import create_network_diagnostic_agent
from .orchestrator import create_orchestrator
from .pod_diagnostic import create_pod_diagnostic_agent

__all__ = [
    "create_network_diagnostic_agent",
    "create_orchestrator",
    "create_pod_diagnostic_agent",
]
```

#### Step 3. orchestrator 의 라우팅 업데이트

`src/k8s_rca_agent/agents/orchestrator.py` 에 다음을 반영합니다.

```python
from .network_diagnostic import create_network_diagnostic_agent
from .pod_diagnostic import create_pod_diagnostic_agent

ORCHESTRATOR_PROMPT = """\
...
## 도메인 라우팅 기준

- **Pod 관련 증상** → `pod_diagnostic`
- **네트워크 관련 증상** (연결 실패, DNS, Service, Ingress) → `network_diagnostic`
...
"""


def create_orchestrator() -> Agent:
    return Agent(
        name="rca_orchestrator",
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            create_pod_diagnostic_agent(),
            create_network_diagnostic_agent(),  # 추가
        ],
    )
```

#### Step 4. import 검증

```bash
python -c "from k8s_rca_agent.agents import create_network_diagnostic_agent; \
           agent = create_network_diagnostic_agent(); \
           print(f'OK: {agent.name}')"
```

기대 출력: `OK: network_diagnostic`

### 검증

#### 4.1 단위 import 확인

```bash
PYTHONPATH=src python -c "from k8s_rca_agent.agents import create_orchestrator; print('OK')"
```

#### 4.2 라우팅 확인 (실제 LLM 호출)

```bash
python -m k8s_rca_agent.main --cluster <your-cluster> \
  "default 네임스페이스의 my-service 에서 connection refused 발생하는데 봐줘"
```

orchestrator 가 `network_diagnostic` 을 호출하는 trace 가 보여야 합니다.

#### 4.3 syntax 자동 검증

```bash
ruff check src/k8s_rca_agent/agents/
mypy src/k8s_rca_agent/agents/
```

### 자주 만나는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `ImportError: cannot import name 'create_network_diagnostic_agent'` | `agents/__init__.py` 누락 | Step 2 적용 |
| LLM 이 새 specialist 를 부르지 않고 항상 pod_diagnostic 호출 | Orchestrator system prompt 에 라우팅 기준 누락 | Step 3 의 prompt 갱신 확인 |
| Network specialist 가 잘못된 도구 호출 | system prompt 가 모호함 | "자주 보는 증상" 표를 더 구체적으로 작성 |

---

## 2. 튜토리얼: 자체 도구 추가

### 목표

EKS MCP 가 제공하지 않는 작업이 필요할 때 (예: 외부 비용 시스템 조회). 한 specialist agent 에 도구 한 개를 추가합니다.

### 단계별 작업

#### Step 1. 도구 파일 생성

`src/k8s_rca_agent/tools/cost_tools.py` 를 새로 만듭니다.

```python
"""비용 추정 도구 — 외부 시스템에서 데이터를 가져온다."""
from __future__ import annotations

import logging

from strands import tool

from k8s_rca_agent.domain.validation import (
    validate_cluster_name,
    validate_namespace,
    validate_resource_name,
)

logger = logging.getLogger(__name__)


@tool
def get_pod_cost_estimate(cluster: str, namespace: str, pod_name: str) -> dict:
    """특정 Pod 의 월 비용 추정값을 반환한다.

    EKS MCP 가 제공하지 않는 외부 비용 시스템 데이터를 조회한다.
    OOMKilled 같은 진단에서 "메모리를 늘려라"고 권장하기 전에 비용 영향을
    함께 안내할 때 사용한다.

    Args:
        cluster: 클러스터 등록 이름 (예: "prod-us")
        namespace: 네임스페이스
        pod_name: Pod 이름

    Returns:
        {
            "monthly_usd": float,
            "compute_usd": float,
            "memory_usd": float,
            "currency": "USD",
        }
    """
    cluster = validate_cluster_name(cluster)
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name)

    logger.info("비용 조회: cluster=%s ns=%s pod=%s", cluster, namespace, pod_name)

    # TODO: 실제 비용 시스템(예: 사내 FinOps API) 호출
    # 여기서는 stub
    return {
        "monthly_usd": 12.34,
        "compute_usd": 8.00,
        "memory_usd": 4.34,
        "currency": "USD",
    }
```

#### Step 2. `tools/__init__.py` 에 export 추가

```python
from .cost_tools import get_pod_cost_estimate

__all__ = ["get_pod_cost_estimate"]
```

#### Step 3. specialist agent 의 tools 배열에 추가

`src/k8s_rca_agent/agents/pod_diagnostic.py`:

```python
from k8s_rca_agent.infrastructure.container import container
from k8s_rca_agent.tools import get_pod_cost_estimate


def create_pod_diagnostic_agent() -> Agent:
    return Agent(
        ...,
        tools=[container.eks_mcp, get_pod_cost_estimate],  # 둘 다
    )
```

#### Step 4. system prompt 에 사용 시점 명시

```python
POD_DIAGNOSTIC_PROMPT = """\
...
## 비용 영향 분석 (선택)

OOMKilled 나 메모리 limit 증설을 권장하기 전에 ``get_pod_cost_estimate`` 도구로
현재 비용을 확인하고, 권장 조치의 비용 영향을 함께 안내합니다.
...
"""
```

### 검증

```bash
# 1) 도구가 등록됐는지
python -c "from k8s_rca_agent.tools import get_pod_cost_estimate; \
           print(get_pod_cost_estimate.__doc__[:80])"

# 2) 입력 검증 동작 확인
python -c "
from k8s_rca_agent.tools.cost_tools import get_pod_cost_estimate
result = get_pod_cost_estimate.func('prod-us', 'default', 'nginx')
assert result['currency'] == 'USD'
print('OK')
"
```

### 자주 만나는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| LLM 이 도구를 부르지 않음 | docstring 이 모호함 | "언제 이 도구를 쓰는지" 를 명시 |
| `AttributeError: 'function' object has no attribute 'func'` | `@tool` 데코레이터 미적용 | import 경로 확인 |
| 입력 검증 실패가 LLM 에 안 보임 | 예외 메시지가 모호함 | `ValueError` 메시지를 자세히 |

### 도구 작성 체크리스트

- [ ] LLM 이 보고 도구를 선택할 수 있도록 docstring 이 명확하다
- [ ] 모든 파라미터에 타입 힌트가 있다
- [ ] 입력 검증(`validate_*`)을 거친다
- [ ] 부수 효과(쓰기) 작업과 조회 작업이 분리되어 있다
- [ ] 에러 메시지를 LLM 이 이해할 수 있다

---

## 3. 튜토리얼: 다른 MCP 서버 통합

### 목표

EKS MCP 외에 Prometheus MCP server 를 추가해 메트릭 데이터도 LLM 이 활용할 수 있게 합니다.

### 단계별 작업

#### Step 1. mcp_client.py 에 팩토리 추가

`src/k8s_rca_agent/infrastructure/mcp_client.py`:

```python
def create_prometheus_mcp_client():
    """Prometheus MCP 클라이언트.

    환경 변수 ``PROMETHEUS_MCP_ENDPOINT`` 가 필요하다 (HTTP transport).
    """
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    endpoint = os.getenv("PROMETHEUS_MCP_ENDPOINT")
    if not endpoint:
        raise ValueError("PROMETHEUS_MCP_ENDPOINT 가 설정되지 않았습니다")

    logger.info("Prometheus MCP 시작 — endpoint=%s", endpoint)
    return MCPClient(lambda: streamablehttp_client(endpoint))
```

#### Step 2. Container 에 등록

`src/k8s_rca_agent/infrastructure/container.py`:

```python
from .mcp_client import create_eks_mcp_client, create_prometheus_mcp_client


class Container:
    @cached_property
    def eks_mcp(self):
        return create_eks_mcp_client()

    @cached_property
    def prometheus_mcp(self):
        return create_prometheus_mcp_client()
```

#### Step 3. 사용할 specialist agent 에 추가

새 `resource_diagnostic` specialist 를 만든다면:

```python
# agents/resource_diagnostic.py
return Agent(
    name="resource_diagnostic",
    ...,
    tools=[container.eks_mcp, container.prometheus_mcp],  # 둘 다
)
```

Strands 가 두 MCP 서버의 도구를 모두 자동으로 노출합니다.

#### Step 4. 도구 이름 충돌 시

만약 두 MCP 서버가 같은 이름의 도구를 노출한다면 (드뭅니다), Strands `MCPClient` 의 prefix 옵션을 사용합니다 — [Strands MCP 통합 문서](./00-references.md#1-strands-agents-sdk).

### 검증

```bash
PROMETHEUS_MCP_ENDPOINT=http://localhost:9090/mcp \
python -c "from k8s_rca_agent.infrastructure.container import container; \
           print(container.prometheus_mcp)"
```

### 자주 만나는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `ValueError: PROMETHEUS_MCP_ENDPOINT 가 설정되지 않았습니다` | 환경 변수 누락 | `export PROMETHEUS_MCP_ENDPOINT=...` |
| MCP server 인증 실패 | SigV4 또는 token 누락 | 서버 종류에 맞는 transport 사용 |
| 도구 이름 충돌 | EKS MCP 와 같은 이름 | prefix 부여 |

---

## 4. 도메인 모델 확장

### 목표

진단 결과에 비용 정보까지 포함하도록 `Diagnosis` 모델을 확장합니다.

### 단계별 작업

#### Step 1. 도메인 모델 변경

`src/k8s_rca_agent/domain/models.py`:

```python
@dataclass(frozen=True)
class CostImpact:
    monthly_usd: float
    description: str  # 예: "메모리 limit 1Gi → 2Gi 변경 시 +$8/월"


@dataclass(frozen=True)
class Diagnosis:
    root_cause: str
    affected_resources: list[str]
    confidence: float
    recommended_actions: list[str]
    evidence: list[str]
    summary: str = ""
    cost_impact: CostImpact | None = None  # 추가

    def to_dict(self) -> dict:
        result = {
            "root_cause": self.root_cause,
            "affected_resources": self.affected_resources,
            "confidence": self.confidence,
            "recommended_actions": self.recommended_actions,
            "evidence": self.evidence,
            "summary": self.summary,
        }
        if self.cost_impact:
            result["cost_impact"] = {
                "monthly_usd": self.cost_impact.monthly_usd,
                "description": self.cost_impact.description,
            }
        return result
```

#### Step 2. 테스트 추가

`tests/domain/test_models.py`:

```python
def test_diagnosis_with_cost_impact():
    cost = CostImpact(monthly_usd=8.0, description="메모리 증설")
    d = Diagnosis(
        root_cause="OOMKilled", affected_resources=["pod/api"], confidence=0.85,
        recommended_actions=["메모리 limit 2Gi"], evidence=[], summary="",
        cost_impact=cost,
    )
    out = d.to_dict()
    assert out["cost_impact"]["monthly_usd"] == 8.0


def test_diagnosis_without_cost_impact_omits_field():
    d = Diagnosis(
        root_cause="x", affected_resources=[], confidence=0.5,
        recommended_actions=[], evidence=[],
    )
    assert "cost_impact" not in d.to_dict()
```

### 검증

```bash
pytest tests/domain/test_models.py -v
```

### 자주 만나는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `TypeError: __init__() missing 1 required positional argument` | dataclass 에 default 없는 필드 추가 | 새 필드는 `= None` 기본값 |
| 기존 테스트 실패 | dict 포맷 변경 | 기존 테스트가 `==` 비교한다면 신중히 |

---

## 5. 테스트 작성

| 계층 | 테스트 방식 | 비고 |
|------|------------|------|
| `domain/` (models, validation) | 순수 단위 테스트 | 외부 의존성 없음, 빠름 |
| `infrastructure/redaction.py` | 단위 테스트 | 입출력만 검증 |
| `infrastructure/mcp_client.py` | 통합 테스트 또는 mock | 실제 MCP 서버 필요 시 통합 |
| `agents/` | 통합 테스트 | 실제 LLM 호출 또는 mock LLM |

### 빠른 단위 테스트 — 외부 의존성 없음

```python
# tests/domain/test_validation.py
def test_validate_cluster_name_rejects_path_traversal():
    with pytest.raises(InvalidResourceName):
        validate_cluster_name("../etc/passwd")
```

### Mock 기반 단위 테스트

```python
# tests/agents/test_pod_diagnostic.py
def test_pod_diagnostic_uses_mcp(mocker):
    mock_mcp = mocker.MagicMock()
    mocker.patch(
        "k8s_rca_agent.infrastructure.container.container.eks_mcp",
        mock_mcp,
    )
    agent = create_pod_diagnostic_agent()
    assert mock_mcp in agent.tools
```

### 실행

```bash
pytest tests/ -v
pytest tests/domain/ -v        # domain 만
pytest -k cluster              # cluster 키워드 매칭
pytest --cov=k8s_rca_agent     # 커버리지
```

---

## 6. 코드 품질 자동화

### Ruff (린트와 포맷)

```bash
ruff check src tests           # 검사
ruff check src tests --fix     # 자동 수정
ruff format src tests          # 포맷
```

### mypy

```bash
mypy src
```

### pre-commit (커밋 시 자동 실행, 권장)

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
```

```bash
pip install pre-commit
pre-commit install
```

---

## 7. 일반 개발 워크플로우

```
[1] 작업 시작 시 — 어떤 종류의 변경인가?

  도구만 추가         → §2 (15 분)
  새 specialist     → §1 (30 분)
  MCP 서버 추가      → §3 (30 분)
  도메인 변경        → §4 (1 시간)

[2] 코드 작성

  - 단위 테스트 먼저 (TDD), 또는
  - 코드 → 테스트 (시간 절약)

[3] 검증 (모든 변경)

  pytest tests/
  ruff check src tests
  mypy src

[4] 로컬 통합 검증 (선택)

  python -m k8s_rca_agent.main --cluster <c> "관련 시나리오"

[5] 진입점 검증 (배포 직전)

  python -m k8s_rca_agent.agentcore_app
  curl localhost:8080/invocations -d '{...}'

[6] PR
  - 5 초 안에 의도가 보이는가?
  - 추상화가 정당화되는가?
  - 사람이 line-by-line 이해했는가?
```

---

## 다음 단계

- 운영 환경 배포 절차 → [04. AgentCore 배포](./04-deployment-agentcore.md)
- 가독성 원칙과 검토 기준 → [05. 코드 스타일](./05-code-style.md)
- 보안 모델과 운영 체크리스트 → [06. 보안 & 부하](./06-security-and-load.md)

## 더 깊이 알아보기

- Strands `@tool` 데코레이터의 schema 추출 동작 — [Strands MCP Tools 통합](./00-references.md#1-strands-agents-sdk)
- 다른 도메인 MCP 서버를 어떻게 짤지 — [MCP 공식 사이트](./00-references.md#4-model-context-protocol-mcp)

---

[← 02. 아키텍처](./02-architecture.md) · [04. AgentCore 배포 →](./04-deployment-agentcore.md)
