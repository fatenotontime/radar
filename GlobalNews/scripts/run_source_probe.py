#!/usr/bin/env python3
"""Produce a reviewable, repeatable Radar source-probe bundle.

This is an operational test script, not the Radar crawler. It never changes
Source Policy, news data, archives, or service configuration. Network results
are evidence about reachability and response shape only; licensing and source
activation remain manual decisions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import platform
import socket
import sys
import time
from typing import Any

from probe_sources import probe_one


SCRIPT_VERSION = "2026-09-13.3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("catalog must be a non-empty JSON list")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("every catalog item must be an object")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("every catalog item needs a non-empty source_id")
        if source_id in seen:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        if not isinstance(item.get("url"), str) or not item["url"].startswith(("http://", "https://")):
            raise ValueError(f"invalid URL for {source_id}")
    return value


def final_result(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer a successful structured response, otherwise retain last evidence."""
    for result in attempts:
        if result.get("http_status") is not None and result.get("error_class") is None:
            return result
    return attempts[-1]


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_summary(path: Path, metadata: dict[str, Any], records: list[dict[str, Any]]) -> None:
    hints = Counter(record["final"].get("network_hint", "unknown") for record in records)
    errors = Counter(record["final"].get("error_class") or "none" for record in records)
    statuses = Counter(str(record["final"].get("http_status") or "none") for record in records)
    final_results = Counter(record["final"].get("final_result", "failure") for record in records)
    parser_errors = Counter(
        record["final"].get("parser_error") or "none" for record in records
    )
    summary = {
        "source_count": len(records),
        "network_hint_counts": dict(sorted(hints.items())),
        "error_class_counts": dict(sorted(errors.items())),
        "http_status_counts": dict(sorted(statuses.items())),
        "final_result_counts": dict(sorted(final_results.items())),
        "parser_error_counts": dict(sorted(parser_errors.items())),
        "reachable_response_count": sum(
            record["final"].get("http_status") is not None for record in records
        ),
        "license_reviewed_count": 0,
        "verified_for_collection_count": 0,
        "activation_warning": "Network reachability does not verify licensing or enable collection.",
    }
    write_json(path.with_suffix(".json"), {"metadata": metadata, "summary": summary})

    lines = [
        "# Research Radar Source Probe Summary",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- Started: `{metadata['started_at']}`",
        f"- Finished: `{metadata['finished_at']}`",
        f"- Host: `{metadata['hostname']}`",
        f"- Account: `{metadata['account']}`",
        f"- Catalog SHA-256: `{metadata['catalog_sha256']}`",
        "",
        "## Counts",
        "",
        f"- Sources tested: **{summary['source_count']}**",
        f"- Reachable HTTP responses: **{summary['reachable_response_count']}**",
        f"- Network hints: `{json.dumps(summary['network_hint_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- HTTP statuses: `{json.dumps(summary['http_status_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- Final results: `{json.dumps(summary['final_result_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- Parser errors: `{json.dumps(summary['parser_error_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- Errors: `{json.dumps(summary['error_class_counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Interpretation boundary",
        "",
        "This bundle records DNS/TLS/HTTP and response-shape evidence only. It does not verify licensing, permitted fields, rate limits, or collection authority. No source is enabled by this script.",
        "",
        "Per-source attempts are in `results.jsonl`; execution metadata is in `run_metadata.json`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_catalog = Path(__file__).resolve().parent.parent / "config" / "source_probe_candidates.json"
    parser.add_argument("--catalog", type=Path, default=default_catalog)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    if args.timeout <= 0 or args.attempts < 1 or args.delay < 0:
        parser.error("timeout and attempts must be positive; delay cannot be negative")

    catalog = args.catalog.resolve()
    sources = load_catalog(catalog)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    started_at = utc_now()
    run_id = started_at.replace("-", "").replace(":", "").replace("+", "_")
    metadata = {
        "run_id": run_id,
        "script": "run_source_probe.py",
        "script_version": SCRIPT_VERSION,
        "started_at": started_at,
        "finished_at": None,
        "hostname": socket.gethostname(),
        "account": getpass.getuser(),
        "platform": platform.platform(),
        "python": sys.version,
        "catalog": str(catalog),
        "catalog_sha256": sha256_file(catalog),
        "source_count": len(sources),
        "timeout_seconds": args.timeout,
        "attempts_per_source": args.attempts,
        "delay_seconds": args.delay,
        "proxy_mode": "direct; urllib environment proxies disabled by probe_sources",
        "writes_runtime_radar_data": False,
        "license_reviewed": False,
        "verified_for_collection": False,
    }
    write_json(output_dir / "run_metadata.json", metadata)

    records: list[dict[str, Any]] = []
    with (output_dir / "results.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for index, source in enumerate(sources):
            attempts: list[dict[str, Any]] = []
            for attempt_number in range(1, args.attempts + 1):
                result = probe_one(source, args.timeout)
                result["attempt"] = attempt_number
                attempts.append(result)
                print(
                    f"[{index + 1}/{len(sources)}] {source['source_id']} attempt={attempt_number} "
                    f"status={result.get('http_status')} hint={result.get('network_hint')}",
                    flush=True,
                )
                if result.get("http_status") is not None and result.get("error_class") is None:
                    break
                if attempt_number < args.attempts:
                    time.sleep(args.delay)
            record = {
                "source_id": source["source_id"],
                "name": source.get("name"),
                "url": source["url"],
                "attempt_count": len(attempts),
                "final": final_result(attempts),
                "attempts": attempts,
            }
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    metadata["finished_at"] = utc_now()
    write_json(output_dir / "run_metadata.json", metadata)
    write_summary(output_dir / "summary.md", metadata, records)
    print(f"Output: {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
