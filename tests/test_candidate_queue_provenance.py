import csv
from types import SimpleNamespace

from geotransfer_gap.corpus import expand_source_phase_queue as phases
from geotransfer_gap.corpus import run_oriented_candidate_queue as queue
from geotransfer_gap.maps import lanelet


def _scene_outputs(root, status):
    testing = root / "testing"
    testing.mkdir(parents=True)
    for name in (
        "validation.json",
        "manifest.csv",
        "map_000000.bin",
        "ind_scene.json",
    ):
        (testing / name).write_text(name)
    for name in queue.REUSABLE_OUTPUTS[status]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)


def test_deferred_rows_retry_but_rejected_evidence_is_reusable(tmp_path):
    fingerprints = {"selection": "s1", "runtime": "r1"}
    root = tmp_path / "rejected"
    _scene_outputs(root, "source_geometry_rejection")
    row = {
        "status": "source_geometry_rejection",
        "root": str(root),
        "screen_fingerprints": fingerprints,
        "output_fingerprints": queue.output_fingerprints(
            root, "source_geometry_rejection"
        ),
    }

    assert queue.reusable_result(row, fingerprints)
    assert not queue.reusable_result(dict(row, status="deferred"), fingerprints)
    assert not queue.reusable_result(dict(row, status="technical_gate_error"), fingerprints)
    assert not queue.reusable_result(dict(row, status="source_audit_error"), fingerprints)


def test_reuse_binds_actual_inputs_and_relevant_outputs_only(tmp_path):
    fingerprints = {
        "selection": "s1",
        "source_inputs": {"tracks": "a"},
        "runtime": "r1",
        "config": "c1",
    }
    root = tmp_path / "rejected"
    _scene_outputs(root, "unresolved_semantics_screen")
    row = {
        "status": "unresolved_semantics_screen",
        "root": str(root),
        "screen_fingerprints": fingerprints,
        "output_fingerprints": queue.output_fingerprints(
            root, "unresolved_semantics_screen"
        ),
    }

    assert queue.reusable_result(row, fingerprints)
    for changed in (
        {**fingerprints, "selection": "s2"},
        {**fingerprints, "source_inputs": {"tracks": "b"}},
        {**fingerprints, "runtime": "r2"},
        {**fingerprints, "config": "c2"},
    ):
        assert not queue.reusable_result(row, changed)
    (root / "reviewer_note.md").write_text("manual note")
    assert queue.reusable_result(row, fingerprints)
    (root / "testing/map_audit.json").write_text("changed audit")
    assert not queue.reusable_result(row, fingerprints)


def test_source_fingerprint_uses_recording_map_resolver(tmp_path, monkeypatch):
    source = tmp_path / "source"
    data = source / "data"
    data.mkdir(parents=True)
    recording_meta = data / "12_recordingMeta.csv"
    with recording_meta.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("locationId",))
        writer.writeheader()
        writer.writerow({"locationId": "1"})
    monkeypatch.setattr(lanelet, "SOURCE", source)
    row = {"recording": 12, "location": 4}
    paths = queue.source_input_paths(row, source)

    assert paths["lanelet_map"] == source / "maps/lanelets/01_bendplatz_constuction/location1_construction.osm"
    assert paths["opendrive_map"] == source / "maps/opendrive/01_bendplatz_constuction/bendplatz_construction.xodr"
    paths["lanelet_map"].parent.mkdir(parents=True)
    paths["lanelet_map"].write_text("first")
    before = queue.file_fingerprints(paths)
    paths["lanelet_map"].write_text("second")
    assert before["lanelet_map"] != queue.file_fingerprints(paths)["lanelet_map"]


def test_scene_reuse_keeps_pair_metadata_and_actor_evidence():
    row = {
        "recording": 8,
        "location": 3,
        "ego": 119,
        "first_frame": 7919,
        "actor": 120,
        "actor_class": "car",
        "task_evidence": {"source_actor": 120},
        "status": "deferred",
        "root": "/tmp/source-row",
        "screen_fingerprints": {"source": "row"},
    }
    scene = {
        "recording": 8,
        "location": 3,
        "ego": 119,
        "first_frame": 7919,
        "status": "awaiting_manual_review",
        "root": "/tmp/scene-evidence",
        "screen_fingerprints": {"source": "scene"},
    }
    opportunities = [
        {"track_id": 118, "preserved_for_claimed_interaction": False},
        {"track_id": 120, "preserved_for_claimed_interaction": True},
    ]

    result = queue.candidate_result(scene, row, opportunities)

    assert queue.candidate_key(result) == (8, 119, 7919, 120)
    assert result["task_evidence"] == {"source_actor": 120}
    assert result["candidate_actor_fidelity"] == opportunities[1]
    assert result["root"] == scene["root"]
    assert result["status"] == scene["status"]
    assert result["screen_fingerprints"] == scene["screen_fingerprints"]
    assert not queue.same_pair_version(
        {"recording": 8, "ego": 119, "first_frame": 7919}, result
    )


def test_optional_scope_command_errors_remain_retryable(tmp_path):
    proof = tmp_path / "scope.json"
    proof.write_text("{}")

    assert queue.scope_audit_failed(SimpleNamespace(returncode=1), proof)
    assert not queue.scope_audit_failed(SimpleNamespace(returncode=0), proof)
    assert queue.scope_audit_failed(
        SimpleNamespace(returncode=0), tmp_path / "missing.json"
    )


def test_phase_expansion_is_deterministic_and_preserves_actor_variants():
    seeds = [
        {
            "recording": 8,
            "location": 3,
            "ego": 119,
            "first_frame": 100,
            "actor": 118,
            "status": "deferred",
        },
        {
            "recording": 8,
            "location": 3,
            "ego": 119,
            "first_frame": 100,
            "actor": 120,
            "status": "technical_rejection",
        },
    ]

    first = phases.phase_variants(seeds)
    second = phases.phase_variants(seeds)
    jobs = list(first.values())

    assert first == second
    assert list(first.items()) == list(second.items())
    assert {row["actor"] for row in jobs} == {118, 120}
    assert len(jobs) == 16
    assert all(row["first_frame"] != 100 for row in jobs)
