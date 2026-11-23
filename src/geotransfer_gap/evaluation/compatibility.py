"""Secondary offline diagnostics and explicitly limited benchmark compatibility.

This module consumes PE01 saved frames and already measured PE02--PE08
evidence.  It has no simulator, model, map-library, or BehaviorBench imports.
"""

from __future__ import annotations

import math
from statistics import median


CORE_CRITERIA = (
    ("bounded_task_completion", "task.outcome"),
    ("safe_completion_core_v1", "task.safe_completion"),
)
CORE_CRITERION_SET_ID = "all_core_v1"
CORE_CRITERION_SET_VERSION = "1.0.0"
BEHAVIORBENCH_REVISION = "805fe04c6977b60c41c92c31f1a5211fbd704f44"
_BB_LEARNED_CONTROLLERS = {"traffic:ppo", "traffic:smart"}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _distribution(values, units, reason):
    values = sorted(float(value) for value in values if _finite(value))
    if not values:
        return {"status": "unavailable", "reason": reason, "value": None,
                "units": units, "sample_count": 0}
    index = (len(values) - 1) * 0.95
    low, high = math.floor(index), math.ceil(index)
    p95 = values[low] if low == high else values[low] * (high - index) + values[high] * (index - low)
    return {
        "status": "valid", "reason": "Finite supported saved observations",
        "value": {"minimum": values[0], "maximum": values[-1],
                  "mean": sum(values) / len(values), "median": float(median(values)),
                  "p95": p95},
        "units": units, "sample_count": len(values),
    }


def _point(actor):
    if (not isinstance(actor, dict) or actor.get("present") is not True
            or not _finite(actor.get("x")) or not _finite(actor.get("y"))):
        return None
    return float(actor["x"]), float(actor["y"])


def _actor_map(frame):
    return {row.get("id"): row for row in frame.get("actors", ())
            if isinstance(row, dict) and type(row.get("id")) is int}


def _trace_time(frame, index, report, nominal_dt):
    value = frame.get("time_s")
    if _finite(value):
        return float(value), "recorded_time_s"
    if report.get("schema_version") == 2:
        step = frame.get("step", index)
        if type(step) is int and step >= 0:
            return float(step * nominal_dt), "inferred_legacy_10hz_step"
    return None, "missing_time"


def _reference_generations(valid, positions):
    generation = -1
    active = False
    result = []
    for source_valid, position in zip(valid, positions):
        usable = source_valid is True and position is not None
        if usable and not active:
            generation += 1
        result.append(generation if usable else None)
        active = usable
    return result


def _reference_exclusions():
    return {"missing_predicted_pose": 0, "missing_reference_time_sample": 0,
            "invalid_reference_pose": 0, "lifetime_mismatch": 0,
            "missing_trace_time": 0, "source_validity_mismatch": 0,
            "missing_predicted_lifetime": 0}


