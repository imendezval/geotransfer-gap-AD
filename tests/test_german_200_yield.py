from __future__ import annotations

import hashlib
import json

import pytest

from geotransfer_gap.corpus.german_200_yield import (
    _mode_probe_status,
    _spawn_mode_status,
    _validated_reports,
    lifecycle_compatibility_status,
    map_route_status,
    main,
    physical_source_status,
    register_unique_candidate_id,
    required_boolean_groups_status,
    status_from_boolean_evidence,
)


def test_missing_evidence_is_not_established_not_failed() -> None:
    assert status_from_boolean_evidence([]) == "not_established"
    assert _spawn_mode_status(None, "idm")[0] == "not_established"
    assert _mode_probe_status({"modes": {}}, "expert")[0] == "not_established"


def test_conflicting_evidence_is_not_established() -> None:
    assert status_from_boolean_evidence([True, False]) == "not_established"
    assert status_from_boolean_evidence([True, None]) == "not_established"


def test_map_route_failure_is_not_hidden_by_other_passing_condition() -> None:
    assert map_route_status(False, []) == "failed"
    assert map_route_status(True, [4]) == "failed"
    assert map_route_status(True, []) == "passed"
    assert map_route_status(True, None) == "not_established"


def test_reviewable_overlap_without_resolution_stays_pending() -> None:
    physical = {
        "ego_boundary_contact": False,
        "unreviewable_overlap_count": 0,
        "overlap_pair_count": 1,
    }
    assert physical_source_status(physical, "technical_rejection", None) == "pending_human_review"
    assert physical_source_status(physical, "technical_rejection", True) == "passed"
    assert physical_source_status(physical, "source_physical_rejection", True) == "failed"


def test_replay_requires_both_explicit_evidence_groups() -> None:
    assert required_boolean_groups_status([[True], []]) == "not_established"
    assert required_boolean_groups_status([[True], [False]]) == "failed"
    assert required_boolean_groups_status([[True, False], [True]]) == "not_established"


def test_lifecycle_marker_does_not_stand_in_for_missing_trace() -> None:
    independent, marker = lifecycle_compatibility_status(False, False)
    assert independent == "not_established"
    assert marker == "failed"
    assert lifecycle_compatibility_status(True, False) == ("failed", "failed")


def test_explicit_boolean_classification() -> None:
    assert status_from_boolean_evidence([True, True]) == "passed"
    assert status_from_boolean_evidence([False]) == "failed"


def test_matrix_identity_check_rejects_ambiguous_rows() -> None:
    seen = set()
    register_unique_candidate_id(seen, "same")
    with pytest.raises(ValueError, match="ambiguous primary candidate identity"):
        register_unique_candidate_id(seen, "same")
    with pytest.raises(ValueError, match="missing or ambiguous"):
        register_unique_candidate_id(seen, None)


def test_unbound_file_is_not_interpreted_and_hash_mismatch_aborts(tmp_path) -> None:
    testing = tmp_path / "testing"
    testing.mkdir()
    report_path = testing / "validation.json"
    report_path.write_text(json.dumps({"binary_round_trip": "passed"}))
    unbound = {"root": str(tmp_path), "output_tree_sha256": {}}
    assert _validated_reports(unbound, testing)["validation.json"] is None

    actual = hashlib.sha256(report_path.read_bytes()).hexdigest()
    mismatched = {
        "root": str(tmp_path),
        "output_tree_sha256": {"testing/validation.json": "0" * 64},
    }
    assert actual != mismatched["output_tree_sha256"]["testing/validation.json"]
    with pytest.raises(ValueError, match="hash mismatch"):
        _validated_reports(mismatched, testing)


def test_cli_refuses_to_overwrite_either_output(tmp_path) -> None:
    occupied = tmp_path / "matrix.json"
    occupied.write_text("saved")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        main(["--repo-root", str(tmp_path), "--output", str(occupied)])

    compact = tmp_path / "compact.json"
    compact.write_text("saved")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        main([
            "--repo-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "new-matrix.json"),
            "--compact-output",
            str(compact),
        ])
