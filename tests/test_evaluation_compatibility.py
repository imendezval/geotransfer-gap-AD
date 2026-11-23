"""Synthetic contracts for PE12 secondary offline measurements."""

from types import SimpleNamespace

import pytest

from geotransfer_gap.evaluation.compatibility import (
    _core_assessment,
    _measure_reference,
    _traffic_exposure,
    _traffic_gap,
    _traffic_acceleration,
    _traffic_distribution,
    measure_secondary,
)
from geotransfer_gap.evaluation.profile import load_profile


PROFILE = load_profile()
EGO, TRAFFIC = 41, 7


def task_context(positions, valid=None, *, source_id=EGO):
    valid = [True] * len(positions) if valid is None else valid
    return SimpleNamespace(
        status="valid", reason="synthetic hash-checked source reference",
        start_source_step=0, goal_source_step=len(positions) - 1,
        reference_source_id=source_id,
        reference_positions=tuple(positions), reference_valid=tuple(valid),
        reference_source_sha256="a" * 64,
        identity={"source_scene_sha256": "a" * 64, "binary_sha256": "b" * 64},
    )


def actor(source_id, x, *, role="ego", generation=0, owner="ego:ppo", vx=1.0,
          vy=0.0, present=True, source_valid=True):
    return {"id": source_id, "present": present,
            "x": float(x) if present else None, "y": 0.0 if present else None,
            "vx": float(vx) if present else None, "vy": float(vy) if present else None,
            "heading": 0.0 if present else None, "length": 4.5, "width": 1.8,
            "role": role, "lifetime_generation": generation,
            "effective_owner": owner, "source_valid": source_valid}


def frame(step, actors, *, applied=True, time_s=None):
    return {"step": step, "time_s": step / 10 if time_s is None else time_s,
            "transition_applied": applied, "actors": actors}


def report(count, *, requested=None, terminal="horizon", schema=3):
    return {"schema_version": schema, "requested_observation_frames": count if requested is None else requested,
            "terminal_reason": terminal}


def test_reference_deviation_excludes_warmup_and_is_not_a_safety_verdict():
    positions = [(float(step), 0.0) for step in range(91)]
    frames = [frame(step, [actor(EGO, step if step < 10 else step + 2)])
              for step in range(91)]
    result = measure_secondary(
        frames, EGO, report(91), PROFILE, task_context=task_context(positions),
        task_result={"bounded_task_completion": {"outcome": "completed"},
                     "safe_completion": {"outcome": "pass"}},
    )
    result = result["reference_deviation"]
    assert result["warmup_ade"]["value"]["mean"] == pytest.approx(0)
    assert result["ade"]["value"] == pytest.approx(2)
    assert result["fde"]["value"] == pytest.approx(2)
    assert result["coverage"]["expected_primary_observations"] == 81
    assert result["criterion_outcome"] == "not_assessed"
    core = _core_assessment({"bounded_task_completion": {"outcome": "completed"},
                             "safe_completion": {"outcome": "pass"}})
    assert core["criterion_outcome"] == "pass"


def test_partial_reference_coverage_keeps_ade_and_requires_endpoint_for_fde():
    positions = [(float(step), 0.0) for step in range(91)]
    frames = [frame(step, [actor(EGO, step + 1)]) for step in range(20)]
    result = _measure_reference(frames, EGO, report(20, requested=91, terminal="ego_collision"),
                                PROFILE, task_context(positions))
    assert result["ade"]["status"] == "valid"
    assert result["ade"]["value"] == pytest.approx(1)
    assert result["coverage"]["matched_primary_observations"] == 10
    assert result["coverage"]["fraction"] == pytest.approx(10 / 81)
    assert result["fde"]["status"] == "unavailable"
    assert result["fde"]["value"] is None


def test_reference_fde_does_not_slide_past_the_bounded_task_endpoint():
    positions = [(float(step), 0.0) for step in range(91)]
    task = task_context(positions)
    task.goal_source_step = 50
    frames = [frame(step, [actor(EGO, step + 1)]) for step in range(91)]
    result = _measure_reference(frames, EGO, report(91), PROFILE, task)
    assert result["coverage"]["expected_primary_observations"] == 41
    assert result["coverage"]["matched_primary_observations"] == 41
    assert result["ade"]["status"] == "valid"
    assert result["fde"]["status"] == "unavailable"
    assert "outside the source task bounds" in result["fde"]["reason"]


def test_reference_time_grid_and_lifetime_boundaries_are_not_bridged():
    positions = [(float(step), 0.0) for step in range(91)]
    frames = [frame(step, [actor(EGO, step,
                                 generation=1 if step in {5, 15} else 0)],
                    time_s=step / 10 + (0.02 if step == 14 else 0.0))
              for step in range(91)]
    result = _measure_reference(frames, EGO, report(91), PROFILE,
                                task_context(positions))
    assert result["coverage"]["exclusions"]["missing_reference_time_sample"] == 1
    assert result["coverage"]["exclusions"]["lifetime_mismatch"] == 1
    assert result["warmup_coverage"]["exclusions"]["lifetime_mismatch"] == 1
    assert result["fde"]["status"] == "valid"


def test_missing_reference_is_unavailable_and_alternative_path_does_not_fail_core():
    missing = _measure_reference([], EGO, report(0), PROFILE, None)
    assert missing["ade"]["status"] == "unavailable"
    assert missing["ade"]["value"] is None
    core = _core_assessment({
        "bounded_task_completion": {"outcome": "completed"},
        "safe_completion": {"outcome": "pass"},
    })
    assert core["criterion_set"]["id"] == "all_core_v1"
    assert core["criterion_outcome"] == "pass"
    # Reference deviation does not feed this fixed safety/task criterion set.
    assert core["criterion_outcome"] != missing["criterion_outcome"]
    contradictory = task_context([(0.0, 0.0)])
    contradictory.reference_source_id = 99
    invalid = _measure_reference([], EGO, report(0), PROFILE, contradictory)
    assert invalid["status"] == "invalid"
    assert invalid["ade"]["value"] is None


