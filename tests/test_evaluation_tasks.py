"""Synthetic route/task/efficiency cases without simulator or dataset access."""

import json
import math

import pytest
from types import SimpleNamespace

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.evaluation.context import TaskContext
from geotransfer_gap.evaluation.kinematics import measure_kinematics
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.evaluation.tasks import measure_tasks
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


def run(frames, task, *, planner="ppo", terminal="horizon", requested=None):
    profile = PROFILE
    for index, frame in enumerate(frames):
        frame.update(step=index, time_s=index / 10,
                     transition_applied=index < len(frames) - 1)
    report = {
        "schema_version": 3, "planner": "controller_matrix", "ego_controller": planner,
        "requested_observation_frames": requested or len(frames),
        "terminal_reason": terminal,
    }
    measured = measure_kinematics(frames, EGO, report, profile)
    result = measure_tasks(frames, EGO, report, profile, measured["exposure"],
                           measured["events"], task)
    return result, measured


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
    result, _ = run(frames([0, 1, 2, 3], goals={3}, terminal_missing=True), task,
                    terminal="ego_removed", requested=8)
    task_result = result["task"]
    assert task_result["native_goal_event"]["step"] == 3
    assert task_result["bounded_task_completion"]["outcome"] == "completed"
    assert task_result["bounded_task_completion"]["completion_basis"] == "native_goal_event"
    assert task_result["terminal"]["truncation_status"] == "observed_before_requested_horizon"


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

