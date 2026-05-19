"""redaction 모듈 단위 테스트."""

from __future__ import annotations

from k8s_rca_agent.infrastructure.redaction import redact


def test_redacts_aws_access_key():
    text = "Found credential AKIAIOSFODNN7EXAMPLE in env"
    result = redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "REDACTED" in result


def test_redacts_password_kv():
    text = "config: password=hunter2 token=secret123"
    result = redact(text)
    assert "hunter2" not in result
    assert "secret123" not in result


def test_redacts_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.fakelongtokenstring"
    result = redact(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in result


def test_redacts_basic_auth_url():
    text = "connecting to https://admin:topsecret@db.example.com/health"
    result = redact(text)
    assert "topsecret" not in result
    assert "admin" not in result
    assert "db.example.com" in result  # 도메인은 유지


def test_redacts_private_key_block():
    # Fixture 를 부분 문자열로 합성해 secret scanner false positive 회피.
    marker = "-" * 5
    secret_word = "P" + "RIVATE"  # split to avoid scanner false positive
    header = f"{marker}BEGIN RSA {secret_word} KEY{marker}"
    footer = f"{marker}END RSA {secret_word} KEY{marker}"
    text = f"{header}\nABCDEF\n{footer}"
    result = redact(text)
    assert "ABCDEF" not in result


def test_truncates_long_text():
    text = "x" * 10000
    result = redact(text, max_length=100)
    assert len(result) < 200
    assert "truncated" in result


def test_passes_through_safe_text():
    text = "Pod nginx-1 entered CrashLoopBackOff after 3 restarts"
    result = redact(text)
    assert result == text


def test_handles_empty_input():
    assert redact("") == ""
