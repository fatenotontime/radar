import json
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EXPECTED_S_SOURCE_IDS = {
    "arxiv_api",
    "acs_jctc",
    "rsc_pccp",
    "huggingface",
    "anthropic",
    "openai",
    "nvidia",
}
EXPECTED_A_SOURCE_IDS = {
    "chemrxiv",
    "acs_catalysis",
    "acs_chem_mater",
    "aip_jcp",
    "materials_project",
    "allenai",
    "meta_ai",
    "mistral_ai",
    "gpaw",
    "materials_cloud",
    "ase",
}


def _load(name: str) -> dict[str, object]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_source_assurance_manifest_declares_version_and_default_priority():
    manifest = _load("source_assurance_priorities.json")

    assert manifest["schema_version"] == 1
    assert manifest["default_priority"] == "B_or_C"


def test_source_assurance_manifest_has_exact_s_sources():
    manifest = _load("source_assurance_priorities.json")

    assert set(manifest["priorities"]["S"]) == EXPECTED_S_SOURCE_IDS


def test_source_assurance_manifest_has_exact_a_sources():
    manifest = _load("source_assurance_priorities.json")

    assert set(manifest["priorities"]["A"]) == EXPECTED_A_SOURCE_IDS


def test_source_assurance_sets_are_disjoint_and_total_eighteen_sources():
    priorities = _load("source_assurance_priorities.json")["priorities"]
    s_sources = priorities["S"]
    a_sources = priorities["A"]

    assert set(s_sources).isdisjoint(a_sources)
    assert len(s_sources) + len(a_sources) == 18


def test_all_assurance_sources_exist_in_master_candidate_catalog():
    priorities = _load("source_assurance_priorities.json")["priorities"]
    prioritized_sources = set(priorities["S"]) | set(priorities["A"])
    master_candidates = json.loads(
        (CONFIG_DIR / "source_probe_candidates.json").read_text(encoding="utf-8")
    )
    master_source_ids = {item["source_id"] for item in master_candidates}

    assert prioritized_sources <= master_source_ids
