"""민감 정보 redaction.

K8s 이벤트 메시지나 컨테이너 로그에는 의도치 않게 토큰/키/패스워드가
포함될 수 있다. 이런 값을 LLM 컨텍스트(외부 API)로 보내기 전에 마스킹한다.
"""

from __future__ import annotations

import re

# 알려진 형태의 자격 증명/토큰
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET_KEY = re.compile(r"\b[A-Za-z0-9/+=]{40}\b")  # 실제 형태는 더 좁지만 보수적으로
_BEARER_TOKEN = re.compile(r"(?i)\b(bearer|token)[\s:=]+([A-Za-z0-9._\-]{20,})", re.IGNORECASE)
_GENERIC_KV_SECRET = re.compile(
    r'(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)\s*[=:]\s*["\']?([^"\'\s,}]{4,})',
)
_BASIC_AUTH_URL = re.compile(r"://([^/:@\s]+):([^/:@\s]+)@")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN[^-]+PRIVATE KEY-----.*?-----END[^-]+PRIVATE KEY-----",
    re.DOTALL,
)

_REDACTED = "***REDACTED***"

# LLM 토큰 비용/응답 크기를 제한하기 위한 기본 상한
_DEFAULT_MAX_LENGTH = 4096


def redact(text: str, max_length: int = _DEFAULT_MAX_LENGTH) -> str:
    """텍스트에서 민감해 보이는 값을 마스킹하고 길이를 제한한다.

    Args:
        text: 원본 텍스트 (이벤트 메시지, 로그 등)
        max_length: 잘라낼 최대 길이 (그 이상은 끝부분이 잘림)

    Returns:
        redaction이 적용되고 길이가 제한된 텍스트.
    """
    if not text:
        return text

    text = _PRIVATE_KEY_BLOCK.sub(_REDACTED, text)
    text = _BASIC_AUTH_URL.sub(f"://{_REDACTED}@", text)
    text = _GENERIC_KV_SECRET.sub(rf"\1={_REDACTED}", text)
    text = _BEARER_TOKEN.sub(rf"\1 {_REDACTED}", text)
    text = _AWS_ACCESS_KEY.sub(_REDACTED, text)
    # AWS_SECRET_KEY는 false positive가 너무 많아서 의도적으로 제외.
    # (40자 base64 문자열은 일반 데이터에 흔함)

    return _truncate(text, max_length)


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n... [truncated, original length={len(text)}]"
