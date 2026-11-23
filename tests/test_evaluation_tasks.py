"""Synthetic route/task/efficiency cases without simulator or dataset access."""

import json
import math

import pytest
from types import SimpleNamespace

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.evaluation.context import TaskContext
from geotransfer_gap.evaluation import context as context_module
from geotransfer_gap.evaluation.kinematics import measure_kinematics
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.evaluation.tasks import (
    _safe_completion,
    finalize_safe_completion,
    measure_tasks,
)
from geotransfer_gap.evaluation import tasks as task_module


EGO = 41
PROFILE = load_profile()


def actor(step, x, y=0.0, *, speed=1.0, present=True, goal=False,
          collision=0, source_valid=True, generation=0):
    if isinstance(x, (tuple, list)):
        x, y = x
    return {
        "id": EGO, "binary_index": 1, "present": present,
        "x": float(x) if present else None, "y": float(y) if present else None,
        "vx": float(speed), "vy": 0.0, "heading": 0.0,
        "length": 4.5, "width": 1.8,
        "lifetime_generation": generation, "source_valid": source_valid,
        "effective_owner": "ego:ppo", "collision_state": collision,
        "reached_goal": goal,
    }


def task_for(points, *, goal=None, radius=0.5, deadline=None,
             route_status="valid", span=None):
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    return TaskContext(
        status="valid", reason="synthetic bound source task", scene_id="synthetic",
        start_source_step=0, goal_source_step=max(0, len(points) - 1),
        goal_xy=goal or points[-1], completion_radius_m=radius,
        deadline_s=deadline, reference_points=tuple(points),
        route_status=route_status,
        route_reason="synthetic validated route" if route_status == "valid" else "route unavailable",
        route_span_m=length if span is None else span,
        identity={"scene_id": "synthetic", "manifest_sha256": "a" * 64},
    )


def run(frames, task, *, planner="ppo", terminal="horizon", requested=None,
        evaluation_capture=None, evaluation_capture_bound=False):
    profile = PROFILE
    for index, frame in enumerate(frames):
        frame.update(step=index, time_s=index / 10,
                     transition_applied=index < len(frames) - 1)
    report = {
        "schema_version": 3, "planner": "controller_matrix", "ego_controller": planner,
        "ego_binary_index": 1, "ego_source_id": EGO,
        "binary_sha256": "b" * 64, "scene": {"root": "artifacts", "path": "synthetic"},
        "requested_observation_frames": requested or len(frames),
        "terminal_reason": terminal,
    }
    measured = measure_kinematics(frames, EGO, report, profile)
    result = measure_tasks(frames, EGO, report, profile, measured["exposure"],
                           measured["events"], task,
                           evaluation_capture=evaluation_capture,
                           evaluation_capture_bound=evaluation_capture_bound)
    return result, measured


def native_goal_capture(count, goal=(3.0, 0.0), *, ego_id=EGO, binary_index=1):
    return {
        "schema_version": 1, "ego_source_id": ego_id, "ego_binary_index": binary_index,
        "binary_sha256": "b" * 64, "scene": {"root": "artifacts", "path": "synthetic"},
        "observations": [{
            "step": step,
            "actors": [{"source_id": ego_id, "binary_index": binary_index,
                        "navigation_goal_world_xy": list(goal)}],
        } for step in range(count)],
    }


def frames(xs, *, ys=None, speeds=None, goals=(), collisions=(), missing_collision=(),
           terminal_missing=False):
    ys = ys or [0.0] * len(xs)
    speeds = speeds or [1.0] * len(xs)
    rows = []
    for index, (x, y, speed) in enumerate(zip(xs, ys, speeds)):
        row = actor(index, x, y, speed=speed, goal=index in goals,
                    collision=1 if index in collisions else 0)
        if index in missing_collision:
            row.pop("collision_state")
        rows.append({"actors": [row]})
    if terminal_missing:
        final = dict(rows[-1]["actors"][0], present=False, x=None, y=None,
                     goal=True, collision_state=0)
        rows[-1]["actors"] = [final]
    return rows


