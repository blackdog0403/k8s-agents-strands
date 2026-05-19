"""validation 모듈 단위 테스트."""

from __future__ import annotations

import pytest

from k8s_rca_agent.domain.validation import (
    InvalidResourceName,
    validate_namespace,
    validate_resource_name,
)


class TestValidateNamespace:
    def test_accepts_valid_dns1123_label(self):
        assert validate_namespace("production") == "production"
        assert validate_namespace("my-app-1") == "my-app-1"
        assert validate_namespace("a") == "a"

    def test_rejects_empty(self):
        with pytest.raises(InvalidResourceName, match="빈 문자열"):
            validate_namespace("")

    def test_rejects_uppercase(self):
        with pytest.raises(InvalidResourceName, match="DNS-1123"):
            validate_namespace("Production")

    def test_rejects_special_characters(self):
        with pytest.raises(InvalidResourceName):
            validate_namespace("my_namespace")
        with pytest.raises(InvalidResourceName):
            validate_namespace("ns/sub")
        with pytest.raises(InvalidResourceName):
            validate_namespace("ns.sub")  # namespace는 라벨이라 점 불가

    def test_rejects_too_long(self):
        with pytest.raises(InvalidResourceName, match="63자"):
            validate_namespace("a" * 64)

    def test_rejects_starting_with_hyphen(self):
        with pytest.raises(InvalidResourceName):
            validate_namespace("-myapp")


class TestValidateResourceName:
    def test_accepts_subdomain_form(self):
        # Pod 이름은 종종 점이 들어감 (StatefulSet의 pod-0.svc 같은 건 X지만, 일반 이름은 가능)
        assert validate_resource_name("nginx-7b4f9c-xz2k") == "nginx-7b4f9c-xz2k"

    def test_rejects_path_traversal_attempt(self):
        with pytest.raises(InvalidResourceName):
            validate_resource_name("../etc/passwd")
        with pytest.raises(InvalidResourceName):
            validate_resource_name("name with space")


class TestValidateClusterName:
    def test_accepts_normal_names(self):
        from k8s_rca_agent.domain.validation import validate_cluster_name

        assert validate_cluster_name("prod-us") == "prod-us"
        assert validate_cluster_name("dev_eks_01") == "dev_eks_01"
        assert validate_cluster_name("Cluster1") == "Cluster1"

    def test_rejects_empty(self):
        from k8s_rca_agent.domain.validation import validate_cluster_name

        with pytest.raises(InvalidResourceName):
            validate_cluster_name("")

    def test_rejects_starting_with_digit_or_hyphen(self):
        from k8s_rca_agent.domain.validation import validate_cluster_name

        with pytest.raises(InvalidResourceName):
            validate_cluster_name("1cluster")
        with pytest.raises(InvalidResourceName):
            validate_cluster_name("-cluster")

    def test_rejects_special_chars(self):
        from k8s_rca_agent.domain.validation import validate_cluster_name

        with pytest.raises(InvalidResourceName):
            validate_cluster_name("cluster/sub")
        with pytest.raises(InvalidResourceName):
            validate_cluster_name("cluster.sub")
        with pytest.raises(InvalidResourceName):
            validate_cluster_name("../etc/passwd")

    def test_rejects_too_long(self):
        from k8s_rca_agent.domain.validation import validate_cluster_name

        with pytest.raises(InvalidResourceName):
            validate_cluster_name("a" + "b" * 100)
