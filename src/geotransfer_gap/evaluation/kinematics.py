"""Observed episode exposure and raw state-based ego kinematics."""

from __future__ import annotations

import math
from statistics import median

from geotransfer_gap.evaluation.contracts import AssessmentStatus, CriterionOutcome, MetricResult


_KINEMATICS = (
    ("trajectory.speed", "m/s"),
    ("trajectory.acceleration_longitudinal", "m/s^2"),
    ("trajectory.acceleration_lateral", "m/s^2"),
    ("trajectory.yaw_rate", "rad/s"),
    ("trajectory.yaw_acceleration", "rad/s^2"),
    ("trajectory.jerk_longitudinal", "m/s^3"),
    ("trajectory.jerk_world_norm", "m/s^3"),
)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _quantile(values, probability):
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    fraction = position - low
    return float(ordered[low] * (1 - fraction) + ordered[low + 1] * fraction)


def _distribution(values):
    return {
        "minimum": float(min(values)),
        "maximum": float(max(values)),
        "mean": float(sum(values) / len(values)),
        "median": float(median(values)),
        "p95": _quantile(values, 0.95),
    }


def _rows(frames, ego_id):
    return [(frame, next((row for row in frame.get("actors", ())
                          if row.get("id") == ego_id), None))
            for frame in frames]


def _owner(actor):
    value = actor.get("effective_owner") if actor else None
    return value if isinstance(value, str) and value else None


def _lifetime(actor):
    value = actor.get("lifetime_generation") if actor else None
    return value if type(value) is int and value >= 0 else None


def _present(actor):
    return bool(actor and actor.get("present") is True)


def _pose(actor):
    return _present(actor) and _number(actor.get("x")) and _number(actor.get("y"))


def _velocity(actor):
    return _present(actor) and _number(actor.get("vx")) and _number(actor.get("vy"))


def _heading(actor):
    return _present(actor) and _number(actor.get("heading"))


def _same_interval_owner(first, second):
    return _owner(first["left"]) == _owner(second["left"])


def _times(rows, schema_version, nominal_dt):
    supplied = [frame.get("time_s") for frame, _ in rows]
    if supplied and all(value is None for value in supplied) and schema_version == 2:
        # The retained flat expert/SMART producer sampled on the 10 Hz native
        # evaluation clock. Keep this inferred timebase explicit in the result.
        return [float(frame.get("step", i)) * nominal_dt
                for i, (frame, _) in enumerate(rows)], "inferred_legacy_10hz_step"
    if supplied and all(_number(value) for value in supplied):
        return [float(value) for value in supplied], "recorded_time_s"
    return [float(value) if _number(value) else None for value in supplied], "partial_or_unavailable"


def _intervals(rows, times):
    intervals = []
    for index in range(max(0, len(rows) - 1)):
        frame, left = rows[index]
        _, right = rows[index + 1]
        reasons = []
        if times[index] is None or times[index + 1] is None:
            reasons.append("missing_time")
            dt = None
        else:
            dt = times[index + 1] - times[index]
            if not _number(dt) or dt <= 0:
                reasons.append("nonincreasing_time")
                dt = None
        applied = frame.get("transition_applied")
        if applied is False:
            reasons.append("transition_not_applied")
            dt = None
        if left is None or right is None:
            reasons.append("missing_observation")
        elif not _present(left) or not _present(right):
            reasons.append("actor_not_present")
        elif (_lifetime(left) is not None and _lifetime(right) is not None
              and _lifetime(left) != _lifetime(right)):
            reasons.append("lifetime_boundary")
        elif (type(left.get("source_valid")) is bool
              and type(right.get("source_valid")) is bool
              and left["source_valid"] != right["source_valid"]):
            reasons.append("source_validity_boundary")
        intervals.append({
            "index": index,
            "dt": float(dt) if dt is not None else None,
            "mid": float((times[index] + times[index + 1]) / 2)
            if dt is not None else None,
            "left": left,
            "right": right,
            "reasons": reasons,
            "applied": applied,
            "inferred_transition": applied is None,
        })
    return intervals


def _exclusion_counts(intervals):
    counts = {}
    for interval in intervals:
        for reason in interval["reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _sample(step, time_s, value, actor, *, exposure_s=None, stencil_steps=None,
            support_kind="observation"):
    return {
        "step": step,
        "time_s": float(time_s) if time_s is not None else None,
        "value": float(value),
        "exposure_s": float(exposure_s) if exposure_s is not None else None,
        "stencil_steps": stencil_steps,
        "support_kind": support_kind,
        "lifetime_generation": _lifetime(actor),
        "effective_owner": _owner(actor),
    }