def _measure_reference(frames, ego_id, report, profile, task_context):
    timing = profile.values["time"]
    nominal_dt = timing["nominal_sample_interval_s"]
    warmup = timing["warmup_transitions"]
    last = timing["primary_last_observation_index"]
    reference_positions = getattr(task_context, "reference_positions", ()) if task_context else ()
    reference_valid = getattr(task_context, "reference_valid", ()) if task_context else ()
    source_id = getattr(task_context, "reference_source_id", None) if task_context else None
    source_hash = getattr(task_context, "reference_source_sha256", None) if task_context else None
    task_start = getattr(task_context, "start_source_step", None) if task_context else None
    task_goal = getattr(task_context, "goal_source_step", None) if task_context else None
    context_status = getattr(task_context, "status", None)
    identity_mismatch = context_status == "valid" and (
        type(source_id) is not int or source_id != ego_id
        or type(task_start) is not int or type(task_goal) is not int
        or task_start < 0 or task_goal < task_start
        or (reference_positions and len(reference_positions) != len(reference_valid)))
    if (context_status != "valid" or identity_mismatch or type(source_id) is not int
            or source_id != ego_id or not reference_positions
            or len(reference_positions) != len(reference_valid)):
        reason = (getattr(task_context, "reason", None)
                  if task_context and context_status != "valid"
                  else "Hash-checked task reference ego identity or track shape is inconsistent"
                  if identity_mismatch
                  else "Hash-checked source ego reference track is unavailable")
        unavailable_status = ("invalid" if context_status == "invalid" or identity_mismatch
                              else "unavailable")
        missing = {"status": unavailable_status, "reason": reason,
                   "value": None, "units": "m", "sample_count": 0}
        return {"status": unavailable_status, "reason": reason,
                "provenance": {"kind": "converted_source_ego_track",
                               "source_id": source_id, "sha256": source_hash},
                "alignment": "unavailable", "coverage": {
                    "expected_primary_observations": None, "matched_primary_observations": 0,
                    "fraction": None, "endpoint_supported": False},
                "warmup_coverage": {"expected_warmup_observations": None,
                                    "matched_warmup_observations": 0, "fraction": None},
                "warmup_ade": dict(missing), "ade": dict(missing), "fde": dict(missing),
                "criterion_outcome": "not_assessed"}

    source_generations = _reference_generations(reference_valid, reference_positions)
    matched_by_window = {"warmup": [], "primary": []}
    primary_expected = 0
    observed_primary_steps, observed_warmup_steps = set(), set()
    exclusions = {"warmup": _reference_exclusions(), "primary": _reference_exclusions()}
    outside_task_bounds = 0
    indexed_ego = []
    for index, frame in enumerate(frames):
        step = frame.get("step", index)
        if type(step) is not int:
            continue
        if step < task_start or step > task_goal:
            outside_task_bounds += 1
            continue
        if step < warmup:
            window = "warmup"
        elif step <= last:
            window = "primary"
        else:
            continue
        if window == "primary":
            observed_primary_steps.add(step)
        else:
            observed_warmup_steps.add(step)
        ego = _actor_map(frame).get(ego_id)
        indexed_ego.append((index, frame, ego))

    requested = report.get("requested_observation_frames")
    if type(requested) is int and requested > warmup:
        primary_expected = max(0, min(last, requested - 1, task_goal)
                               - max(warmup, task_start) + 1)
    else:
        primary_expected = len(observed_primary_steps)
    warmup_expected = (max(0, min(warmup - 1, requested - 1, task_goal) - task_start + 1)
                       if type(requested) is int and requested > 0
                       else len(observed_warmup_steps))

    aligned_modes = set()
    for index, frame, ego in indexed_ego:
        step = frame.get("step", index)
        window = "warmup" if step < warmup else "primary"
        window_exclusions = exclusions[window]
        time_s, time_source = _trace_time(frame, index, report, nominal_dt)
        aligned_modes.add(time_source)
        position = _point(ego)
        if position is None:
            window_exclusions["missing_predicted_pose"] += 1
            continue
        if time_s is None:
            window_exclusions["missing_trace_time"] += 1
            continue
        source_index_float = time_s / nominal_dt
        source_index = round(source_index_float)
        if (source_index < 0 or source_index >= len(reference_positions)
                or abs(source_index_float - source_index) > 1e-6):
            window_exclusions["missing_reference_time_sample"] += 1
            continue
        reference_position = reference_positions[source_index]
        if reference_valid[source_index] is not True or reference_position is None:
            window_exclusions["invalid_reference_pose"] += 1
            continue
        if ego.get("source_valid") is False:
            window_exclusions["source_validity_mismatch"] += 1
            continue
        predicted_generation = ego.get("lifetime_generation") if ego else None
        reference_generation = source_generations[source_index]
        if (type(predicted_generation) is int and reference_generation is not None
                and predicted_generation != reference_generation):
            window_exclusions["lifetime_mismatch"] += 1
            continue
        if type(predicted_generation) is not int:
            window_exclusions["missing_predicted_lifetime"] += 1
        error = math.dist(position, reference_position)
        if _finite(error):
            matched_by_window[window].append({"step": step, "time_s": time_s,
                                               "error_m": error,
                                               "predicted_lifetime_generation": predicted_generation,
                                               "reference_lifetime_generation": reference_generation})

    warmup_errors = [row["error_m"] for row in matched_by_window["warmup"]]
    primary_rows = matched_by_window["primary"]
    primary_errors = [row["error_m"] for row in primary_rows]
    if primary_errors:
        ade = {"status": "valid", "reason": "Mean Euclidean error at exact shared timestamps and compatible lifetimes",
               "value": sum(primary_errors) / len(primary_errors), "units": "m",
               "sample_count": len(primary_errors), "criterion_outcome": "not_assessed"}
    else:
        ade = {"status": "unavailable", "reason": "No primary-window observations align to a valid source reference sample",
               "value": None, "units": "m", "sample_count": 0,
               "criterion_outcome": "not_assessed"}
    warmup_ade = (_distribution(warmup_errors, "m", "No warmup reference samples were supported")
                  if warmup_errors else
                  {"status": "unavailable", "reason": "No warmup reference samples were supported",
                   "value": None, "units": "m", "sample_count": 0})
    last_requested_step = (min(requested - 1, last)
                           if type(requested) is int and requested > 0 else None)
    endpoint = next((row for row in reversed(primary_rows)
                     if row["step"] == last_requested_step), None)
    horizon_reached = (report.get("terminal_reason") == "horizon"
                       and type(requested) is int and len(frames) == requested)
    if endpoint is not None and horizon_reached:
        fde = {"status": "valid", "reason": "Prediction and source endpoint both observed at the requested horizon",
               "value": endpoint["error_m"], "units": "m", "sample_count": 1,
               "criterion_outcome": "not_assessed", "step": endpoint["step"],
               "time_s": endpoint["time_s"]}
    else:
        reason = ("Requested horizon is not recorded" if type(requested) is not int else
                  "Requested horizon was not reached" if not horizon_reached else
                  "Fixed primary endpoint lies outside the source task bounds"
                  if last_requested_step is not None
                  and not task_start <= last_requested_step <= task_goal else
                  "Predicted or source reference endpoint is absent, invalid, or lifetime-mismatched")
        fde = {"status": "unavailable", "reason": reason, "value": None,
               "units": "m", "sample_count": 0, "criterion_outcome": "not_assessed",
               "step": last_requested_step}
    total_expected = max(primary_expected, 0)
    coverage = {
        "window": "primary", "expected_primary_observations": total_expected,
        "observed_primary_observations": len(observed_primary_steps),
        "matched_primary_observations": len(primary_rows),
        "fraction": len(primary_rows) / total_expected if total_expected else None,
        "endpoint_supported": endpoint is not None and horizon_reached,
        "exclusions": exclusions["primary"],
    }
    warmup_coverage = {
        "expected_warmup_observations": warmup_expected,
        "observed_warmup_observations": len(observed_warmup_steps),
        "matched_warmup_observations": len(matched_by_window["warmup"]),
        "fraction": (len(matched_by_window["warmup"]) / warmup_expected
                     if warmup_expected else None),
        "exclusions": exclusions["warmup"],
        "outside_source_task_bounds_observations": outside_task_bounds,
    }
    alignment = "exact_timestamp_on_10hz_source_sample_grid_no_interpolation"
    if "inferred_legacy_10hz_step" in aligned_modes:
        alignment += ";_legacy_trace_time_inferred_from_step"
    status = "valid" if ade["status"] == "valid" else "unavailable"
    return {
        "status": status,
        "reason": "Reference deviation is descriptive and does not determine safety or task outcome",
        "provenance": {"kind": "converted_source_ego_track", "source_id": source_id,
                       "sha256": source_hash,
                       "source_sample_period_s": nominal_dt,
                       "task_source_bounds": {"start_inclusive": task_start,
                                              "goal_inclusive": task_goal},
                       "source_identity": getattr(task_context, "identity", None)},
        "alignment": alignment,
        "warmup_attribution": "Warmup observations before transition 10 are reported separately and excluded from primary ADE/FDE",
        "coverage": coverage,
        "warmup_coverage": warmup_coverage,
        "warmup_ade": warmup_ade,
        "ade": ade,
        "fde": fde,
        "matched_samples": primary_rows,
        "criterion_outcome": "not_assessed",
        "limitations": [
            "No interpolation or time warping is used; only exact shared source sample times are matched.",
            "The source expert path is a behavioral reference, not a safe-path oracle.",
            "Partial ADE coverage is reported with its denominator; FDE requires the requested endpoint.",
            "A known predicted lifetime must equal the source-valid segment at the matched time.",
            ("Some aligned predicted rows lacked lifetime metadata; only exact-time stable-source-ID matches were retained."
             if (exclusions["primary"]["missing_predicted_lifetime"]
                 or exclusions["warmup"]["missing_predicted_lifetime"]) else
             "Predicted lifetime generations were present on all aligned samples."),
        ],
    }


