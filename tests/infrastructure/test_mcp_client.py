"""mcp_client 모듈의 transport 선택 분기 검증.

실제 MCP 서버를 띄우지 않는다 — 환경 변수에 따라 어떤 분기로 가는지,
endpoint 가 region 별로 다르게 구성되는지만 본다.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from k8s_rca_agent.infrastructure import mcp_client


def test_default_managed_endpoint_uses_aws_region(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert mcp_client._default_managed_endpoint() == "https://eks-mcp.eu-west-1.api.aws/mcp"


def test_default_managed_endpoint_falls_back_to_aws_default_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    assert mcp_client._default_managed_endpoint() == "https://eks-mcp.ap-northeast-2.api.aws/mcp"


def test_default_managed_endpoint_final_fallback(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    # region 이 전혀 없으면 us-west-2 로 떨어짐
    assert mcp_client._default_managed_endpoint() == "https://eks-mcp.us-west-2.api.aws/mcp"


def test_create_eks_mcp_client_invalid_transport_raises(monkeypatch):
    monkeypatch.setenv("EKS_MCP_TRANSPORT", "grpc")
    with pytest.raises(ValueError, match="EKS_MCP_TRANSPORT"):
        mcp_client.create_eks_mcp_client()


def test_create_eks_mcp_client_dispatches_to_stdio(monkeypatch):
    monkeypatch.setenv("EKS_MCP_TRANSPORT", "stdio")
    with patch.object(mcp_client, "_create_stdio_client", return_value="STDIO_CLIENT") as m:
        result = mcp_client.create_eks_mcp_client()
    m.assert_called_once()
    assert result == "STDIO_CLIENT"


def test_create_eks_mcp_client_dispatches_to_http(monkeypatch):
    monkeypatch.setenv("EKS_MCP_TRANSPORT", "http")
    with patch.object(mcp_client, "_create_http_client", return_value="HTTP_CLIENT") as m:
        result = mcp_client.create_eks_mcp_client()
    m.assert_called_once()
    assert result == "HTTP_CLIENT"


def test_create_eks_mcp_client_default_is_stdio(monkeypatch):
    monkeypatch.delenv("EKS_MCP_TRANSPORT", raising=False)
    with patch.object(mcp_client, "_create_stdio_client", return_value="STDIO") as m:
        mcp_client.create_eks_mcp_client()
    m.assert_called_once()
