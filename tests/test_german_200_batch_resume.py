import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from geotransfer_gap.corpus import finalize_german_200_batch as finalize
from geotransfer_gap.corpus import run_german_200_batch as batch


def write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def candidate_root(tmp_path: Path, *, technical: bool = False, review_assets: bool = False) -> Path:
    root = tmp_path / "scene"
    for name in (
        "conversion.log",
        "testing/validation.json",
        "testing/manifest.csv",
        "testing/map_000000.bin",
        "testing/ind_fixture.json",
        "testing/map_audit.json",
        "testing/map_semantics_audit.json",
        "testing/rule_applicability_audit.json",
        "testing/physical_source_audit.json",
    ):
        write(root / name)
    if technical:
        for name in (
            "testing/admission_hybrid_startup.json",
            "testing/interaction_fidelity_audit_hybrid_startup.json",
        ):
            write(root / name)
    if review_assets:
        write(root / "testing/source_image_registration.json")
        write(root / "testing/rule_review_montage.png")
    return root


@pytest.mark.parametrize("status", ["source_geometry_rejection", "source_physical_rejection"])
def test_source_rejections_reuse_only_with_current_preflight_outputs(tmp_path, status):
    root = candidate_root(tmp_path)
    fingerprint = {"global": {"runner": "same"}, "source": "same"}
    result = {
        "status": status,
        "root": str(root),
        "input_fingerprint": fingerprint,
        "output_tree_sha256": batch.output_tree_fingerprint(root),
    }

    assert batch.reusable(result, fingerprint)
    assert not batch.reusable(result, {**fingerprint, "source": "changed"})

    write(root / "testing/map_audit.json", "changed")
    assert not batch.reusable(result, fingerprint)


def test_review_blocked_reuse_requires_gate_and_review_evidence(tmp_path):
    root = candidate_root(tmp_path, technical=True, review_assets=True)
    fingerprint = {"global": {"tools": "current"}, "source": "current"}
    result = {
        "status": "review_blocked",
        "root": str(root),
        "input_fingerprint": fingerprint,
        "output_tree_sha256": batch.output_tree_fingerprint(root),
    }

    assert batch.reusable(result, fingerprint)
    (root / "testing/source_image_registration.json").unlink()
    assert not batch.reusable(result, fingerprint)


def test_transient_errors_are_always_retried_even_with_complete_outputs(tmp_path):
    root = candidate_root(tmp_path, technical=True, review_assets=True)
    fingerprint = {"global": "current"}
    result = {
        "status": "transient_error",
        "root": str(root),
        "input_fingerprint": fingerprint,
        "output_tree_sha256": batch.output_tree_fingerprint(root),
    }

    assert not batch.reusable(result, fingerprint)


def test_finalizer_rejects_stale_global_and_row_fingerprints():
    current = {"runner": "r2", "tools": {"gate": "new"}, "config": "cfg2", "support": "s2"}
    finalize.require_fingerprint_match(current, current, "scratch row")
    for changed in (
        {**current, "runner": "r1"},
        {**current, "tools": {"gate": "old"}},
        {**current, "config": "cfg1"},
        {**current, "support": "s1"},
    ):
        with pytest.raises(ValueError, match="Stale producer/input fingerprint"):
            finalize.require_fingerprint_match(changed, current, "scratch row")


def test_finalizer_rejects_mismatched_owner_marker():
    owner = {"queue_sha256": "frozen", "output_root": "/tmp/scratch"}
    finalize.require_owner_match(owner, owner)
    with pytest.raises(ValueError, match="owner marker"):
        finalize.require_owner_match(owner, {**owner, "queue_sha256": "other"})


def test_existing_ledger_with_old_producer_fails_before_resume():
    ledger = {
        "queue_sha256": "frozen",
        "queue_row_count": 1,
        "results": [{"queue_index": 0, "input_fingerprint": {"global": {"runner": "old"}}}],
    }
    with pytest.raises(ValueError, match="choose a new named namespace"):
        batch.validate_existing_ledger(ledger, [{}], "frozen", {}, {"runner": "current"})


def test_finalizer_rejects_candidate_roots_outside_owned_namespace(tmp_path):
    output = tmp_path / "owned"
    inside = output / "candidate_runs" / "scene"
    inside.mkdir(parents=True)
    finalize.require_candidate_root({"root": str(inside)}, output, "scratch")
    outside = tmp_path / "other" / "scene"
    outside.mkdir(parents=True)
    with pytest.raises(ValueError, match="escapes its owned namespace"):
        finalize.require_candidate_root({"root": str(outside)}, output, "scratch")


def test_namespaced_output_root_and_nested_validation_queue_envelope(monkeypatch, tmp_path):
    project = tmp_path / "project"
    artifacts = project / "artifacts"
    queue_path = artifacts / "german_200_v1" / "next_validation_queue.json"
    output = artifacts / "german_200_v1_runs" / "batch_next"
    cfg = SimpleNamespace(artifacts=artifacts, project=project)
    monkeypatch.setattr(batch, "PROJECT_ROOT", project)

    assert batch.output_namespace(cfg, queue_path, output) == output.resolve()
    assert batch.get_rows({"next_validation_queue": {"candidates": [{"id": 1}]}}) == [{"id": 1}]

    with pytest.raises(ValueError, match="Output root"):
        batch.output_namespace(cfg, queue_path, project / "outside")