def _core_assessment(task, task_metrics=()):
    bounded = task.get("bounded_task_completion") if isinstance(task, dict) else None
    safe = task.get("safe_completion") if isinstance(task, dict) else None
    bounded_outcome = bounded.get("outcome") if isinstance(bounded, dict) else None
    safe_outcome = safe.get("outcome") if isinstance(safe, dict) else None
    metric_statuses = {row.get("metric_id"): row.get("status")
                       for row in task_metrics if isinstance(row, dict)}
    criterion_rows = []
    for criterion_id, source_id, outcome, recognized in (
            (CORE_CRITERIA[0][0], CORE_CRITERIA[0][1], bounded_outcome,
             {"completed": "pass", "failed": "fail"}),
            (CORE_CRITERIA[1][0], CORE_CRITERIA[1][1], safe_outcome,
             {"pass": "pass", "fail": "fail"})):
        source_status = metric_statuses.get(source_id)
        criterion = recognized.get(outcome, "not_assessed") if source_status in (None, "valid") else "not_assessed"
        status = ("valid" if criterion in {"pass", "fail"} else
                  source_status if source_status in {"unavailable", "invalid", "not_applicable", "undefined"}
                  else "unavailable")
        criterion_rows.append({"criterion_id": criterion_id, "source_metric_id": source_id,
                               "outcome": criterion,
                               "status": status,
                               "reason": ("criterion was assessed" if criterion in {"pass", "fail"}
                                          else f"source status/outcome is {source_status!r}/{outcome!r}; required result is unknown")})
    if any(row["outcome"] == "fail" for row in criterion_rows):
        outcome = "fail"
    elif all(row["outcome"] == "pass" for row in criterion_rows):
        outcome = "pass"
    else:
        outcome = "not_assessed"
    value = {"outcome": outcome} if outcome in {"pass", "fail"} else None
    return {
        "status": "valid" if value is not None else "unavailable",
        "reason": ("All fixed All-Core criteria were assessed" if value is not None else
                   "At least one fixed All-Core criterion lacks a valid result"),
        "value": value,
        "criterion_outcome": outcome,
        "criterion_set": {"id": CORE_CRITERION_SET_ID,
                          "version": CORE_CRITERION_SET_VERSION,
                          "required_criteria": [
                              {"criterion_id": item[0], "source_metric_id": item[1]}
                              for item in CORE_CRITERIA]},
        "criteria": criterion_rows,
        "interpretation": "Fixed-set episode assessment; missing criteria remain indeterminate and are not removed",
    }


