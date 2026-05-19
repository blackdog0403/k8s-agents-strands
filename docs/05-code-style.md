# 05. 코드 스타일

[← 04. AgentCore 배포](./04-deployment-agentcore.md) · [06. 보안 & 부하 →](./06-security-and-load.md)

이 프로젝트의 모든 코드는 **읽기 쉬워야 한다**는 단 하나의 원칙을 따릅니다.
영리한 코드보다 명확한 코드가 항상 낫습니다.

---

## 핵심 원칙

> **6 개월 후의 자신, 또는 처음 보는 동료가 5 초 안에 의도를 파악할 수 있어야 한다.**

이 한 문장이 모든 결정의 기준입니다.

---

## AI 보조 개발의 원칙

이 프로젝트는 AI 도구의 도움을 받아 개발됩니다. 그래도 **운영에 올라가는 코드는 사람이 이해할 수 있어야 합니다.**

| 원칙 | 의미 |
|------|------|
| **사람이 검토하지 않은 코드는 commit 하지 않습니다** | AI 가 짠 코드도 line-by-line 검토 후에 사용 |
| **이해하지 못한 코드는 운영에 올리지 않습니다** | "동작은 한다"는 이유로 머지하지 않습니다 |
| **MCP 와 SDK 우선, 직접 구현은 마지막** | 검증된 코드를 쓰는 것이 사람이 읽기에도 더 명확합니다 |
| **추상화는 정당화될 때만** | 지금 필요 없는 layer 는 사람이 읽을 때 noise 일 뿐입니다 |
| **이름이 의도를 드러내야 합니다** | AI 도움 받았는지와 무관하게 코드는 사람을 위한 문서입니다 |

PR 리뷰의 첫 질문은 한결같이 같습니다 — "이 코드가 무엇을 하는지 5 초 안에 알겠는가?"

---

## 1. 이름은 의도를 드러낸다

이름 하나가 주석 10 줄을 대체할 수 있습니다.

```python
# 무엇을 하는지 알기 어려움
def proc(d):
    return [x for x in d if x.s != "R"]

# 이름만 봐도 명확함
def find_unhealthy_pods(pods: list[dict]) -> list[dict]:
    return [pod for pod in pods if pod["phase"] != "Running"]
```

### 변수명 규칙

| 안 좋음 | 더 나음 | 이유 |
|---------|---------|------|
| `data`, `result`, `tmp` | `pods`, `unhealthy_pods`, `mcp_response` | 무엇을 담는지 명시 |
| `i`, `j` | `pod_index`, `attempt` | 의미 있는 인덱스 |
| `flag`, `check` | `is_healthy`, `has_warnings` | bool 은 동사로 시작 |
| `getList`, `doStuff` | `find_pod_events` | 동작 + 대상 |

### 단축어 피하기

```python
# 안 좋음
def proc_evt(e):
    ns = e.metadata.namespace
    ...

# 더 나음
def process_event(event):
    namespace = event.metadata.namespace
    ...
```

---

## 2. 매직 스트링과 매직 넘버는 상수로

```python
# 의미가 흩어져 있음
if transport == "stdio":
    ...
elif transport == "http":
    ...

# 한 곳에 정의
_TRANSPORT_STDIO = "stdio"
_TRANSPORT_HTTP = "http"
```

`infrastructure/redaction.py` 에서도 임계값을 상수로 분리합니다.

```python
_REDACTED = "***REDACTED***"
_DEFAULT_MAX_LENGTH = 4096
```

---

## 3. 함수는 한 가지 일만

함수가 하는 일을 한 문장으로 설명할 수 없으면 너무 큰 것입니다.

```python
# 분기, IO, 변환이 한 함수에 섞여 있음
def get_mcp_client():
    transport = os.getenv("EKS_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        package = os.getenv("EKS_MCP_PACKAGE", "awslabs.eks-mcp-server@latest")
        from mcp import StdioServerParameters, stdio_client
        from strands.tools.mcp import MCPClient
        return MCPClient(lambda: stdio_client(StdioServerParameters(command="uvx", args=[package])))
    else:
        from mcp.client.streamable_http import streamablehttp_client
        from strands.tools.mcp import MCPClient
        endpoint = os.getenv("EKS_MCP_ENDPOINT")
        return MCPClient(lambda: streamablehttp_client(endpoint))

# 분기와 위임 — 각 transport 는 별도 함수
def create_eks_mcp_client():
    transport = os.getenv("EKS_MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        return _create_stdio_client()
    if transport == "http":
        return _create_http_client()
    raise ValueError(f"지원하지 않는 EKS_MCP_TRANSPORT: {transport!r}")
```

