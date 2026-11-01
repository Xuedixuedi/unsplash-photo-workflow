"""Strip secrets from anything that might be logged or printed."""

from __future__ import annotations

import os
import re
from typing import Any

SECRET_ENV_NAMES = (
    "UNSPLASH_ACCESS_KEY",
    "UNSPLASH_SECRET_KEY",
    "UNSPLASH_USER_TOKEN",
    "LLM_API_KEY",
    "UPW_PASSWORD",
    "UPW_SESSION_SECRET",
    "DATABASE_URL",
    "SENTRY_DSN",
)

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_QUERY_SECRET = re.compile(r"(?i)(client_secret|access_token|refresh_token|code|api_key|token)=([^&\s]+)")


def known_secrets(extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if len(value) >= 6:
            found.append(value)
    for value in extra or []:
        if value and len(value) >= 6:
            found.append(value)
    # Longest first so a short secret cannot leave a longer one half-visible.
    return sorted(set(found), key=len, reverse=True)


def redact(text: str, extra: list[str] | None = None) -> str:
    cleaned = _BEARER.sub("Bearer ***REDACTED***", text)
    cleaned = _QUERY_SECRET.sub(r"\1=***REDACTED***", cleaned)
    for secret in known_secrets(extra):
        cleaned = cleaned.replace(secret, "***REDACTED***")
    return cleaned


def redact_obj(value: Any, extra: list[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact(value, extra)
    if isinstance(value, dict):
        return {str(key): redact_obj(item, extra) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_obj(item, extra) for item in value]
    if isinstance(value, tuple):
        return [redact_obj(item, extra) for item in value]
    return value