def _traffic_owner_category(owner):
    if owner == "warmup_replay":
        return "warmup_replay"
    if owner == "source_hold_replay":
        return "source_hold_replay"
    if owner in {"context_replay", "traffic:expert"}:
        return "expert_replay"
    if owner in _BB_LEARNED_CONTROLLERS:
        return "learned_controller"
    if isinstance(owner, str) and owner.startswith("traffic:"):
        return "nonlearned_controller"
    return None


def _traffic_exposure(frames, report, profile, *, window):
    warmup = profile.values["time"]["warmup_transitions"]
    last = profile.values["time"]["primary_last_observation_index"]
    counts = {"warmup_replay": {"transition_actor_pairs": 0, "actor_seconds": 0.0},
              "source_hold_replay": {"transition_actor_pairs": 0, "actor_seconds": 0.0},
              "expert_replay": {"transition_actor_pairs": 0, "actor_seconds": 0.0},
              "learned_controller": {"transition_actor_pairs": 0, "actor_seconds": 0.0},
              "nonlearned_controller": {"transition_actor_pairs": 0, "actor_seconds": 0.0}}
    expected = 0
    unknown = 0
    for index, left_frame in enumerate(frames[:-1]):
        step = left_frame.get("step", index)
        if window == "warmup" and not (type(step) is int and step < warmup):
            continue
        if window == "primary" and not (type(step) is int and warmup <= step < last):
            continue
        right_frame = frames[index + 1]
        left_actors, right_actors = _actor_map(left_frame), _actor_map(right_frame)
        dt = None
        left_time, _ = _trace_time(left_frame, index, report,
                                   profile.values["time"]["nominal_sample_interval_s"])
        right_time, _ = _trace_time(right_frame, index + 1, report,
                                    profile.values["time"]["nominal_sample_interval_s"])
        if left_time is not None and right_time is not None and right_time > left_time:
            dt = right_time - left_time
        for source_id, left in left_actors.items():
            if left.get("role") not in {"traffic", "context"} or left.get("present") is not True:
                continue
            expected += 1
            right = right_actors.get(source_id)
            if (dt is None or left_frame.get("transition_applied") is not True
                    or right is None or right.get("present") is not True):
                continue
            left_gen, right_gen = left.get("lifetime_generation"), right.get("lifetime_generation")
            if ((type(left_gen) is int or type(right_gen) is int) and left_gen != right_gen):
                continue
            if (type(left.get("source_valid")) is bool and type(right.get("source_valid")) is bool
                    and left["source_valid"] != right["source_valid"]):
                continue
            category = _traffic_owner_category(left.get("effective_owner"))
            if category is None:
                unknown += 1
                continue
            counts[category]["transition_actor_pairs"] += 1
            counts[category]["actor_seconds"] += dt
    classified = sum(row["transition_actor_pairs"] for row in counts.values())
    valid = classified > 0
    return {
        "status": "valid" if valid else "unavailable",
        "reason": ("Recorded actor roles, effective owners, and applied transitions support actor-time exposure"
                   if expected else "No typed traffic/context actor transition is available"),
        "units": {"transition_actor_pairs": "actor-transitions", "actor_seconds": "actor-s"},
        "value": counts if valid else None,
        "coverage": {"expected_transition_actor_pairs": expected,
                     "classified_transition_actor_pairs": classified,
                     "unknown_owner_transition_actor_pairs": unknown,
                     "excluded_transition_actor_pairs": expected - classified - unknown,
                     "complete": classified == expected and unknown == 0},
        "interpretation": "Exposure is summed across present non-ego actor lifetimes; replay, source hold and learned owners are distinct",
        "limitations": ["Unapplied or missing transitions and lifetime/source-validity boundaries contribute no actor-time.",
                        "Legacy traces without recorded actor roles/owners do not receive inferred exposure."],
    }