### 가이드라인

- 한 함수는 **20 줄 이내** 권장
- 들여쓰기가 **3 단계 이상** 이면 함수 분리 신호
- 함수 안에 빈 줄로 구분된 "섹션" 이 있으면 그 섹션이 별도 함수가 될 후보

---

## 4. 도메인 메서드로 의미 부여

데이터에 의미를 부여하는 작업은 도메인 객체 자신이 합니다.

```python
# 호출하는 쪽에서 매번 직렬화 로직 재구성
output = {
    "root_cause": d.root_cause,
    "affected_resources": d.affected_resources,
    "confidence": d.confidence,
    "recommended_actions": d.recommended_actions,
    "evidence": d.evidence,
    "summary": d.summary,
}

# 도메인 객체가 알아서
output = d.to_dict()
```

`domain/models.py` 의 `Diagnosis.to_dict()` 가 단일 진실 원천(SSOT)입니다.

---

## 5. 타입 힌트는 필수

타입은 문서이자 IDE 도움말이자 mypy 검증 대상입니다.

```python
# 안 좋음
def validate(name):
    ...

# 더 나음
def validate_cluster_name(name: str) -> str:
    ...
```

- public 함수와 메서드에는 모두 타입 힌트
- `Any` 는 외부 라이브러리 객체에만 (예: MCP 응답)
- `dict` 보다 `dict[str, int]` 처럼 구체적으로

---

## 6. Docstring — 무엇이 아니라 왜를 적는다

```python
# 코드를 그대로 다시 쓴 docstring — 가치 없음
def validate_cluster_name(name: str) -> str:
    """name 을 받아서 검증하고 반환한다."""
    ...

# 의도와 맥락 — 가치 있음
def validate_cluster_name(name: str) -> str:
    """등록된 EKS 클러스터 이름을 검증한다.

    실제 등록 여부는 IAM 이 검증하지만, 도구 진입 시점에 형식부터 거른다.
    """
    ...
```

### `@tool` 함수의 docstring 은 특별히 중요

LLM 이 docstring 을 읽고 어떤 도구를 부를지 결정합니다. **언제 이 도구를 쓰는지** 를 분명히 적습니다. EKS MCP 가 제공하는 도구가 대부분 커버하므로 우리가 직접 만든 `@tool` 은 드물지만, 만들 때는 docstring 에 충분한 맥락을 적습니다.

---

## 7. 조건문은 긍정형과 guard clause

```python
# early return 없이 들여쓰기가 깊어짐
def invoke(payload):
    if payload is not None:
        if payload.get("query"):
            if payload.get("cluster"):
                # 실제 로직
                ...

# guard clause 로 평탄하게
def invoke(payload):
    if payload is None:
        raise ValueError("empty payload")
    if not payload.get("query"):
        raise ValueError("missing query")
    if not payload.get("cluster"):
        raise ValueError("missing cluster")
    # 실제 로직 — 들여쓰기 한 단계
    ...
```

---

## 8. 주석은 "왜"만

코드가 무엇을 하는지는 코드를 보면 알 수 있습니다. 주석은 코드만 봐서는 알 수 없는 정보를 적습니다.

```python
# 코드를 다시 한국어로 쓴 주석 — 가치 없음
count = count + 1  # count 를 1 증가시킨다

# 의도와 이유 — 코드만 봐서는 모르는 정보
# 토큰은 약 14 분 후 만료되므로 만료 직전에 갱신해야 한다.
_TOKEN_REFRESH_INTERVAL_SECONDS = 600
```

좋은 주석의 예시 (현재 코드에서 발췌):

