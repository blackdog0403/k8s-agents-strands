# Contributing to k8s-agents-strands

> 🌐 **Language**: [English](./CONTRIBUTING.md) · **한국어**

이 프로젝트에 관심을 가져주셔서 감사합니다. 기여 절차와 검토 기준을 안내합니다.

## 핵심 원칙

이 프로젝트의 모든 변경은 다음 네 가지 원칙을 따릅니다.

1. **사람이 이해하지 못한 코드는 머지하지 않습니다** — AI 도구로 작성한 코드도 line-by-line 검토 후에 PR 을 올립니다.
2. **MCP 와 SDK 를 우선 사용합니다** — 직접 구현은 정말 필요할 때만 합니다.
3. **5초 안에 의도가 보이는 코드를 씁니다** — 6 개월 후 자신이 다시 봐도 즉시 읽혀야 합니다.
4. **추상화는 정당화될 때만 만듭니다** — 미리 만들지 않습니다.

배경과 예시는 [docs/05-code-style.md](./docs/05-code-style.md) 에 있습니다.

## 기여 절차

### 1) 이슈를 먼저 만듭니다

코드 작성 전에 이슈로 의논해주세요.

- **Bug**: 재현 단계, 기대 동작, 실제 동작
- **Feature**: 해결하려는 문제, 제안하는 변경, 검토한 대안

큰 변경(아키텍처 변경, 의존성 추가, 새 specialist 도입)은 사전 합의가 필요합니다.

### 2) Fork 와 브랜치

```bash
git clone https://github.com/<your-username>/k8s-agents-strands
cd k8s-agents-strands
git checkout -b feature/short-description
```

브랜치 이름 규칙:

- `feature/...` — 새 기능
- `fix/...` — 버그 수정
- `docs/...` — 문서만 수정
- `refactor/...` — 동작 변화 없는 정리

### 3) 개발 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,agentcore]"
pre-commit install   # 권장
```

### 4) 코드 작성

새 기능을 추가할 때는 [docs/03-development.md](./docs/03-development.md) 의 튜토리얼을 따라가는 것을 권장합니다.

자주 쓰는 명령:

```bash
# 단위 테스트
pytest tests/

# 린트와 타입 검사
ruff check src tests
ruff format src tests
mypy src

# 로컬 실행
python -m k8s_rca_agent.main --cluster <your-cluster> "..."
```

### 5) PR 제출 전 체크리스트

- [ ] 변경 의도가 PR 설명에 분명히 적혀 있다
- [ ] `pytest tests/` 통과
- [ ] `ruff check src tests` 통과
- [ ] `ruff format --check src tests` 통과
- [ ] `mypy src` 통과
- [ ] 새 기능에 대한 테스트가 추가되었다
- [ ] 관련 문서를 업데이트했다 (`docs/` 또는 README)
- [ ] AI 도구로 작성한 부분은 line-by-line 검토를 마쳤다

### 6) PR 본문 양식

```markdown
## 변경 내용
- 무엇이 어떻게 바뀌었는지

## 의도와 동기
- 왜 이 변경이 필요한지

## 검증 방법
- 어떻게 테스트했는지

## 영향 범위
- 호환성 깨지는 변경인지, 의존성 추가·제거가 있는지
```

## 코드 스타일

- Python 3.11 이상
- 라인 길이 100 자
- public API 에는 type hints 필수
- Docstring 은 "왜"를 적습니다 (코드만 봐서는 모르는 정보)
- 매직 스트링과 매직 넘버는 모듈 레벨 상수로 분리

자세한 규칙은 [docs/05-code-style.md](./docs/05-code-style.md) 에 있습니다.

## 라이선스

이 프로젝트에 기여하면 기여 내용은 [Apache License 2.0](./LICENSE) 으로 라이선스됩니다.

별도의 CLA 서명은 요구하지 않습니다. PR 제출 자체가 라이선스 동의로 간주됩니다.

## 행동 강령

모든 참여자는 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) 를 준수해야 합니다.

## 질문과 도움

- 일반 질문 / 사용법 — GitHub Discussions (활성화된 경우)
- 버그 / 기능 제안 — GitHub Issues
- 보안 취약점 — 공개 issue 가 아닌 GitHub private security advisory 로 신고

## 처음 기여하시는 분께

- `good first issue` 라벨이 붙은 이슈부터 시작해보세요.
- 작은 PR 도 환영합니다 — 오타 수정도 좋습니다.
- 막히는 부분이 있으면 이슈에 댓글로 질문해주세요.