def _traffic_distribution(frames, report, profile, *, window, field):
    warmup = profile.values["time"]["warmup_transitions"]
    last = profile.values["time"]["primary_last_observation_index"]
    values = []
    pose_count = 0
    for index, frame in enumerate(frames):
        step = frame.get("step", index)
        if window == "warmup" and not (type(step) is int and step < warmup):
            continue
        if window == "primary" and not (type(step) is int and warmup <= step <= last):
            continue
        for actor in _actor_map(frame).values():
            if actor.get("role") not in {"traffic", "context"} or actor.get("present") is not True:
                continue
            if _point(actor) is None:
                continue
            pose_count += 1
            if field == "speed_m_s":
                if _finite(actor.get("vx")) and _finite(actor.get("vy")):
                    values.append(math.hypot(actor["vx"], actor["vy"]))
    summary = _distribution(values, "m/s", "No finite traffic velocity observations")
    summary["coverage"] = {"present_pose_observations": pose_count,
                            "finite_velocity_observations": len(values),
                            "fraction": len(values) / pose_count if pose_count else None}
    summary["window"] = window
    return summary


def _traffic_acceleration(frames, report, profile, *, window):
    warmup = profile.values["time"]["warmup_transitions"]
    last = profile.values["time"]["primary_last_observation_index"]
    nominal = profile.values["time"]["nominal_sample_interval_s"]
    values = []
    expected = 0
    exclusions = {"missing_time_or_velocity": 0, "unapplied_transition": 0,
                  "lifetime_or_source_boundary": 0, "owner_boundary": 0,
                  "interval_exceeds_derivative_support": 0}
    for index, left_frame in enumerate(frames[:-1]):
        step = left_frame.get("step", index)
        if window == "warmup" and not (type(step) is int and step < warmup):
            continue
        if window == "primary" and not (type(step) is int and warmup <= step < last):
            continue
        right_frame = frames[index + 1]
        right_actors = _actor_map(right_frame)
        left_time, _ = _trace_time(left_frame, index, report, nominal)
        right_time, _ = _trace_time(right_frame, index + 1, report, nominal)
        for source_id, left in _actor_map(left_frame).items():
            if left.get("role") not in {"traffic", "context"} or left.get("present") is not True:
                continue
            expected += 1
            right = right_actors.get(source_id)
            if (right is None or left_time is None or right_time is None or right_time <= left_time
                    or not all(_finite(actor.get(name)) for actor in (left, right)
                               for name in ("vx", "vy"))):
                exclusions["missing_time_or_velocity"] += 1
                continue
            if left_frame.get("transition_applied") is not True:
                exclusions["unapplied_transition"] += 1
                continue
            left_gen, right_gen = left.get("lifetime_generation"), right.get("lifetime_generation")
            if ((type(left_gen) is int or type(right_gen) is int) and left_gen != right_gen
                    or type(left.get("source_valid")) is bool
                    and type(right.get("source_valid")) is bool
                    and left["source_valid"] != right["source_valid"]):
                exclusions["lifetime_or_source_boundary"] += 1
                continue
            if left.get("effective_owner") != right.get("effective_owner"):
                exclusions["owner_boundary"] += 1
                continue
            dt = right_time - left_time
            if dt > 1.5 * nominal:
                exclusions["interval_exceeds_derivative_support"] += 1
                continue
            values.append(math.hypot(right["vx"] - left["vx"], right["vy"] - left["vy"]) / dt)
    summary = _distribution(values, "m/s^2", "No valid same-lifetime traffic acceleration intervals")
    summary["coverage"] = {"expected_actor_intervals": expected,
                            "valid_acceleration_intervals": len(values),
                            "fraction": len(values) / expected if expected else None,
                            "exclusions": exclusions}
    summary["window"] = window
    return summary


