"""metrics 모듈 단위 테스트.

EMF JSON 페이로드의 형식과 dimension 처리, time_block 의 단위를 검증한다.
실제 CloudWatch 와 통신하지 않는다 — stdout JSON 만 본다.
"""

from __future__ import annotations

import json
import time

import pytest

from k8s_rca_agent.infrastructure.metrics import emit, time_block


def _captured_payload(capsys: pytest.CaptureFixture[str]) -> dict:
    out = capsys.readouterr().out.strip()
    assert out, "metrics emitted nothing on stdout"
    # 한 줄 한 메트릭
    return json.loads(out.splitlines()[-1])


def test_emit_writes_emf_payload(capsys):
    emit(
        "rca.invocation.count",
        value=1,
        dimensions={"cluster": "prod-us", "status": "success"},
    )
    payload = _captured_payload(capsys)

    assert payload["rca.invocation.count"] == 1
    assert payload["cluster"] == "prod-us"
    assert payload["status"] == "success"
    assert "_aws" in payload
    metric_def = payload["_aws"]["CloudWatchMetrics"][0]
    assert metric_def["Namespace"] == "RcaAgent"
    assert metric_def["Metrics"][0] == {"Name": "rca.invocation.count", "Unit": "Count"}
    assert sorted(metric_def["Dimensions"][0]) == ["cluster", "status"]


def test_emit_includes_properties_but_not_in_dimensions(capsys):
    emit(
        "rca.tool_call.count",
        value=1,
        dimensions={"tool": "get_pod"},
        properties={"invocation_id": "abc-123"},
    )
    payload = _captured_payload(capsys)

    assert payload["invocation_id"] == "abc-123"
    # invocation_id 는 dimension 이 아니어야 함 (카디널리티 ↑ 방지)
    assert "invocation_id" not in payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]


def test_emit_with_no_dimensions(capsys):
    emit("rca.heartbeat", value=1)
    payload = _captured_payload(capsys)
    assert payload["rca.heartbeat"] == 1
    # 빈 dimension list
    assert payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [[]]


def test_time_block_emits_milliseconds(capsys):
    with time_block("rca.invocation.latency_ms", dimensions={"cluster": "x"}):
        time.sleep(0.01)
    payload = _captured_payload(capsys)

    assert payload["rca.invocation.latency_ms"] >= 10  # 적어도 10ms
    assert payload["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Unit"] == "Milliseconds"


def test_time_block_emits_even_on_exception(capsys):
    with pytest.raises(RuntimeError):
        with time_block("rca.failed_op_ms", dimensions={"op": "x"}):
            raise RuntimeError("boom")

    payload = _captured_payload(capsys)
    assert "rca.failed_op_ms" in payload
