"""Offline task, route-progress and efficiency measurements."""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path

from geotransfer_gap.artifacts import reference, resolve_reference, sha256
from geotransfer_gap.config import settings
from geotransfer_gap.evaluation.context import TaskContext
from geotransfer_gap.evaluation.contracts import (
    AssessmentStatus,
    CriterionOutcome,
    MetricResult,
)


_PROJECTION_DISTANCE_TIE_M = 0.1
_PROJECTION_ARC_TIE_M = 0.5
_CONTINUITY_SLACK_M = 0.5
_DIRECTION_EPSILON_M = 0.02
_NATIVE_GOAL_MATCH_TOLERANCE_M = 0.1


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _point(value):
    return (isinstance(value, (tuple, list)) and len(value) == 2
            and _finite(value[0]) and _finite(value[1]))


def _actor_rows(frames, ego_id):
    return [next((actor for actor in frame.get("actors", ())
                  if actor.get("id") == ego_id), None) for frame in frames]


def _generation(actor):
    value = actor.get("lifetime_generation") if actor else None
    return value if type(value) is int and value >= 0 else None


def _same_lifetime(left, right):
    if left is None or right is None or left.get("id") != right.get("id"):
        return False
    a, b = _generation(left), _generation(right)
    return a == b if a is not None or b is not None else True


def _present_pose(actor):
    return bool(actor and actor.get("present") is True
                and _finite(actor.get("x")) and _finite(actor.get("y")))


def _present(actor):
    return bool(actor and actor.get("present") is True)


def _metric(metric_id, version, *, status, reason, value=None, units=None,
            window=None, samples=None, duration=None, actors=(),
            criterion=CriterionOutcome.NOT_ASSESSED, limitations=(),
            interpretation=None, evidence_refs=()):
    return MetricResult(
        metric_id=metric_id, definition_version=version, status=status,
        reason=reason, value=value, units=units, window=window,
        eligible_samples=samples, eligible_duration_s=duration,
        actors=tuple(actors), criterion_outcome=criterion,
        limitations=tuple(limitations), interpretation=interpretation,
        evidence_refs=tuple(evidence_refs),
    ).to_dict()


def _json_pointer(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("evidence selector must be a JSON Pointer")
    current = value
    if not pointer:
        return current
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise ValueError(f"evidence selector does not resolve: {pointer}")
    return current


def _verify_reference(record):
    if (type(record) is not dict or set(record) != {"reference", "sha256", "selector"}
            or not isinstance(record["reference"], dict)
            or not isinstance(record["sha256"], str)):
        raise ValueError("evidence reference must bind a portable path, hash and selector")
    path = resolve_reference(record["reference"])
    if not path.is_file() or sha256(path) != record["sha256"]:
        raise ValueError(f"annotation evidence hash differs: {path}")
    value = json.loads(path.read_text())
    return path, _json_pointer(value, record["selector"])


def _load_annotation(task, profile):
    if getattr(task, "scene_id", None) is None or getattr(task, "identity", None) is None:
        return {"status": "unavailable", "reason": "Task scene identity is unavailable",
                "claims": [], "claims_data": [], "task_claim": None,
                "task_claim_evidence": []}
    configured = Path(profile.values["profile"]["annotations_directory"])
    directory = configured if configured.is_absolute() else settings().project / configured
    path = directory / f"{task.scene_id}.json"
    if not path.is_file():
        return {"status": "absent", "reason": "No sparse evaluation annotation is supplied",
                "claims": [], "claims_data": [], "task_claim": None,
                "task_claim_evidence": []}
    try:
        try:
            annotation_ref = {"kind": "sparse_evaluation_annotation",
                              "reference": reference(path), "sha256": sha256(path)}
        except ValueError:
            annotation_ref = {"kind": "sparse_evaluation_annotation",
                              "path": str(path.resolve()), "sha256": sha256(path)}
    except OSError:
        annotation_ref = None
    try:
        annotation = json.loads(path.read_text())
        manifest_sha = task.identity["manifest_sha256"]
        if (type(annotation) is not dict or type(annotation.get("schema_version")) is not int
                or annotation.get("schema_version") != 1
                or annotation.get("scene_id") != task.scene_id
                or annotation.get("manifest_sha256") != manifest_sha
                or not isinstance(annotation.get("claims"), list)):
            raise ValueError("annotation schema, scene or manifest identity differs")
        identifiers = set()
        task_claims = []
        task_claim_evidence = {}
        summaries = []
        claims_data = []
        for claim in annotation["claims"]:
            required = {"claim_id", "claim_type", "scope", "decision_status",
                        "decision", "evidence_refs", "review"}
            if (type(claim) is not dict or not required <= set(claim)
                    or set(claim) - required - {"reason"}
                    or not isinstance(claim["claim_id"], str) or not claim["claim_id"].strip()
                    or claim["claim_id"] in identifiers
                    or claim["claim_type"] not in {"task_definition", "interaction_criterion",
                                                    "rule_applicability", "physical_map_coverage"}
                    or type(claim["scope"]) is not dict
                    or not claim["scope"]
                    or claim["decision_status"] not in {"supported", "explicitly_unassessable", "rejected"}
                    or not isinstance(claim["evidence_refs"], list)
                    or type(claim["review"]) is not dict):
                raise ValueError("annotation claim is malformed or duplicated")
            identifiers.add(claim["claim_id"])
            evidence_values = []
            if claim["decision_status"] == "supported":
                if claim["decision"] is None or not claim["evidence_refs"]:
                    raise ValueError("supported annotation claim lacks a decision or evidence")
                for record in claim["evidence_refs"]:
                    _, selected_value = _verify_reference(record)
                    evidence_values.append(selected_value)
            elif claim["decision"] is not None or not isinstance(claim.get("reason"), str):
                raise ValueError("unassessable/rejected claim requires null decision and a claim reason")
            review = claim["review"]
            if (set(review) - {"status", "evidence_ref", "reason"}
                    or "status" not in review):
                raise ValueError("annotation review record has unsupported fields")
            if review.get("status") not in {"reviewed", "unreviewed", "not_required"}:
                raise ValueError("unsupported annotation review status")
            if review.get("status") == "reviewed":
                _verify_reference(review.get("evidence_ref"))
            elif "evidence_ref" in review:
                raise ValueError("unreviewed annotation must not imply review evidence")
            if claim["claim_type"] == "task_definition":
                task_claims.append(claim)
                task_claim_evidence[claim["claim_id"]] = evidence_values
            claims_data.append({"claim": claim, "selected_evidence": evidence_values})
            summaries.append({"claim_id": claim["claim_id"],
                              "claim_type": claim["claim_type"],
                              "decision_status": claim["decision_status"],
                              "review_status": review["status"],
                              "evidence_refs": claim["evidence_refs"]})
        if len([claim for claim in task_claims
                if claim["decision_status"] == "supported"]) > 1:
            raise ValueError("multiple supported task definitions are ambiguous")
        return {"status": "valid", "reason": "Annotation identity and evidence hashes verified",
                "evidence_ref": annotation_ref, "claims": summaries,
                "claims_data": claims_data,
                "task_claim": next((claim for claim in task_claims
                    if claim["decision_status"] == "supported"), None),
                "task_claim_evidence": task_claim_evidence}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": f"Sparse annotation is invalid: {exc}",
                "evidence_ref": annotation_ref,
                "claims": [], "claims_data": [], "task_claim": None,
                "task_claim_evidence": []}