def _traffic_gap(safety_metrics, window):
    metric = next((row for row in safety_metrics
                   if row.get("metric_id") == "safety.footprint_clearance"
                   and row.get("window") == window), None)
    if not metric or metric.get("status") != "valid":
        return {"status": metric.get("status", "unavailable") if metric else "unavailable",
                "reason": metric.get("reason", "PE04 clearance evidence was not emitted") if metric else
                "PE04 clearance evidence was not emitted", "value": None, "units": "m",
                "sample_count": 0, "source_metric_id": "safety.footprint_clearance"}
    sample_rows = (metric.get("value") or {}).get("samples", [])
    values = [row.get("clearance_m") for row in sample_rows if isinstance(row, dict)]
    result = _distribution(values, "m", "PE04 has no finite footprint-clearance observations")
    result.update(window=window, source_metric_id="safety.footprint_clearance",
                  coverage=(metric.get("value") or {}).get("coverage"),
                  interpretation="Existing PE04 minimum ego-to-present-actor footprint gap; not recomputed")
    return result


def _benchmark_compatibility(safety_metrics):
    native = []
    for metric_id in ("safety.native_vehicle_collision_onsets", "safety.native_offroad_onsets"):
        row = next((item for item in safety_metrics
                    if item.get("metric_id") == metric_id and item.get("window") == "full"), None)
        native.append({"metric_id": metric_id,
                       "status": row.get("status", "unavailable") if row else "unavailable",
                       "reason": row.get("reason", "PE03 native observation was not emitted") if row else
                       "PE03 native observation was not emitted",
                       "value": row.get("value") if row and row.get("status") == "valid" else None,
                       "evidence_refs": row.get("evidence_refs", []) if row else []})
    return {
        "behaviorbench": {
            "status": "unavailable", "compatibility_level": "unavailable",
            "upstream_revision_reviewed": BEHAVIORBENCH_REVISION,
            "wosac_score": {"status": "unavailable", "value": None,
                            "reason": "The pinned WOSAC metametric requires benchmark ground-truth distribution references, aligned multi-rollout feature histograms, and the nine configured likelihood components; this saved episode supplies none of that benchmark context."},
            "fault_classification": {"status": "unavailable", "value": None,
                                     "reason": "The pinned collision classifier's approach/stopped/lane-drift heuristic is not native ground truth; required preceding poses, lane context, and event logs are not universally bound to historical traces."},
            "supported_native_diagnostics": native,
            "differences": [
                "Pinned WOSAC evaluator fixes 91 observations and defaults to 10 initialization steps and 32 rollouts; GeoTransfer does not claim those benchmark semantics.",
                "No WOSAC likelihood or metametric is inferred from GeoTransfer safety metrics.",
                "Pinned BB metrics contain -1/infinity and zero defaults; those sentinel conventions are not imported or used.",
            ],
        },
        "nuplan_closed_loop": {
            "status": "unavailable", "compatibility_level": "unavailable",
            "value": None,
            "reason": "No faithful or fully specified adapted nuPlan closed-loop score can be derived without nuPlan map, route, drivable-area, rule, and scorer-context evidence.",
            "formula": None,
        },
    }


