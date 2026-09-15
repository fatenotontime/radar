import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import compare_source_probe_runs as comparator
from scripts.compare_source_probe_runs import compare_probe_runs, main


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


@pytest.mark.parametrize("output_side", ["primary", "fallback"])
@pytest.mark.parametrize("path_form", ["exact", "normalized_alias"])
def test_cli_rejects_an_input_path_as_output_without_changing_it(
    tmp_path: Path, output_side: str, path_form: str
):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    records = [_record("shared", final_result="success", http_status=200)]
    _write_results(primary, records)
    _write_results(fallback, records)
    input_path = primary if output_side == "primary" else fallback
    before = input_path.read_bytes()
    output = input_path
    if path_form == "normalized_alias":
        alias_parent = tmp_path / "alias-parent"
        alias_parent.mkdir()
        output = alias_parent / ".." / input_path.name

    with pytest.raises(ValueError, match="output must differ from probe inputs"):
        main(
            [
                "--primary-results",
                str(primary),
                "--fallback-results",
                str(fallback),
                "--output",
                str(output),
            ]
        )

    assert input_path.read_bytes() == before


def test_cli_does_not_overwrite_an_existing_output(tmp_path: Path):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    output = tmp_path / "comparison.json"
    records = [_record("shared", final_result="success", http_status=200)]
    _write_results(primary, records)
    _write_results(fallback, records)
    old_output = b"existing immutable output\n"
    output.write_bytes(old_output)
    expected_paths = {primary, fallback, output}

    with pytest.raises(FileExistsError):
        main(
            [
                "--primary-results",
                str(primary),
                "--fallback-results",
                str(fallback),
                "--output",
                str(output),
            ]
        )

    assert output.read_bytes() == old_output
    assert set(tmp_path.iterdir()) == expected_paths


def test_cli_cleans_temporary_file_when_atomic_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    output = tmp_path / "comparison.json"
    records = [_record("shared", final_result="success", http_status=200)]
    _write_results(primary, records)
    _write_results(fallback, records)
    primary_before = primary.read_bytes()
    fallback_before = fallback.read_bytes()

    def fail_publish(source: object, destination: object) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(comparator.os, "link", fail_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        main(
            [
                "--primary-results",
                str(primary),
                "--fallback-results",
                str(fallback),
                "--output",
                str(output),
            ]
        )

    assert primary.read_bytes() == primary_before
    assert fallback.read_bytes() == fallback_before
    assert not output.exists()
    assert set(tmp_path.iterdir()) == {primary, fallback}


def test_cli_cleans_temporary_file_when_writing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    primary = tmp_path / "primary.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    output = tmp_path / "comparison.json"
    records = [_record("shared", final_result="success", http_status=200)]
    _write_results(primary, records)
    _write_results(fallback, records)
    old_output = b"existing immutable output\n"
    output.write_bytes(old_output)
    primary_before = primary.read_bytes()
    fallback_before = fallback.read_bytes()

    def fail_write(value: object, handle: object, **kwargs: object) -> None:
        handle.write("partial")
        raise OSError("simulated write failure")

    monkeypatch.setattr(comparator.json, "dump", fail_write)

    with pytest.raises(OSError, match="simulated write failure"):
        main(
            [
                "--primary-results",
                str(primary),
                "--fallback-results",
                str(fallback),
                "--output",
                str(output),
            ]
        )

    assert primary.read_bytes() == primary_before
    assert fallback.read_bytes() == fallback_before
    assert output.read_bytes() == old_output
    assert set(tmp_path.iterdir()) == {primary, fallback, output}