def _apply_task_claim(task, claim, evidence_values):
    if claim is None:
        return task, None
    if claim["review"].get("status") != "reviewed":
        return task, "supported task definition is not human-reviewed"
    decision = claim["decision"]
    allowed = {"task_id", "start_source_step", "goal_source_step",
               "completion_radius_m", "deadline_s"}
    if (type(decision) is not dict or set(decision) - allowed
            or not isinstance(decision.get("task_id"), str)
            or not decision["task_id"].strip()):
        return task, "task definition decision has an unsupported shape"
    aliases = {
        "start_source_step": {"start_source_step", "start"},
        "goal_source_step": {"goal_source_step", "goal", "goal_sample"},
        "completion_radius_m": {"completion_radius_m", "goal_radius_m"},
        "deadline_s": {"deadline_s"},
    }
    for field, expected in decision.items():
        if field == "task_id":
            continue
        supported = any(isinstance(value, dict)
                        and any(value.get(name) == expected for name in aliases[field])
                        for value in evidence_values)
        if not supported:
            return task, f"task definition {field} lacks a matching selected evidence value"
    start = decision.get("start_source_step", task.start_source_step)
    goal = decision.get("goal_source_step", task.goal_source_step)
    radius = decision.get("completion_radius_m", task.completion_radius_m)
    deadline = decision.get("deadline_s", task.deadline_s)
    if (type(start) is not int or type(goal) is not int or start < task.start_source_step
            or goal < start or goal > task.goal_source_step
            or not _finite(radius) or radius <= 0
            or (deadline is not None and (not _finite(deadline) or deadline <= 0))):
        return task, "task definition bounds or thresholds are inconsistent"
    if task.route_status != "valid" or not task.reference_points:
        if start != task.start_source_step or goal != task.goal_source_step:
            return task, "annotated task bounds require a validated source route"
        points = task.reference_points
    else:
        start_offset = start - task.start_source_step
        end_offset = goal - task.start_source_step
        points = task.reference_points[start_offset:end_offset + 1]
    span = sum(math.dist(left, right) for left, right in zip(points, points[1:]))
    route_status = task.route_status
    route_reason = task.route_reason
    route_span = task.route_span_m
    if route_status == "valid":
        if span <= 0 or not math.isfinite(span):
            route_status, route_reason, route_span, points = (
                "unavailable", "Annotated task route has no positive finite span", None, ())
        else:
            route_span = span
    goal_xy = points[-1] if points else task.goal_xy
    return replace(task, task_id=decision["task_id"],
                   start_source_step=start, goal_source_step=goal, goal_xy=goal_xy,
                   completion_radius_m=float(radius), deadline_s=float(deadline) if deadline is not None else None,
                   reference_points=points, route_status=route_status,
                   route_reason=route_reason, route_span_m=route_span), None