def get_metric(result, metric_id, window="full"):
    return next(metric for metric in result["metrics"]
                if metric["metric_id"] == metric_id and metric["window"] == window)


def _safe_fixture():
    safe = _safe_completion("completed", [], {
        "event_observation_coverage": {"windows": {"full": {"channels": {
            "collision_state": {"fraction": 1.0},
        }}}},
    })
    return {"task": {"safe_completion": safe,
                     "bounded_task_completion": {"outcome": "completed"}},
            "metrics": [{"metric_id": "task.safe_completion", "status": "unavailable",
                         "value": None, "criterion_outcome": "not_assessed"}]}


def _safe_claim(claim_type, decision):
    return {"claim": {"claim_id": f"safe-{claim_type}-{len(str(decision))}",
                       "claim_type": claim_type, "decision_status": "supported",
                       "scope": {"target": "synthetic primary episode"},
                       "decision": decision,
                       "evidence_refs": [{"sha256": "a" * 64}],
                       "review": {"status": "reviewed"}},
            "selected_evidence": [dict(decision)]}


def _signal_exemption():
    return _safe_claim("rule_applicability", {
        "rule": "traffic_signal", "applicability": "not_applicable",
        "approach_lanelet_ids": [7], "valid_step_range": [10, 90],
        "reason": "Reviewed map evidence shows no signal control on the actual route",
    })


def _signal_lane_samples():
    return [{"step": step, "status": "valid", "lanelet_ids": [7]}
            for step in range(91)]


def _finalize_fixture(task, claims=(), *, map_metrics=(), interactions=(), semantics=None):
    semantics = semantics or {"criteria": {}, "capabilities": {
        "traffic_signal": {"status": "unavailable"}}}
    return finalize_safe_completion(
        task, annotation={"status": "valid", "claims_data": list(claims)},
        map_metrics=list(map_metrics),
        interactions={"interactions": list(interactions)}, semantics=semantics,
        lane_assignment_samples=_signal_lane_samples(), profile=PROFILE,
    )


def test_safe_completion_passes_native_task_and_reviewed_signal_exemption_only():
    task = _safe_fixture()
    diagnostic_failure = {"wrong_way": {"criterion_outcome": "fail",
                                        "status": "valid"}}
    safe = _finalize_fixture(task, [_signal_exemption()], semantics={
        "criteria": diagnostic_failure,
        "capabilities": {"traffic_signal": {"status": "unavailable"}},
    })
    assert safe["outcome"] == "pass"
    assert safe["criteria"]["traffic_signal_applicability"]["outcome"] == "pass"
    assert task["metrics"][0]["criterion_outcome"] == "pass"
    unresolved = _finalize_fixture(_safe_fixture())
    assert unresolved["outcome"] == "not_assessed"
    assert unresolved["criteria"]["traffic_signal_applicability"]["outcome"] == "not_assessed"


def test_applicable_critical_map_boundary_violation_fails_safe_completion():
    task = _safe_fixture()
    map_criterion = _safe_claim("physical_map_coverage", {
        "criterion": "map_footprint_boundary", "applicability": "applicable",
        "safe_completion_critical": True,
    })
    safe = _finalize_fixture(task, [_signal_exemption(), map_criterion], map_metrics=[{
        "metric_id": "safety.map_footprint_outside", "window": "primary",
        "status": "valid", "value": {
            "outside_observation_count": 1,
            "coverage": {"complete_for_selected_window": False},
        },
    }])
    assert safe["outcome"] == "fail"
    assert safe["criteria"]["designated_critical_criteria"]["outcome"] == "fail"


