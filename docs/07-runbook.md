# 07. 운영 Runbook

[← 06. 보안 & 부하](./06-security-and-load.md) · [00. References ↺](./00-references.md)

이 문서는 **on-call 이 알람을 받았을 때 따라가는 절차** 입니다.
모든 시나리오는 다음 5 단계로 정리되어 있습니다.

1. **트리거** — 어떤 alarm 이 울리는가
2. **첫 1 분** — 무엇을 확인하나 (대시보드 / 쿼리)
3. **5 분 안 mitigation** — 사용자 영향 최소화
4. **30 분 안 root cause** — 원인 파악
5. **사후** — 재발 방지

---

## 시나리오 1. AgentCore Invocation 5xx 에러율 폭증

### 트리거
- CloudWatch alarm `RcaAgent-InvocationErrorRate` (5 분간 5xx > 5%)
- PagerDuty 호출

### 첫 1 분
1. CloudWatch Logs Insights 에서 최근 실패 invocation 의 에러 메시지 확인
   ```
   fields @timestamp, invocation_id, error, error_type
   | filter level = "ERROR"
   | sort @timestamp desc
   | limit 50
   ```
2. AgentCore 콘솔의 Runtime 상세 페이지에서 **InvocationCount / 5xxCount** 그래프 확인
3. 실패가 특정 cluster 에 국한되는지, 전체 invocation 에 퍼지는지 dimension 별로 확인

### 5 분 안 mitigation
| 패턴 | 조치 |
|------|------|
| 모든 invocation 실패 | AgentCore Runtime 의 직전 release 로 롤백 (`agentcore update-agent-runtime --container-image <prev-tag>`) |
| 단일 cluster 만 실패 | caller 에게 해당 cluster 진단 일시 중단 안내. 시나리오 5 로 이동 |
| Bedrock 5xx 에 의한 실패 | 시나리오 2 로 이동 |
| MCP timeout 에 의한 실패 | 시나리오 3 으로 이동 |

### 30 분 안 root cause
- CloudTrail 에서 같은 시간대 IAM/리소스 변경 이력 검색 (`eks-mcp:*`, `bedrock:*`, `eks:*`)
- AgentCore release 가 최근 있었으면 image tag 와 commit 비교
- LLM 응답 길이 / 토큰 사용량 폭주가 timeout 을 유발했는지 확인

### 사후
- 5xx 가 외부 의존성(Bedrock/EKS MCP) 때문이면 retry 정책 재검토
- 우리 코드 결함이면 regression test 추가

---

## 시나리오 2. Bedrock Throttle 폭증

### 트리거
- CloudWatch alarm `RcaAgent-BedrockThrottle` (1 분간 ThrottleException > 0)

### 첫 1 분
1. Bedrock 콘솔 → **Service Quotas** 에서 모델별 RPM/TPM 사용률 확인
2. CloudWatch Logs Insights 에서 throttle 이 특정 cluster, 특정 caller 로 몰리는지 확인
   ```
   fields @timestamp, caller, cluster, error_type
   | filter error_type = "ThrottlingException"
   | stats count() by caller, cluster
   ```

### 5 분 안 mitigation
| 패턴 | 조치 |
|------|------|
| 단일 caller 의 burst | caller 에게 진단 호출 빈도 줄이라 안내. 또는 caller 별 rate limit 적용 |
| 여러 caller 동시 | 일시적으로 모델을 lower-tier (Haiku) 로 전환 — `BedrockModel(model_id="...haiku...")` |
| 지속적 추세 | Service Quota 증액 신청 |

### 30 분 안 root cause
- 하루 invocation 추이를 보고 **새 통합** (사내 자동화 등) 이 배포되었는지 확인
- LLM 의 반복 도구 호출 루프(시나리오 4 의 토큰 폭증과 연결됨) 가 아닌지 확인

### 사후
- caller 별 rate limit 미적용 상태면 추가 (운영 갭 분석 P1 §4.3 참고)
- Service Quota 알람 임계값을 80% 로 낮춰 사전 경고

---

## 시나리오 3. EKS MCP Timeout 폭증

### 트리거
- application metric `rca.tool_call.failure_rate{tool=*,reason=timeout}` > 10% (10 분간)

### 첫 1 분
1. EKS MCP managed endpoint 의 health 확인 (`https://eks-mcp.{region}.api.aws/mcp` 응답시간)
2. CloudTrail 에서 `eks-mcp:*` 호출이 5xx 를 반환하는지 확인
3. 영향받는 cluster 의 EKS API server 자체가 정상인지 (`aws eks describe-cluster` 의 endpoint health)

### 5 분 안 mitigation
| 패턴 | 조치 |
|------|------|
| EKS MCP managed 전체 장애 | self-hosted 모드로 fallback (`EKS_MCP_TRANSPORT=stdio` 환경변수로 재배포) |
| 특정 cluster 만 timeout | 그 cluster 의 EKS API server 점검 — VPC peering / 보안그룹 / API server 부하 |
| stdio 모드의 uvx 부팅 실패 | 로그에서 `uvx: command not found` 같은 메시지 확인, base image 재빌드 |

