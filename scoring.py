"""Deterministic opportunity relevance scoring.

The score estimates category relevance and review priority. It is not a win
probability, legal opinion, or substitute for reading the solicitation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

PRIMARY_NAICS = "561720"
RELATED_NAICS = {"561210", "561740", "561790"}

CORE_KEYWORDS = {
    "janitorial": 18,
    "custodial": 18,
    "commercial cleaning": 18,
    "cleaning services": 16,
    "building cleaning": 15,
    "housekeeping": 12,
    "floor care": 10,
    "carpet cleaning": 10,
    "window cleaning": 8,
    "disinfection": 8,
    "sanitation": 7,
    "restroom cleaning": 7,
}

NEGATIVE_PHRASES = {
    "janitorial supplies",
    "custodial supplies",
    "cleaning supplies",
    "paper products",
    "chemical supplies",
    "equipment purchase",
    "cleaning equipment",
}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def score_opportunity(record: dict[str, Any], *, today: date | None = None) -> tuple[int, list[str]]:
    """Return a 0-100 relevance score and a transparent explanation."""
    today = today or date.today()
    title = str(record.get("title") or "")
    description = str(record.get("summary") or record.get("description_text") or "")
    text = f"{title} {description}".lower()
    naics = str(record.get("naics_code") or record.get("naicsCode") or "").strip()
    notice_type = str(record.get("notice_type") or record.get("type") or "").lower()
    set_aside = str(
        record.get("set_aside_description")
        or record.get("typeOfSetAsideDescription")
        or record.get("setAside")
        or ""
    ).strip()
    active = record.get("active", True)

    score = 0
    reasons: list[str] = []

    if naics == PRIMARY_NAICS:
        score += 42
        reasons.append("Primary janitorial NAICS 561720")
    elif naics in RELATED_NAICS:
        score += 28
        reasons.append(f"Related building-services NAICS {naics}")

    keyword_points = 0
    matched: list[str] = []
    for phrase, points in CORE_KEYWORDS.items():
        if phrase in text:
            # Titles signal intent more strongly than body text.
            earned = points if phrase in title.lower() else max(4, points // 2)
            keyword_points += earned
            matched.append(phrase)
    keyword_points = min(keyword_points, 35)
    if keyword_points:
        score += keyword_points
        reasons.append("Service terms: " + ", ".join(matched[:4]))

    negative_matches = [phrase for phrase in NEGATIVE_PHRASES if phrase in text]
    service_language_present = any(
        phrase in text
        for phrase in ("cleaning services", "janitorial services", "custodial services", "service contract", "performance work statement", "recurring cleaning")
    )
    if negative_matches and not service_language_present:
        score -= 28
        reasons.append("Likely supplies/equipment rather than recurring service")
    elif negative_matches:
        score -= 10
        reasons.append("Contains supply/equipment language; verify scope")

    if any(label in notice_type for label in ("solicitation", "combined")):
        score += 8
        reasons.append("Open solicitation-stage notice")
    elif any(label in notice_type for label in ("sources sought", "pre-solicitation", "presolicitation")):
        score += 5
        reasons.append("Early market-research notice")

    if set_aside:
        score += 5
        reasons.append("Set-aside identified")

    if str(active).lower() in {"yes", "true", "1"} or active is True:
        score += 4

    deadline = _parse_date(record.get("response_deadline") or record.get("responseDeadLine"))
    if deadline:
        days_left = (deadline - today).days
        if days_left >= 21:
            score += 6
            reasons.append(f"{days_left} days to respond")
        elif days_left >= 10:
            score += 4
            reasons.append(f"{days_left} days to respond")
        elif days_left >= 4:
            score -= 3
            reasons.append(f"Only {days_left} days to respond")
        elif days_left >= 0:
            score -= 15
            reasons.append(f"Urgent: {days_left} days to respond")
        else:
            score -= 35
            reasons.append("Response deadline has passed")

    return max(0, min(100, int(score))), reasons


def score_label(score: int) -> str:
    if score >= 75:
        return "High relevance"
    if score >= 50:
        return "Review"
    return "Low relevance"
