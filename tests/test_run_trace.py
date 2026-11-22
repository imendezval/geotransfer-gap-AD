from copy import deepcopy

import pytest

from geotransfer_gap.runtime.run_trace import compare, validate_trace, validate_models, validate_claims


def trace():
    actors = [
        {"source_id": 41, "binary_index": 0, "lifetime_generation": 0, "slot": 0,
         "role": "ego", "declared_controller": "expert", "effective_owner": "warmup_replay",
         "pre_step_native_movement_mode": 2, "planned_movement_mode": 2,
         "applied_movement_mode": 2, "action": [0., 0.], "intent": "replay"},
        {"source_id": 2, "binary_index": 1, "lifetime_generation": 0, "slot": None,
         "role": "context", "declared_controller": None, "effective_owner": "context_replay",
         "pre_step_native_movement_mode": 0, "planned_movement_mode": None,
         "applied_movement_mode": None, "action": None, "intent": None},
    ]
    frames = []
    for step in range(2):
        assignments = deepcopy(actors)
        if step == 1:
            for actor in assignments:
                actor.update(planned_movement_mode=None, applied_movement_mode=None,
                             action=None, intent=None)
        frames.append({
            "step": step, "transition_applied": step == 0, "actors": assignments,
            "state": {"step": step, "actors": [
                {"id": actor["source_id"], "binary_index": actor["binary_index"],
                 "movement_mode": actor["pre_step_native_movement_mode"],
                 "present": True, "collision_state": 0, "removed": False, "x": 1.}
                for actor in assignments
            ]},
        })
    return {
        "schema_version": 3, "planner": "controller_matrix",
        "scene": {"root": "artifacts", "path": "fixture"},
        "ego_controller": "expert", "traffic_controller": "expert",
        "traffic_startup": "immediate", "warmup_replay_frames": 10,
        "steps_semantics": "observation_frames",
        "observation_frames": 2, "requested_observation_frames": 2, "transitions": 1,
        "ego_binary_index": 0, "frames": frames, "terminal_reason": "horizon",
    }


def test_exact_canonical_comparison_normalizes_identity_order_but_reports_action_difference():
    base = trace()
    reordered = deepcopy(base)
    for frame in reordered["frames"]:
        frame["actors"].reverse()
        frame["state"]["actors"].reverse()
    assert compare({"trace": base}, {"trace": reordered}) is None
    reordered["frames"][0]["actors"][1]["action"][0] = 1e-16
    assert compare({"trace": base}, {"trace": reordered}) == {
        "scene": base["scene"], "ego": "expert", "traffic": "expert", "startup": "immediate",
        "tick": 0, "source_id": 41, "lifetime": 0, "field": "trace.frames.actors.action[0]",
        "expected": 0., "actual": 1e-16,
    }


def test_missing_mode_and_incomplete_trace_fail():
    broken = trace()
    broken["frames"][0]["actors"][0].pop("applied_movement_mode")
    with pytest.raises(ValueError, match="mode"):
        validate_trace(broken)
    broken = trace()
    broken["frames"].pop()
    with pytest.raises(ValueError, match="observation"):
        validate_trace(broken)


def test_native_mode_persistence_checks_only_same_present_lifetime():
    broken = trace()
    end = broken["frames"][1]
    end["actors"][0]["pre_step_native_movement_mode"] = 0
    end["state"]["actors"][0]["movement_mode"] = 0
    with pytest.raises(ValueError, match="persist"):
        validate_trace(broken)
    end["actors"][0]["lifetime_generation"] = 1
    validate_trace(broken)


def test_missing_or_invalid_model_provenance_and_admission_claims_fail(tmp_path):
    for model in ("ppo", "smart"):
        with pytest.raises(ValueError, match=f"{model} provenance"):
            validate_models(tmp_path, model, "expert")
    with pytest.raises(ValueError, match="hash"):
        validate_models(tmp_path, "ppo", "expert", models={"ppo": {"checkpoint_sha256": "invalid"}})
    with pytest.raises(ValueError, match="admission"):
        validate_claims({"diagnostic_only": True, "controller_pair_research_admission": "admitted",
                         "task_preservation": "not_assessed"})
    with pytest.raises(ValueError, match="admission"):
        validate_claims({"diagnostic_only": True, "controller_pair_research_admission": "not_established",
                         "task_preservation": "not_assessed",
                         "original_source_admission": {"status": "recorded"}})


def test_native_state_mismatch_identifies_lifetime():
    expected = trace()
    actual = deepcopy(expected)
    actual["frames"][1]["state"]["actors"][0]["x"] += 1
    mismatch = compare({"trace": expected}, {"trace": actual})
    assert mismatch["source_id"] == 41 and mismatch["lifetime"] == 0
    assert mismatch["tick"] == 1 and mismatch["field"] == "trace.frames.state.actors.x"
