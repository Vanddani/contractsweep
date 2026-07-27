"""Minimal email adapter using Resend's HTTPS API."""

from __future__ import annotations

import logging
from typing import Iterable

import requests

LOGGER = logging.getLogger(__name__)


def send_email(
    *,
    api_key: str,
    sender: str,
    recipients: str | Iterable[str],
    subject: str,
    html: str,
) -> bool:
    if isinstance(recipients, str):
        to = [recipients]
    else:
        to = list(recipients)
    if not api_key:
        LOGGER.warning("RESEND_API_KEY not configured; email to %s was not sent", to)
        return False
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": sender, "to": to, "subject": subject, "html": html},
            timeout=30,
        )
    except requests.RequestException as exc:
        LOGGER.error("Resend request failed: %s", exc)
        return False
    if not response.ok:
        LOGGER.error("Resend error %s: %s", response.status_code, response.text[:500])
        return False
    return True