### 30 분 안 root cause
- AWS Health Dashboard 에서 EKS / EKS MCP 장애 공지 확인
- 우리 컨테이너의 outbound 가 VPC endpoint 로만 가는지 (Pattern 4 검증)

### 사후
- managed endpoint 단일 장애에 대비해 stdio fallback 자동화 (운영 갭 분석 P1 §4.4 참고)

---

## 시나리오 4. LLM 토큰 비용 급증

### 트리거
- CloudWatch alarm `RcaAgent-DailyTokenBudget` (일일 한도 80% 초과)
- 또는 비용 알람

### 첫 1 분
1. 메트릭 `rca.llm.tokens` 의 dimension `cluster`, `caller`, `model` 별 합계
2. 최근 1 시간의 invocation 평균 token 사용량 vs 지난 7 일 평균 비교
3. 길어진 invocation 이 있는지 — 도구 호출 회수가 평소보다 많은가

### 5 분 안 mitigation
| 패턴 | 조치 |
|------|------|
| 단일 invocation 의 도구 호출 무한 루프 | Strands `Agent` 의 max iterations 임시 하향, 해당 caller/cluster 일시 차단 |
| 새 caller 의 burst | caller 에게 호출 빈도 줄이라 안내, rate limit 검토 |
| Sonnet 사용 비중 급증 | 일부 케이스를 Haiku 로 라우팅 (orchestrator system prompt 조정) |

### 30 분 안 root cause
- LLM 환각으로 인한 tool 반복 호출인지 — Strands trace 에서 같은 도구가 N 회 이상 호출됐는지 확인
- 평소보다 큰 K8s 응답(예: 수만 개 이벤트) 을 그대로 prompt 에 넣은 케이스인지 확인

### 사후
- 도구 호출 횟수 한도 미적용 상태면 적용 (운영 갭 분석 P1 §4.2)
- prompt-level 응답 사이즈 제한을 specialist system prompt 에 추가
- caller 별 token quota 도입 검토

---

## 시나리오 5. 단일 EKS Cluster 진단 실패 폭증

### 트리거
- 메트릭 `rca.invocation.failure_rate{cluster="prod-eu"}` > 30% (10 분간)
- 다른 cluster 는 정상

### 첫 1 분
1. 그 cluster 의 EKS API server health 확인
2. cluster 에 적용된 `rca-agent-reader` ClusterRoleBinding 이 살아 있는지
   ```bash
   kubectl --context=prod-eu auth can-i get pods --as=system:serviceaccount:default:rca-agent
   ```
3. AgentCore execution role → cluster 의 access entry 매핑 유지 여부
   ```bash
   aws eks describe-access-entry --cluster-name prod-eu --principal-arn <role>
   ```

### 5 분 안 mitigation
| 패턴 | 조치 |
|------|------|
| Access Entry 가 사라짐 | `aws eks create-access-entry` 로 즉시 재등록 |
| RBAC 가 사라짐 | `kubectl apply -f deploy/agentcore/eks-rbac.yaml` 재적용 |
| EKS API server 장애 | 클러스터 owner 팀에 에스컬레이션, 진단 일시 중단 |

### 30 분 안 root cause
- CloudTrail 에서 access entry 또는 IAM 변경 이력 추적 (누가 언제 무엇을)
- cluster 의 EKS upgrade / API 변경 이력 확인

### 사후
- 분기 1 회 액세스 매핑 자동 검증 스크립트 추가 (운영 갭 분석 P1 §2.3 — drift 감지)

---

## 부록 A. 빠른 명령 모음

```bash
# 최근 5 분 실패 invocation
aws logs start-query \
  --log-group-name /aws/bedrock-agentcore/rca-agent \
  --start-time $(($(date +%s) - 300)) --end-time $(date +%s) \
  --query-string 'fields @timestamp, invocation_id, error_type | filter level = "ERROR"'

# AgentCore Runtime 직전 release 로 롤백
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id <id> --container-image <previous-ecr-tag>

# Bedrock 모델 일시 다운그레이드 — 환경변수만 변경 후 재배포
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id <id> \
  --environment "BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,..."

# 단일 cluster 진단 일시 차단 — caller IAM role 의 정책에서 그 cluster ARN 만 임시 제거
```

## 부록 B. 에스컬레이션 경로

| 계층 | 연락처 | 언제 |
|------|--------|------|
| L1 — 본 RCA Agent on-call | (팀 PagerDuty) | 모든 알람 |
| L2 — Bedrock 장애 | AWS Support | Bedrock 5xx 가 30 분 이상 지속 |
| L2 — EKS 장애 | cluster owner 팀 | 단일 cluster 진단 30 분 이상 실패 |
| L3 — 보안 사고 | 보안팀 | 권한 변경, 의심 caller 패턴, 자격 증명 노출 의심 |

---

## 다음 단계

- 보안 모델 다시 확인 → [06. 보안 & 부하](./06-security-and-load.md)
- 메트릭 정의가 어디에 있는지 → [04. AgentCore 배포 §7](./04-deployment-agentcore.md)
- 처음 진단 흐름 다시 보기 → [02. 아키텍처 §5](./02-architecture.md)

---

[← 06. 보안 & 부하](./06-security-and-load.md) · [00. References ↺](./00-references.md)
