from __future__ import annotations

import numpy as np
import pytest

from geotransfer_gap.validation.idm_eligibility import (
    _applicable_leader_evidence,
    _check_new_output,
    _eligibility_dimensions,
    _source_prior_coverage,
    fingerprint_mismatches,
    summarize_route,
    validate_identity,
)


def test_native_route_requires_finite_distinct_points():
    assert summarize_route({"route_x": [0.0, 1.0], "route_y": [0.0, 0.0]})["valid"]
    assert not summarize_route({"route_x": [], "route_y": []})["valid"]
    assert not summarize_route({"route_x": [0.0, float("nan")], "route_y": [0.0, 1.0]})["valid"]
    assert not summarize_route({"route_x": [1.0, 1.0], "route_y": [2.0, 2.0]})["valid"]


def test_native_identity_binds_ego_source_id_to_active_binary_index():
    binary = {"sdc_track_index": 1, "objects": [{"id": 20}, {"id": 42}]}
    state = {"entities": [{}, {}], "active_agent_indices": [0, 1]}
    proof = validate_identity(binary, state)
    assert proof["valid"]
    assert proof["ego_binary_index"] == 1
    assert proof["ego_source_id"] == 42

    absent_ego = validate_identity(binary, {**state, "active_agent_indices": [0]})
    assert not absent_ego["valid"]
    assert "ego_not_associated_with_native_active_slot" in absent_ego["reasons"]


def test_background_prior_coverage_does_not_bridge_a_source_gap():
    valid = np.array([1, 1, 0, 1, 1], dtype=np.uint8)
    obj = {
        "traj_valid": valid,
        "traj_x": np.array([0, 0.05, 0, 80, 80.05], dtype=np.float32),
        "traj_y": np.zeros(5, dtype=np.float32),
        "traj_vx": np.full(5, 2, dtype=np.float32),
        "traj_vy": np.zeros(5, dtype=np.float32),
    }
    proof = _source_prior_coverage(obj, target_velocity=1.0)
    assert proof["contiguous_source_end_step_exclusive"] == 2
    assert proof["source_route_length_m"] == pytest.approx(0.05)
    assert proof["status"] == "fallback_lane_route"


def test_unsupported_leader_task_is_blocked_without_manual_promotion():
    shared = {
        "manual_evidence": {
            "task_types": ["lead_vehicle_braking_response"],
            "task_actor_ids": [9001],
        }
    }
    probe = {"identity": {"ego_source_id": 1}, "role_actor_rows": {}, "leader_observations": {}}
    evidence = _applicable_leader_evidence(shared, probe)
    assert evidence["status"] == "blocked"
    assert evidence["missing_actor_ids"] == [9001]

    dimensions = _eligibility_dimensions("current", "current", "current", "blocked")
    assert dimensions["model_route_status"] == "eligible"
    assert dimensions["task_status"] == "blocked"
    assert dimensions["research_admission"] == "not_established"


def test_changed_role_protocol_source_tool_or_runtime_invalidates_reuse():
    record = {
        "schema_version": 1,
        "record_type": "controller_input_idm_ego_v1",
        "role": "ego",
        "traffic_protocol": "idm",
        "source_identity": {"binary_sha256": "source-a"},
        "binding": {
            "tool_sha256": {"producer": "tool-a"},
            "binary_sha256": "binary-a",
            "runtime_source_sha256": "runtime-a",
        },
    }
    reasons = fingerprint_mismatches(
        record,
        role="traffic",
        traffic_protocol="hybrid_startup",
        source_identity={"binary_sha256": "source-b"},
        tool_sha256={"producer": "tool-b"},
        binary_sha256="binary-b",
        runtime_source_sha256="runtime-b",
    )
    assert set(reasons) == {
        "idm_record_schema_or_role_mismatch",
        "idm_record_role_stale",
        "idm_record_protocol_stale",
        "idm_record_source_identity_stale",
        "idm_record_tool_fingerprint_stale",
        "idm_record_binary_stale",
        "idm_record_runtime_stale",
    }


def test_new_output_guard_refuses_scene_root_and_existing_records(tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    with pytest.raises(ValueError, match="outside the scene root"):
        _check_new_output(scene, scene / "testing")

    output = tmp_path / "proof"
    output.mkdir()
    (output / "controller_input_idm_ego_v1.json").write_text("{}")
    with pytest.raises(FileExistsError, match="choose a new output directory"):
        _check_new_output(scene, output)