def test_unresolved_critical_rule_and_encounter_remain_not_assessed():
    task = _safe_fixture()
    rule = _safe_claim("rule_applicability", {
        "rule": "speed_limit", "applicability": "applicable",
        "approach_lanelet_ids": [7], "limit_kmh": 36.0,
        "valid_step_range": [10, 90], "safe_completion_critical": True,
    })
    encounter = _safe_claim("interaction_criterion", {
        "criterion": "yielding_compliance", "applicability": "applicable",
        "family": "cyclist_crossing",
        "subtype": "cyclist_crossing_before_ego", "source_actor_ids": [99],
        "safe_completion_critical": True,
    })
    safe = _finalize_fixture(task, [_signal_exemption(), rule, encounter],
                             interactions=[{
                                 "family": "cyclist_crossing",
                                 "subtype": "cyclist_crossing_before_ego",
                                 "source_actor_ids": [99],
                                 "interaction_outcome": "unresolved",
                                 "reason": "Conflict region exit is censored",
                                 "measurement": {"actors": [{
                                     "actor_id": 99,
                                     "yielding_compliance": {
                                         "status": "unavailable",
                                         "outcome": "not_assessed",
                                     },
                                 }]},
                             }], semantics={
                                 "criteria": {"speed_limit": {
                                     "status": "unavailable",
                                     "criterion_outcome": "not_assessed",
                                     "reason": "Coverage is incomplete",
                                 }},
                                 "capabilities": {"traffic_signal": {"status": "unavailable"}},
                             })
    assert safe["outcome"] == "not_assessed"
    rows = safe["criteria"]["designated_critical_criteria"]["criteria"]
    assert [row["outcome"] for row in rows] == ["not_assessed", "not_assessed"]


def source_task_scene(tmp_path, monkeypatch, *, object_ids=(99, 57), manifest_ego=(57, 1),
                      contract_ego=(57, 1), scene_name="synthetic_scene"):
    scene_root = tmp_path / "scene"
    testing = scene_root / "testing"
    testing.mkdir(parents=True)
    binary = testing / "map_000000.bin"
    binary.write_bytes(b"synthetic scene binary")
    manifest = tmp_path / "current.json"
    manifest.write_text("{}\n")
    goal = {"x": 2.0, "y": 0.0}
    objects = []
    for source_id in object_ids:
        objects.append({"id": source_id, "position": [{"x": 0.0, "y": 0.0},
                                                         {"x": 1.0, "y": 0.0},
                                                         {"x": 2.0, "y": 0.0}],
                        "valid": [1, 1, 1], "goalPosition": goal})
    scene_path = testing / "ind_synthetic.json"
    write_json(scene_path, {"name": scene_name, "objects": objects})
    validation_path = testing / "validation.json"
    write_json(validation_path, {"binary_sha256": sha256(binary), "recording": 7,
                                 "location": 1, "ego_track": 57, "first_frame": 100,
                                 "ego_goal_sample": 2, "ego_goal": goal})
    write_json(testing / "evaluation_contract_expert.json", {
        "schema_version": 2, "scene_root": str(scene_root), "recording": 7,
        "ego_track_id": contract_ego[0], "ego_binary_index": contract_ego[1],
        "goal_sample": 2, "goal_position": goal,
        "files": {"scene_json": {"sha256": sha256(scene_path)},
                  "scene_binary": {"sha256": sha256(binary)}},
    })
    row = {"name": "synthetic_scene", "recording": 7, "location": 1,
           "ego_track_id": manifest_ego[0], "ego_binary_index": manifest_ego[1],
           "first_frame": 100, "binary_sha256": sha256(binary)}
    monkeypatch.setattr(context_module, "_manifest_scene",
                        lambda root, digest: (row, manifest, None))
    return scene_root, binary


def test_forward_and_reverse_report_signed_net_route_progress():
    route = [(float(i), 0.0) for i in range(21)]
    forward, _ = run(frames([i * 0.5 for i in range(12)]), task_for(route))
    reverse, _ = run(frames([10.0 - i * 0.5 for i in range(12)]), task_for(route))
    assert get_metric(forward, "trajectory.route_progress")["value"]["net_progress_m"] == pytest.approx(5.5)
    assert get_metric(reverse, "trajectory.route_progress")["value"]["net_progress_m"] == pytest.approx(-5.5)
    normalized = get_metric(reverse, "trajectory.normalized_route_progress")["value"]
    assert normalized["raw_normalized_progress"] == pytest.approx(-0.275)
    assert normalized["display_fraction_clipped"] == 0.0