def test_fixed_all_core_set_retains_unknown_criterion():
    result = _core_assessment({
        "bounded_task_completion": {"outcome": "completed"},
        "safe_completion": {"outcome": "not_assessed"},
    })
    assert result["criterion_set"]["required_criteria"] == [
        {"criterion_id": "bounded_task_completion", "source_metric_id": "task.outcome"},
        {"criterion_id": "safe_completion_core_v1", "source_metric_id": "task.safe_completion"},
    ]
    assert result["criterion_outcome"] == "not_assessed"
    assert result["status"] == "unavailable"
    assert result["value"] is None
    failed = _core_assessment({"bounded_task_completion": {"outcome": "failed"}})
    assert failed["criterion_outcome"] == "fail"
    invalid = _core_assessment(
        {"bounded_task_completion": {"outcome": "completed"}},
        [{"metric_id": "task.outcome", "status": "invalid"}],
    )
    assert invalid["criterion_outcome"] == "not_assessed"
    assert invalid["criteria"][0]["status"] == "invalid"


def test_traffic_diagnostics_use_saved_velocity_owner_and_applied_transitions():
    frames = []
    for step in range(13):
        owner = ("warmup_replay" if step < 10 else
                 "source_hold_replay" if step == 10 else "traffic:ppo")
        frames.append(frame(step, [
            actor(EGO, step),
            actor(TRAFFIC, step + 10, role="traffic", owner=owner,
                  vx=float(step), generation=0),
        ]))
    exposure = _traffic_exposure(frames, report(len(frames)), PROFILE, window="primary")
    assert exposure["value"]["source_hold_replay"]["transition_actor_pairs"] == 1
    assert exposure["value"]["learned_controller"]["transition_actor_pairs"] == 1
    assert exposure["coverage"]["complete"] is True
    speed = _traffic_distribution(frames, report(len(frames)), PROFILE,
                                  window="primary", field="speed_m_s")
    assert speed["status"] == "valid"
    assert speed["value"]["mean"] == pytest.approx(11)
    acceleration = _traffic_acceleration(frames, report(len(frames)), PROFILE,
                                         window="primary")
    assert acceleration["status"] == "valid"
    assert acceleration["value"]["mean"] == pytest.approx(10)


def test_traffic_owner_exposure_does_not_infer_missing_legacy_owners():
    frames = [frame(0, [actor(EGO, 0), actor(TRAFFIC, 3, role=None)]),
              frame(1, [actor(EGO, 1), actor(TRAFFIC, 4, role=None)])]
    result = _traffic_exposure(frames, report(2, schema=2), PROFILE, window="full")
    assert result["status"] == "unavailable"
    assert result["value"] is None


def test_gap_diagnostic_reuses_pe04_samples_without_recomputing():
    metrics = [{"metric_id": "safety.footprint_clearance", "window": "primary",
                "status": "valid", "value": {"samples": [
                    {"clearance_m": 2.0}, {"clearance_m": 4.0}],
                    "coverage": {"fraction": 1.0}}}]
    result = _traffic_gap(metrics, "primary")
    assert result["value"]["mean"] == pytest.approx(3)
    assert result["source_metric_id"] == "safety.footprint_clearance"
    unavailable = _traffic_gap([], "primary")
    assert unavailable["status"] == "unavailable" and unavailable["value"] is None


def test_official_benchmark_scores_remain_unavailable_without_required_context():
    result = measure_secondary([], EGO, report(0), PROFILE,
                               task_result={}, safety_metrics=[])
    assert result["benchmark_compatibility"]["behaviorbench"]["wosac_score"]["status"] == "unavailable"
    assert result["benchmark_compatibility"]["behaviorbench"]["fault_classification"]["value"] is None
    assert all(item["status"] == "unavailable"
               for item in result["benchmark_compatibility"]["behaviorbench"][
                   "supported_native_diagnostics"])
    assert result["benchmark_compatibility"]["nuplan_closed_loop"]["value"] is None
    assert result["all_core_pass_rate"]["value"] is None


def test_behaviorbench_native_diagnostics_link_only_existing_p03_metrics():
    native = [{"metric_id": "safety.native_vehicle_collision_onsets", "window": "full",
               "status": "valid", "value": {"observed_onset_count": 1},
               "evidence_refs": [{"kind": "evaluation_capture", "sha256": "c" * 64}]},
              {"metric_id": "safety.native_offroad_onsets", "window": "full",
               "status": "unavailable", "value": None, "evidence_refs": []}]
    result = measure_secondary([], EGO, report(0), PROFILE,
                               task_result={}, safety_metrics=native)
    supported = result["benchmark_compatibility"]["behaviorbench"][
        "supported_native_diagnostics"]
    assert supported[0]["value"] == {"observed_onset_count": 1}
    assert supported[0]["evidence_refs"] == native[0]["evidence_refs"]
    assert supported[1]["status"] == "unavailable" and supported[1]["value"] is None


def test_secondary_import_does_not_load_behaviorbench_or_torch(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "import sys; import geotransfer_gap.evaluation.compatibility; "
        "assert 'torch' not in sys.modules; "
        "assert not any(name.startswith('pufferlib') for name in sys.modules)"
    )
    env = dict(os.environ, GEOTRANSFER_BENCH=str(tmp_path / "missing_behavior_bench"))
    subprocess.run([sys.executable, "-c", code], check=True,
                   cwd=Path(__file__).resolve().parents[1], env=env)
