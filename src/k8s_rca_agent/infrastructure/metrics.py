"""애플리케이션 메트릭 emit — CloudWatch Embedded Metric Format (EMF).

EMF 는 stdout 으로 JSON 한 줄을 출력하면 CloudWatch Logs Agent / AgentCore Runtime 의
log shipper 가 자동으로 메트릭 데이터로 인식해 CloudWatch Metrics 에 적재한다.
별도 PutMetricData API 호출이 없으므로 외부 라이브러리 의존이 없다.

본 모듈이 emit 하는 핵심 지표:

- ``rca.invocation.count``     — invocation 횟수 (status, cluster)
- ``rca.invocation.latency_ms`` — invocation 지연 (status, cluster)
- ``rca.tool_call.count``       — 도구 호출 횟수 (specialist, tool, status)
- ``rca.llm.tokens.input``      — LLM 입력 토큰 (model)
- ``rca.llm.tokens.output``     — LLM 출력 토큰 (model)

Dimension 은 카디널리티가 낮은 값(cluster, status, tool 이름) 만 사용한다.
``invocation_id`` 같은 고카디널리티 식별자는 메트릭이 아니라 *property* 로 동봉해
CloudWatch Logs Insights 에서 검색만 가능하게 한다.

사용 예::

    from k8s_rca_agent.infrastructure.metrics import emit, time_block

    emit("rca.invocation.count", value=1, unit="Count",
         dimensions={"cluster": "prod-us", "status": "success"})

    with time_block("rca.invocation.latency_ms",
                    dimensions={"cluster": "prod-us"}):
        ...

EMF 사양: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# CloudWatch namespace — 모든 메트릭이 이 아래에 모임.
_NAMESPACE = os.getenv("METRICS_NAMESPACE", "RcaAgent")


def emit(
    metric_name: str,
    value: float,
    *,
    unit: str = "Count",
    dimensions: dict[str, str] | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """단일 메트릭 한 점을 EMF JSON 으로 stdout 에 출력한다.

    Args:
        metric_name: ``rca.invocation.count`` 같은 메트릭 이름.
        value: 측정값.
        unit: CloudWatch unit (``Count``, ``Milliseconds``, ``Bytes`` 등).
        dimensions: 카디널리티가 낮은 dimension key=value 쌍.
        properties: 메트릭이 아니라 property 로만 동봉할 추가 필드 — Logs Insights
            에서 검색 가능하지만 CloudWatch Metrics 에는 적재되지 않는다.
    """
    dims = dimensions or {}
    props = properties or {}

    payload: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": _NAMESPACE,
                    "Dimensions": [list(dims.keys())] if dims else [[]],
                    "Metrics": [{"Name": metric_name, "Unit": unit}],
                }
            ],
        },
        metric_name: value,
        **dims,
        **props,
    }

    # stdout 으로 한 줄 — AgentCore Runtime 의 log shipper 가 EMF 로 인식
    print(json.dumps(payload, default=str), file=sys.stdout, flush=True)


@contextmanager
def time_block(metric_name: str, *, dimensions: dict[str, str] | None = None):
    """``with`` 블록의 실행 시간을 ``Milliseconds`` 단위로 emit 한다."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        emit(
            metric_name,
            value=elapsed_ms,
            unit="Milliseconds",
            dimensions=dimensions,
        )