def test_intersecting_route_is_ambiguous_without_continuity_anchor():
    route = [(0, 0), (4, 4), (0, 4), (4, 0)]
    result, _ = run(frames([(2, 2), (2.1, 2.1), (2.2, 2.2)]), task_for(route))
    metric = get_metric(result, "trajectory.route_progress")
    assert metric["status"] == "unavailable"
    assert result["task"]["route_progress"]["windows"]["full"]["branch_ambiguity"] is True


def test_task_context_resolves_nonzero_ego_by_manifest_and_binary_identity(tmp_path, monkeypatch):
    scene_root, binary = source_task_scene(tmp_path, monkeypatch)
    task = context_module.build_task_context(
        scene_root, sha256(binary), 57, expected_ego_binary_index=1,
    )
    assert task.status == "valid"
    assert task.goal_source_step == 2
    assert task.goal_xy == (2.0, 0.0)


def test_task_context_accepts_only_converter_name_derived_from_bound_identity(
        tmp_path, monkeypatch):
    expected = "ind_07_track_57_frame_100"
    scene_root, binary = source_task_scene(
        tmp_path, monkeypatch, scene_name=expected)
    task = context_module.build_task_context(
        scene_root, sha256(binary), 57, expected_ego_binary_index=1,
    )
    assert task.status == "valid", task.reason
    assert task.scene_id == "synthetic_scene"

    conflicting_root, conflicting_binary = source_task_scene(
        tmp_path / "conflict", monkeypatch, scene_name="ind_07_track_58_frame_100")
    rejected = context_module.build_task_context(
        conflicting_root, sha256(conflicting_binary), 57, expected_ego_binary_index=1,
    )
    assert rejected.status == "invalid"
    assert "scene name differs" in rejected.reason


@pytest.mark.parametrize("object_ids,manifest_ego,contract_ego", [
    ((57, 57), (57, 1), (57, 1)),
    ((99, 57), (99, 1), (57, 1)),
    ((99, 57), (57, 0), (57, 1)),
    ((99, 57), (57, 1), (57, 0)),
])
def test_task_context_rejects_duplicate_or_contradictory_ego_identity(
        tmp_path, monkeypatch, object_ids, manifest_ego, contract_ego):
    scene_root, binary = source_task_scene(
        tmp_path, monkeypatch, object_ids=object_ids,
        manifest_ego=manifest_ego, contract_ego=contract_ego,
    )
    task = context_module.build_task_context(
        scene_root, sha256(binary), 57, expected_ego_binary_index=1,
    )
    assert task.status == "invalid"


@pytest.mark.parametrize("route_status,span", [("unavailable", None), ("valid", 0.0)])
def test_missing_or_zero_task_span_never_becomes_normalized_zero(route_status, span):
    task = task_for([(0, 0), (0, 0)], route_status=route_status, span=span)
    result, _ = run(frames([0.0, 0.0, 0.0]), task)
    metric = get_metric(result, "trajectory.normalized_route_progress")
    assert metric["status"] == "unavailable"
    assert metric["value"] is None


def test_positive_polyline_with_missing_validated_span_keeps_normalized_value_unavailable():
    task = task_for([(0, 0), (10, 0)], route_status="valid", span=0.0)
    result, _ = run(frames([0, 1, 2]), task)
    assert get_metric(result, "trajectory.route_progress")["status"] == "valid"
    normalized = get_metric(result, "trajectory.normalized_route_progress")
    assert normalized["status"] == "unavailable"
    assert normalized["value"] is None


