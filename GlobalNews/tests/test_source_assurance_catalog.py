import json
from pathlib import Path

import yaml


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


def _load_workflow() -> dict[str, object]:
    workflow = yaml.load(
        WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    assert isinstance(workflow, dict)
    return workflow


def _workflow_steps(workflow: dict[str, object]) -> list[dict[str, object]]:
    return workflow["jobs"]["probe-s-and-a-sources"]["steps"]


def test_source_assurance_workflow_exists():
    assert WORKFLOW_PATH.is_file()


def test_source_assurance_workflow_has_safe_scoped_triggers():
    workflow = _load_workflow()
    triggers = workflow["on"]

    assert triggers["workflow_dispatch"] == ""
    assert triggers["schedule"] == [{"cron": "17 3 * * 2"}]
    assert set(triggers["pull_request"]["paths"]) == {
        ".github/workflows/radar-sa-source-assurance.yml",
        "GlobalNews/config/source_assurance_priorities.json",
        "GlobalNews/config/source_sa_external_compare.json",
        "GlobalNews/config/source_probe_candidates.json",
        "GlobalNews/scripts/compare_source_probe_runs.py",
        "GlobalNews/scripts/probe_sources.py",
        "GlobalNews/scripts/run_source_probe.py",
        "GlobalNews/tests/test_compare_source_probe_runs.py",
        "GlobalNews/tests/test_source_assurance_catalog.py",
        "GlobalNews/tests/test_source_probe_catalogs.py",
        "GlobalNews/tests/test_probe_sources.py",
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "radar-sa-source-assurance",
        "cancel-in-progress": "false",
    }


def test_source_assurance_workflow_validates_catalogs_before_probing():
    workflow = _load_workflow()
    job = workflow["jobs"]["probe-s-and-a-sources"]
    steps = _workflow_steps(workflow)
    steps_by_name = {step["name"]: step for step in steps}

    assert job["runs-on"] == "ubuntu-latest"
    assert int(job["timeout-minutes"]) >= 45
    assert job["defaults"]["run"]["working-directory"] == "GlobalNews"
    assert steps_by_name["Check out source assurance definitions"]["uses"] == (
        "actions/checkout@v7"
    )
    assert steps_by_name["Set up Python"] == {
        "name": "Set up Python",
        "uses": "actions/setup-python@v7",
        "with": {"python-version": "3.13"},
    }
    assert steps_by_name["Install test dependencies"]["run"] == (
        'python -m pip install "pytest>=7.4,<9" "PyYAML>=6,<7"'
    )

    catalog_test_command = (
        "python -m pytest tests/test_source_assurance_catalog.py "
        "tests/test_source_probe_catalogs.py tests/test_probe_sources.py "
        "tests/test_compare_source_probe_runs.py -q"
    )
    catalog_step = steps_by_name["Validate catalog contracts"]
    probe_step = steps_by_name["Probe S and A sources"]
    assert catalog_step["run"] == catalog_test_command
    assert steps.index(catalog_step) < steps.index(probe_step)


def test_source_assurance_pull_requests_never_run_probe_or_evidence_steps():
    workflow = _load_workflow()
    steps = _workflow_steps(workflow)
    steps_by_name = {step["name"]: step for step in steps}

    event_gate = "github.event_name != 'pull_request'"
    assert steps_by_name["Prepare workflow evidence metadata"]["if"] == event_gate
    assert steps_by_name["Probe S and A sources"]["if"] == event_gate
    assert steps_by_name["Finalize workflow evidence"]["if"] == (
        f"always() && {event_gate}"
    )
    assert steps_by_name["Upload source assurance evidence"]["if"] == (
        f"always() && {event_gate}"
    )


def test_source_assurance_workflow_preserves_honest_evidence_on_failure():
    workflow = _load_workflow()
    job = workflow["jobs"]["probe-s-and-a-sources"]
    steps = _workflow_steps(workflow)
    steps_by_name = {step["name"]: step for step in steps}

    assert "runner.temp" not in json.dumps(job.get("env", {}))
    assert not job.get("env")

    prepare = steps_by_name["Prepare workflow evidence metadata"]
    catalog_test = steps_by_name["Validate catalog contracts"]
    probe = steps_by_name["Probe S and A sources"]
    finalize = steps_by_name["Finalize workflow evidence"]
    upload = steps_by_name["Upload source assurance evidence"]

    assert steps.index(prepare) < steps.index(catalog_test) < steps.index(probe)
    assert prepare["id"] == "prepare"
    assert (
        'evidence_root="${RUNNER_TEMP}/radar-sa-source-evidence-'
        '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
    ) in prepare["run"]
    assert 'mkdir -p "${EVIDENCE_ROOT}"' in prepare["run"]
    assert 'EVIDENCE_ROOT=${evidence_root}' in prepare["run"]
    assert 'evidence_root=${evidence_root}' in prepare["run"]
    assert "GITHUB_ENV" in prepare["run"]
    assert "GITHUB_OUTPUT" in prepare["run"]
    assert "workflow_metadata.json" in prepare["run"]
    for fact in ("run_id", "run_attempt", "event_name", "commit", "catalog"):
        assert f'"{fact}"' in prepare["run"]
    assert '"config/source_sa_external_compare.json"' in prepare["run"]
    assert '"probe_outcome"' not in prepare["run"]
    assert '"probe_complete"' not in prepare["run"]

    assert probe["id"] == "probe"
    assert "python scripts/run_source_probe.py" in probe["run"]
    assert "--catalog config/source_sa_external_compare.json" in probe["run"]
    assert '--output-dir "${EVIDENCE_ROOT}/probe"' in probe["run"]
    assert "--attempts 2" in probe["run"]
    assert "--timeout 20" in probe["run"]
    assert "--delay 1" in probe["run"]

    gated_always = "always() && github.event_name != 'pull_request'"
    assert finalize["if"] == gated_always
    assert finalize["env"] == {"PROBE_OUTCOME": "${{ steps.probe.outcome }}"}
    assert "workflow_result.json" in finalize["run"]
    assert '"probe_outcome"' in finalize["run"]
    assert '"probe_complete"' in finalize["run"]
    assert steps.index(probe) < steps.index(finalize) < steps.index(upload)

    assert upload["if"] == gated_always
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["path"] == "${{ steps.prepare.outputs.evidence_root }}"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "30"
    assert "evidence" in upload["with"]["name"]
    assert "complete" not in upload["with"]["name"].lower()


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
