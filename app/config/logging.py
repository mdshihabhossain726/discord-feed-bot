"""Structured JSON logging with automatic secret redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_REDACTED = "[REDACTED]"

# Key names whose values must never be logged.
_SENSITIVE_KEYS = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|cookie|session)",
    re.IGNORECASE,
)

# Patterns that look like credentials embedded in free text.
_TEXT_PATTERNS = [
    # Authorization-style headers: keep the scheme, hide the credential.
    re.compile(r"\b(Bearer|Bot|Basic)(\s+)[A-Za-z0-9\-._~+/=]{8,}", re.IGNORECASE),
    # key=value pairs in URLs / form bodies: keep the key, hide the value.
    re.compile(
        r"\b(access_token|refresh_token|client_secret|token|password)(=)[^&\s]+",
        re.IGNORECASE,
    ),
    # Discord bot token shape: <id>.<timestamp>.<hmac>
    re.compile(r"\b[A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6,7}\.[A-Za-z0-9_\-]{27,}\b"),
]


def redact_text(text: str) -> str:
    """Mask credential-looking substrings in free text."""

    def _sub(m: re.Match[str]) -> str:
        if m.lastindex and m.lastindex >= 2:
            return f"{m.group(1)}{m.group(2)}{_REDACTED}"
        return _REDACTED

    for pat in _TEXT_PATTERNS:
        text = pat.sub(_sub, text)
    return text


def redact_value(value: Any, key: str | None = None) -> Any:
    """Recursively redact sensitive keys and credential-like strings."""
    if key is not None and _SENSITIVE_KEYS.search(key):
        return _REDACTED
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


# Attributes present on every LogRecord; anything else came from ``extra=``.
_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Format records as single-line JSON, redacting secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _STD_ATTRS and not k.startswith("_"):
                payload[k] = redact_value(v, k)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Library loggers can echo headers/URLs; keep them quiet.
    for noisy in ("httpx", "httpcore", "discord.http"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