def test_source_goal_completion_does_not_claim_encounter_completion():
    task = task_for([(0, 0), (1, 0), (2, 0), (3, 0)])
    result, _ = run(frames([0, 1, 2, 3], goals={3}), task)
    assert result["task"]["native_goal_event"]["observed"] is True
    assert result["task"]["bounded_task_completion"]["outcome"] == "completed"
    assert result["task"]["encounter_completion"]["outcome"] == "not_assessed"


def test_geometric_task_completion_is_independent_of_native_goal_flag():
    task = task_for([(0, 0), (1, 0), (2, 0), (3, 0)])
    result, _ = run(frames([0, 1, 2, 3]), task)
    assert result["task"]["native_goal_event"]["observed"] is False
    assert result["task"]["bounded_task_completion"]["outcome"] == "completed"
    assert result["task"]["bounded_task_completion"]["completion_basis"] == (
        "observed_position_within_validated_source_goal_radius")


def test_horizon_without_task_resolution_is_unresolved_not_failed():
    task = task_for([(float(i * 10), 0) for i in range(11)])
    result, _ = run(frames([0, 0.1, 0.2, 0.3]), task,
                    terminal="horizon", requested=4)
    assert result["task"]["terminal"]["timeout_status"] == "observed"
    assert result["task"]["bounded_task_completion"]["outcome"] == "unresolved"
    assert get_metric(result, "task.outcome")["value"]["outcome"] == "unresolved"


def test_only_an_explicit_deadline_can_make_incomplete_task_fail():
    task = task_for([(float(i * 10), 0) for i in range(11)], deadline=0.5)
    short, _ = run(frames([0, 0.1, 0.2, 0.3]), task, requested=4)
    beyond, _ = run(frames([0, 0.1, 0.2, 0.3, 0.4, 0.5]), task, requested=6)
    assert short["task"]["bounded_task_completion"]["outcome"] == "unresolved"
    assert beyond["task"]["bounded_task_completion"]["outcome"] == "failed"


def test_observation_gap_censors_explicit_deadline_failure():
    task = task_for([(float(i * 10), 0) for i in range(11)], deadline=0.5)
    trace_frames = frames([0, 0.1, 0.2, 0.3, 0.4, 0.5])
    trace_frames[3]["actors"][0].update(present=False, x=None, y=None)
    result, _ = run(trace_frames, task, requested=6)
    assert result["task"]["bounded_task_completion"]["outcome"] == "unresolved"
    assert result["task"]["deadline_assessment"]["supported"] is False
    assert "censors" in result["task"]["deadline_assessment"]["reason"]


def test_completion_after_explicit_deadline_is_failure_with_continuous_coverage():
    task = task_for([(0, 0), (1, 0), (2, 0), (3, 0)], radius=0.2, deadline=0.5)
    result, _ = run(frames([0, 0.5, 1, 1.5, 2, 2.5, 3]), task, requested=7)
    assert result["task"]["bounded_task_completion"]["completion"]["time_s"] == pytest.approx(0.6)
    assert result["task"]["bounded_task_completion"]["outcome"] == "failed"
    assert result["task"]["deadline_assessment"]["supported"] is True
    assert result["task"]["deadline_assessment"]["late_completion_elapsed_s"] == pytest.approx(0.6)


