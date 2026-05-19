"""Diagnosis 도메인 모델 단위 테스트."""

from __future__ import annotations

from k8s_rca_agent.domain.models import Diagnosis


def test_diagnosis_to_dict_serializable():
    d = Diagnosis(
        root_cause="OOMKilled due to memory limit too low",
        affected_resources=["pod/api-1"],
        confidence=0.85,
        recommended_actions=["Increase memory limit to 1Gi"],
        evidence=["last_termination_reason=OOMKilled", "memory limit=256Mi"],
        summary="Memory pressure caused container kill",
    )
    out = d.to_dict()
    assert out["confidence"] == 0.85
    assert "OOMKilled" in out["root_cause"]
    assert len(out["evidence"]) == 2


def test_diagnosis_default_summary_empty():
    d = Diagnosis(
        root_cause="x",
        affected_resources=[],
        confidence=0.5,
        recommended_actions=[],
        evidence=[],
    )
    assert d.summary == ""
    assert d.to_dict()["summary"] == ""
