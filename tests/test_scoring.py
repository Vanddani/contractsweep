from datetime import date, timedelta

from scoring import score_opportunity


def test_primary_janitorial_scores_high():
    score, reasons = score_opportunity(
        {
            "title": "Recurring janitorial services for federal office",
            "naics_code": "561720",
            "notice_type": "Solicitation",
            "active": 1,
            "set_aside_description": "Total Small Business Set-Aside",
            "response_deadline": (date.today() + timedelta(days=20)).isoformat(),
        }
    )
    assert score >= 75
    assert any("561720" in reason for reason in reasons)


def test_supplies_only_is_penalized():
    score, reasons = score_opportunity(
        {
            "title": "Custodial supplies and paper products",
            "naics_code": "423850",
            "notice_type": "Solicitation",
            "active": 1,
            "response_deadline": (date.today() + timedelta(days=20)).isoformat(),
        }
    )
    assert score < 40
    assert any("supplies" in reason.lower() for reason in reasons)


def test_expired_deadline_is_penalized():
    open_score, _ = score_opportunity(
        {
            "title": "Janitorial services",
            "naics_code": "561720",
            "notice_type": "Solicitation",
            "active": 1,
            "response_deadline": (date.today() + timedelta(days=21)).isoformat(),
        }
    )
    expired_score, _ = score_opportunity(
        {
            "title": "Janitorial services",
            "naics_code": "561720",
            "notice_type": "Solicitation",
            "active": 1,
            "response_deadline": (date.today() - timedelta(days=1)).isoformat(),
        }
    )
    assert open_score > expired_score
