<!-- 관련 issue가 있으면 링크: Closes #123 -->

## 변경 내용

<!-- 무엇이 어떻게 바뀌었는지 -->

## 의도 / 동기

<!-- 왜 이 변경이 필요한지 -->

## 검증 방법

<!-- 어떻게 테스트했는지. 명령어/시나리오 -->

```bash
# 예
pytest tests/
ruff check src tests
mypy src
python -m k8s_rca_agent.main --cluster <c> "..."
```

## 영향 범위

- [ ] 호환성 깨지는 변경 (있다면 마이그레이션 가이드 필수)
- [ ] 새 의존성 추가
- [ ] 새 환경 변수 또는 IAM 권한 필요
- [ ] 문서 업데이트 포함

## 체크리스트

- [ ] 변경 의도가 PR 설명에 명확히 적혀 있음
- [ ] `pytest tests/` 통과
- [ ] `ruff check src tests` 통과
- [ ] `mypy src` 통과
- [ ] 새 기능에 대한 테스트 추가
- [ ] 관련 문서 업데이트 (`docs/` 또는 README)
- [ ] **AI 도구로 작성한 부분이 있다면 line-by-line 검토 완료**
- [ ] 추상화가 정당화되는가 (premature 아닌가)
- [ ] [CONTRIBUTING.md](../CONTRIBUTING.md) 의 코드 스타일 따름
