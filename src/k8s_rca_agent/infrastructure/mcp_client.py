"""EKS MCP 클라이언트 팩토리.

Strands SDK는 ``MCPClient``를 ``Agent(tools=[mcp_client])``로 그대로 전달하면
도구 등록과 라이프사이클을 자동으로 관리한다. 본 모듈은 환경에 맞는 transport를
선택해 ``MCPClient``를 만들어 반환한다.

지원 transport:
- **stdio** (로컬/dev): ``uvx awslabs.eks-mcp-server@latest``를 자식 프로세스로 띄움
- **streamable_http** (managed): AWS가 호스팅하는 EKS MCP Server endpoint를 호출
                                 → SigV4 서명을 위한 lightweight proxy 사용

선택 기준은 환경 변수 ``EKS_MCP_TRANSPORT`` (``stdio`` | ``http``).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Managed EKS MCP Server endpoint (preview)
# 형식: https://eks-mcp.{region}.api.aws/mcp — region 은 환경 변수 AWS_REGION 으로 결정.
# 출처: https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html
_MANAGED_ENDPOINT_TEMPLATE = "https://eks-mcp.{region}.api.aws/mcp"


def _default_managed_endpoint() -> str:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2"
    return _MANAGED_ENDPOINT_TEMPLATE.format(region=region)


def create_eks_mcp_client():
    """EKS MCP 서버에 대한 Strands ``MCPClient``를 생성한다.

    환경 변수:
    - ``EKS_MCP_TRANSPORT``: ``stdio`` (기본, 로컬 dev) 또는 ``http`` (managed)
    - ``EKS_MCP_ENDPOINT``: ``http`` 모드에서 사용할 endpoint URL.
      미지정 시 ``AWS_REGION`` 으로부터 기본 endpoint 를 구성한다.
    - ``EKS_MCP_PACKAGE``: ``stdio`` 모드의 uvx 패키지명 (기본 ``awslabs.eks-mcp-server@latest``)
    """
    transport = os.getenv("EKS_MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        return _create_stdio_client()
    if transport == "http":
        return _create_http_client()
    raise ValueError(f"지원하지 않는 EKS_MCP_TRANSPORT: {transport!r} (stdio 또는 http)")


def _create_stdio_client():
    """로컬/개발용 — uvx로 EKS MCP server를 자식 프로세스로 띄운다."""
    from mcp import StdioServerParameters, stdio_client
    from strands.tools.mcp import MCPClient

    package = os.getenv("EKS_MCP_PACKAGE", "awslabs.eks-mcp-server@latest")
    logger.info("EKS MCP (stdio) 시작 — package=%s", package)

    return MCPClient(lambda: stdio_client(StdioServerParameters(command="uvx", args=[package])))


def _create_http_client():
    """Managed EKS MCP Server (preview) — Streamable HTTP + SigV4."""
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    endpoint = os.getenv("EKS_MCP_ENDPOINT") or _default_managed_endpoint()
    logger.info("EKS MCP (streamable_http) 시작 — endpoint=%s", endpoint)

    # NOTE: managed endpoint 는 SigV4 인증이 필요하다. 본 팩토리는 SigV4 서명을
    # 직접 수행하지 않으므로, AWS 가 제공하는 공식 proxy 인 mcp-proxy-for-aws
    # (https://github.com/aws/mcp-proxy-for-aws) 를 sidecar 또는 stdio 형태로
    # 앞에 두고 호출하는 구성을 권장한다.
    # 자세한 구성은 docs/04-deployment-agentcore.md 참고.
    return MCPClient(lambda: streamablehttp_client(endpoint))
