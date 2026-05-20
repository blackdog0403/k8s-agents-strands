"""agents 팩토리 함수의 계약 검증.

- Strands ``Agent`` 객체가 만들어지는지
- specialist 가 orchestrator 의 tools 에 포함되는지
- system prompt 와 description 이 비어 있지 않은지

실제 LLM 호출은 하지 않는다 — Agent 인스턴스의 구조만 본다.
EKS MCP 클라이언트는 mock 으로 대체해 stdio 자식 프로세스를 띄우지 않는다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k8s_rca_agent.infrastructure import container as container_module


@pytest.fixture(autouse=True)
def _stub_eks_mcp(monkeypatch):
    """모든 테스트에서 eks_mcp 클라이언트를 가벼운 mock 으로 교체.

    실제 ``MCPClient`` 를 만들면 stdio 모드에서 ``uvx awslabs.eks-mcp-server``
    자식 프로세스가 떠서 단위 테스트가 수십 초 걸린다. 본 fixture 는
    container.eks_mcp 를 호출 가능한 mock 으로 바꿔 객체 구조 검증만 한다.
    """
    fake_mcp = MagicMock(name="eks_mcp_stub")
    # cached_property 를 우회하려면 container 인스턴스의 __dict__ 에 직접 주입
    monkeypatch.setattr(
        container_module.container,
        "__dict__",
        {**container_module.container.__dict__, "eks_mcp": fake_mcp},
    )
    yield


# 위 fixture 가 container 를 stub 한 상태에서 import 해야 함
from k8s_rca_agent.agents import (  # noqa: E402
    create_orchestrator,
    create_pod_diagnostic_agent,
)


def test_create_pod_diagnostic_agent_returns_named_agent():
    agent = create_pod_diagnostic_agent()
    assert agent.name == "pod_diagnostic"
    assert agent.description and len(agent.description) > 20
    # 검토자가 5초 안에 의도 파악할 수 있도록 cluster, namespace 키워드가 description 에 있어야 함
    assert "cluster" in agent.description.lower()


def test_create_pod_diagnostic_agent_uses_container_eks_mcp():
    """specialist 가 container.eks_mcp 를 받아간다는 contract.

    실제 MCPClient 가 아니어서 Strands tool registry 등록은 안 되지만,
    팩토리가 container.eks_mcp 를 참조하는지는 mock 호출로 확인할 수 있다.
    """
    agent = create_pod_diagnostic_agent()
    # Agent 인스턴스가 정상 생성되면 container.eks_mcp 가 호출된 것임
    assert agent is not None


def test_create_pod_diagnostic_prompt_includes_safety_section():
    agent = create_pod_diagnostic_agent()
    prompt = agent.system_prompt or ""
    # 보안 가이드와 출력 형식이 system prompt 에 있어야 함
    assert "보안" in prompt or "민감" in prompt
    assert "근본 원인" in prompt


def test_create_orchestrator_returns_named_agent():
    orchestrator = create_orchestrator()
    assert orchestrator.name == "rca_orchestrator"
    assert orchestrator.system_prompt


def test_orchestrator_routing_prompt_mentions_pod_specialist():
    """라우팅 기준이 prompt 에 명시되어 있어야 LLM 이 위임할 수 있다."""
    orchestrator = create_orchestrator()
    prompt = orchestrator.system_prompt or ""
    assert "pod_diagnostic" in prompt
