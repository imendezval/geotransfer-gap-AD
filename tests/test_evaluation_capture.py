from copy import deepcopy
from types import SimpleNamespace

import pytest

from geotransfer_gap.evaluation.capture import EvaluationCapture, validate_evaluation_capture
from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.runtime.run_trace import _capture_expected_file


def fixture_capture(collision_state=1):
    ids = [100, 1035, 500]
    binary = {
        "objects": [
            {"id": sid, "traj_valid": [1], "traj_x": [100.0 + i], "traj_y": [200.0 + i]}
            for i, sid in enumerate(ids)
        ],
        "sdc_track_index": 1,
    }
    entities = [
        {"traj_x": [90.0 + i], "traj_y": [180.0 + i], "collision_state": 0,
         "collided_with_index": -1, "collision_x": 0., "collision_y": 0.,
         "collision_other_x": 0., "collision_other_y": 0., "goal_position_x": 0.,
         "goal_position_y": 0., "removed": False, "x": 0.}
        for i in range(3)
    ]
    # The ego has no canonical terminal pose, but the detector has retained
    # the collision flag and copied center fields at this observation.
    entities[1].update(removed=True, x=-10000., collision_state=collision_state,
                       collided_with_index=2, collision_x=2., collision_y=3.,
                       collision_other_x=4., collision_other_y=5.,
                       goal_position_x=1., goal_position_y=2.)
    actors = [
        SimpleNamespace(source_id=sid, fixed_binary_index=i, lifetime_generation=4,
                        native_present=(i != 1), controller_eligible=True)
        for i, sid in enumerate(ids)
    ]
    snapshot = SimpleNamespace(step=0, actors=(actors[2], actors[1], actors[0]))
    capture = EvaluationCapture(binary, {
        "dynamics_model": "classic", "action_type_flag": 1, "episode_length": 91,
        "observation_width": 1151, "goal_behavior": 3,
    })
    capture.capture_pre_step(snapshot, {"entities": entities})
    trace = {
        "schema_version": 3, "planner": "controller_matrix",
        "scene": {"root": "artifacts", "path": "synthetic"},
        "binary_sha256": "a" * 64, "ego_binary_index": 1,
        "ego_controller": "smart", "traffic_controller": "idm",
        "traffic_startup": "immediate", "steps_semantics": "observation_frames",
        "requested_observation_frames": 1, "observation_frames": 1,
        "terminal_reason": "ego_collision",
        "frames": [{
            "step": 0, "transition_applied": False,
            "state": {"step": 0, "actors": [
                {"id": 500, "binary_index": 2, "present": True},
                {"id": 1035, "binary_index": 1, "present": False},
                {"id": 100, "binary_index": 0, "present": True},
            ]},
            "actors": [
                {"source_id": 500, "binary_index": 2, "lifetime_generation": 4},
                {"source_id": 1035, "binary_index": 1, "lifetime_generation": 4},
                {"source_id": 100, "binary_index": 0, "lifetime_generation": 4},
            ],
        }],
    }
    return capture, trace


def test_terminal_collision_maps_nonzero_ego_and_transforms_detector_centers():
    capture, trace = fixture_capture()
    saved = capture.build(trace, "b" * 64)
    assert validate_evaluation_capture(saved, trace, "b" * 64)
    assert saved["ego_source_id"] == 1035
    rows = {row["source_id"]: row for row in saved["observations"][0]["actors"]}
    ego = rows[1035]
    assert ego["binary_index"] == 1 and ego["lifetime_generation"] == 4
    assert ego["collision_partner_binary_index"] == 2
    assert ego["collision_partner_source_id"] == 500
    assert ego["collision_center_world_xy"] == [12., 23.]
    assert ego["partner_center_world_xy"] == [14., 25.]
    assert ego["navigation_goal_world_xy"] is None  # absent terminal pose


def test_capture_rejects_stale_trace_hash_partner_identity_and_nonfinite_centers():
    capture, trace = fixture_capture()
    saved = capture.build(trace, "b" * 64)
    with pytest.raises(ValueError, match="identity or protocol"):
        validate_evaluation_capture(saved, trace, "c" * 64)
    corrupted = deepcopy(saved)
    ego = next(row for row in corrupted["observations"][0]["actors"] if row["source_id"] == 1035)
    ego["collision_partner_source_id"] = 100
    with pytest.raises(ValueError, match="partner identity"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)
    corrupted = deepcopy(saved)
    ego = next(row for row in corrupted["observations"][0]["actors"] if row["source_id"] == 1035)
    ego["collision_center_world_xy"][0] = float("inf")
    with pytest.raises(ValueError, match="nonfinite number"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)


def test_offroad_flag_does_not_reuse_stale_vehicle_collision_fields():
    capture, trace = fixture_capture(collision_state=2)
    saved = capture.build(trace, "b" * 64)
    ego = next(row for row in saved["observations"][0]["actors"] if row["source_id"] == 1035)
    assert ego["collision_state"] == 2
    assert ego["collision_partner_binary_index"] is None
    assert ego["collision_partner_source_id"] is None
    assert ego["collision_center_world_xy"] is None
    assert ego["partner_center_world_xy"] is None


def test_parent_requires_and_hashes_capture_only_when_requested(tmp_path):
    capture, trace = fixture_capture()
    trace_path = tmp_path / "trace.json"
    write_json(trace_path, trace)
    assert _capture_expected_file(tmp_path, {}, trace) == {}
    with pytest.raises(FileNotFoundError):
        _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace)

    saved = capture.build(trace, sha256(trace_path))
    write_json(tmp_path / "evaluation_capture.json", saved)
    assert _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace) == {
        "evaluation_capture": "evaluation_capture.json",
    }
    saved["ego_controller"] = "ppo"
    write_json(tmp_path / "evaluation_capture.json", saved)
    with pytest.raises(ValueError, match="identity or protocol"):
        _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace)