```python
# infrastructure/mcp_client.py
# NOTE: managed endpoint 는 SigV4 인증이 필요하다. AWS 가 제공하는 lightweight
# proxy(예: agentcore-mcp-proxy) 를 앞에 두는 것을 권장한다.
```

---

## 9. 파일과 모듈 구성

각 파일은 **한 가지 주제**만 다룹니다.

```
# 잡탕
utils.py        # 무슨 utils?

# 주제별 분리
mcp_client.py   # MCP 클라이언트 팩토리
container.py    # DI 컨테이너
redaction.py    # 응답 마스킹
```

### 파일 상단

모든 파일은 **모듈 docstring** 으로 시작합니다.

```python
"""EKS MCP 클라이언트 팩토리.

Strands SDK 는 ``MCPClient`` 를 ``Agent(tools=[mcp_client])`` 로 그대로 전달하면
도구 등록과 라이프사이클을 자동으로 관리한다. 본 모듈은 환경에 맞는 transport 를
선택해 ``MCPClient`` 를 만들어 반환한다.
"""
```

### Import 순서 (PEP 8)

```python
# 1) 표준 라이브러리
from __future__ import annotations
import os
import logging

# 2) 서드파티
from strands import Agent
from mcp import StdioServerParameters, stdio_client

# 3) 자체 패키지
from k8s_rca_agent.infrastructure.container import container
```

---

## 10. 에러 메시지는 행동 가능하게

```python
# 안 좋음
raise ValueError("invalid")

# 더 나음
raise ValueError(
    "label_selector 또는 field_selector 중 하나는 필수입니다 "
    "(서버 사이드 필터링 강제)"
)
```

LLM 이 도구 호출 시 받는 에러도 마찬가지입니다 — 메시지를 읽고 어떻게 회복할지 결정하므로, 메시지가 행동 가능해야 합니다.

---

## 11. 자동 검증

사람이 일일이 신경 쓰지 않아도 되도록 도구에 맡깁니다.

### Ruff (린트와 포맷)

```bash
ruff check src tests
ruff format src tests
```

설정은 `pyproject.toml` 에 있습니다 — 라인 길이 100 자, pyflakes, isort, bugbear, pyupgrade 룰셋 활성.

### mypy (타입 체크)

```bash
mypy src
```

### pre-commit (커밋 전 자동 실행)

```bash
pip install pre-commit
pre-commit install
```

---

## 코드 리뷰 체크리스트

- [ ] **사람이 5 초 안에 의도를 파악할 수 있는가** (가장 중요)
- [ ] AI 가 작성한 부분도 검토자가 line-by-line 이해했는가
- [ ] 추상화가 지금 정당화되는가 (premature 아닌가)
- [ ] 변수와 함수 이름만 봐도 의도가 드러나는가
- [ ] 매직 스트링과 매직 넘버를 상수로 분리했는가
- [ ] 함수가 한 가지 일만 하는가 (20 줄, 들여쓰기 3 단계 이내)
- [ ] 타입 힌트가 모든 public API 에 있는가
- [ ] Docstring 이 "무엇" 이 아니라 "왜" 를 적는가
- [ ] guard clause 로 들여쓰기를 평탄하게 했는가
- [ ] 도메인 의미가 도메인 객체에 들어 있는가
- [ ] ruff 와 mypy 가 통과하는가
- [ ] MCP 또는 SDK 로 충분한 일을 직접 구현하지 않았는가

---

## 다음 단계

- 보안 모델과 layered defense → [06. 보안 & 부하](./06-security-and-load.md)
- 처음으로 돌아가 다시 보고 싶다면 → [01. 시작하기](./01-getting-started.md)

## 더 깊이 알아보기

- 표준 스타일과 docstring 규칙 — [PEP 8](./00-references.md#7-python-코드-스타일), [PEP 257](./00-references.md#7-python-코드-스타일)
- 가독성 원칙의 실전 예시 — [The Art of Readable Code](./00-references.md#7-python-코드-스타일)
- 이름과 함수 다루는 법 — [Clean Code 챕터 2-3](./00-references.md#7-python-코드-스타일)

---

[← 04. AgentCore 배포](./04-deployment-agentcore.md) · [06. 보안 & 부하 →](./06-security-and-load.md)
