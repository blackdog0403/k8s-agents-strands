"""DI 컨테이너 — MCP 클라이언트 라이프사이클만 관리한다.

EKS MCP Server가 K8s 데이터 접근을 담당하므로, 컨테이너의 책임은 매우 단순해졌다.
"""

from __future__ import annotations

from functools import cached_property

from .mcp_client import create_eks_mcp_client


class Container:
    """애플리케이션 의존성 컨테이너 (싱글톤 라이프사이클)."""

    @cached_property
    def eks_mcp(self):
        """EKS MCP 클라이언트.

        Strands SDK가 ``Agent(tools=[mcp])`` 로 받으면 connect/list_tools/disconnect를
        자동 처리하므로, 우리는 인스턴스를 한 번 만들어 공유하기만 하면 된다.
        """
        return create_eks_mcp_client()


container = Container()
