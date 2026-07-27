"""SAM.gov Contract Opportunities API ingestion helpers."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scoring import score_opportunity

LOGGER = logging.getLogger(__name__)
API_URL = "https://api.sam.gov/opportunities/v2/search"
DEFAULT_NAICS = ("561720", "561210", "561790", "561740")


class SamApiError(RuntimeError):
    pass


def _session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "ContractSweep-MVP/1.0"})
    return session


def _first_path_component(path: Any) -> str:
    text = str(path or "").strip()
    return text.split(".")[0].strip() if text else ""


def _place(record: dict[str, Any]) -> tuple[str, str]:
    pop = record.get("placeOfPerformance") or {}
    if not isinstance(pop, dict):
        pop = {}
    state_obj = pop.get("state") or {}
    city_obj = pop.get("city") or {}
    state = state_obj.get("code") if isinstance(state_obj, dict) else state_obj
    city = city_obj.get("name") if isinstance(city_obj, dict) else city_obj
    office = record.get("officeAddress") or {}
    if not isinstance(office, dict):
        office = {}
    if not state:
        state = office.get("state") or ""
    if not city:
        city = office.get("city") or ""
    return str(state or "").upper(), str(city or "").title()


def normalize_opportunity(record: dict[str, Any]) -> dict[str, Any]:
    notice_id = str(record.get("noticeId") or "").strip()
    state, city = _place(record)
    agency = (
        _first_path_component(record.get("fullParentPathName"))
        or str(record.get("department") or "").strip()
        or "Federal agency"
    )
    path = str(record.get("fullParentPathName") or "")
    office = path.split(".")[-1].strip() if path else str(record.get("office") or "").strip()
    poc_value = record.get("pointOfContact") or []
    if isinstance(poc_value, dict):
        poc = [poc_value]
    elif isinstance(poc_value, list):
        poc = [item for item in poc_value if isinstance(item, dict)]
    else:
        poc = []
    resources_value = record.get("resourceLinks") or []
    if isinstance(resources_value, str):
        resources = [resources_value]
    elif isinstance(resources_value, list):
        resources = [str(item) for item in resources_value if item]
    else:
        resources = []
    active_value = record.get("active")
    active = 1 if active_value is None or str(active_value).strip().lower() in {"yes", "true", "1"} else 0
    source_url = f"https://sam.gov/opp/{notice_id}/view" if notice_id else str(record.get("uiLink") or "")

    normalized: dict[str, Any] = {
        "notice_id": notice_id,
        "title": str(record.get("title") or "Untitled opportunity").strip(),
        "solicitation_number": str(record.get("solicitationNumber") or "").strip(),
        "agency": agency,
        "office": office,
        "posted_date": str(record.get("postedDate") or "")[:10],
        "response_deadline": str(record.get("responseDeadLine") or record.get("reponseDeadLine") or "")[:10],
        "naics_code": str(record.get("naicsCode") or "").strip(),
        "classification_code": str(record.get("classificationCode") or "").strip(),
        "state": state,
        "city": city,
        "set_aside_code": str(record.get("typeOfSetAside") or "").strip(),
        "set_aside_description": str(record.get("typeOfSetAsideDescription") or "").strip(),
        "notice_type": str(record.get("type") or "").strip(),
        "active": active,
        "description_url": str(record.get("description") or "").strip(),
        "source_url": source_url,
        "resource_links": json.dumps(resources),
        "point_of_contact": json.dumps(poc),
        "source": "SAM.gov",
        "raw_json": json.dumps(record),
    }
    normalized["relevance_score"], _ = score_opportunity(normalized)
    return normalized


def fetch_opportunities(
    api_key: str,
    *,
    lookback_days: int = 30,
    naics_codes: Iterable[str] = DEFAULT_NAICS,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch and deduplicate recently posted opportunities for each NAICS code."""
    if not api_key:
        raise SamApiError("SAM_API_KEY is required")
    if lookback_days < 1 or lookback_days > 365:
        raise ValueError("lookback_days must be between 1 and 365")
    page_size = max(1, min(int(page_size), 1000))

    posted_to = date.today()
    posted_from = posted_to - timedelta(days=lookback_days)
    session = _session()
    deduped: dict[str, dict[str, Any]] = {}

    for naics in naics_codes:
        code = str(naics).strip()
        if not code:
            continue
        offset = 0
        while True:
            params = {
                "api_key": api_key,
                "postedFrom": posted_from.strftime("%m/%d/%Y"),
                "postedTo": posted_to.strftime("%m/%d/%Y"),
                "ncode": code,
                "limit": page_size,
                "offset": offset,
            }
            LOGGER.info("Fetching SAM.gov NAICS=%s offset=%s", code, offset)
            try:
                response = session.get(API_URL, params=params, timeout=60)
            except requests.RequestException as exc:
                raise SamApiError(f"SAM.gov request failed: {exc}") from exc

            if response.status_code == 404:
                break
            if not response.ok:
                detail = response.text[:500]
                raise SamApiError(f"SAM.gov returned HTTP {response.status_code}: {detail}")

            try:
                payload = response.json()
            except ValueError as exc:
                raise SamApiError("SAM.gov returned invalid JSON") from exc

            page = payload.get("opportunitiesData") or []
            total = int(payload.get("totalRecords") or 0)
            for raw in page:
                normalized = normalize_opportunity(raw)
                if normalized["notice_id"]:
                    deduped[normalized["notice_id"]] = normalized

            offset += page_size
            if not page or offset >= total:
                break

    return list(deduped.values())
