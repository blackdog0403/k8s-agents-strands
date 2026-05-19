"""로컬 개발용 CLI.

빠른 반복 개발을 위한 진입점. AgentCore 진입점 계약을 거치지 않고 바로 orchestrator를
호출하므로, 도메인 로직 디버깅에 가장 효율적이다.

AgentCore 계약 자체를 검증하려면 ``python -m k8s_rca_agent.agentcore_app``를 사용한다.

사용 예:
  python -m k8s_rca_agent.main --cluster prod-us "default 네임스페이스의 nginx 봐줘"
  python -m k8s_rca_agent.main --cluster prod-us
"""

from __future__ import annotations

import argparse
import logging
import sys

from k8s_rca_agent.agents import create_orchestrator


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _ask(orchestrator, cluster: str, query: str) -> None:
    user_message = f"[cluster={cluster}] {query}"
    response = orchestrator(user_message)
    print("\n" + "=" * 80)
    print(f"RCA 결과 (cluster={cluster})")
    print("=" * 80)
    print(response)


def run_once(cluster: str, query: str) -> None:
    orchestrator = create_orchestrator()
    _ask(orchestrator, cluster, query)


def run_interactive(default_cluster: str) -> None:
    orchestrator = create_orchestrator()
    print("Kubernetes RCA Agent — 'exit' 또는 Ctrl+C로 종료")
    print(f"기본 cluster: {default_cluster} ('cluster <name>'로 변경)")
    print("-" * 60)

    cluster = default_cluster
    while True:
        try:
            line = input(f"\n[{cluster}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            return

        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            return
        if line.lower().startswith("cluster "):
            cluster = line.split(maxsplit=1)[1].strip()
            print(f"cluster 변경됨: {cluster}")
            continue

        try:
            _ask(orchestrator, cluster, line)
        except Exception as exc:  # noqa: BLE001 — REPL 보호
            print(f"\n[오류] {type(exc).__name__}: {exc}")


def main() -> int:
    _setup_logging()

    parser = argparse.ArgumentParser(description="Kubernetes RCA Agent (local CLI)")
    parser.add_argument("--cluster", required=True, help="진단 대상 EKS 클러스터 이름")
    parser.add_argument(
        "query",
        nargs="*",
        help="질의. 비우면 인터랙티브 모드로 실행됩니다.",
    )
    args = parser.parse_args()

    if args.query:
        run_once(args.cluster, " ".join(args.query))
    else:
        run_interactive(args.cluster)
    return 0


if __name__ == "__main__":
    sys.exit(main())