def test_stationary_wait_is_candidate_only_and_restart_remains_observed():
    xs = [0.0] * 31 + [float(i) for i in range(1, 12)]
    speeds = [0.0] * 30 + [1.0] * 12
    route = [(float(i), 0.0) for i in range(21)]
    trace_frames = frames(xs, speeds=speeds)
    for index, frame in enumerate(trace_frames):
        leader_x = 6.0 if index <= 30 else 6.0 + index - 30
        frame["actors"].append({
            "id": 88, "binary_index": 0, "present": True,
            "x": leader_x, "y": 0.0, "vx": 0.0 if index <= 30 else 1.0,
            "vy": 0.0, "heading": 0.0, "length": 4.5, "width": 1.8,
            "lifetime_generation": 0, "source_valid": True,
            "effective_owner": "traffic:expert",
        })
    result, _ = run(trace_frames, task_for(route))
    stationary = get_metric(result, "efficiency.stationary_duration")["value"]
    assert stationary["duration_s"] == pytest.approx(3.0)
    low = get_metric(result, "efficiency.low_progress_candidate")["value"]
    assert low["candidate"] is True
    assert low["confirmed_deadlock"] is False
    assert low["stalling_assessment"] == "not_assessed"
    assert any(row["signed_route_advance_m"] == pytest.approx(0.0)
               for row in low["candidates"])
    assert trace_frames[0]["actors"][1]["vx"] == 0.0
    assert trace_frames[31]["actors"][0]["x"] > trace_frames[30]["actors"][0]["x"]
    assert trace_frames[31]["actors"][1]["vx"] == 1.0
    assert result["task"]["bounded_task_completion"]["outcome"] == "unresolved"


def test_native_goal_terminal_without_pose_preserves_completion_event():
    task = task_for([(float(i), 0.0) for i in range(5)])
    trace = frames([0, 1, 2, 3], goals={3}, terminal_missing=True)
    result, _ = run(frames([0, 1, 2, 3], goals={3}, terminal_missing=True), task,
                    terminal="ego_removed", requested=8,
                    evaluation_capture=native_goal_capture(len(trace), goal=(4.0, 0.0)),
                    evaluation_capture_bound=True)
    task_result = result["task"]
    assert task_result["native_goal_event"]["step"] == 3
    assert task_result["bounded_task_completion"]["outcome"] == "completed"
    assert task_result["bounded_task_completion"]["completion_basis"] == "matched_native_goal_event"
    assert task_result["native_goal_event"]["task_goal_binding"]["matches"] is True
    assert task_result["terminal"]["truncation_status"] == "observed_before_requested_horizon"


def test_unbound_or_contradictory_native_goal_does_not_complete_source_task():
    task = task_for([(0, 0), (1, 0), (2, 0), (3, 0)])
    trace = frames([0.0, 0.5, 1.0, 1.5], goals={3})
    unbound, _ = run([dict(frame, actors=[dict(frame["actors"][0])]) for frame in trace], task)
    contradictory, _ = run([dict(frame, actors=[dict(frame["actors"][0])]) for frame in trace], task,
                           evaluation_capture=native_goal_capture(len(trace), goal=(9.0, 0.0)),
                           evaluation_capture_bound=True)
    assert unbound["task"]["native_goal_event"]["observed"] is True
    assert unbound["task"]["bounded_task_completion"]["outcome"] == "unresolved"
    assert contradictory["task"]["native_goal_event"]["task_goal_binding"]["matches"] is False
    assert contradictory["task"]["bounded_task_completion"]["outcome"] == "unresolved"


def test_smart_branch_ambiguity_and_goal_visibility_are_reported_separately():
    route = [(0, 0), (4, 4), (0, 4), (4, 0)]
    result, _ = run(frames([(2, 2), (2.1, 2.1), (2.2, 2.2)]),
                    task_for(route), planner="smart")
    assert result["task"]["planner_goal_visibility"] == {
        "status": "known", "value": False,
        "reason": "The inspected SMART input path has no simulator navigation-goal input",
    }
    assert result["task"]["branch_context"]["ambiguous"] is True
    assert "cannot alone establish" in result["task"]["branch_context"][
        "smart_goal_visibility_limitation"]


def test_missing_critical_safety_coverage_prevents_safe_completion_pass():
    task = task_for([(float(i), 0.0) for i in range(4)])
    result, _ = run(frames([0, 1, 2, 3], goals={3}, missing_collision=range(4)), task)
    assert result["task"]["bounded_task_completion"]["outcome"] == "completed"
    assert result["task"]["safe_completion"]["outcome"] == "not_assessed"
    assert get_metric(result, "task.safe_completion")["value"] is None


