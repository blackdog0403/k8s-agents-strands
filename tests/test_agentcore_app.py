"""agentcore_app 의 invoke 계약과 메트릭 emit 검증.

실제 LLM 또는 MCP 호출은 mocking 한다 — payload validation 과
invocation 단위 메트릭 emit 만 본다.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from k8s_rca_agent import agentcore_app


@pytest.fixture
def fake_orchestrator():
    """Strands Agent 인스턴스를 흉내내는 callable. 호출되면 고정 응답 반환."""

    def _orchestrator(message):
        assert "[cluster=" in message
        return "## 근본 원인\n테스트 응답입니다.\n"

    return _orchestrator


def test_build_query_rejects_missing_query():
    with pytest.raises(ValueError, match="query"):
        agentcore_app._build_query({"cluster": "prod-us"})


def test_build_query_rejects_missing_cluster():
    with pytest.raises(ValueError, match="cluster"):
        agentcore_app._build_query({"query": "look at nginx"})


def test_build_query_strips_whitespace():
    q, c = agentcore_app._build_query({"query": "  q  ", "cluster": "  prod-us  "})
    assert q == "q"
    assert c == "prod-us"


def test_invoke_returns_response_and_cluster(capsys, fake_orchestrator):
    with patch.object(agentcore_app, "create_orchestrator", return_value=fake_orchestrator):
        result = agentcore_app.invoke({"query": "look at nginx", "cluster": "prod-us"})

    assert result["cluster"] == "prod-us"
    assert "근본 원인" in result["response"]


def test_invoke_emits_success_metrics(capsys, fake_orchestrator):
    with patch.object(agentcore_app, "create_orchestrator", return_value=fake_orchestrator):
        agentcore_app.invoke({"query": "q", "cluster": "prod-us"})

    out = capsys.readouterr().out
    payloads = [json.loads(line) for line in out.strip().splitlines() if line.startswith("{")]
    metric_names = [
        m["Name"] for p in payloads for m in p["_aws"]["CloudWatchMetrics"][0]["Metrics"]
    ]
    # latency 와 count 둘 다 emit 되어야 함
    assert "rca.invocation.latency_ms" in metric_names
    assert "rca.invocation.count" in metric_names

    count_payload = next(p for p in payloads if "rca.invocation.count" in p)
    assert count_payload["status"] == "success"
    assert count_payload["cluster"] == "prod-us"


def test_invoke_emits_failure_metric_on_orchestrator_exception(capsys):
    def boom(_message):
        raise RuntimeError("LLM unreachable")

    with patch.object(agentcore_app, "create_orchestrator", return_value=boom):
        with pytest.raises(RuntimeError, match="LLM unreachable"):
            agentcore_app.invoke({"query": "q", "cluster": "prod-us"})

    out = capsys.readouterr().out
    payloads = [json.loads(line) for line in out.strip().splitlines() if line.startswith("{")]
    count_payload = next(p for p in payloads if "rca.invocation.count" in p)
    assert count_payload["status"] == "failure"


def test_invoke_emits_bad_request_metric_on_validation_error(capsys):
    with pytest.raises(ValueError):
        agentcore_app.invoke({"query": "", "cluster": ""})

    out = capsys.readouterr().out
    payloads = [json.loads(line) for line in out.strip().splitlines() if line.startswith("{")]
    count_payload = next(p for p in payloads if "rca.invocation.count" in p)
    assert count_payload["status"] == "bad_request"
    assert count_payload["cluster"] == "unknown"
