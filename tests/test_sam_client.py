from sam_client import normalize_opportunity


def test_normalize_opportunity_flattens_core_fields():
    record = {
        "noticeId": "abc123",
        "title": "Janitorial services",
        "fullParentPathName": "AGENCY.OFFICE",
        "postedDate": "2026-07-20",
        "responseDeadLine": "2026-08-20T15:00:00-05:00",
        "naicsCode": "561720",
        "placeOfPerformance": {"state": {"code": "IL"}, "city": {"name": "chicago"}},
        "active": "Yes",
        "resourceLinks": "https://example.gov/attachment.pdf",
        "pointOfContact": {"fullName": "Contract Specialist", "email": "person@example.gov"},
    }
    item = normalize_opportunity(record)
    assert item["notice_id"] == "abc123"
    assert item["agency"] == "AGENCY"
    assert item["office"] == "OFFICE"
    assert item["state"] == "IL"
    assert item["city"] == "Chicago"
    assert item["response_deadline"] == "2026-08-20"
    assert item["active"] == 1
    assert "attachment.pdf" in item["resource_links"]
    assert "Contract Specialist" in item["point_of_contact"]


def test_explicit_inactive_values_stay_inactive():
    for value in (False, 0, "No", "false", "0"):
        item = normalize_opportunity({"noticeId": f"id-{value}", "active": value})
        assert item["active"] == 0


def test_missing_active_defaults_to_active():
    item = normalize_opportunity({"noticeId": "missing-active"})
    assert item["active"] == 1
