"""脱敏：避免密钥或内部错误泄露到前端。"""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(
    r"Bearer\s+[a-zA-Z0-9._-]+", re.IGNORECASE
)


def redact_secrets(text: str) -> str:
    text = _SECRET_PATTERN.sub("[REDACTED]", text)
    return _BEARER_PATTERN.sub("Bearer [REDACTED]", text)


def sanitize_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """前端可见 meta：去掉内部调试字段。"""
    cleaned = dict(meta)
    cleaned.pop("llm_fallback", None)
    return cleaned


def public_error_message(exc: Exception) -> str:
    return "服务暂时不可用，请稍后重试。"