def _route_segments(points):
    result, arc = [], 0.0
    for index, (left, right) in enumerate(zip(points, points[1:])):
        dx, dy = right[0] - left[0], right[1] - left[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        result.append((index, left, dx, dy, length, arc, arc + length))
        arc += length
    return result


def _candidate_projections(point, segments):
    candidates = []
    for index, start, dx, dy, length, arc_start, _ in segments:
        fraction = min(1.0, max(0.0,
                                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                                / (length * length)))
        projected = (start[0] + fraction * dx, start[1] + fraction * dy)
        candidates.append({
            "segment": index,
            "arc_m": arc_start + fraction * length,
            "distance_m": math.dist(point, projected),
            "tangent": (dx / length, dy / length),
        })
    if not candidates:
        return []
    nearest = min(row["distance_m"] for row in candidates)
    return [row for row in candidates
            if row["distance_m"] <= nearest + _PROJECTION_DISTANCE_TIE_M]


def _project_rollout(frames, actors, times, task):
    segments = _route_segments(task.reference_points)
    projections, run = [], -1
    prior = None
    for index, (frame, actor, time_s) in enumerate(zip(frames, actors, times)):
        sample = {"step": frame.get("step", index), "observation_index": index,
                  "time_s": time_s,
                  "status": "unavailable", "reason": "ego pose is absent"}
        if not _present_pose(actor):
            prior = None
            projections.append(sample)
            continue
        position = (float(actor["x"]), float(actor["y"]))
        candidates = _candidate_projections(position, segments)
        if not candidates:
            sample["reason"] = "reference route has no nonzero segment"
            prior = None
            projections.append(sample)
            continue
        displacement = None
        if prior is not None:
            previous_index, previous_actor, previous_position, previous_projection = prior
            if (index != previous_index + 1 or not _same_lifetime(previous_actor, actor)
                    or (type(previous_actor.get("source_valid")) is bool
                        and type(actor.get("source_valid")) is bool
                        and previous_actor["source_valid"] != actor["source_valid"])
                    or frames[previous_index].get("transition_applied") is False):
                prior = None
            else:
                displacement = math.dist(position, previous_position)
                candidates = [row for row in candidates
                              if abs(row["arc_m"] - previous_projection["arc_m"])
                              <= displacement + _CONTINUITY_SLACK_M]
                if not candidates:
                    sample["reason"] = "projection discontinuity exceeds observed displacement"
                    prior = None
                    projections.append(sample)
                    continue
        if len(candidates) > 1:
            arc_values = [row["arc_m"] for row in candidates]
            if max(arc_values) - min(arc_values) > _PROJECTION_ARC_TIE_M:
                sample.update(reason="ambiguous route projection at loop or branch",
                              candidate_count=len(candidates), branch_ambiguous=True)
                prior = None
                projections.append(sample)
                continue
        if prior is not None and displacement is not None:
            previous_projection = prior[3]
            best_change = min(abs(row["arc_m"] - previous_projection["arc_m"])
                              for row in candidates)
            tied = [row for row in candidates
                    if abs(abs(row["arc_m"] - previous_projection["arc_m"])
                           - best_change) <= _PROJECTION_DISTANCE_TIE_M]
            if len(tied) > 1 and max(row["arc_m"] for row in tied) - min(
                    row["arc_m"] for row in tied) > _PROJECTION_ARC_TIE_M:
                sample.update(reason="continuity leaves multiple route branches",
                              candidate_count=len(tied), branch_ambiguous=True)
                prior = None
                projections.append(sample)
                continue
            candidates = tied
        chosen = min(candidates, key=lambda row: (row["distance_m"], row["segment"]))
        if prior is not None:
            if displacement is not None and displacement > _DIRECTION_EPSILON_M:
                delta = chosen["arc_m"] - prior[3]["arc_m"]
                motion_dot = ((position[0] - prior[2][0]) * chosen["tangent"][0]
                              + (position[1] - prior[2][1]) * chosen["tangent"][1])
                if (abs(motion_dot) > _DIRECTION_EPSILON_M
                        and delta * motion_dot < -_DIRECTION_EPSILON_M):
                    sample.update(reason="route projection direction contradicts observed motion",
                                  branch_ambiguous=True)
                    prior = None
                    projections.append(sample)
                    continue
            run = prior[3]["run"]
        else:
            run += 1
        sample.update(status="valid", reason=None, route_arc_m=float(chosen["arc_m"]),
                      route_distance_m=float(chosen["distance_m"]),
                      route_segment_index=chosen["segment"], run=run,
                      candidate_count=len(candidates))
        projections.append(sample)
        prior = (index, actor, position, {**chosen, "run": run})
    return projections


def _window_indices(count, name, warmup, last):
    return [index for index in range(count)
            if name == "full" or warmup <= index <= last]


def _route_metric_records(frames, actors, times, task, profile, evidence_refs):
    warmup = profile.values["time"]["warmup_transitions"]
    last = profile.values["time"]["primary_last_observation_index"]
    projections = _project_rollout(frames, actors, times, task) if task.route_status == "valid" else []
    metrics = []
    window_results = {}
    actor_refs = tuple(sorted({(actor["id"], _generation(actor)) for actor in actors if actor},
                              key=lambda row: (row[0], -1 if row[1] is None else row[1])))
    route_status = (AssessmentStatus.INVALID if task.route_status == "invalid"
                    else AssessmentStatus.UNAVAILABLE)
    for window in ("full", "primary"):
        selected = _window_indices(len(frames), window, warmup, last)
        valid = [index for index in selected
                 if index < len(projections) and projections[index]["status"] == "valid"]
        reason = task.route_reason
        route_value = normalized_value = None
        if task.route_status == "valid" and len(valid) >= 2:
            start, end = valid[0], valid[-1]
            ambiguous_prefix = any(
                projections[index].get("branch_ambiguous")
                for index in selected if index < start and index < len(projections)
            )
            segment_ids = {projections[index]["run"] for index in range(start, end + 1)
                           if projections[index]["status"] == "valid"}
            missing_projection = [index for index in range(start, end + 1)
                                  if projections[index]["status"] != "valid"]
            if ambiguous_prefix:
                reason = "Initial route projection is ambiguous; no window baseline is selected"
            elif len(segment_ids) == 1 and not missing_projection:
                net = projections[end]["route_arc_m"] - projections[start]["route_arc_m"]
                fraction = net / task.route_span_m if task.route_span_m and task.route_span_m > 0 else None
                route_value = {
                    "net_progress_m": float(net),
                    "start_step": frames[start].get("step", start),
                    "end_step": frames[end].get("step", end),
                    "start_route_arc_m": projections[start]["route_arc_m"],
                    "end_route_arc_m": projections[end]["route_arc_m"],
                    "start_projection_distance_m": projections[start]["route_distance_m"],
                    "end_projection_distance_m": projections[end]["route_distance_m"],
                    "raw_normalized_progress": float(fraction) if fraction is not None else None,
                    "display_fraction_clipped": (float(min(1.0, max(0.0, fraction)))
                                                  if fraction is not None else None),
                    "projection_samples": len(valid),
                    "projection_continuous": True,
                }
                normalized_value = ((fraction, route_value)
                                    if _finite(task.route_span_m) and task.route_span_m > 0
                                    else None)
                reason = "Signed net route advancement on one continuity-consistent projection"
            else:
                reason = "Route progress crosses missing or ambiguous projection support"
        elif task.route_status == "valid":
            reason = "Fewer than two supported route projections in this window"
        status = AssessmentStatus.VALID if route_value is not None else route_status
        metrics.append(_metric(
            "trajectory.route_progress", profile.definition_version, status=status,
            reason=reason, value=route_value, units="m", window=window,
            samples=len(valid) if valid else None, actors=actor_refs,
            evidence_refs=evidence_refs,
            limitations=("Signed net arc progress is separate from PE02 observed distance",
                          "Source future geometry is used offline only"),
        ))
        n_status = AssessmentStatus.VALID if normalized_value else route_status
        metrics.append(_metric(
            "trajectory.normalized_route_progress", profile.definition_version,
            status=n_status,
            reason=(reason if normalized_value else
                    "A positive validated task route span and continuous projection are required"),
            value=(normalized_value[1] if normalized_value else None),
            units="fraction", window=window, samples=len(valid) if valid else None,
            actors=actor_refs, evidence_refs=evidence_refs,
            limitations=("Raw fraction is retained; clipped fraction is display-only",
                         "Values outside [0, 1] are not clipped in the measurement"),
        ))
        selected_samples = [projections[index] for index in selected if index < len(projections)]
        ambiguous = [row for row in selected_samples if row.get("branch_ambiguous")]
        window_results[window] = {
            "status": "valid" if route_value is not None else status.value,
            "reason": reason,
            "branch_ambiguity": bool(ambiguous),
            "ambiguous_steps": [row["step"] for row in ambiguous],
            "projection_samples": selected_samples,
            "progress": route_value,
        }
    return metrics, {"status": task.route_status, "reason": task.route_reason,
                     "task_span_m": task.route_span_m, "windows": window_results}


def _intervals(frames, actors, times):
    """Reuse PE02's observation masks and trace identity for state intervals."""
    intervals = []
    for index in range(max(0, len(frames) - 1)):
        left, right = actors[index], actors[index + 1]
        dt = None
        reason = None
        if frames[index].get("transition_applied") is False:
            reason = "transition_not_applied"
        elif not (_present(left) and _present(right) and _same_lifetime(left, right)):
            reason = "ego_pose_or_lifetime_boundary"
        elif (type(left.get("source_valid")) is bool
              and type(right.get("source_valid")) is bool
              and left["source_valid"] != right["source_valid"]):
            reason = "source_validity_boundary"
        elif not (_finite(times[index]) and _finite(times[index + 1])
                  and times[index + 1] > times[index]):
            reason = "time_missing_or_nonincreasing"
        else:
            dt = float(times[index + 1] - times[index])
        intervals.append({"index": index, "dt": dt, "reason": reason, "left": left})
    return intervals


def _stationary(frames, actors, times, profile, evidence_refs, exposure):
    thresholds = profile.values["efficiency"]["stationary_speed_sensitivity_m_s"]
    primary_threshold = profile.values["efficiency"]["stationary_speed_below_m_s"]
    warmup = profile.values["time"]["warmup_transitions"]
    last = profile.values["time"]["primary_last_observation_index"]
    intervals = _intervals(frames, actors, times)
    metrics, output = [], {}
    actor_refs = tuple(sorted({(actor["id"], _generation(actor)) for actor in actors if actor},
                              key=lambda row: (row[0], -1 if row[1] is None else row[1])))
    for window in ("full", "primary"):
        selected = [item for item in intervals
                    if window == "full" or warmup <= item["index"] <= last]
        supported, missing_speed = [], 0
        for item in selected:
            actor = item["left"]
            if item["dt"] is None:
                continue
            if not (_finite(actor.get("vx")) and _finite(actor.get("vy"))):
                missing_speed += 1
                continue
            supported.append({"step": frames[item["index"]].get("step", item["index"]),
                              "time_s": times[item["index"]],
                              "speed_m_s": math.hypot(actor["vx"], actor["vy"]),
                              "duration_s": item["dt"]})
        if supported:
            values = {}
            for threshold in thresholds:
                rows = [item for item in supported if item["speed_m_s"] < threshold]
                values[f"below_{threshold:g}_m_s"] = {
                    "threshold_m_s": float(threshold),
                    "duration_s": float(sum(item["duration_s"] for item in rows)),
                    "sample_count": len(rows),
                }
            eligible_duration = sum(item["duration_s"] for item in supported)
            pose_duration = exposure.get("windows", {}).get(window, {}).get(
                "pose_duration_s")
            coverage_complete = (missing_speed == 0 and _finite(pose_duration)
                                 and abs(eligible_duration - pose_duration) <= 1e-8)
            payload = {
                "primary_threshold_m_s": float(primary_threshold),
                "duration_s": values[f"below_{primary_threshold:g}_m_s"]["duration_s"],
                "sample_count": values[f"below_{primary_threshold:g}_m_s"]["sample_count"],
                "threshold_sensitivity": values,
                "duration_method": "left_observation_sampled_interval_approximation",
                "sampling_resolution_s": 0.1,
                "supported_duration_s": float(eligible_duration),
                "pose_supported_duration_s": float(pose_duration) if _finite(pose_duration) else None,
                "missing_speed_intervals": missing_speed,
                "coverage_complete": coverage_complete,
            }
            status = AssessmentStatus.VALID
            reason = ("Stationary occupancy is a sampled speed threshold, not a stall verdict"
                      if coverage_complete else
                      "Stationary occupancy is a supported partial-duration estimate")
            duration = payload["duration_s"]
        else:
            payload, status = None, AssessmentStatus.UNAVAILABLE
            reason, duration = "No supported speed interval is available", None
            eligible_duration = None
        metrics.append(_metric(
            "efficiency.stationary_duration", profile.definition_version,
            status=status, reason=reason, value=payload, units="s", window=window,
            samples=len(supported) if supported else None, duration=eligible_duration,
            actors=actor_refs, evidence_refs=evidence_refs,
            limitations=("Low speed is not interpreted as waiting opportunity or deadlock",
                         "Durations are left-observation sampled approximations"),
        ))
        output[window] = payload
    return metrics, output, intervals


def _planner_goal_visibility(report):
    planner = report.get("ego_controller") if report.get("planner") == "controller_matrix" else report.get("planner")
    if planner == "smart":
        return {"status": "known", "value": False,
                "reason": "The inspected SMART input path has no simulator navigation-goal input"}
    if planner == "ppo":
        return {"status": "known", "value": True,
                "reason": "PPO receives the simulator navigation goal in its observation"}
    if planner in {"expert", "idm"}:
        return {"status": "not_applicable", "value": None,
                "reason": "Saved trajectory/controller is not a navigation-goal-conditioned planner"}
    return {"status": "unavailable", "value": None,
            "reason": "Planner goal visibility is not recorded for this layout"}


def _low_progress(frames, times, route_output, profile, evidence_refs):
    distance_threshold = profile.values["efficiency"]["low_progress_candidate_distance_m"]
    window_s = profile.values["efficiency"]["low_progress_candidate_window_s"]
    nominal_dt = profile.values["time"]["nominal_sample_interval_s"]
    minimum_intervals = math.ceil(window_s / nominal_dt)
    metrics = []
    for window in ("full", "primary"):
        route = route_output["windows"][window]
        samples = route["projection_samples"]
        by_index = {row["observation_index"]: row for row in samples}
        selected = [row for row in samples if row.get("status") == "valid"]
        candidates = []
        assessed_windows = 0
        for start in selected:
            if not _finite(start.get("time_s")):
                continue
            end = next((row for row in selected
                        if row["time_s"] is not None
                        and row["time_s"] >= start["time_s"] + window_s), None)
            if end is None or end["run"] != start["run"]:
                continue
            start_index = start.get("observation_index")
            end_index = end.get("observation_index")
            if start_index is None or end_index is None:
                continue
            if end_index - start_index < minimum_intervals:
                continue
            # Do not let a pair bridge missing or ambiguous observations.
            adjacent_times = [times[index + 1] - times[index]
                              for index in range(start_index, end_index)]
            if (any(index not in by_index or by_index[index].get("status") != "valid"
                    for index in range(start_index, end_index + 1))
                    or any(not _finite(dt) or dt <= 0 or dt > nominal_dt * 1.5
                           for dt in adjacent_times)):
                continue
            assessed_windows += 1
            advance = end["route_arc_m"] - start["route_arc_m"]
            if advance < distance_threshold:
                candidates.append({
                    "start_step": start["step"], "end_step": end["step"],
                    "observed_duration_s": float(end["time_s"] - start["time_s"]),
                    "signed_route_advance_m": float(advance),
                    "candidate": True,
                    "confirmed_deadlock": False,
                    "reason": "low progress candidate; opportunity to proceed is unassessed",
                })
        valid = bool(assessed_windows) and route["status"] == "valid"
        payload = (None if not valid else {
            "candidate": bool(candidates),
            "threshold_distance_m": float(distance_threshold),
            "window_s": float(window_s),
            "candidates": candidates,
            "assessed_window_count": assessed_windows,
            "confirmed_deadlock": False,
            "stalling_assessment": "not_assessed",
            "stalling_reason": "A low-progress candidate does not establish opportunity to proceed",
        })
        metrics.append(_metric(
            "efficiency.low_progress_candidate", profile.definition_version,
            status=AssessmentStatus.VALID if valid else AssessmentStatus.UNAVAILABLE,
            reason=("Observed fixed windows yield inspectable low-progress candidates only"
                    if valid else route["reason"]),
            value=payload, units={"route_advance": "m", "window": "s"}, window=window,
            samples=len(selected) if valid else None, evidence_refs=evidence_refs,
            limitations=("Candidate status never confirms deadlock",
                         "Insufficient opportunity-to-proceed evidence remains unassessed"),
        ))
    return metrics


def _native_goal(events, exposure, goal_binding):
    goals = [row for row in events if row.get("channel") == "goal_reached"]
    coverage = exposure.get("event_observation_coverage", {}).get("windows", {}).get("full", {})
    channel = coverage.get("channels", {}).get("reached_goal", {})
    first = min(goals, key=lambda row: row.get("time_s") if _finite(row.get("time_s")) else math.inf) if goals else None
    observed = bool(goals)
    complete_coverage = channel.get("fraction") == 1.0
    absence_observed = not observed and complete_coverage
    return {
        "status": "valid" if observed or absence_observed else "unavailable",
        "observed": True if observed else False if absence_observed else None,
        "step": first.get("step") if first else None,
        "time_s": first.get("time_s") if first else None,
        "attribution": first.get("attribution") if first else None,
        "source": first.get("evidence") if first else "no_active_goal_flag_observed",
        "coverage": channel,
        "task_goal_binding": goal_binding,
    }


def _captured_task_goal_binding(capture, capture_bound, ego_id, ego_binary_index,
                                task, report, frame_count):
    if not capture_bound or capture is None:
        return {"status": "unavailable", "matches": None,
                "reason": "No hash-bound native navigation-goal capture is available"}
    if (type(capture.get("schema_version")) is not int or capture.get("schema_version") != 1
            or capture.get("ego_source_id") != ego_id
            or capture.get("ego_binary_index") != ego_binary_index
            or capture.get("binary_sha256") != report.get("binary_sha256")
            or capture.get("scene") != report.get("scene")
            or not isinstance(capture.get("observations"), list)
            or len(capture["observations"]) != frame_count):
        return {"status": "invalid", "matches": None,
                "reason": "Bound native goal capture identity or observation count contradicts the trace"}
    if task.goal_xy is None:
        return {"status": "unavailable", "matches": None,
                "reason": "Validated source task has no goal position"}
    recorded_goals = []
    for step, observation in enumerate(capture["observations"]):
        if (not isinstance(observation, dict) or observation.get("step") != step
                or not isinstance(observation.get("actors"), list)):
            return {"status": "invalid", "matches": None,
                    "reason": "Native goal capture step sequence differs from the trace"}
        actors = [row for row in observation.get("actors", ())
                  if isinstance(row, dict) and row.get("source_id") == ego_id]
        if not actors:
            continue
        if len(actors) != 1 or actors[0].get("binary_index") != ego_binary_index:
            return {"status": "invalid", "matches": None,
                    "reason": "Native goal capture ego identity is duplicated or inconsistent"}
        goal = actors[0].get("navigation_goal_world_xy")
        if goal is None:
            continue
        if not (isinstance(goal, list) and len(goal) == 2
                and all(_finite(value) for value in goal)):
            return {"status": "invalid", "matches": None,
                    "reason": "Native goal capture contains a malformed goal position"}
        recorded_goals.append({"step": step,
                               "position_world_xy": [float(goal[0]), float(goal[1])]})
    if not recorded_goals:
        return {"status": "unavailable", "matches": None,
                "reason": "Bound capture contains no ego navigation-goal position"}
    distances = [math.dist(row["position_world_xy"], task.goal_xy) for row in recorded_goals]
    matches = all(distance <= _NATIVE_GOAL_MATCH_TOLERANCE_M for distance in distances)
    return {
        "status": "valid",
        "matches": matches,
        "reason": ("Captured native navigation goal matches the bounded source task"
                   if matches else
                   "Captured native navigation goal differs from the bounded source task"),
        "matching_tolerance_m": _NATIVE_GOAL_MATCH_TOLERANCE_M,
        "recorded_goal_observation_count": len(recorded_goals),
        "maximum_goal_difference_m": float(max(distances)),
        "last_recorded_goal_step": recorded_goals[-1]["step"],
    }


def _safe_completion(task_outcome, events, exposure):
    channels = exposure.get("event_observation_coverage", {}).get("windows", {}).get(
        "full", {}).get("channels", {})
    results = {}
    failure = False
    for name, event_channel, coverage_channel in (
            ("native_vehicle_collision", "native_vehicle_collision", "collision_state"),
            ("native_offroad", "native_offroad", "collision_state")):
        occurred = any(row.get("channel") == event_channel for row in events)
        coverage = channels.get(coverage_channel, {})
        complete = coverage.get("fraction") == 1.0
        if occurred:
            status, outcome, reason = "valid", "fail", "a native safety event was observed"
        elif complete:
            status, outcome, reason = "valid", "pass", "the native channel is complete with no observed event"
        else:
            status, outcome, reason = "unavailable", "not_assessed", "native event coverage is incomplete"
        failure = failure or outcome == "fail"
        results[name] = {"status": status, "outcome": outcome,
                         "reason": reason, "coverage": coverage}
    if failure:
        outcome, reason = "fail", "A required native safety criterion failed"
    elif task_outcome != "completed":
        outcome, reason = "not_assessed", "Validated bounded-task completion was not observed"
    elif any(item["outcome"] != "pass" for item in results.values()):
        outcome, reason = "not_assessed", "One or more required native safety channels are unassessed"
    else:
        # The episode composer adds any explicitly designated PE07/PE08
        # criteria once those owners have produced their evidence.
        outcome, reason = "not_assessed", "Encounter and conditional criteria await episode composition"
    return {"outcome": outcome, "reason": reason,
            "criterion_set_id": "safe_completion_core_v1", "criteria": results}


def _claim_is_bound(row):
    claim = row.get("claim", {})
    return (claim.get("decision_status") == "supported"
            and claim.get("review", {}).get("status") == "reviewed"
            and type(claim.get("decision")) is dict
            and bool(row.get("selected_evidence"))
            and all(any(type(evidence) is dict and evidence.get(key) == value
                        for evidence in row["selected_evidence"])
                    for key, value in claim["decision"].items()))


def _criterion_record(outcome, reason, *, status=None, evidence_refs=()):
    if status is None:
        status = "valid" if outcome in {"pass", "fail"} else "unavailable"
    return {"status": status, "outcome": outcome, "reason": reason,
            "evidence_refs": list(evidence_refs)}


def _scope_covers_lane_samples(decision, lane_samples, profile, *, rule,
                               applicability, require_reason=False):
    """Require an explicit lane/time decision to cover the actual primary route."""
    if (type(decision) is not dict or decision.get("rule") != rule
            or decision.get("applicability") != applicability
            or (require_reason and (not isinstance(decision.get("reason"), str)
                                    or not decision["reason"].strip()))
            or ("safe_completion_critical" in decision
                and type(decision["safe_completion_critical"]) is not bool)):
        return False
    start = profile.values["time"]["primary_start_observation"]
    end = profile.values["time"]["primary_last_observation_index"]
    selected = list(lane_samples[start:min(end + 1, len(lane_samples))])
    if not selected or any(row.get("status") != "valid" for row in selected):
        return False
    step_range = decision.get("valid_step_range")
    lane_ids = decision.get("approach_lanelet_ids")
    if (not isinstance(step_range, list) or len(step_range) != 2
            or any(type(value) is not int for value in step_range)
            or step_range[0] > step_range[1]
            or not isinstance(lane_ids, list) or not lane_ids
            or any(type(value) is not int for value in lane_ids)
            or len(set(lane_ids)) != len(lane_ids)):
        return False
    return (all(type(row.get("step")) is int for row in selected)
            and all(right["step"] == left["step"] + 1
                    for left, right in zip(selected, selected[1:]))
            and all(step_range[0] <= row["step"] <= step_range[1]
                    and set(row.get("lanelet_ids", ())) & set(lane_ids)
                    for row in selected))


def finalize_safe_completion(task_measurement, *, annotation, map_metrics,
                             interactions, semantics, lane_assignment_samples,
                             profile):
    """Apply the PE07/PE08 designated criteria to the task owner's core result.

    Diagnostic failures are not promoted to critical criteria. A supported
    reviewed designation is required, and missing or unresolved evidence stays
    not assessed.
    """
    task = task_measurement["task"]
    safe = task.get("safe_completion")
    if not isinstance(safe, dict):
        return None
    criteria = safe["criteria"]
    designated = []
    claims = annotation.get("claims_data", ()) if annotation.get("status") == "valid" else ()
    for row in claims:
        claim = row.get("claim", {})
        decision = claim.get("decision")
        scope = claim.get("scope", {})
        is_critical = ((type(decision) is dict
                        and decision.get("safe_completion_critical") is True)
                       or scope.get("safe_completion_critical") is True)
        if is_critical:
            designated.append(row)

    supplemental = []
    signal_claims = []
    for row in claims:
        claim = row.get("claim", {})
        decision = claim.get("decision")
        if (claim.get("claim_type") == "rule_applicability"
                and type(decision) is dict and decision.get("rule") == "traffic_signal"):
            signal_claims.append(row)
    signal_pass = False
    signal_unknown_reason = "No reviewed actual-approach signal-applicability decision is supplied"
    for row in signal_claims:
        claim = row.get("claim", {})
        decision = claim.get("decision")
        if not _claim_is_bound(row):
            signal_unknown_reason = "Signal-applicability claim lacks reviewed hash-bound support"
            continue
        if (type(decision) is dict and decision.get("applicability") == "not_applicable"
                and _scope_covers_lane_samples(
                    decision, lane_assignment_samples, profile, rule="traffic_signal",
                    applicability="not_applicable", require_reason=True)):
            signal_pass = True
            break
        signal_unknown_reason = (
            "Signal applicability is supported or claimed, but the dynamic signal timeline is unavailable"
        )
    signal_criterion = _criterion_record(
        "pass" if signal_pass else "not_assessed",
        "Reviewed signal exemption covers the observed directed approach"
        if signal_pass else signal_unknown_reason,
        status="not_applicable" if signal_pass else "unavailable",
        evidence_refs=(signal_claims[0].get("claim", {}).get("evidence_refs", ())
                       if signal_pass and signal_claims else ()),
    )
    criteria["traffic_signal_applicability"] = signal_criterion
    for row in designated:
        claim = row.get("claim", {})
        decision = claim.get("decision")
        refs = claim.get("evidence_refs", ())
        claim_type = claim.get("claim_type")
        if (claim_type == "rule_applicability" and type(decision) is dict
                and decision.get("rule") == "traffic_signal"):
            continue
        if not _claim_is_bound(row):
            supplemental.append(_criterion_record(
                "not_assessed", "Critical designation or decision lacks reviewed hash-bound support",
                evidence_refs=refs))
            continue
        decision = dict(decision)
        if claim_type == "rule_applicability":
            rule = decision.get("rule")
            family = {"wrong_way": "wrong_way", "speed_limit": "speed_limit",
                      "stop_sign": "stop_sign", "priority_yield": "priority_yielding",
                      "traffic_signal": "traffic_signal"}.get(rule)
            applicability = decision.get("applicability")
            if family is None:
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical rule criterion has an unsupported rule family",
                    evidence_refs=refs))
                continue
            if applicability == "not_applicable":
                if rule == "traffic_signal":
                    # The mandatory signal criterion above consumes this
                    # exemption; the dynamic signal verdict remains unavailable.
                    continue
                observed = semantics.get("criteria", {}).get(family, {})
                if observed.get("status") == "not_applicable":
                    supplemental.append(_criterion_record(
                        "pass", "Reviewed rule exemption matches the measured actual approach",
                        status="not_applicable", evidence_refs=refs))
                else:
                    supplemental.append(_criterion_record(
                        "not_assessed", "Reviewed rule exemption does not establish actual-scope nonapplicability",
                        evidence_refs=refs))
                continue
            if applicability != "applicable":
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical rule applicability is unknown",
                    evidence_refs=refs))
                continue
            if (rule == "wrong_way"
                    and not _scope_covers_lane_samples(
                        decision, lane_assignment_samples, profile, rule="wrong_way",
                        applicability="applicable")):
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical wrong-way scope does not cover the observed primary route",
                    evidence_refs=refs))
                continue
            observed = semantics.get("criteria", {}).get(family, {})
            outcome = observed.get("criterion_outcome")
            if outcome not in {"pass", "fail"}:
                supplemental.append(_criterion_record(
                    "not_assessed", observed.get("reason", "Critical rule evidence is incomplete"),
                    status=observed.get("status"), evidence_refs=refs))
            else:
                supplemental.append(_criterion_record(
                    outcome, observed.get("reason", "Critical rule criterion was assessed"),
                    status=observed.get("status"), evidence_refs=refs))
        elif claim_type == "physical_map_coverage":
            if (decision.get("criterion") != "map_footprint_boundary"
                    or decision.get("safe_completion_critical") is not True):
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical map criterion is unsupported",
                    evidence_refs=refs))
                continue
            if decision.get("applicability") == "not_applicable":
                if isinstance(decision.get("reason"), str) and decision["reason"].strip():
                    supplemental.append(_criterion_record(
                        "pass", "Reviewed evidence declares the map criterion not applicable",
                        status="not_applicable", evidence_refs=refs))
                else:
                    supplemental.append(_criterion_record(
                        "not_assessed", "Map criterion nonapplicability lacks an explicit reason",
                        evidence_refs=refs))
                continue
            if decision.get("applicability") != "applicable":
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical map criterion applicability is unknown",
                    evidence_refs=refs))
                continue
            metric = next((item for item in map_metrics
                           if item.get("metric_id") == "safety.map_footprint_outside"
                           and item.get("window") == "primary"), None)
            value = metric.get("value") if metric else None
            if (type(value) is dict and type(value.get("outside_observation_count")) is int
                    and value["outside_observation_count"] > 0):
                supplemental.append(_criterion_record(
                    "fail", "An observed mapped-footprint boundary violation occurred",
                    evidence_refs=refs))
            elif (metric and metric.get("status") == "valid" and type(value) is dict
                  and value.get("coverage", {}).get("complete_for_selected_window") is True
                  and value.get("outside_observation_count") == 0):
                supplemental.append(_criterion_record(
                    "pass", "Complete primary map observations show no footprint outside the mapped surface",
                    evidence_refs=refs))
            else:
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical map-footprint evidence is incomplete",
                    status=metric.get("status") if metric else "unavailable",
                    evidence_refs=refs))
        elif claim_type == "interaction_criterion":
            if (decision.get("criterion") != "yielding_compliance"
                    or decision.get("safe_completion_critical") is not True
                    or decision.get("applicability") not in {"applicable", "not_applicable"}
                    or not isinstance(decision.get("family"), str)
                    or not isinstance(decision.get("subtype"), str)
                    or not isinstance(decision.get("source_actor_ids"), list)
                    or not decision["source_actor_ids"]
                    or any(type(value) is not int for value in decision["source_actor_ids"])
                    or len(set(decision["source_actor_ids"])) != len(decision["source_actor_ids"])):
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical encounter criterion is unsupported",
                    evidence_refs=refs))
                continue
            matches = [item for item in interactions.get("interactions", ())
                       if item.get("family") == decision.get("family")
                       and item.get("subtype") == decision.get("subtype")
                       and item.get("source_actor_ids") == decision.get("source_actor_ids")]
            if len(matches) != 1:
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical encounter does not uniquely match a measured source interaction",
                    evidence_refs=refs))
                continue
            measurement = matches[0].get("measurement", {})
            actor_results = [row for row in measurement.get("actors", ())
                             if row.get("actor_id") in decision["source_actor_ids"]]
            actor_results_by_id = {row.get("actor_id"): row for row in actor_results}
            if set(actor_results_by_id) != set(decision["source_actor_ids"]):
                supplemental.append(_criterion_record(
                    "not_assessed", "Critical encounter lacks a measured yielding result for every actor",
                    evidence_refs=refs))
                continue
            yielding = [row.get("yielding_compliance", {})
                        for row in actor_results_by_id.values()]
            if (decision["applicability"] == "not_applicable"
                    and all(row.get("status") == "not_applicable" for row in yielding)):
                supplemental.append(_criterion_record(
                    "pass", "PE07 confirms yielding is not applicable to this actual encounter",
                    status="not_applicable", evidence_refs=refs))
            elif any(row.get("outcome") == "fail" for row in yielding):
                supplemental.append(_criterion_record(
                    "fail", "A measured critical yielding criterion failed",
                    evidence_refs=refs))
            elif (decision["applicability"] == "applicable"
                  and all(row.get("status") == "valid" and row.get("outcome") == "pass"
                          for row in yielding)):
                supplemental.append(_criterion_record(
                    "pass", "The measured critical yielding criteria passed",
                    evidence_refs=refs))
            else:
                supplemental.append(_criterion_record(
                    "not_assessed", matches[0].get("reason", "Critical encounter criterion remains unresolved"),
                    evidence_refs=refs))
        else:
            supplemental.append(_criterion_record(
                "not_assessed", "Critical designation uses an unsupported annotation type",
                evidence_refs=refs))

    criteria["designated_critical_criteria"] = {
        "status": ("valid" if all(item["outcome"] in {"pass", "fail"}
                                  for item in supplemental) else
                   "unavailable" if supplemental else "not_applicable"),
        "outcome": ("fail" if any(item["outcome"] == "fail" for item in supplemental)
                    else "pass" if all(item["outcome"] == "pass" for item in supplemental)
                    else "not_assessed"),
        "criteria": supplemental,
        "reason": ("All reviewed designated critical criteria were assessed"
                   if supplemental and all(item["outcome"] in {"pass", "fail"}
                                           for item in supplemental)
                   else "No additional reviewed critical criteria were designated"
                   if not supplemental else
                   "One or more designated critical criteria remain unassessed"),
    }
    required = [item for item in criteria.values() if isinstance(item, dict)
                and "outcome" in item]
    failures = [item for item in required if item.get("outcome") == "fail"]
    unknown = [item for item in required if item.get("outcome") != "pass"]
    if failures:
        safe.update(outcome="fail", reason="A required safe-completion criterion failed")
    elif task["bounded_task_completion"]["outcome"] != "completed":
        safe.update(outcome="not_assessed",
                    reason="Validated bounded-task completion was not observed")
    elif unknown:
        safe.update(outcome="not_assessed",
                    reason="One or more applicable safe-completion criteria remain unassessed")
    else:
        safe.update(outcome="pass",
                    reason="Task completion and all applicable designated critical criteria passed")
    metric = next((item for item in task_measurement["metrics"]
                   if item.get("metric_id") == "task.safe_completion"), None)
    if metric is not None:
        outcome = safe["outcome"]
        metric.update(
            status="valid" if outcome in {"pass", "fail"} else "unavailable",
            value={"outcome": outcome} if outcome in {"pass", "fail"} else None,
            criterion_outcome=outcome if outcome in {"pass", "fail"} else "not_assessed",
            reason=safe["reason"],
        )
    return safe


