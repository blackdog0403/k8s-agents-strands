"""도메인 모델.

EKS MCP Server가 K8s 리소스 표현을 제공하므로, 우리는 자체 비즈니스 결과물인
``Diagnosis`` 만 도메인 모델로 정의한다. 향후 도구 응답에 의미 있는 도메인 변환이
필요해지면 ``PodSnapshot`` 같은 클래스를 다시 추가한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnosis:
    """RCA 결과 — Agent가 진단을 내릴 때 만들어내는 도메인 객체."""

    root_cause: str
    affected_resources: list[str]
    confidence: float  # 0.0 ~ 1.0
    recommended_actions: list[str]
    evidence: list[str]
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "root_cause": self.root_cause,
            "affected_resources": self.affected_resources,
            "confidence": self.confidence,
            "recommended_actions": self.recommended_actions,
            "evidence": self.evidence,
            "summary": self.summary,
        }
