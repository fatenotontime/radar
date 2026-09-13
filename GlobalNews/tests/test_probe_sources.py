from scripts.probe_sources import _check_parser, _classify_format, _network_hint


def test_probe_format_detection_is_small_and_deterministic():
    assert _classify_format("application/json", b'{"ok": true}') == "json"
    assert _classify_format("application/rss+xml", b"<rss><channel/></rss>") == "xml_feed"
    assert _classify_format("text/html", b"<!doctype html><html></html>") == "html"


def test_probe_hints_do_not_claim_collection_is_verified():
    assert _network_hint(200, "json", None) == ("ecs_candidate_pending_policy", False)
    assert _network_hint(200, "html", None) == ("manual_review", True)
    assert _network_hint(403, "unknown", "http_error") == ("blocked", True)
    assert _network_hint(None, "unknown", "TimeoutError") == ("needs_external_comparison", True)


def test_bounded_parser_check_records_errors_without_misreading_truncation():
    assert _check_parser("json", b'{"ok": true}', False) == ("valid", None)
    status, error = _check_parser("json", b'{"ok":', False)
    assert status == "error"
    assert error.startswith("JSONDecodeError:")
    assert _check_parser("json", b'{"partial":', True) == ("not_attempted_truncated", None)
    assert _check_parser("xml_feed", b"<rss><channel>", True) == ("prefix_valid", None)
