"""Bedrock AgentCore Runtime 진입점.

이 모듈은 AgentCore의 ``/invocations`` 계약을 만족시킨다.

페이로드 스펙:

    POST /invocations
    {
        "query": "...",          # 사용자 질의 (필수)
        "cluster": "prod-us"     # 진단 대상 EKS 클러스터 이름 (필수)
    }

Strands의 ``MCPClient``는 ``Agent(tools=[mcp])`` 로 전달되면 invocation 동안
자동으로 connect → list_tools → tool_calls → disconnect 라이프사이클을 처리한다.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from k8s_rca_agent.agents import create_orchestrator
from k8s_rca_agent.infrastructure.metrics import emit, time_block

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _build_query(payload: dict[str, Any]) -> tuple[str, str]:
    query = (payload.get("query") or "").strip()
    cluster = (payload.get("cluster") or "").strip()

    if not query:
        raise ValueError("'query' 필드가 비어 있습니다.")
    if not cluster:
        raise ValueError("'cluster' 필드가 비어 있습니다. 진단 대상 클러스터를 명시해야 합니다.")
    return query, cluster


def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """단일 invocation 처리."""
    try:
        query, cluster = _build_query(payload)
    except ValueError:
        # cluster 를 모르면 dimension 으로 unknown 표기 (카디널리티 ↑ 안 함)
        emit(
            "rca.invocation.count",
            value=1,
            dimensions={"cluster": "unknown", "status": "bad_request"},
        )
        raise

    status = "success"
    try:
        with time_block(
            "rca.invocation.latency_ms",
            dimensions={"cluster": cluster},
        ):
            orchestrator = create_orchestrator()
            user_message = f"[cluster={cluster}] {query}"
            response = orchestrator(user_message)
    except Exception:
        status = "failure"
        raise
    finally:
        emit(
            "rca.invocation.count",
            value=1,
            dimensions={"cluster": cluster, "status": status},
        )

    return {
        "response": str(response),
        "cluster": cluster,
    }


def main() -> int:
    _setup_logging()

    try:
        from bedrock_agentcore.runtime import BedrockAgentCoreApp
    except ImportError:
        logger.error(
            "bedrock-agentcore SDK가 설치되지 않았습니다. "
            '`pip install -e ".[agentcore]"` 로 설치하거나, '
            "로컬 CLI 개발에는 `python -m k8s_rca_agent.main`을 사용하세요."
        )
        return 1

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def handler(payload):  # type: ignore[no-redef]
        return invoke(payload)

    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
