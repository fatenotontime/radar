import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.compare_source_probe_runs import compare_probe_runs


def _write_results(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _record(source_id: str, **final: object) -> dict:
    return {"source_id": source_id, "final": final}


def test_both_successful_probes_are_both_reachable(tmp_path: Path):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_results(primary, [_record("source-a", final_result="success", http_status=200)])
    _write_results(fallback, [_record("source-a", final_result="success", http_status=204)])

    comparison = compare_probe_runs(primary, fallback)

    assert comparison["classification_counts"] == {"both_reachable": 1}
    assert comparison["sources"] == [
        {
            "source_id": "source-a",
            "primary": {
                "final_result": "success",
                "http_status": 200,
                "error_class": None,
                "parser_error": None,
            },
            "fallback": {
                "final_result": "success",
                "http_status": 204,
                "error_class": None,
                "parser_error": None,
            },
            "classification": "both_reachable",
        }
    ]


def test_comparison_classifies_all_outcomes_and_preserves_parser_errors(tmp_path: Path):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_results(
        primary,
        [
            _record("both-ok", final_result="success", http_status=200),
            _record("fallback-ok", final_result="failure", error_class="TimeoutError"),
            _record("primary-ok", final_result="success", http_status=200),
            _record(
                "access-review",
                final_result="failure",
                http_status=403,
                error_class="http_error",
            ),
            _record(
                "both-bad",
                final_result="failure",
                http_status=500,
                error_class="http_error",
                parser_error="JSONDecodeError: primary",
            ),
        ],
    )
    _write_results(
        fallback,
        [
            _record("both-ok", final_result="success", http_status=204),
            _record("fallback-ok", final_result="success", http_status=200),
            _record("primary-ok", final_result="failure", error_class="TimeoutError"),
            _record("access-review", final_result="failure", error_class="TimeoutError"),
            _record(
                "both-bad",
                final_result="failure",
                http_status=502,
                error_class="http_error",
                parser_error="XMLParseError: fallback",
            ),
        ],
    )

    comparison = compare_probe_runs(primary, fallback)

    assert comparison["interpretation_boundary"] == (
        "Network evidence only; this does not authorize collection."
    )
    assert comparison["classification_counts"] == {
        "both_failed": 1,
        "both_reachable": 1,
        "fallback_reachable": 1,
        "policy_or_access_review": 1,
        "primary_reachable": 1,
    }
    by_id = {source["source_id"]: source for source in comparison["sources"]}
    assert by_id["access-review"]["classification"] == "policy_or_access_review"
    assert by_id["both-bad"]["classification"] == "both_failed"
    assert by_id["both-bad"]["primary"]["parser_error"] == "JSONDecodeError: primary"
    assert by_id["both-bad"]["fallback"]["parser_error"] == "XMLParseError: fallback"


def test_comparison_rejects_mismatched_source_id_sets(tmp_path: Path):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_results(primary, [_record("shared", final_result="success")])
    _write_results(
        fallback,
        [
            _record("shared", final_result="success"),
            _record("fallback-only", final_result="success"),
        ],
    )

    with pytest.raises(ValueError, match="source_id sets differ"):
        compare_probe_runs(primary, fallback)


@pytest.mark.parametrize("duplicate_side", ["primary", "fallback"])
def test_comparison_rejects_duplicate_source_ids(tmp_path: Path, duplicate_side: str):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    one_record = [_record("shared", final_result="success")]
    duplicate_records = one_record * 2
    _write_results(primary, duplicate_records if duplicate_side == "primary" else one_record)
    _write_results(fallback, duplicate_records if duplicate_side == "fallback" else one_record)

    with pytest.raises(ValueError, match="duplicate source_id: shared"):
        compare_probe_runs(primary, fallback)


def test_cli_writes_sorted_utf8_json_with_trailing_newline(tmp_path: Path):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_results(
        primary,
        [
            _record("z-source", final_result="failure", parser_error="解析失败"),
            _record("a-source", final_result="success", http_status=200),
        ],
    )
    _write_results(
        fallback,
        [
            _record("z-source", final_result="failure", error_class="TimeoutError"),
            _record("a-source", final_result="success", http_status=200),
        ],
    )
    output = tmp_path / "nested" / "comparison.json"
    script = Path(__file__).resolve().parent.parent / "scripts" / "compare_source_probe_runs.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--primary-results",
            str(primary),
            "--fallback-results",
            str(fallback),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    raw_output = output.read_text(encoding="utf-8")
    assert raw_output.endswith("\n")
    assert "解析失败" in raw_output
    written = json.loads(raw_output)
    assert [source["source_id"] for source in written["sources"]] == [
        "a-source",
        "z-source",
    ]