def _make_metric(metric_id, definition_version, samples, units, window, *,
                 no_data_status, no_data_reason, no_data_exclusions=None,
                 threshold=None, absolute=False, extra_limitations=(), actors=()):
    if not samples:
        return MetricResult(
            metric_id, definition_version, no_data_status, no_data_reason, None, units,
            CriterionOutcome.NOT_ASSESSED, eligible_samples=0,
            eligible_duration_s=None, window=window, actors=actors,
            limitations=(tuple(f"excluded_{key}={value}" for key, value
                               in sorted((no_data_exclusions or {}).items()) if value)
                         + tuple(extra_limitations)),
        )
    values = [row["value"] for row in samples]
    supported_durations = [row["exposure_s"] for row in samples
                           if row["exposure_s"] is not None]
    eligible_duration = sum(supported_durations) if supported_durations else None
    result = {"distribution": _distribution(values), "samples": samples}
    if threshold is not None:
        exceeds = [row for row in samples
                   if (abs(row["value"]) if absolute else row["value"]) > threshold]
        result.update({
            "threshold": float(threshold),
            "exceedance_samples": len(exceeds),
            "exceedance_sample_fraction": float(len(exceeds) / len(samples)),
            "exceedance_duration_s": float(sum(row["exposure_s"] or 0.0 for row in exceeds)),
            "duration_method": "supported_sample_exposure_sum",
        })
    limitations = (tuple(f"excluded_{key}={value}" for key, value
                         in sorted((no_data_exclusions or {}).items()) if value)
                   + tuple(extra_limitations))
    return MetricResult(
        metric_id, definition_version, AssessmentStatus.VALID,
        "Measured from supported observed states", result, units,
        CriterionOutcome.NOT_ASSESSED, eligible_samples=len(samples),
        eligible_duration_s=float(eligible_duration) if eligible_duration is not None else None,
        window=window, actors=actors, limitations=limitations,
    )


def _summary_metric(metric_id, version, *, status, reason, value, units, window,
                    eligible_samples=None, eligible_duration_s=None, limitations=(), actors=()):
    return MetricResult(metric_id, version, status, reason, value, units,
                        CriterionOutcome.NOT_ASSESSED,
                        eligible_samples=eligible_samples,
                        eligible_duration_s=eligible_duration_s,
                        window=window, actors=actors, limitations=tuple(limitations))


def _exclusions_text(values):
    return tuple(f"excluded_{name}={count}" for name, count in sorted(values.items()) if count)


def _ownership_segments(rows, times, intervals):
    """Expose contiguous ego identity/owner/source-valid runs from saved rows."""
    masks = []
    for index, (frame, actor) in enumerate(rows):
        masks.append({
            "step": frame.get("step", index),
            "time_s": times[index],
            "actor_recorded": actor is not None,
            "present": actor.get("present") if actor else None,
            "pose_observed": bool(actor and _pose(actor)),
            "velocity_observed": bool(actor and _velocity(actor)),
            "heading_observed": bool(actor and _heading(actor)),
            "lifetime_generation": _lifetime(actor),
            "lifetime_metadata_known": _lifetime(actor) is not None,
            "effective_owner": _owner(actor),
            "owner_metadata_known": _owner(actor) is not None,
            "source_valid": actor.get("source_valid") if actor else None,
        })

    segments = []
    current = None
    previous_key = None
    for index, (frame, actor) in enumerate(rows):
        if actor is None:
            key = None
        else:
            key = (_owner(actor), _lifetime(actor), actor.get("present"),
                   actor.get("source_valid") if type(actor.get("source_valid")) is bool else None)
        boundary = key != previous_key
        if current is None or boundary:
            reason = None
            if index:
                prior_actor = rows[index - 1][1]
                if actor is None or prior_actor is None:
                    reason = "missing_actor_observation"
                elif _lifetime(actor) != _lifetime(prior_actor) and (
                        _lifetime(actor) is not None or _lifetime(prior_actor) is not None):
                    reason = "lifetime_change_or_unknown_boundary"
                elif _owner(actor) != _owner(prior_actor):
                    reason = "effective_owner_change_or_unknown_boundary"
                elif actor.get("source_valid") != prior_actor.get("source_valid"):
                    reason = "source_validity_gap_or_reentry"
                elif actor.get("present") != prior_actor.get("present"):
                    reason = "presence_change"
            current = {
                "segment_index": len(segments),
                "start_step": frame.get("step", index),
                "end_step": frame.get("step", index),
                "start_time_s": times[index],
                "end_time_s": times[index],
                "effective_owner": _owner(actor),
                "owner_status": "known" if _owner(actor) is not None else "unknown",
                "lifetime_generation": _lifetime(actor),
                "lifetime_status": "known" if _lifetime(actor) is not None else "unknown_contiguous_source_id",
                "source_valid": actor.get("source_valid") if actor else None,
                "present": actor.get("present") if actor else None,
                "observation_count": 0,
                "applied_transitions": 0,
                "observed_duration_s": 0.0,
                "owned_interval_end_step": None,
                "owned_interval_end_time_s": None,
                "unrecorded_transitions": 0,
                "boundary_before": reason,
            }
            segments.append(current)
        current["end_step"] = frame.get("step", index)
        current["end_time_s"] = times[index]
        current["observation_count"] += 1
        if index < len(intervals):
            interval = intervals[index]
            if interval["dt"] is not None and not interval["reasons"] and key is not None:
                current["observed_duration_s"] += interval["dt"]
                current["applied_transitions"] += interval["applied"] is True
                current["unrecorded_transitions"] += interval["applied"] is None
                current["owned_interval_end_step"] = rows[index + 1][0].get("step", index + 1)
                current["owned_interval_end_time_s"] = times[index + 1]
        previous_key = key
    return masks, segments