def _deadline_support(frames, actors, times, deadline_s, profile):
    if not times or not _finite(times[0]) or not _finite(deadline_s):
        return {"status": "unavailable", "supported": False,
                "reason": "Task deadline or trace timebase is unavailable"}
    cutoff = float(times[0] + deadline_s)
    bracket = next((index for index, value in enumerate(times)
                    if _finite(value) and value >= cutoff), None)
    if bracket is None:
        return {"status": "unavailable", "supported": False,
                "reason": "Trace ended before the explicit task deadline"}
    nominal_dt = profile.values["time"]["nominal_sample_interval_s"]
    for index in range(bracket + 1):
        if not _finite(times[index]) or not _present_pose(actors[index]):
            return {"status": "unavailable", "supported": False,
                    "reason": f"Ego pose/time gap censors deadline assessment at observation {index}"}
        if index:
            prior_frame = frames[index - 1]
            frame = frames[index]
            dt = times[index] - times[index - 1]
            if (not _finite(dt) or dt <= 0 or dt > nominal_dt * 1.5
                    or frame.get("step", index) != prior_frame.get("step", index - 1) + 1
                    or not _same_lifetime(actors[index - 1], actors[index])
                    or (type(actors[index - 1].get("source_valid")) is bool
                        and type(actors[index].get("source_valid")) is bool
                        and actors[index - 1]["source_valid"] != actors[index]["source_valid"])):
                return {"status": "unavailable", "supported": False,
                        "reason": f"Observation gap or ego identity boundary censors deadline at {index}"}
    return {"status": "valid", "supported": True,
            "reason": "Continuous ego pose/time observations span the explicit task deadline",
            "deadline_time_s": cutoff, "last_supported_step": frames[bracket].get("step", bracket)}


