from copy import deepcopy
from types import SimpleNamespace

import pytest

from geotransfer_gap.evaluation.capture import EvaluationCapture, validate_evaluation_capture
from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.runtime.run_trace import _capture_expected_file


def fixture_capture(collision_state=1, partner_index=2):
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
                       collided_with_index=partner_index, collision_x=2., collision_y=3.,
                       collision_other_x=4., collision_other_y=5.,
                       goal_position_x=1., goal_position_y=2.)
    actors = [
        SimpleNamespace(source_id=sid, fixed_binary_index=i, lifetime_generation=4,
                        native_present=(i != 1), controller_eligible=(i == 1),
                        current_active_slot=i)
        for i, sid in enumerate(ids)
    ]
    snapshot = SimpleNamespace(step=0, actors=(actors[2], actors[1], actors[0]),
                               active_agent_indices=(0, 1, 2))
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
                {"id": 500, "binary_index": 2, "present": True, "collision_state": 0},
                {"id": 1035, "binary_index": 1, "present": False,
                 "collision_state": collision_state},
                {"id": 100, "binary_index": 0, "present": True, "collision_state": 0},
            ]},
            "actors": [
                {"source_id": 500, "binary_index": 2, "lifetime_generation": 4,
                 "slot": 2, "role": "context"},
                {"source_id": 1035, "binary_index": 1, "lifetime_generation": 4,
                 "slot": 1, "role": "ego"},
                {"source_id": 100, "binary_index": 0, "lifetime_generation": 4,
                 "slot": 0, "role": "context"},
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
    assert ego["collision_partner_status"] == "mapped"
    assert ego["native_collision_partner_index"] == 2
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


def test_unmapped_native_partner_is_explicit_unknown_without_a_source_id():
    capture, trace = fixture_capture(partner_index=99)
    saved = capture.build(trace, "b" * 64)
    ego = next(row for row in saved["observations"][0]["actors"] if row["source_id"] == 1035)
    assert ego["collision_partner_status"] == "unmapped_index"
    assert ego["native_collision_partner_index"] == 99
    assert ego["collision_partner_binary_index"] is None
    assert ego["collision_partner_source_id"] is None


def test_goal_counter_is_identity_bound_and_v1_captures_remain_readable():
    capture, trace = fixture_capture()
    # Rebuild with the read-only counter result from the mapped ego slot.
    capture._observations.clear()
    state = {"entities": [
        {"traj_x": [90.0 + i], "traj_y": [180.0 + i], "collision_state": 0,
         "collided_with_index": -1, "collision_x": 0., "collision_y": 0.,
         "collision_other_x": 0., "collision_other_y": 0., "goal_position_x": 0.,
         "goal_position_y": 0., "removed": False, "x": 0.}
        for i in range(3)
    ]}
    state["entities"][1].update(collision_state=1, collided_with_index=2,
                                collision_x=2., collision_y=3.,
                                collision_other_x=4., collision_other_y=5.)
    capture.capture_pre_step(
        SimpleNamespace(step=0, actors=(
            SimpleNamespace(source_id=1035, fixed_binary_index=1, lifetime_generation=4,
                            native_present=False, controller_eligible=True,
                            current_active_slot=1),
            SimpleNamespace(source_id=500, fixed_binary_index=2, lifetime_generation=4,
                            native_present=True, controller_eligible=False,
                            current_active_slot=2),
            SimpleNamespace(source_id=100, fixed_binary_index=0, lifetime_generation=4,
                            native_present=True, controller_eligible=False,
                            current_active_slot=0),
        ), active_agent_indices=(0, 1, 2)),
        state,
        goal_counter={"status": "observed", "slot": 1,
                      "slot_mapping_verified": True, "value": 0.0, "reason": None},
    )
    saved = capture.build(trace, "b" * 64)
    assert validate_evaluation_capture(saved, trace, "b" * 64)
    fractional = deepcopy(saved)
    fractional["observations"][0]["ego_goal_counter"]["value"] = 0.5
    with pytest.raises(ValueError, match="fractional"):
        validate_evaluation_capture(fractional, trace, "b" * 64)
    corrupted = deepcopy(saved)
    corrupted["observations"][0]["ego_goal_counter"]["slot"] = 0
    with pytest.raises(ValueError, match="slot/eligibility differs"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)
    corrupted = deepcopy(saved)
    corrupted["observations"][0]["ego_goal_counter"]["lifetime_generation"] = 5
    with pytest.raises(ValueError, match="actor identity differs"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)

    legacy = deepcopy(saved)
    legacy["schema_version"] = 1
    legacy["observations"][0].pop("ego_goal_counter")
    assert validate_evaluation_capture(legacy, trace, "b" * 64)


def test_goal_remove_counter_rejects_more_than_one_event_per_applied_transition():
    capture, trace = fixture_capture()
    first = capture._observations[0]
    first["ego_goal_counter"].update(
        status="observed", slot=1, slot_mapping_verified=True,
        controller_eligible=True, value=0.0, reason=None,
    )
    second = deepcopy(first)
    second["step"] = 1
    second["ego_goal_counter"]["value"] = 2.0
    capture._observations.append(second)

    trace["requested_observation_frames"] = 2
    trace["observation_frames"] = 2
    trace["transitions"] = 1
    trace["frames"][0]["transition_applied"] = True
    final_frame = deepcopy(trace["frames"][0])
    final_frame["step"] = 1
    final_frame["state"]["step"] = 1
    final_frame["transition_applied"] = False
    trace["frames"].append(final_frame)

    with pytest.raises(ValueError, match="exceeds one GOAL_REMOVE event"):
        capture.build(trace, "b" * 64)


def test_capture_collision_state_and_native_settings_must_match_canonical_evidence():
    capture, trace = fixture_capture()
    saved = capture.build(trace, "b" * 64)
    corrupted = deepcopy(saved)
    ego = next(row for row in corrupted["observations"][0]["actors"] if row["source_id"] == 1035)
    ego["collision_state"] = 0
    with pytest.raises(ValueError, match="collision state"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)
    recorded = {"native": deepcopy(saved["native_settings"])}
    corrupted = deepcopy(saved)
    corrupted["native_settings"]["goal_behavior"] = 4
    with pytest.raises(ValueError, match="differ from verification"):
        validate_evaluation_capture(corrupted, trace, "b" * 64, verification=recorded)
    corrupted = deepcopy(saved)
    corrupted["native_settings"]["invented_setting"] = 1
    with pytest.raises(ValueError, match="native settings"):
        validate_evaluation_capture(corrupted, trace, "b" * 64)


def test_parent_requires_and_hashes_capture_only_when_requested(tmp_path):
    capture, trace = fixture_capture()
    trace_path = tmp_path / "trace.json"
    write_json(trace_path, trace)
    assert _capture_expected_file(tmp_path, {}, trace) == {}
    with pytest.raises(FileNotFoundError):
        _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace)

    saved = capture.build(trace, sha256(trace_path))
    write_json(tmp_path / "evaluation_capture.json", saved)
    provenance = {"native": deepcopy(saved["native_settings"])}
    assert _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace, provenance) == {
        "evaluation_capture": "evaluation_capture.json",
    }
    mismatched_provenance = {"native": {**provenance["native"], "goal_behavior": 4}}
    with pytest.raises(ValueError, match="differ from verification"):
        _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace,
                               mismatched_provenance)
    saved["ego_controller"] = "ppo"
    write_json(tmp_path / "evaluation_capture.json", saved)
    with pytest.raises(ValueError, match="identity or protocol"):
        _capture_expected_file(tmp_path, {"capture_evaluation": True}, trace)