def measure_secondary(frames, ego_id, report, profile, *, task_context=None,
                      task_result=None, task_metrics=(), safety_metrics=()):
    """Measure P2 diagnostics from saved evidence; never emit benchmark placeholders."""
    frames = list(frames)
    reference = _measure_reference(frames, ego_id, report, profile, task_context)
    all_core = _core_assessment(task_result if isinstance(task_result, dict) else {}, task_metrics)
    windows = ("full", "warmup", "primary")
    traffic = {
        "status": "valid" if any(
            actor.get("role") in {"traffic", "context"}
            for frame in frames for actor in frame.get("actors", ())
            if isinstance(actor, dict)) else "unavailable",
        "interpretation": "Saved traffic plausibility diagnostics only; no human-realism or WOSAC claim",
        "speed_m_s": {window: _traffic_distribution(frames, report, profile,
                                                     window=window, field="speed_m_s")
                      for window in windows},
        "acceleration_m_s2": {window: _traffic_acceleration(frames, report, profile,
                                                              window=window)
                              for window in windows},
        "nearest_ego_footprint_gap_m": {window: _traffic_gap(safety_metrics, window)
                                         for window in ("full", "primary")},
        "owner_exposure": {window: _traffic_exposure(frames, report, profile, window=window)
                           for window in ("full", "warmup", "primary")},
        "limitations": [
            "Velocity and acceleration are saved-state observations; unsupported intervals are excluded.",
            "Gap distribution reuses PE04 oriented-footprint clearance for the ego and closest present actor, not every traffic pair.",
            "Owner exposure sums actor-seconds and requires recorded role, effective owner, and applied transitions.",
        ],
    }
    return {
        "schema_version": 1,
        "reference_deviation": reference,
        "all_core_pass_rate": all_core,
        "traffic_plausibility": traffic,
        "benchmark_compatibility": _benchmark_compatibility(safety_metrics),
        "provenance": {"profile_definition": profile.definition_version,
                       "compatibility_code": "geotransfer_p2_secondary_v1"},
    }
