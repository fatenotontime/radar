#!/usr/bin/env python3
"""Compare network evidence from two existing source-probe runs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


INTERPRETATION_BOUNDARY = "Network evidence only; this does not authorize collection."
ACCESS_REVIEW_HTTP_STATUSES = {401, 403, 407, 429, 451}


def _load_results(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                source_id = record["source_id"]
                if source_id in records:
                    raise ValueError(f"duplicate source_id: {source_id}")
                records[source_id] = record
    return records


def _evidence(record: dict[str, Any]) -> dict[str, Any]:
    final = record["final"]
    return {
        "final_result": final.get("final_result"),
        "http_status": final.get("http_status"),
        "error_class": final.get("error_class"),
        "parser_error": final.get("parser_error"),
    }


def _classification(primary: dict[str, Any], fallback: dict[str, Any]) -> str:
    primary_success = primary["final_result"] == "success"
    fallback_success = fallback["final_result"] == "success"
    if primary_success and fallback_success:
        return "both_reachable"
    if not primary_success and fallback_success:
        return "fallback_reachable"
    if primary_success and not fallback_success:
        return "primary_reachable"
    if (
        primary["http_status"] in ACCESS_REVIEW_HTTP_STATUSES
        or fallback["http_status"] in ACCESS_REVIEW_HTTP_STATUSES
    ):
        return "policy_or_access_review"
    return "both_failed"


def compare_probe_runs(primary_path: Path, fallback_path: Path) -> dict[str, Any]:
    """Return a source-by-source comparison of two probe result files."""
    primary = _load_results(primary_path)
    fallback = _load_results(fallback_path)
    if primary.keys() != fallback.keys():
        primary_only = sorted(primary.keys() - fallback.keys())
        fallback_only = sorted(fallback.keys() - primary.keys())
        raise ValueError(
            "source_id sets differ: "
            f"primary_only={primary_only}, fallback_only={fallback_only}"
        )
    sources: list[dict[str, Any]] = []
    for source_id in sorted(primary):
        primary_evidence = _evidence(primary[source_id])
        fallback_evidence = _evidence(fallback[source_id])
        classification = _classification(primary_evidence, fallback_evidence)
        sources.append(
            {
                "source_id": source_id,
                "primary": primary_evidence,
                "fallback": fallback_evidence,
                "classification": classification,
            }
        )
    counts = Counter(source["classification"] for source in sources)
    return {
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
        "classification_counts": dict(sorted(counts.items())),
        "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-results", required=True, type=Path)
    parser.add_argument("--fallback-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    comparison = compare_probe_runs(args.primary_results, args.fallback_results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