def _native_goal_counter_delta(previous, current, previous_frame):
    """Return an assessable cumulative-counter delta for one applied transition."""
    if previous_frame.get("transition_applied") is not True:
        return 0.0
    if (not isinstance(previous, dict) or not isinstance(current, dict)
            or previous.get("status") != "observed"
            or current.get("status") != "observed"
            or previous.get("slot_mapping_verified") is not True
            or current.get("slot_mapping_verified") is not True
            or previous.get("controller_eligible") is not True
            or type(previous.get("slot")) is not int
            or current.get("slot") != previous.get("slot")
            or previous.get("source_id") != current.get("source_id")
            or previous.get("binary_index") != current.get("binary_index")
            or type(previous.get("lifetime_generation")) is not int
            or previous.get("lifetime_generation") != current.get("lifetime_generation")
            or not _number(previous.get("value")) or not _number(current.get("value"))):
        return None
    return float(current["value"] - previous["value"])


def _event_rows(rows, times, report, warmup, last, *,
                evaluation_capture=None, evaluation_capture_bound=False):
    events = []
    channels = ("collision_state", "reached_goal")
    coverage = {"windows": {}}
    counter_observations = None
    if (evaluation_capture_bound and isinstance(evaluation_capture, dict)
            and evaluation_capture.get("schema_version") == 2
            and isinstance(evaluation_capture.get("observations"), list)
            and len(evaluation_capture["observations"]) == len(rows)):
        counter_observations = [row.get("ego_goal_counter")
                                for row in evaluation_capture["observations"]]
    for window in ("full", "primary"):
        selected = [(frame, actor) for i, (frame, actor) in enumerate(rows)
                    if window == "full" or warmup <= i <= last]
        details = {"observation_count": len(selected), "channels": {}}
        for channel in channels:
            count = sum(actor is not None and (
                type(actor.get(channel)) is bool if channel == "reached_goal"
                else type(actor.get(channel)) is int
            ) for _, actor in selected)
            details["channels"][channel] = {
                "status": "valid" if count else "unavailable",
                "observations_with_field": count if count else None,
                "observation_count": len(selected),
                "fraction": float(count / len(selected)) if count and selected else None,
            }
        if counter_observations is not None:
            selected_indices = [index for index in range(len(rows))
                                if window == "full" or warmup <= index <= last]
            selected_counters = [counter_observations[index] for index in selected_indices]
            valid_count = sum(isinstance(item, dict)
                              and item.get("status") == "observed"
                              and item.get("slot_mapping_verified") is True
                              for item in selected_counters)
            expected_transitions = assessable_transitions = 0
            for left_index, right_index in zip(selected_indices, selected_indices[1:]):
                if right_index != left_index + 1:
                    continue
                if rows[left_index][0].get("transition_applied") is True:
                    expected_transitions += 1
                    delta = _native_goal_counter_delta(
                        counter_observations[left_index],
                        counter_observations[right_index], rows[left_index][0],
                    )
                    assessable_transitions += delta is not None
            complete = (valid_count == len(selected_indices)
                        and assessable_transitions == expected_transitions)
            initial = selected_counters[0] if selected_counters else None
            initial_value = (float(initial["value"])
                             if isinstance(initial, dict) and initial.get("status") == "observed"
                             and _number(initial.get("value")) else None)
            details["channels"]["native_goal_counter"] = {
                "status": "valid" if complete else "unavailable",
                "observations_with_field": valid_count if valid_count else None,
                "observation_count": len(selected_indices),
                "fraction": (float(valid_count / len(selected_indices))
                             if valid_count and selected_indices else None),
                "assessable_applied_transition_count": assessable_transitions,
                "expected_applied_transition_count": expected_transitions,
                "initial_value": initial_value,
                "left_censored_initial_active": bool(initial_value is not None
                                                     and initial_value > 0),
            }
        coverage["windows"][window] = details
    for index, (frame, actor) in enumerate(rows):
        if actor is None:
            continue
        step = frame.get("step", index)
        flags = (
            ("native_vehicle_collision", actor.get("collision_state"), {1}, "collision_state"),
            ("native_offroad", actor.get("collision_state"), {2}, "collision_state"),
            ("goal_reached", actor.get("reached_goal"), {True}, "reached_goal"),
        )
        for channel, observed, active_values, flag_key in flags:
            if ((flag_key == "collision_state" and type(observed) is not int)
                    or (flag_key == "reached_goal" and type(observed) is not bool)
                    or observed not in active_values):
                continue
            prior = rows[index - 1][1] if index else None
            same_actor = prior is not None and prior.get("id") == actor.get("id")
            same_lifetime = (same_actor and
                             (_lifetime(prior) == _lifetime(actor)
                              or _lifetime(prior) is None or _lifetime(actor) is None))
            prior_value = (prior.get("reached_goal") if channel == "goal_reached"
                           else prior.get("collision_state")) if same_lifetime else None
            prior_has_valid_flag = (
                type(prior_value) is bool if flag_key == "reached_goal"
                else type(prior_value) is int
            ) if same_lifetime else False
            prior_active = prior_value in active_values if prior_has_valid_flag else None
            if prior_active is True:
                continue
            if index == 0:
                observed_as, attribution = "active_at_first_observation", "initial_condition"
            elif index <= warmup:
                observed_as = "newly_observed_during_warmup" if prior_active is False else "active_after_unknown_prior"
                attribution = "warmup_or_initial_condition"
            else:
                observed_as = "newly_observed_onset" if prior_active is False else "active_after_unknown_prior"
                previous_frame = rows[index - 1][0]
                owner = _owner(prior) if prior else None
                attribution = ("recorded_controlled_transition"
                               if previous_frame.get("transition_applied") is True
                               and owner and owner.startswith("ego:")
                               and prior_active is False else "unattributed")
            events.append({
                "event_id": f"{channel}:{actor['id']}:{_lifetime(actor)}:{step}",
                "channel": channel,
                "observation": observed_as,
                "attribution": attribution,
                "step": step,
                "time_s": times[index],
                "actor": {"source_id": actor["id"],
                          "lifetime_generation": _lifetime(actor),
                          "binary_index": actor.get("binary_index")},
                "pose_present": _present(actor),
                "evidence": "trace_native_state_or_goal_flag",
                "cause_established": False,
            })
    if counter_observations is not None:
        by_step_and_actor = {(row.get("step"), row.get("actor", {}).get("source_id"),
                              row.get("actor", {}).get("lifetime_generation")): row
                             for row in events if row.get("channel") == "goal_reached"}
        for index in range(1, min(len(rows), len(counter_observations))):
            previous_counter = counter_observations[index - 1]
            current_counter = counter_observations[index]
            delta = _native_goal_counter_delta(previous_counter, current_counter,
                                               rows[index - 1][0])
            if delta is None or delta <= 0:
                continue
            step = rows[index][0].get("step", index)
            source_id = current_counter["source_id"]
            generation = current_counter["lifetime_generation"]
            existing = by_step_and_actor.get((step, source_id, generation))
            if existing is not None:
                existing["evidence"] = "trace_native_goal_flag_and_goal_counter_increment"
                existing["native_goal_counter_delta"] = delta
                existing["native_goal_counter_before"] = float(previous_counter["value"])
                existing["native_goal_counter_after"] = float(current_counter["value"])
                continue
            previous_frame, previous_actor = rows[index - 1]
            owner = _owner(previous_actor) if previous_actor else None
            if index <= warmup:
                observation, attribution = "newly_observed_during_warmup", "warmup_or_initial_condition"
            elif previous_frame.get("transition_applied") is True and owner and owner.startswith("ego:"):
                observation, attribution = "newly_observed_onset", "recorded_controlled_transition"
            else:
                observation, attribution = "newly_observed_onset", "unattributed"
            event = {
                "event_id": f"goal_reached:{source_id}:{generation}:{step}",
                "channel": "goal_reached", "observation": observation,
                "attribution": attribution, "step": step, "time_s": times[index],
                "actor": {"source_id": source_id,
                          "lifetime_generation": generation,
                          "binary_index": current_counter["binary_index"]},
                "pose_present": _present(rows[index][1]),
                "evidence": "hash_bound_native_goals_reached_counter_increment",
                "native_goal_counter_delta": delta,
                "native_goal_counter_before": float(previous_counter["value"]),
                "native_goal_counter_after": float(current_counter["value"]),
                "cause_established": False,
            }
            events.append(event)
            by_step_and_actor[(step, source_id, generation)] = event
    terminal = report.get("terminal_reason")
    if terminal not in (None, "horizon"):
        frame, actor = rows[-1] if rows else ({}, None)
        index = len(rows) - 1
        events.append({
            "event_id": f"terminal:{terminal}:{frame.get('step', index)}",
            "channel": "trace_terminal", "observation": "terminal_recorded",
            "attribution": "terminal_status_only", "step": frame.get("step", index),
            "time_s": times[-1] if times else None,
            "actor": None if actor is None else {
                "source_id": actor.get("id"),
                "lifetime_generation": _lifetime(actor),
                "binary_index": actor.get("binary_index"),
            },
            "pose_present": _present(actor), "terminal_reason": terminal,
            "evidence": "trace_terminal_reason", "cause_established": False,
        })
    return events, coverage


