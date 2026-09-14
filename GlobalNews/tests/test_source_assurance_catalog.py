import json
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "radar-sa-source-assurance.yml"
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


def test_source_assurance_workflow_exists():
    assert WORKFLOW_PATH.is_file()


def test_source_assurance_workflow_has_safe_scoped_triggers():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'cron: "17 3 * * 2"' in workflow
    assert "pull_request:" in workflow
    for path in (
        ".github/workflows/radar-sa-source-assurance.yml",
        "GlobalNews/config/source_assurance_priorities.json",
        "GlobalNews/config/source_sa_external_compare.json",
        "GlobalNews/config/source_probe_candidates.json",
        "GlobalNews/scripts/probe_sources.py",
        "GlobalNews/scripts/run_source_probe.py",
        "GlobalNews/tests/test_source_assurance_catalog.py",
        "GlobalNews/tests/test_source_probe_catalogs.py",
        "GlobalNews/tests/test_probe_sources.py",
    ):
        assert f'      - "{path}"' in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "concurrency:" in workflow
    assert "cancel-in-progress: false" in workflow


def test_source_assurance_workflow_validates_catalogs_before_probing():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "uses: actions/checkout@v7" in workflow
    assert "uses: actions/setup-python@v7" in workflow
    assert 'python-version: "3.13"' in workflow
    assert 'python -m pip install "pytest>=7.4,<9"' in workflow

    catalog_test = (
        "python -m pytest tests/test_source_assurance_catalog.py "
        "tests/test_source_probe_catalogs.py -q"
    )
    probe_command = "python scripts/run_source_probe.py"
    assert catalog_test in workflow
    assert workflow.index(catalog_test) < workflow.index(probe_command)


def test_source_assurance_workflow_preserves_complete_probe_bundle():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "--catalog config/source_sa_external_compare.json" in workflow
    assert '--output-dir "${PROBE_OUTPUT_DIR}"' in workflow
    assert "--attempts 2" in workflow
    assert "--timeout 20" in workflow
    assert "--delay 1" in workflow
    assert (
        "PROBE_OUTPUT_DIR: ${{ runner.temp }}/radar-sa-source-assurance-"
        "${{ github.run_id }}-${{ github.run_attempt }}"
    ) in workflow
    assert "if: always()" in workflow
    assert "uses: actions/upload-artifact@v7" in workflow
    assert "path: ${{ env.PROBE_OUTPUT_DIR }}" in workflow
    assert "if-no-files-found: error" in workflow
    assert "retention-days: 30" in workflow


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


def test_external_comparison_catalog_exactly_matches_s_and_a_master_candidates():
    priorities = _load("source_assurance_priorities.json")["priorities"]
    prioritized_source_ids = set(priorities["S"]) | set(priorities["A"])
    master_candidates = _load("source_probe_candidates.json")
    external_candidates = _load("source_sa_external_compare.json")

    assert len(external_candidates) == 18
    assert {item["source_id"] for item in external_candidates} == prioritized_source_ids

    master_by_source_id = {item["source_id"]: item for item in master_candidates}
    assert external_candidates == [
        master_by_source_id[item["source_id"]] for item in external_candidates
    ]
