"""LLM 입력 sanity check.

EKS MCP Server에 임의 문자열을 그대로 보내기 전에 형식 검증을 거친다.
실제 권한 검증은 IAM이, 리소스 존재 여부는 MCP/EKS가 처리한다 — 여기서는
명백히 잘못된 형식만 빠르게 걸러서 무의미한 호출을 막는다.
"""

from __future__ import annotations

import re

# DNS-1123 label: 소문자/숫자/하이픈, 시작과 끝은 영숫자, 최대 63자.
_DNS_1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_MAX_LABEL_LENGTH = 63

# DNS-1123 subdomain: 라벨을 점(.)으로 이은 형태. Pod 등의 일반 리소스 이름.
_DNS_1123_SUBDOMAIN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)
_MAX_SUBDOMAIN_LENGTH = 253

# EKS 클러스터 이름 — 영문자로 시작, 영숫자/하이픈/언더스코어 허용
_EKS_CLUSTER_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9\-_]{0,99}$")


class InvalidResourceName(ValueError):
    """K8s 리소스 식별자 형식이 잘못된 경우."""


def validate_namespace(name: str) -> str:
    if not name:
        raise InvalidResourceName("namespace는 빈 문자열일 수 없다")
    if len(name) > _MAX_LABEL_LENGTH:
        raise InvalidResourceName(
            f"namespace 길이는 최대 {_MAX_LABEL_LENGTH}자다 (입력: {len(name)}자)"
        )
    if not _DNS_1123_LABEL.match(name):
        raise InvalidResourceName(f"namespace는 DNS-1123 라벨 형식이어야 한다: {name!r}")
    return name


def validate_resource_name(name: str) -> str:
    if not name:
        raise InvalidResourceName("리소스 이름은 빈 문자열일 수 없다")
    if len(name) > _MAX_SUBDOMAIN_LENGTH:
        raise InvalidResourceName(
            f"리소스 이름 길이는 최대 {_MAX_SUBDOMAIN_LENGTH}자다 (입력: {len(name)}자)"
        )
    if not _DNS_1123_SUBDOMAIN.match(name):
        raise InvalidResourceName(f"리소스 이름은 DNS-1123 서브도메인 형식이어야 한다: {name!r}")
    return name


def validate_cluster_name(name: str) -> str:
    if not name:
        raise InvalidResourceName("cluster 이름은 빈 문자열일 수 없다")
    if not _EKS_CLUSTER_NAME.match(name):
        raise InvalidResourceName(
            f"cluster 이름은 영문자로 시작하고 영숫자/하이픈/언더스코어만 허용한다: {name!r}"
        )
    return name