def measure_kinematics(frames, ego_id, report, profile, *,
                       evaluation_capture=None, evaluation_capture_bound=False):
    """Calculate PE02 metrics from saved states; no simulator imports or calls."""
    profile_values = profile.values
    version = profile_values["profile"]["definition_version"]
    timing = profile_values["time"]
    rows = _rows(frames, ego_id)
    times, time_source = _times(rows, report.get("schema_version"), timing["nominal_sample_interval_s"])
    intervals = _intervals(rows, times)
    observation_masks, owner_segments = _ownership_segments(rows, times, intervals)
    warmup = timing["warmup_transitions"]
    last = timing["primary_last_observation_index"]
    count = len(rows)
    metrics = []
    exposure = {
        "time_source": time_source,
        "transition_counts": {
            "applied": sum(frame.get("transition_applied") is True for frame, _ in rows[:-1]),
            "unrecorded": sum(frame.get("transition_applied") is None for frame, _ in rows[:-1]),
            "not_applied": sum(frame.get("transition_applied") is False for frame, _ in rows[:-1]),
            "observed_adjacent_intervals": max(0, count - 1),
        },
        "windows": {},
        "effective_owner_segments": owner_segments,
        "observation_masks": observation_masks,
    }

    for window in ("full", "primary"):
        selected_indices = [i for i in range(count)
                            if window == "full" or warmup <= i <= last]
        window_actors = tuple(sorted(
            {(ego_id, _lifetime(rows[i][1])) for i in selected_indices if rows[i][1] is not None},
            key=lambda item: (item[0], -1 if item[1] is None else item[1]),
        ))
        selected_intervals = [item for item in intervals
                              if window == "full" or warmup <= item["index"] < last]
        usable_time = [item for item in selected_intervals if item["dt"] is not None]
        structural = _exclusion_counts(selected_intervals)
        pose_exclusions = dict(structural)
        pose_exclusions["missing_pose"] = sum(
            item["dt"] is not None and not item["reasons"]
            and not (_pose(item["left"]) and _pose(item["right"]))
            for item in selected_intervals
        )
        recorded_duration = sum(item["dt"] for item in usable_time)
        # Stable, present pose support: a gap, disappearance, generation switch
        # or source-validity switch breaks the interval rather than being bridged.
        pose_intervals = [item for item in usable_time if not item["reasons"]
                          and _pose(item["left"]) and _pose(item["right"])]
        pose_distance = [math.hypot(item["right"]["x"] - item["left"]["x"],
                                    item["right"]["y"] - item["left"]["y"])
                         for item in pose_intervals]
        controlled = [item for item in usable_time if not item["reasons"]
                      and item["applied"] is True
                      and warmup <= item["index"] <= last
                      and _owner(item["left"]) is not None
                      and _owner(item["left"]).startswith("ego:")]
        timed_support = bool(usable_time)
        summary = {
            "observation_count": len(selected_indices),
            "recorded_interval_count": len(usable_time) if timed_support else None,
            "recorded_duration_s": float(recorded_duration) if timed_support else None,
            "transition_count": sum(item["applied"] is True for item in selected_intervals),
            "transition_count_status": "valid" if report.get("schema_version") == 3 else "unknown_for_legacy",
            "unknown_transition_count": sum(item["inferred_transition"] for item in selected_intervals),
            "controlled_transition_count": len(controlled) if controlled else None,
            "controlled_duration_s": float(sum(item["dt"] for item in controlled)) if controlled else None,
            "pose_interval_count": len(pose_intervals) if pose_intervals else None,
            "pose_duration_s": float(sum(item["dt"] for item in pose_intervals)) if pose_intervals else None,
            "pose_interval_exclusions": pose_exclusions,
            "observed_distance_m": float(sum(pose_distance)) if pose_distance else None,
            "interval_exclusions": structural,
            "requested_horizon_reached": report.get("terminal_reason") == "horizon"
            and count == report.get("requested_observation_frames", count),
            "ended_before_requested_horizon": count < report.get("requested_observation_frames", count),
            "post_terminal_trajectory_unobserved": report.get("terminal_reason") not in (None, "horizon"),
        }
        exposure["windows"][window] = summary

        if timed_support:
            metrics.append(_summary_metric(
                "exposure.recorded_duration", version, status=AssessmentStatus.VALID,
                reason="Sum of valid adjacent observed intervals; no final unrecorded transition is added",
                value={"duration_s": float(recorded_duration),
                       "interval_count": len(usable_time),
                       "applied_transitions": sum(item["applied"] is True for item in usable_time),
                       "adjacent_transition_unknown": sum(item["inferred_transition"] for item in usable_time)},
                units="s", window=window, eligible_samples=len(usable_time),
                eligible_duration_s=float(recorded_duration),
                limitations=(_exclusions_text(structural)
                             + (("Legacy traces do not record transition application",)
                                if exposure["transition_counts"]["unrecorded"] else ())),
                actors=window_actors,
            ))
        else:
            metrics.append(_summary_metric(
                "exposure.recorded_duration", version, status=AssessmentStatus.UNAVAILABLE,
                reason="No adjacent valid timestamps support elapsed exposure", value=None,
                units="s", window=window, actors=window_actors,
            ))

        if controlled:
            controlled_duration = sum(item["dt"] for item in controlled)
            metrics.append(_summary_metric(
                "exposure.controlled_duration", version, status=AssessmentStatus.VALID,
                reason="Known applied ego-owned intervals with stable ownership",
                value={"duration_s": float(controlled_duration), "transition_count": len(controlled),
                       "attribution": "recorded_effective_owner"},
                units="s", window=window, eligible_samples=len(controlled),
                eligible_duration_s=float(controlled_duration),
                limitations=_exclusions_text(structural), actors=window_actors,
            ))
        elif report.get("schema_version") == 2:
            metrics.append(_summary_metric(
                "exposure.controlled_duration", version, status=AssessmentStatus.UNAVAILABLE,
                reason="Legacy trace does not record applied transitions or effective ownership",
                value=None, units="s", window=window, actors=window_actors,
            ))
        elif not timed_support:
            metrics.append(_summary_metric(
                "exposure.controlled_duration", version, status=AssessmentStatus.UNAVAILABLE,
                reason="No timed interval supports controller exposure", value=None,
                units="s", window=window, actors=window_actors,
            ))
        else:
            metrics.append(_summary_metric(
                "exposure.controlled_duration", version, status=AssessmentStatus.UNAVAILABLE,
                reason="No stable present ego-owned applied interval is supported", value=None,
                units="s", window=window,
                limitations=("Absent states, lifetime gaps and ownership handovers are excluded",),
                actors=window_actors,
            ))

        if pose_intervals:
            pose_duration = sum(item["dt"] for item in pose_intervals)
            limitations = _exclusions_text(pose_exclusions)
            if any(actor and _lifetime(actor) is None for _, actor in rows):
                limitations += ("Contiguous source ID is used where historical lifetime metadata is absent",)
            metrics.append(_summary_metric(
                "exposure.pose_duration", version, status=AssessmentStatus.VALID,
                reason="Observed present ego pose at both ends of supported intervals",
                value={"duration_s": float(pose_duration), "interval_count": len(pose_intervals)},
                units="s", window=window, eligible_samples=len(pose_intervals),
                eligible_duration_s=float(pose_duration), limitations=limitations,
                actors=window_actors,
            ))
            metrics.append(_summary_metric(
                "trajectory.observed_distance", version, status=AssessmentStatus.VALID,
                reason="Sum of consecutive observed ego-centre displacements",
                value={"distance_m": float(sum(pose_distance)), "interval_count": len(pose_intervals)},
                units="m", window=window, eligible_samples=len(pose_intervals),
                eligible_duration_s=float(pose_duration), limitations=limitations,
                actors=window_actors,
            ))
        else:
            metrics.append(_summary_metric(
                "exposure.pose_duration", version, status=AssessmentStatus.UNAVAILABLE,
                reason="No timed consecutive present poses support pose exposure", value=None,
                units="s", window=window, actors=window_actors,
            ))
            pose_observations = any(_pose(rows[i][1]) for i in selected_indices)
            distance_status = (AssessmentStatus.UNAVAILABLE
                               if not timed_support or not pose_observations
                               else AssessmentStatus.UNDEFINED)
            metrics.append(_summary_metric(
                "trajectory.observed_distance", version, status=distance_status,
                reason=("Timed position support is unavailable" if distance_status is AssessmentStatus.UNAVAILABLE
                        else "Observed poses do not form a supported consecutive displacement"), value=None,
                units="m", window=window, actors=window_actors,
            ))

        kinematic_samples = {key: [] for key, _ in _KINEMATICS}
        observed_heading = sum(_heading(rows[i][1]) for i in selected_indices)
        observed_velocity = sum(_velocity(rows[i][1]) for i in selected_indices)
        metric_exclusions = {key: dict(structural) for key, _ in _KINEMATICS}
        metric_exclusions["trajectory.speed"]["missing_velocity_observations"] = sum(
            actor is not None and _present(actor) and not _velocity(actor)
            for _, actor in (rows[i] for i in selected_indices)
        )
        metric_exclusions["trajectory.speed"]["absent_observations"] = sum(
            actor is None or not _present(actor)
            for _, actor in (rows[i] for i in selected_indices)
        )
        sample_limitations = []
        if report.get("schema_version") == 2:
            sample_limitations.append(
                "Effective owner is unknown in this legacy trace; controller attribution and handovers are not verifiable"
            )
        if any(actor is not None and _lifetime(actor) is None
               for _, actor in (rows[i] for i in selected_indices)):
            sample_limitations.append(
                "Historical lifetime metadata is missing; continuity uses adjacent observations of the stable source ID"
            )
        if any(_present(actor) and _owner(actor) is None
               for _, actor in (rows[i] for i in selected_indices)):
            sample_limitations.append("Effective owner is missing for one or more observed ego samples")
        for index in selected_indices:
            frame, actor = rows[index]
            if actor is None or not _present(actor):
                continue
            if _velocity(actor):
                exposure_s = None
                if index < len(intervals):
                    interval = intervals[index]
                    if interval["dt"] is not None and not interval["reasons"]:
                        exposure_s = interval["dt"]
                kinematic_samples["trajectory.speed"].append(
                    _sample(frame.get("step", index), times[index],
                            math.hypot(actor["vx"], actor["vy"]), actor,
                            exposure_s=exposure_s, stencil_steps=[index],
                            support_kind="left_observation_interval"))
        world_accel_intervals = []
        body_accel_intervals = []
        yaw_intervals = []
        for interval in selected_intervals:
            index = interval["index"]
            if interval["dt"] is None or interval["reasons"]:
                continue
            left, right, dt = interval["left"], interval["right"], interval["dt"]
            if not (_present(left) and _present(right)):
                continue
            if _heading(left) and _heading(right):
                delta = math.atan2(math.sin(right["heading"] - left["heading"]),
                                   math.cos(right["heading"] - left["heading"]))
                yaw_rate = delta / dt
                yaw_intervals.append({"index": index, "mid": interval["mid"],
                                      "value": yaw_rate, "dt": dt, "left": left,
                                      "right": right})
                kinematic_samples["trajectory.yaw_rate"].append(
                    _sample(index, interval["mid"], yaw_rate, left,
                            exposure_s=dt, stencil_steps=[index, index + 1],
                            support_kind="transition_interval"))
            else:
                metric_exclusions["trajectory.yaw_rate"]["missing_heading"] = \
                    metric_exclusions["trajectory.yaw_rate"].get("missing_heading", 0) + 1
                metric_exclusions["trajectory.yaw_acceleration"]["missing_heading"] = \
                    metric_exclusions["trajectory.yaw_acceleration"].get("missing_heading", 0) + 1
            if not (_velocity(left) and _velocity(right)):
                for metric_id in ("trajectory.acceleration_longitudinal",
                                  "trajectory.acceleration_lateral",
                                  "trajectory.jerk_longitudinal",
                                  "trajectory.jerk_world_norm"):
                    metric_exclusions[metric_id]["missing_velocity"] = \
                        metric_exclusions[metric_id].get("missing_velocity", 0) + 1
                continue
            ax = (right["vx"] - left["vx"]) / dt
            ay = (right["vy"] - left["vy"]) / dt
            world_accel_intervals.append({"index": index, "mid": interval["mid"],
                                          "dt": dt, "world": (ax, ay), "left": left})
            if not (_heading(left) and _heading(right)):
                for metric_id in ("trajectory.acceleration_longitudinal",
                                  "trajectory.acceleration_lateral",
                                  "trajectory.jerk_longitudinal"):
                    metric_exclusions[metric_id]["missing_heading"] = \
                        metric_exclusions[metric_id].get("missing_heading", 0) + 1
                continue
            delta = math.atan2(math.sin(right["heading"] - left["heading"]),
                               math.cos(right["heading"] - left["heading"]))
            theta_mid = left["heading"] + delta / 2
            along = ax * math.cos(theta_mid) + ay * math.sin(theta_mid)
            lateral = -ax * math.sin(theta_mid) + ay * math.cos(theta_mid)
            body_accel_intervals.append({"index": index, "mid": interval["mid"],
                                         "dt": dt, "world": (ax, ay),
                                         "longitudinal": along, "lateral": lateral,
                                         "left": left})
            kinematic_samples["trajectory.acceleration_longitudinal"].append(
                _sample(index, interval["mid"], along, left, exposure_s=dt,
                        stencil_steps=[index, index + 1], support_kind="transition_interval"))
            kinematic_samples["trajectory.acceleration_lateral"].append(
                _sample(index, interval["mid"], lateral, left, exposure_s=dt,
                        stencil_steps=[index, index + 1], support_kind="transition_interval"))

        for left, right in zip(yaw_intervals, yaw_intervals[1:]):
            if right["index"] != left["index"] + 1:
                metric_exclusions["trajectory.yaw_acceleration"]["nonadjacent_stencil"] = \
                    metric_exclusions["trajectory.yaw_acceleration"].get("nonadjacent_stencil", 0) + 1
                continue
            if not _same_interval_owner(left, right):
                metric_exclusions["trajectory.yaw_acceleration"]["owner_handover"] = \
                    metric_exclusions["trajectory.yaw_acceleration"].get("owner_handover", 0) + 1
                continue
            support = right["mid"] - left["mid"]
            if support <= 0:
                metric_exclusions["trajectory.yaw_acceleration"]["nonincreasing_midpoint"] = \
                    metric_exclusions["trajectory.yaw_acceleration"].get("nonincreasing_midpoint", 0) + 1
                continue
            value = (right["value"] - left["value"]) / support
            kinematic_samples["trajectory.yaw_acceleration"].append(
                _sample(right["index"], right["mid"], value, left["left"],
                        exposure_s=support, stencil_steps=[left["index"], right["index"] + 1],
                        support_kind="adjacent_transition_midpoint_separation"))

        for left, right in zip(body_accel_intervals, body_accel_intervals[1:]):
            if right["index"] != left["index"] + 1:
                metric_exclusions["trajectory.jerk_longitudinal"]["nonadjacent_stencil"] = \
                    metric_exclusions["trajectory.jerk_longitudinal"].get("nonadjacent_stencil", 0) + 1
                continue
            if not _same_interval_owner(left, right):
                metric_exclusions["trajectory.jerk_longitudinal"]["owner_handover"] = \
                    metric_exclusions["trajectory.jerk_longitudinal"].get("owner_handover", 0) + 1
                continue
            support = right["mid"] - left["mid"]
            if support <= 0:
                continue
            longitudinal = (right["longitudinal"] - left["longitudinal"]) / support
            kinematic_samples["trajectory.jerk_longitudinal"].append(
                _sample(right["index"], right["mid"], longitudinal, left["left"],
                        exposure_s=support, stencil_steps=[left["index"], right["index"] + 1],
                        support_kind="adjacent_transition_midpoint_separation"))

        for left, right in zip(world_accel_intervals, world_accel_intervals[1:]):
            if right["index"] != left["index"] + 1:
                metric_exclusions["trajectory.jerk_world_norm"]["nonadjacent_stencil"] = \
                    metric_exclusions["trajectory.jerk_world_norm"].get("nonadjacent_stencil", 0) + 1
                continue
            if not _same_interval_owner(left, right):
                metric_exclusions["trajectory.jerk_world_norm"]["owner_handover"] = \
                    metric_exclusions["trajectory.jerk_world_norm"].get("owner_handover", 0) + 1
                continue
            support = right["mid"] - left["mid"]
            if support <= 0:
                continue
            jx = (right["world"][0] - left["world"][0]) / support
            jy = (right["world"][1] - left["world"][1]) / support
            kinematic_samples["trajectory.jerk_world_norm"].append(
                _sample(right["index"], right["mid"], math.hypot(jx, jy), left["left"],
                        exposure_s=support, stencil_steps=[left["index"], right["index"] + 1],
                        support_kind="adjacent_transition_midpoint_separation"))

        comfort = profile_values["comfort"]
        thresholds = {
            "trajectory.acceleration_longitudinal": (comfort["longitudinal_acceleration_abs_limit_m_s2"], True),
            "trajectory.acceleration_lateral": (comfort["lateral_acceleration_abs_limit_m_s2"], True),
            "trajectory.jerk_longitudinal": (comfort["longitudinal_jerk_abs_limit_m_s3"], True),
            "trajectory.jerk_world_norm": (comfort["total_world_jerk_limit_m_s3"], False),
        }
        for metric_id, units in _KINEMATICS:
            samples = kinematic_samples[metric_id]
            if metric_id == "trajectory.speed":
                status = AssessmentStatus.UNAVAILABLE
                reason = "No present ego state has recorded finite world velocity"
            elif metric_id == "trajectory.yaw_rate":
                if not observed_heading:
                    status, reason = AssessmentStatus.UNAVAILABLE, "Present ego heading is missing"
                elif not timed_support:
                    status, reason = AssessmentStatus.UNAVAILABLE, "No adjacent timed observation supports yaw rate"
                elif not yaw_intervals and metric_exclusions[metric_id].get("missing_heading", 0):
                    status, reason = AssessmentStatus.UNAVAILABLE, "Heading is missing on the available transition support"
                else:
                    status, reason = AssessmentStatus.UNDEFINED, "No supported heading transition is available"
            elif metric_id == "trajectory.yaw_acceleration":
                if not observed_heading:
                    status, reason = AssessmentStatus.UNAVAILABLE, "Present ego heading is missing"
                elif not timed_support:
                    status, reason = AssessmentStatus.UNAVAILABLE, "No timed support for yaw acceleration"
                elif not yaw_intervals and metric_exclusions[metric_id].get("missing_heading", 0):
                    status, reason = AssessmentStatus.UNAVAILABLE, "Heading is missing on the available transition support"
                else:
                    status, reason = AssessmentStatus.UNDEFINED, "Too few adjacent heading intervals for yaw acceleration"
            elif metric_id == "trajectory.jerk_world_norm":
                if not observed_velocity:
                    status, reason = AssessmentStatus.UNAVAILABLE, "Present ego world velocity is missing"
                elif not timed_support:
                    status, reason = AssessmentStatus.UNAVAILABLE, "No timed support for world acceleration"
                elif not world_accel_intervals and metric_exclusions[metric_id].get("missing_velocity", 0):
                    status, reason = AssessmentStatus.UNAVAILABLE, "World velocity is missing on the available transition support"
                else:
                    status, reason = AssessmentStatus.UNDEFINED, "Too few adjacent world-acceleration intervals for jerk"
            elif metric_id == "trajectory.jerk_longitudinal":
                if not observed_velocity or not observed_heading:
                    status, reason = AssessmentStatus.UNAVAILABLE, "World velocity or heading support is unavailable"
                elif not timed_support:
                    status, reason = AssessmentStatus.UNAVAILABLE, "No timed support for longitudinal jerk"
                elif not body_accel_intervals and (
                        metric_exclusions[metric_id].get("missing_velocity", 0)
                        or metric_exclusions[metric_id].get("missing_heading", 0)):
                    status, reason = AssessmentStatus.UNAVAILABLE, "Velocity or heading is missing on the available transition support"
                else:
                    status, reason = AssessmentStatus.UNDEFINED, "Too few adjacent body-frame acceleration intervals for jerk"
            else:
                if not observed_velocity or not observed_heading:
                    status, reason = AssessmentStatus.UNAVAILABLE, "World velocity or heading support is unavailable"
                elif not timed_support:
                    status, reason = AssessmentStatus.UNAVAILABLE, "No timed support for body-frame acceleration"
                elif not body_accel_intervals and (
                        metric_exclusions[metric_id].get("missing_velocity", 0)
                        or metric_exclusions[metric_id].get("missing_heading", 0)):
                    status, reason = AssessmentStatus.UNAVAILABLE, "Velocity or heading is missing on the available transition support"
                else:
                    status, reason = AssessmentStatus.UNDEFINED, "No supported body-frame acceleration interval is available"
            threshold = thresholds.get(metric_id)
            metrics.append(_make_metric(
                metric_id, version, samples, units, window,
                no_data_status=status, no_data_reason=reason,
                no_data_exclusions=metric_exclusions[metric_id],
                threshold=threshold[0] if threshold else None,
                absolute=threshold[1] if threshold else False,
                extra_limitations=sample_limitations,
                actors=window_actors,
            ))

    events, coverage = _event_rows(
        rows, times, report, warmup, last,
        evaluation_capture=evaluation_capture,
        evaluation_capture_bound=evaluation_capture_bound,
    )
    exposure["event_observation_coverage"] = coverage
    requested = report.get("requested_observation_frames", count)
    exposure["censoring"] = {
        "terminal_reason": report.get("terminal_reason"),
        "observations_recorded": count,
        "requested_observations": requested,
        "requested_horizon_reached": report.get("terminal_reason") == "horizon" and count == requested,
        "ended_before_requested_horizon": count < requested,
        "post_terminal_trajectory_unobserved": report.get("terminal_reason") not in (None, "horizon"),
        "primary_window_complete": count > last,
        "unobserved_future_is_unknown": True,
    }
    return {"metrics": [metric.to_dict() for metric in metrics],
            "exposure": exposure, "events": events}