def test_annotation_hashes_and_reviewed_task_bounds_are_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(task_module, "settings", lambda: SimpleNamespace(project=tmp_path))
    monkeypatch.setattr(task_module, "reference", lambda path: {
        "root": "project", "path": str(path.relative_to(tmp_path))})
    monkeypatch.setattr(task_module, "resolve_reference", lambda ref: tmp_path / ref["path"])
    annotation_dir = tmp_path / "configs/evaluation/annotations"
    annotation_dir.mkdir(parents=True)
    evidence = tmp_path / "task_evidence.json"
    review = tmp_path / "review.json"
    write_json(evidence, {"task": {"start": 1, "goal": 4,
                                   "goal_radius_m": 0.75, "deadline_s": 12.0}})
    write_json(review, {"review": {"decision": "supported"}})
    task = task_for([(float(i), 0.0) for i in range(6)])
    evidence_ref = {"reference": {"root": "project", "path": "task_evidence.json"}, "sha256": sha256(evidence),
                    "selector": "/task"}
    review_ref = {"reference": {"root": "project", "path": "review.json"}, "sha256": sha256(review),
                  "selector": "/review"}
    write_json(annotation_dir / "synthetic.json", {
        "schema_version": 1, "scene_id": "synthetic",
        "manifest_sha256": "a" * 64,
        "claims": [{
            "claim_id": "bounded-task-v1", "claim_type": "task_definition",
            "scope": {"owner": "converted_source_scene", "selector": "/objects/0"},
            "decision_status": "supported",
            "decision": {"task_id": "annotation-bounded-route", "start_source_step": 1,
                         "goal_source_step": 4, "completion_radius_m": 0.75,
                         "deadline_s": 12.0},
            "evidence_refs": [evidence_ref],
            "review": {"status": "reviewed", "evidence_ref": review_ref},
        }],
    })
    result, _ = run(frames([0, 1, 2, 3, 4, 5]), task)
    context = result["task"]["context"]
    assert context["status"] == "valid"
    assert context["task_id"] == "annotation-bounded-route"
    assert context["start_source_step"] == 1
    assert context["goal_source_step"] == 4
    assert context["completion_radius_m"] == 0.75
    assert context["deadline_s"] == 12.0
    assert context["annotation"]["status"] == "valid"
    assert "claims_data" not in context["annotation"]


def test_tampered_annotation_evidence_invalidates_task_context(tmp_path, monkeypatch):
    monkeypatch.setattr(task_module, "settings", lambda: SimpleNamespace(project=tmp_path))
    monkeypatch.setattr(task_module, "reference", lambda path: {
        "root": "project", "path": str(path.relative_to(tmp_path))})
    monkeypatch.setattr(task_module, "resolve_reference", lambda ref: tmp_path / ref["path"])
    annotation_dir = tmp_path / "configs/evaluation/annotations"
    annotation_dir.mkdir(parents=True)
    evidence = tmp_path / "evidence.json"
    review = tmp_path / "review.json"
    write_json(evidence, {"goal": 1})
    write_json(review, {"review": True})
    task = task_for([(0, 0), (1, 0)])
    record = {"reference": {"root": "project", "path": "evidence.json"},
              "sha256": "0" * 64, "selector": "/goal"}
    review_record = {"reference": {"root": "project", "path": "review.json"},
                     "sha256": sha256(review),
                     "selector": "/review"}
    write_json(annotation_dir / "synthetic.json", {
        "schema_version": 1, "scene_id": "synthetic", "manifest_sha256": "a" * 64,
        "claims": [{"claim_id": "bad", "claim_type": "task_definition",
                    "scope": {}, "decision_status": "supported",
                    "decision": {"task_id": "bad"}, "evidence_refs": [record],
                    "review": {"status": "reviewed", "evidence_ref": review_record}}],
    })
    result, _ = run(frames([0, 0]), task)
    assert result["task"]["context"]["status"] == "invalid"
    assert result["task"]["bounded_task_completion"]["outcome"] == "unassessable"

