import json
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EXPECTED_EXTERNAL_IDS = {
    "arxiv_api",
    "acs_jacs",
    "rsc_chemistry",
    "anthropic",
    "google_deepmind",
    "nvidia",
    "reuters_world",
    "ap_world",
    "bbc_world",
}


def _load(name: str) -> list[dict[str, str]]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_candidate_pool_has_at_least_one_hundred_unique_unactivated_entries():
    candidates = _load("source_probe_candidates.json")
    source_ids = [item["source_id"] for item in candidates]

    assert len(candidates) >= 100
    assert len(source_ids) == len(set(source_ids))
    assert all(item["url"].startswith(("https://", "http://")) for item in candidates)
    assert all(item.get("role") for item in candidates)
    assert all("enabled" not in item for item in candidates)


def test_external_comparison_is_exactly_the_nine_ecs_anomalies_and_matches_master():
    candidates = {
        item["source_id"]: item for item in _load("source_probe_candidates.json")
    }
    external = _load("source_external_compare.json")

    assert {item["source_id"] for item in external} == EXPECTED_EXTERNAL_IDS
    assert len(external) == 9
    assert all(candidates[item["source_id"]] == item for item in external)
