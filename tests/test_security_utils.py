from security_utils import csv_safe, safe_http_url, safe_local_url


def test_safe_local_url_blocks_external_redirects():
    fallback = "/dashboard"
    assert safe_local_url("/opportunity/12?tab=notes", fallback) == "/opportunity/12?tab=notes"
    assert safe_local_url("https://evil.example/path", fallback) == fallback
    assert safe_local_url("//evil.example/path", fallback) == fallback
    assert safe_local_url("javascript:alert(1)", fallback) == fallback


def test_safe_http_url_allows_only_absolute_http_urls():
    assert safe_http_url("https://sam.gov/opp/abc/view") == "https://sam.gov/opp/abc/view"
    assert safe_http_url("http://example.gov/file") == "http://example.gov/file"
    assert safe_http_url("javascript:alert(1)") == ""
    assert safe_http_url("/relative/path") == ""


def test_csv_safe_neutralizes_spreadsheet_formulas():
    for value in ("=1+1", "+SUM(A1:A2)", "-2+3", "@cmd", "\t=1", "\r=1"):
        assert csv_safe(value).startswith("'")
    assert csv_safe("Ordinary text") == "Ordinary text"
    assert csv_safe(42) == 42
    assert csv_safe(None) == ""
