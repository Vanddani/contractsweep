"""Small, framework-independent safety helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


def safe_local_url(value: Any, fallback: str) -> str:
    """Return a same-origin relative URL or a known-safe fallback."""
    target = str(value or "").strip()
    if not target:
        return fallback
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return fallback
    return target


def safe_http_url(value: Any) -> str:
    """Allow only absolute HTTP(S) URLs for external links."""
    target = str(value or "").strip()
    parsed = urlsplit(target)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return target


def csv_safe(value: Any) -> Any:
    """Neutralize spreadsheet formulas while preserving numeric values."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text
