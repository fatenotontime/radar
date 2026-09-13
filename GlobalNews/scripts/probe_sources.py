#!/usr/bin/env python3
"""Run a small, direct-network source probe without changing Radar data.

The probe deliberately does not decide licensing or enable sources.  It emits
JSON Lines so a later review can combine network evidence with Source Policy.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
from xml.etree import ElementTree


READ_LIMIT = 8192
USER_AGENT = "ResearchRadarSourceProbe/1.0 (private operational check)"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_format(content_type: str, sample: bytes) -> str:
    lowered = content_type.lower()
    stripped = sample.lstrip().lower()
    if "json" in lowered or stripped.startswith((b"{", b"[")):
        return "json"
    if "xml" in lowered or stripped.startswith(b"<?xml") or b"<rss" in stripped[:512] or b"<feed" in stripped[:512]:
        return "xml_feed"
    if "html" in lowered or b"<html" in stripped[:512] or b"<!doctype html" in stripped[:512]:
        return "html"
    return "other"


def _check_parser(detected_format: str, sample: bytes, truncated: bool) -> tuple[str, str | None]:
    """Validate bounded response data without treating truncation as corruption."""
    try:
        if detected_format == "json":
            if truncated:
                return "not_attempted_truncated", None
            json.loads(sample.decode("utf-8"))
            return "valid", None
        if detected_format == "xml_feed":
            if truncated:
                parser = ElementTree.XMLPullParser(events=("start",))
                parser.feed(sample)
                return "prefix_valid", None
            ElementTree.fromstring(sample)
            return "valid", None
        if detected_format == "html":
            return "not_applicable", None
        return "unsupported_format", None
    except (UnicodeDecodeError, json.JSONDecodeError, ElementTree.ParseError) as exc:
        return "error", f"{type(exc).__name__}: {str(exc)[:240]}"


def _network_hint(status: int | None, detected_format: str, error_class: str | None) -> tuple[str, bool]:
    if status in {401, 407}:
        return "manual", True
    if status in {403, 429, 451}:
        return "blocked", True
    if error_class:
        return "needs_external_comparison", True
    if status is not None and 200 <= status < 400 and detected_format in {"json", "xml_feed"}:
        return "ecs_candidate_pending_policy", False
    if status is not None and 200 <= status < 400:
        return "manual_review", True
    return "needs_external_comparison", True


def probe_one(source: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = source["url"]
    host = urlparse(url).hostname
    result: dict[str, Any] = {
        "source_id": source["source_id"],
        "name": source["name"],
        "url": url,
        "role": source.get("role"),
        "tested_at": _utc_now(),
        "dns": None,
        "dns_status": "not_attempted",
        "connection_status": "not_attempted",
        "tls": None,
        "tls_status": "not_attempted",
        "http_status": None,
        "http_status_state": "not_attempted",
        "latency_ms": None,
        "content_type": None,
        "format": "unknown",
        "parser_status": "not_attempted",
        "parser_error": None,
        "error_class": None,
        "error": None,
        "final_result": "failure",
    }
    started = time.monotonic()
    try:
        if not host:
            raise ValueError("URL has no hostname")
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        result["dns_status"] = "attempting"
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        result["dns"] = addresses[:4]
        result["dns_status"] = "success"
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            result["connection_status"] = "attempting"
            with socket.create_connection((host, port), timeout=timeout) as raw:
                result["connection_status"] = "success"
                result["tls_status"] = "attempting"
                with context.wrap_socket(raw, server_hostname=host) as secured:
                    result["tls"] = secured.version()
                    result["tls_status"] = "success"
        else:
            result["connection_status"] = "attempting"
            with socket.create_connection((host, port), timeout=timeout):
                result["connection_status"] = "success"
            result["tls_status"] = "not_applicable"

        opener = build_opener(ProxyHandler({}))
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/atom+xml, application/rss+xml, application/json, text/html;q=0.5, */*;q=0.1",
                "Connection": "close",
            },
        )
        result["http_status_state"] = "attempting"
        with opener.open(request, timeout=timeout) as response:
            sample = response.read(READ_LIMIT)
            result["http_status"] = response.status
            result["http_status_state"] = "received"
            result["content_type"] = response.headers.get("Content-Type")
            result["final_url"] = response.geturl()
            result["sample_bytes"] = len(sample)
            result["format"] = _classify_format(result["content_type"] or "", sample)
            result["sample_truncated"] = len(sample) == READ_LIMIT
            result["parser_status"], result["parser_error"] = _check_parser(
                result["format"], sample, result["sample_truncated"]
            )
            if result["parser_error"] is None and result["format"] in {
                "json",
                "xml_feed",
                "html",
            }:
                result["final_result"] = "success"
    except HTTPError as exc:
        result["http_status"] = exc.code
        result["http_status_state"] = "received"
        result["error_class"] = "http_error"
        result["error"] = str(exc)[:300]
    except (URLError, socket.timeout, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
        result["error_class"] = type(exc).__name__
        result["error"] = str(exc)[:300]
    finally:
        for field in ("dns_status", "connection_status", "tls_status", "http_status_state"):
            if result[field] == "attempting":
                result[field] = "failure"
        result["latency_ms"] = round((time.monotonic() - started) * 1000)

    hint, action_required = _network_hint(result["http_status"], result["format"], result["error_class"])
    result["network_hint"] = hint
    result["action_required"] = action_required
    result["license_status"] = "not_reviewed"
    result["verified_for_collection"] = False
    result["final_result"] = (
        "success"
        if result["http_status"] is not None
        and 200 <= result["http_status"] < 400
        and result["error_class"] is None
        and result["parser_error"] is None
        else "failure"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()

    sources = json.loads(args.catalog.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        for source in sources:
            record = probe_one(source, args.timeout)
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            print(f"{record['source_id']}: {record['http_status']} {record['network_hint']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
