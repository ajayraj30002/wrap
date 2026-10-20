"""Redaction and sanitization utilities for analytics telemetry."""

import re
from typing import Any

# Sensitive key patterns (case-insensitive)
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE),
    re.compile(r"session[-_]?token", re.IGNORECASE),
    re.compile(r"encrypted", re.IGNORECASE),
]

# Sensitive value patterns
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]+", re.IGNORECASE)
WRAP_KEY_PATTERN = re.compile(r"wrap_[A-Za-z0-9_\-]+", re.IGNORECASE)
GENERIC_KEY_PATTERN = re.compile(r"(gsk|sk|AIza|ghp|xoxb)_[A-Za-z0-9_\-]+", re.IGNORECASE)

REDACTED_STR = "[REDACTED]"


def sanitize_payload(obj: Any) -> Any:
    """Recursively sanitize dictionaries, lists, and strings to eliminate secrets."""
    if obj is None:
        return None

    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            k_str = str(k)
            # Check if key name matches any sensitive pattern
            if any(p.search(k_str) for p in SENSITIVE_KEY_PATTERNS):
                sanitized[k_str] = REDACTED_STR
            else:
                sanitized[k_str] = sanitize_payload(v)
        return sanitized

    if isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]

    if isinstance(obj, (int, float, bool)):
        return obj

    if isinstance(obj, str):
        val = obj
        # Redact bearer headers
        val = BEARER_PATTERN.sub("Bearer [REDACTED]", val)
        # Redact WRAP keys
        val = WRAP_KEY_PATTERN.sub("wrap_[REDACTED]", val)
        # Redact common provider key prefixes
        val = GENERIC_KEY_PATTERN.sub("[REDACTED_KEY]", val)
        return val

    # For objects with __dict__
    if hasattr(obj, "__dict__"):
        return sanitize_payload(vars(obj))

    return str(obj)