def measure_tasks(frames, ego_id, report, profile, exposure, events,
                  task_context: TaskContext | None, *, evidence_refs=(),
                  evaluation_capture=None, evaluation_capture_bound=False,
                  annotation=None):
    """Measure task progress and efficiency from one already-loaded saved trace."""
    masks = exposure.get("observation_masks", ())
    times = ([row.get("time_s") for row in masks] if len(masks) == len(frames)
             else [frame.get("time_s") for frame in frames])
    actors = _actor_rows(frames, ego_id)
    task = task_context or TaskContext("unavailable", "No source task context was supplied")
    evidence_refs = tuple(evidence_refs) + tuple(task.evidence_refs)
    version = profile.definition_version
    annotation = annotation if annotation is not None else _load_annotation(task, profile)
    annotation_problem = None
    if annotation.get("evidence_ref"):
        evidence_refs += (annotation["evidence_ref"],)
    if annotation["status"] == "invalid":
        task = replace(task, status="invalid", reason=annotation["reason"],
                       route_status="invalid", route_reason=annotation["reason"],
                       reference_points=(), route_span_m=None)
    elif annotation["status"] == "valid":
        claim = annotation.get("task_claim")
        claim_values = annotation.get("task_claim_evidence", {}).get(
            claim["claim_id"], []) if claim else []
        task, annotation_problem = _apply_task_claim(task, claim, claim_values)
        if annotation_problem:
            task = replace(task, status="invalid", reason=annotation_problem,
                           route_status="invalid", route_reason=annotation_problem,
                           reference_points=(), route_span_m=None)
    # A caller attaches the checked input evidence references after composition.
    route_metrics, route_output = _route_metric_records(
        frames, actors, times, task, profile, evidence_refs
    )
    stationary_metrics, stationary, intervals = _stationary(
        frames, actors, times, profile, evidence_refs, exposure
    )
    low_metrics = _low_progress(frames, times, route_output, profile, evidence_refs)

    goal_binding = _captured_task_goal_binding(
        evaluation_capture, evaluation_capture_bound, ego_id,
        report.get("ego_binary_index"), task, report, len(frames),
    )
    native_goal = _native_goal(events, exposure, goal_binding)
    geometric_goal = None
    if task.status == "valid" and task.goal_xy and task.completion_radius_m:
        rows = []
        for index, actor in enumerate(actors):
            if _present_pose(actor):
                distance = math.dist((float(actor["x"]), float(actor["y"])), task.goal_xy)
                if distance <= task.completion_radius_m:
                    rows.append({"index": index, "step": frames[index].get("step", index),
                                 "time_s": times[index], "distance_m": float(distance),
                                 "attribution": ("warmup_or_initial_condition"
                                                 if index <= profile.values["time"]["warmup_transitions"]
                                                 else "observed_during_or_after_policy_window")})
        geometric_goal = min(rows, key=lambda row: row["index"]) if rows else None
    native_row = next((row for row in events if row.get("channel") == "goal_reached"), None)
    completion = None
    completion_basis = None
    native_completion = None
    if task.status == "valid":
        if native_row is not None and goal_binding.get("matches") is True:
            event_index = next((index for index, frame in enumerate(frames)
                                if frame.get("step", index) == native_row.get("step")), None)
            native_completion = {"step": native_row.get("step"),
                                 "time_s": native_row.get("time_s"),
                                 "attribution": native_row.get("attribution"),
                                 "index": event_index}
        candidates = []
        if native_completion is not None:
            candidates.append((native_completion, "matched_native_goal_event"))
        if geometric_goal is not None:
            candidates.append((geometric_goal,
                               "observed_position_within_validated_source_goal_radius"))
        if candidates:
            completion, completion_basis = min(
                candidates,
                key=lambda item: (item[0].get("time_s")
                                  if _finite(item[0].get("time_s")) else math.inf,
                                  item[0].get("index", math.inf)),
            )
        deadline_assessment = {"status": "not_applicable", "supported": False,
                               "reason": "No explicit validated task deadline is defined"}
        if task.deadline_s is None:
            if completion is not None:
                outcome, outcome_reason = "completed", "the bounded source goal was observed"
            else:
                terminal_reason = report.get("terminal_reason")
                if terminal_reason == "horizon":
                    unresolved_reason = "horizon/recording end does not define task failure"
                elif terminal_reason:
                    unresolved_reason = f"terminal {terminal_reason} ended before task resolution; no task failure rule applies"
                else:
                    unresolved_reason = "recording ended before task resolution; no task failure rule applies"
                outcome, outcome_reason = "unresolved", unresolved_reason
        else:
            deadline_assessment = _deadline_support(
                frames, actors, times, task.deadline_s, profile
            )
            completion_elapsed = (completion.get("time_s") - times[0]
                                  if completion is not None
                                  and _finite(completion.get("time_s")) and times
                                  and _finite(times[0]) else None)
            if completion is not None and completion_elapsed is None:
                outcome, outcome_reason = (
                    "unresolved", "completion is observed but its time cannot be compared with the explicit deadline")
            elif completion is not None and completion_elapsed <= task.deadline_s:
                outcome, outcome_reason = "completed", "the bounded source goal was observed by its deadline"
                deadline_assessment = {"status": "valid", "supported": True,
                                       "reason": "Observed task completion is at or before the explicit deadline",
                                       "completion_elapsed_s": float(completion_elapsed),
                                       "deadline_s": task.deadline_s}
            elif deadline_assessment["supported"]:
                if completion is not None:
                    outcome = "failed"
                    outcome_reason = "the bounded source goal was observed after its explicit deadline"
                    deadline_assessment["reason"] = outcome_reason
                    deadline_assessment["late_completion_elapsed_s"] = float(completion_elapsed)
                else:
                    outcome = "failed"
                    outcome_reason = "an explicit validated task deadline elapsed without observed completion"
            else:
                outcome = "unresolved"
                outcome_reason = deadline_assessment["reason"]
    else:
        outcome, outcome_reason = "unassessable", task.reason
        deadline_assessment = {"status": "unavailable", "supported": False,
                               "reason": "Task context is unassessable"}

    task_metric = _metric(
        "task.outcome", version,
        status=AssessmentStatus.VALID if task.status == "valid" else
        (AssessmentStatus.INVALID if task.status == "invalid" else AssessmentStatus.UNAVAILABLE),
        reason=outcome_reason,
        value={"outcome": outcome, "reason": outcome_reason,
               "completion_basis": completion_basis,
               "completion_step": completion.get("step") if completion else None,
               "completion_time_s": completion.get("time_s") if completion else None,
               "completion_attribution": completion.get("attribution") if completion else None}
        if task.status == "valid" else None,
        units=None, window="full", evidence_refs=evidence_refs,
        criterion=(CriterionOutcome.PASS if outcome == "completed" else
                   CriterionOutcome.FAIL if outcome == "failed" else CriterionOutcome.NOT_ASSESSED),
    )
    completion_metrics = []
    if completion is not None and _finite(completion.get("time_s")) and times and _finite(times[0]):
        start_time = times[0]
        policy_start = times[profile.values["time"]["warmup_transitions"]] \
            if len(times) > profile.values["time"]["warmup_transitions"] else None
        completion_time = {
            "elapsed_from_first_observation_s": float(completion["time_s"] - start_time),
            "elapsed_from_policy_start_s": (
                float(completion["time_s"] - policy_start)
                if _finite(policy_start) and type(completion.get("index")) is int
                and completion["index"] > profile.values["time"]["warmup_transitions"]
                and completion["time_s"] >= policy_start else None),
            "step": completion.get("step"),
            "time_s": float(completion["time_s"]),
            "completion_basis": completion_basis,
            "attribution": completion.get("attribution"),
        }
        completion_metrics.append(_metric(
            "efficiency.completion_time", version, status=AssessmentStatus.VALID,
            reason="First observed bounded-task completion time on the recorded trace timebase",
            value=completion_time, units="s", window="full", samples=1,
            evidence_refs=evidence_refs,
            limitations=("Completion time is observation time, not a causal action timestamp",),
        ))
    else:
        completion_time = None
        completion_metrics.append(_metric(
            "efficiency.completion_time", version,
            status=(AssessmentStatus.INVALID if task.status == "invalid"
                    else AssessmentStatus.UNAVAILABLE),
            reason=("Task completion time is unavailable because the bounded task was not observed"
                    if task.status == "valid" else task.reason),
            value=None, units="s", window="full", evidence_refs=evidence_refs,
        ))
    requested = report.get("requested_observation_frames")
    terminal_reason = report.get("terminal_reason")
    terminal = {
        "reason": terminal_reason,
        "requested_observation_frames": requested,
        "observed_observation_frames": len(frames),
        "horizon_reached": terminal_reason == "horizon" and len(frames) == requested,
        "ended_before_requested_horizon": type(requested) is int and len(frames) < requested,
        "timeout_status": "observed" if terminal_reason == "horizon" else "not_observed",
        "truncation_status": ("observed_before_requested_horizon"
                               if type(requested) is int and len(frames) < requested
                               else "terminal_reason_recorded" if terminal_reason not in (None, "horizon")
                               else "not_observed"),
        "cause": terminal_reason,
    }
    safe = _safe_completion(outcome, events, exposure)
    if safe["outcome"] == "pass":
        safe_metric_status, safe_criterion, safe_value = (
            AssessmentStatus.VALID, CriterionOutcome.PASS, {"outcome": "pass"})
    elif safe["outcome"] == "fail":
        safe_metric_status, safe_criterion, safe_value = (
            AssessmentStatus.VALID, CriterionOutcome.FAIL, {"outcome": "fail"})
    else:
        safe_metric_status, safe_criterion, safe_value = (
            AssessmentStatus.UNAVAILABLE, CriterionOutcome.NOT_ASSESSED, None)
    safe_metric = _metric(
        "task.safe_completion", version, status=safe_metric_status,
        reason=safe["reason"], value=safe_value, units=None, window="full",
        criterion=safe_criterion, evidence_refs=evidence_refs,
        limitations=("A safe-completion pass requires every applicable critical criterion",
                     "Encounter/rule criteria remain unassessed until PE07/PE08"),
    )
    metrics = (route_metrics + stationary_metrics + low_metrics + completion_metrics
               + [task_metric, safe_metric])
    annotation_summary = {key: value for key, value in annotation.items()
                         if key not in {"claims_data", "task_claim_evidence"}}
    task_result = {
        "context": {**task.summary(), "annotation": annotation_summary,
                    "annotation_application_reason": annotation_problem},
        "native_goal_event": native_goal,
        "deadline_assessment": deadline_assessment,
        "planner_goal_visibility": _planner_goal_visibility(report),
        "bounded_task_completion": {
            "outcome": outcome, "reason": outcome_reason,
            "completion_basis": completion_basis,
            "completion": completion,
            "native_goal_event_is_separate": True,
            "geometric_goal_observation": geometric_goal,
        },
        "encounter_completion": {
            "outcome": "not_assessed",
            "reason": "Actual encounter realization and interaction completion are owned by PE07",
        },
        "safe_completion": safe,
        "completion_time": completion_time,
        "stationary_duration": stationary,
        "low_progress": {
            "confirmed_deadlock": False,
            "assessment": "not_assessed",
            "reason": "Progress opportunity evidence is not established by low progress alone",
        },
        "route_progress": route_output,
        "branch_context": {
            "ambiguous": any(item["branch_ambiguity"]
                             for item in route_output["windows"].values()),
            "smart_goal_visibility_limitation": (
                "SMART has no navigation-goal input; route branch ambiguity cannot alone establish a rule explanation"
                if _planner_goal_visibility(report)["value"] is False else None),
        },
        "terminal": terminal,
        "supported_interval_count": sum(item["dt"] is not None for item in intervals),
    }
    return {"task": task_result, "metrics": metrics}
