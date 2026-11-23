"""Offline collision, oriented-footprint clearance, and TTC measurements.

This module consumes saved observations only. It never runs a simulator or
uses a future observation to predict motion. Native flags, sampled geometry,
and the constant-velocity TTC model remain separate evidence channels.
"""

from __future__ import annotations

import math
from statistics import median

from geotransfer_gap.evaluation.contracts import AssessmentStatus, CriterionOutcome, MetricResult


_EPS = 1e-10


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _generation(actor):
    value = actor.get("lifetime_generation")
    return value if type(value) is int and value >= 0 else None


def _present(actor):
    return isinstance(actor, dict) and actor.get("present") is True


def _same_lifetime(first, second):
    if not first or not second or first.get("id") != second.get("id"):
        return False
    left, right = _generation(first), _generation(second)
    # Historical flat traces lack generation metadata. Adjacent source identity
    # is retained, but a known/unknown boundary is never silently joined.
    return left == right if left is not None or right is not None else True


def _actor_map(frame):
    return {row.get("id"): row for row in frame.get("actors", ())
            if type(row.get("id")) is int}


def _typed_actor(actor):
    value = actor.get("type")
    if value in (1, "vehicle"):
        return "vehicle"
    if value in (2, "pedestrian"):
        return "pedestrian"
    if value in (3, "cyclist"):
        return "cyclist"
    return None


def _dimension_observations(frames):
    values = {}
    for frame in frames:
        for actor in frame.get("actors", ()):
            generation = _generation(actor)
            if generation is None:
                continue
            key = (actor.get("id"), generation)
            row = values.setdefault(key, {"length": [], "width": []})
            for name in ("length", "width"):
                value = actor.get(name)
                if _finite(value) and value > 0:
                    row[name].append(float(value))
    result = {}
    for key, row in values.items():
        # Dimensions describe a fixed actor footprint. Impute only a missing
        # sample from that same recorded lifetime when its observed values are
        # constant; do not borrow a population or type-average dimension.
        dims = {}
        for name in ("length", "width"):
            observed = row[name]
            if observed and max(observed) - min(observed) <= 1e-6:
                dims[name] = float(median(observed))
        if dims:
            result[key] = dims
    return result


def _dimensions(actor, dimension_observations):
    raw = {}
    invalid = False
    for name in ("length", "width"):
        value = actor.get(name)
        if value is None:
            raw[name] = None
        elif not _finite(value) or value <= 0:
            raw[name] = None
            invalid = True
        else:
            raw[name] = float(value)
    key = (actor.get("id"), _generation(actor))
    known = dimension_observations.get(key, {}) if key[1] is not None else {}
    imputed = []
    for name in ("length", "width"):
        if raw[name] is None and name in known:
            raw[name] = known[name]
            imputed.append(name)
    if raw["length"] is None or raw["width"] is None:
        return None, "unavailable", tuple(imputed), invalid
    return (raw["length"], raw["width"]), (
        "same_actor_lifetime_constant_observations" if imputed else "trace_observation"
    ), tuple(imputed), invalid


def _rectangle(actor, dimensions):
    if not (_present(actor) and _finite(actor.get("x")) and _finite(actor.get("y"))
            and _finite(actor.get("heading"))):
        return None
    dims, _, _, _ = _dimensions(actor, dimensions)
    if dims is None:
        return None
    length, width = dims
    c, s = math.cos(actor["heading"]), math.sin(actor["heading"])
    cx, cy = actor["x"], actor["y"]
    # Match the corner convention used by validation.audit_physical_source.
    return [
        (cx + a * length / 2 * c - b * width / 2 * s,
         cy + a * length / 2 * s + b * width / 2 * c)
        for a, b in ((-1, -1), (-1, 1), (1, 1), (1, -1))
    ]


def _geometry_helpers():
    # Reuse the existing audited pure-geometry owner. It is intentionally
    # imported only when an episode measurement needs rectangles, keeping
    # profile/config/trace-only imports free of map and native stacks.
    from geotransfer_gap.maps.audit_rule_applicability import box_distance, polygon_overlap

    return box_distance, polygon_overlap


def _velocity(actor, index, frames, times, ego_id):
    if _present(actor) and _finite(actor.get("vx")) and _finite(actor.get("vy")):
        return (float(actor["vx"]), float(actor["vy"])), "recorded_world_velocity"
    # The approved fallback is causal and limited to source-valid non-ego
    # actors whose stable lifetime generation is explicitly known.
    if (actor.get("id") == ego_id or actor.get("source_valid") is not True
            or _generation(actor) is None or index <= 0
            or frames[index - 1].get("transition_applied") is False):
        return None, None
    previous = _actor_map(frames[index - 1]).get(actor.get("id"))
    dt = (times[index] - times[index - 1]
          if times[index] is not None and times[index - 1] is not None else None)
    if (not _present(previous) or not _same_lifetime(previous, actor)
            or previous.get("source_valid") is not True
            or not all(_finite(value) for value in
                       (previous.get("x"), previous.get("y"), actor.get("x"), actor.get("y")))
            or not _finite(dt) or dt <= 0):
        return None, None
    return ((actor["x"] - previous["x"]) / dt,
            (actor["y"] - previous["y"]) / dt), \
        "observed_position_backward_difference_same_lifetime"


def _sat_entry(first, second, first_velocity, second_velocity):
    """Return continuous first overlap time on the unbounded time axis."""
    theta_a, theta_b = first["heading"], second["heading"]
    axes = ((math.cos(theta_a), math.sin(theta_a)),
            (-math.sin(theta_a), math.cos(theta_a)),
            (math.cos(theta_b), math.sin(theta_b)),
            (-math.sin(theta_b), math.cos(theta_b)))
    dims_a = first["_dimensions"]
    dims_b = second["_dimensions"]
    rel_pos = (second["x"] - first["x"], second["y"] - first["y"])
    rel_vel = (second_velocity[0] - first_velocity[0],
               second_velocity[1] - first_velocity[1])
    enter, leave = -math.inf, math.inf
    for ax, ay in axes:
        ra = (dims_a[0] / 2 * abs(ax * math.cos(theta_a) + ay * math.sin(theta_a))
              + dims_a[1] / 2 * abs(-ax * math.sin(theta_a) + ay * math.cos(theta_a)))
        rb = (dims_b[0] / 2 * abs(ax * math.cos(theta_b) + ay * math.sin(theta_b))
              + dims_b[1] / 2 * abs(-ax * math.sin(theta_b) + ay * math.cos(theta_b)))
        separation = rel_pos[0] * ax + rel_pos[1] * ay
        speed = rel_vel[0] * ax + rel_vel[1] * ay
        radius = ra + rb
        if abs(speed) <= _EPS:
            if abs(separation) > radius + _EPS:
                return None
            continue
        low = (-radius - separation) / speed
        high = (radius - separation) / speed
        if low > high:
            low, high = high, low
        enter, leave = max(enter, low), min(leave, high)
        if enter > leave + _EPS:
            return None
    if leave < -_EPS:
        return None
    return max(0.0, enter)


def _ttc(first, second, first_velocity, second_velocity, first_box, second_box,
         polygon_overlap, horizon):
    if polygon_overlap(first_box, second_box):
        return "overlap_now", 0.0
    entry = _sat_entry(first, second, first_velocity, second_velocity)
    if entry is None or entry > horizon + _EPS:
        return "no_overlap_predicted_within_horizon", None
    return "finite_future_overlap", float(max(0.0, entry))


def _status_metric(metric_id, version, status, reason, value=None, *, units=None,
                   interpretation=None, eligible_samples=None, eligible_duration_s=None,
                   window=None, actors=(), limitations=()):
    actor_rows = sorted(set(actors), key=lambda item: (item[0], -1 if item[1] is None else item[1]))
    return MetricResult(
        metric_id, version, status, reason, value, units,
        CriterionOutcome.NOT_ASSESSED, interpretation=interpretation,
        eligible_samples=eligible_samples, eligible_duration_s=eligible_duration_s,
        window=window, actors=tuple(actor_rows), limitations=tuple(limitations),
    ).to_dict()


def _time_values(frames, profile, exposure):
    masks = exposure.get("observation_masks", ())
    supplied = [row.get("time_s") for row in masks]
    if len(supplied) == len(frames):
        return supplied
    nominal = profile.values["time"]["nominal_sample_interval_s"]
    if frames and all(frame.get("time_s") is None for frame in frames) \
            and frames[0].get("step") is not None:
        return [float(frame.get("step", index)) * nominal
                for index, frame in enumerate(frames)]
    return [frame.get("time_s") for frame in frames]


def _interval_dt(index, frames, times):
    if index >= len(frames) - 1 or frames[index].get("transition_applied") is False:
        return None
    left, right = times[index], times[index + 1]
    if not (_finite(left) and _finite(right) and right > left):
        return None
    return float(right - left)


def _identity_continuous(actor, following):
    if not (_present(actor) and _present(following) and _same_lifetime(actor, following)):
        return False
    left_valid, right_valid = actor.get("source_valid"), following.get("source_valid")
    if type(left_valid) is bool or type(right_valid) is bool:
        if type(left_valid) is not bool or type(right_valid) is not bool or left_valid != right_valid:
            return False
    return True


def _event_capture_index(capture, bound):
    if not bound or not isinstance(capture, dict):
        return {}
    return {row.get("step"): row for row in capture.get("observations", ())}


def _enrich_collision_events(events, frames, ego_id, report, capture_by_step,
                             capture_bound, times):
    rows_by_step = {frame.get("step", index): _actor_map(frame)
                    for index, frame in enumerate(frames)}
    for event in events:
        if event.get("channel") != "native_vehicle_collision":
            continue
        step = event.get("step")
        index = next((i for i, frame in enumerate(frames)
                      if frame.get("step", i) == step), None)
        actor = rows_by_step.get(step, {}).get(ego_id)
        captured = None
        if capture_bound and step in capture_by_step:
            captured = next((row for row in capture_by_step[step].get("actors", ())
                             if row.get("source_id") == ego_id
                             and row.get("binary_index") == report.get("ego_binary_index")), None)
        partner_id = (captured.get("collision_partner_source_id")
                      if captured and captured.get("collision_partner_status") == "mapped" else None)
        partner_index = (captured.get("collision_partner_binary_index")
                         if partner_id is not None else None)
        partner_capture = (next((row for row in capture_by_step.get(step, {}).get("actors", ())
                                 if row.get("source_id") == partner_id
                                 and row.get("binary_index") == partner_index), None)
                           if partner_id is not None else None)
        details = {
            "partner_status": (captured.get("collision_partner_status") if captured
                               else "capture_unavailable"),
            "partner_source_id": partner_id,
            "partner_binary_index": partner_index,
            "partner_lifetime_generation": (partner_capture.get("lifetime_generation")
                                             if partner_capture else None),
            "collision_centers_world_xy": ({
                "ego_detector_center": captured.get("collision_center_world_xy"),
                "partner_detector_center": captured.get("partner_center_world_xy"),
                "meaning": "detector actor centers, not exact impact points",
            } if captured else None),
            "fault_status": "unknown",
            "fault_reason": "saved collision evidence does not establish legal or benchmark responsibility",
            "preimpact_relative_speed_proxy_m_s": None,
            "preimpact_speed_support": None,
        }
        partner = rows_by_step.get(step, {}).get(partner_id) if partner_id is not None else None
        if index is not None and index > 0 and actor is not None and partner is not None:
            prior_actors = _actor_map(frames[index - 1])
            prior_ego, prior_partner = prior_actors.get(ego_id), prior_actors.get(partner_id)
            partner_life = details["partner_lifetime_generation"]
            ego_life_ok = (_present(prior_ego) and prior_ego.get("id") == actor.get("id")
                           and (_generation(prior_ego) == _generation(actor)
                                if _generation(prior_ego) is not None or _generation(actor) is not None
                                else True))
            partner_life_ok = (_present(prior_partner) and prior_partner.get("id") == partner_id
                               and (_generation(prior_partner) == partner_life
                                    if _generation(prior_partner) is not None or partner_life is not None
                                    else True))
            if ego_life_ok and partner_life_ok:
                ego_velocity, ego_method = _velocity(prior_ego, index - 1, frames, times, ego_id)
                partner_velocity, partner_method = _velocity(
                    prior_partner, index - 1, frames, times, ego_id)
                if ego_velocity is not None and partner_velocity is not None:
                    details["preimpact_relative_speed_proxy_m_s"] = float(math.hypot(
                        ego_velocity[0] - partner_velocity[0],
                        ego_velocity[1] - partner_velocity[1]))
                    details["preimpact_speed_support"] = {
                        "observation_step": frames[index - 1].get("step", index - 1),
                        "ego_velocity_method": ego_method,
                        "partner_velocity_method": partner_method,
                    }
        ego_type = _typed_actor(actor or {})
        partner_type = _typed_actor(partner or {})
        details["collision_type"] = (
            f"{ego_type}_{partner_type}" if ego_type and partner_type else None
        )
        details["collision_type_status"] = "supported" if details["collision_type"] else "unknown"
        event["collision_details"] = details


def _native_metric(events, exposure, report, version, window, warmup, last):
    rows = [event for event in events if event.get("channel") == "native_vehicle_collision"]
    selected = [event for event in rows if window == "full" or
                warmup <= event.get("step", -1) <= last]
    onset_rows = [event for event in selected if event.get("observation") in
                  ("newly_observed_onset", "newly_observed_during_warmup")]
    channels = exposure.get("event_observation_coverage", {}).get("windows", {})
    coverage = channels.get("full" if window == "full" else "primary", {}).get(
        "channels", {}).get("collision_state", {})
    if coverage.get("status") != "valid":
        return _status_metric(
            "safety.native_vehicle_collision_onsets", version, AssessmentStatus.UNAVAILABLE,
            "Native vehicle-collision state is absent from the selected trace window",
            units="onsets", window=window,
            limitations=("No native collision event count is inferred from geometry or terminal labels",),
        )
    warm = [event for event in selected if event.get("attribution") in
            ("warmup_or_initial_condition", "initial_condition")]
    controlled = [event for event in onset_rows
                  if event.get("attribution") == "recorded_controlled_transition"]
    coverage_incomplete = (coverage.get("fraction") != 1.0
                           or any(row.get("collision_details", {}).get("partner_status")
                                  not in ("mapped",) for row in onset_rows)
                           or any(event.get("observation") in
                                  ("active_after_unknown_prior", "active_at_first_observation")
                                  for event in selected))
    value = {
        "observed_onset_count": len(onset_rows),
        "count_is_lower_bound": bool(coverage_incomplete),
        "warmup_or_initial_condition_count": len(warm),
        "recorded_controlled_transition_count": len(controlled),
        "unattributed_or_unknown_prior_count": sum(
            event.get("observation") == "active_after_unknown_prior" for event in selected),
        "left_censored_initial_active_count": sum(
            event.get("observation") == "active_at_first_observation" for event in selected),
        "event_observation_coverage": coverage,
        "onsets": onset_rows,
        "responsibility": "unknown unless separately supported; no responsibility heuristic applied",
    }
    actors = [(event.get("actor", {}).get("source_id"),
               event.get("actor", {}).get("lifetime_generation")) for event in selected]
    return _status_metric(
        "safety.native_vehicle_collision_onsets", version, AssessmentStatus.VALID,
        "Observed native collision-state transitions; count is not an exhaustive contact catalog",
        value, units="onsets", window=window,
        eligible_samples=coverage.get("observations_with_field"), actors=actors,
        limitations=("Native event occurrence is distinct from sampled overlap and predictive TTC",
                     "A latched or incompletely observed flag can hide distinct contacts"),
    )


def _window_metrics(frames, ego_id, report, profile, events, exposure, times, window):
    values = profile.values
    version = values["profile"]["definition_version"]
    warmup = values["time"]["warmup_transitions"]
    last = values["time"]["primary_last_observation_index"]
    indices = [i for i in range(len(frames)) if window == "full" or warmup <= i <= last]
    dims = _dimension_observations(frames)
    box_distance = polygon_overlap = None
    horizon_values = values["safety"]["ttc"]["sensitivity_horizons_s"]
    primary_horizon = values["safety"]["ttc"]["primary_horizon_s"]
    horizon_values = sorted(set([primary_horizon, *horizon_values]))
    snapshots = []
    invalid_dimension_count = 0
    any_counterpart = False
    for index in indices:
        frame = frames[index]
        actors = _actor_map(frame)
        ego = actors.get(ego_id)
        if not _present(ego):
            snapshots.append({"index": index, "step": frame.get("step", index),
                              "time_s": times[index], "ego_present": False,
                              "expected_pairs": 0, "geometry_pairs": [], "ttc_pairs": [],
                          "coverage_complete": False, "ttc_coverage_complete": False})
            continue
        counterparts = [row for sid, row in sorted(actors.items())
                        if sid != ego_id and _present(row)]
        any_counterpart |= bool(counterparts)
        expected = len(counterparts)
        ego_box = _rectangle(ego, dims)
        ego_dims, ego_dim_source, ego_imputed, ego_bad_dim = _dimensions(ego, dims)
        invalid_dimension_count += bool(expected and ego_bad_dim)
        geometry_pairs, ttc_pairs = [], []
        missing_geometry_reasons, missing_ttc_reasons = {}, {}

        def missing(counter, reason):
            counter[reason] = counter.get(reason, 0) + 1

        for actor in counterparts:
            other_box = _rectangle(actor, dims)
            other_dims, other_dim_source, other_imputed, other_bad_dim = _dimensions(actor, dims)
            invalid_dimension_count += bool(other_bad_dim)
            base = {
                "actor": {"source_id": actor["id"],
                          "lifetime_generation": _generation(actor)},
                "dimensions_m": {"ego": ego_dims, "actor": other_dims},
                "dimension_source": {"ego": ego_dim_source, "actor": other_dim_source},
                "dimension_imputed_fields": {"ego": list(ego_imputed),
                                              "actor": list(other_imputed)},
            }
            if ego_box is None or other_box is None:
                if not all(_finite(value) for value in
                           (ego.get("x"), ego.get("y"), ego.get("heading"),
                            actor.get("x"), actor.get("y"), actor.get("heading"))):
                    missing(missing_geometry_reasons, "pose_or_heading_missing")
                elif ego_dims is None or other_dims is None:
                    missing(missing_geometry_reasons, "dimensions_missing")
                else:
                    missing(missing_geometry_reasons, "footprint_unavailable")
                missing(missing_ttc_reasons, "geometry_unavailable")
                continue
            if box_distance is None:
                box_distance, polygon_overlap = _geometry_helpers()
            gap = float(box_distance(ego_box, other_box))
            overlap = bool(polygon_overlap(ego_box, other_box))
            geometry_pairs.append({**base, "clearance_m": gap, "overlap": overlap})
            ego_velocity, ego_velocity_method = _velocity(ego, index, frames, times, ego_id)
            actor_velocity, actor_velocity_method = _velocity(actor, index, frames, times, ego_id)
            if ego_velocity is None or actor_velocity is None:
                missing(missing_ttc_reasons, "velocity_missing")
                continue
            first = {**ego, "_dimensions": ego_dims}
            second = {**actor, "_dimensions": other_dims}
            per_horizon = {}
            for horizon in horizon_values:
                interpretation, ttc_s = _ttc(first, second, ego_velocity,
                                             actor_velocity, ego_box, other_box,
                                             polygon_overlap, horizon)
                per_horizon[str(float(horizon))] = {
                    "interpretation": interpretation, "ttc_s": ttc_s,
                }
            ttc_pairs.append({
                **base,
                "velocity_support": {"ego": ego_velocity_method,
                                     "actor": actor_velocity_method},
                "horizons": per_horizon,
            })
        snapshots.append({
            "index": index, "step": frame.get("step", index),
            "time_s": times[index], "ego_present": True,
            "expected_pairs": expected, "geometry_pairs": geometry_pairs,
            "ttc_pairs": ttc_pairs,
            "coverage_complete": expected == len(geometry_pairs),
            "ttc_coverage_complete": expected == len(ttc_pairs),
            "missing_geometry_reasons": missing_geometry_reasons,
            "missing_ttc_reasons": missing_ttc_reasons,
        })

    expected_geometry = sum(row["expected_pairs"] for row in snapshots)
    supported_geometry = sum(len(row["geometry_pairs"]) for row in snapshots)
    expected_ttc = sum(row["expected_pairs"] for row in snapshots)
    supported_ttc = sum(len(row["ttc_pairs"]) for row in snapshots)
    geometry_missing = {}
    ttc_missing = {}
    for row in snapshots:
        for key, amount in row.get("missing_geometry_reasons", {}).items():
            geometry_missing[key] = geometry_missing.get(key, 0) + amount
        for key, amount in row.get("missing_ttc_reasons", {}).items():
            ttc_missing[key] = ttc_missing.get(key, 0) + amount
    if invalid_dimension_count:
        invalid_limitation = (f"invalid_nonpositive_or_nonfinite_dimensions={invalid_dimension_count}",)
    else:
        invalid_limitation = ()

    # Native events use the same PE02 transition/onset machinery. This section
    # only enriches those rows from the hash-bound optional native capture.
    metrics = [_native_metric(events, exposure, report, version, window, warmup, last)]
    actor_refs = [(ego_id, generation) for generation in sorted(
        { _generation(_actor_map(frames[i]).get(ego_id, {})) for i in indices },
        key=lambda value: -1 if value is None else value)]
    if invalid_dimension_count:
        invalid_reason = "Present saved actors contain nonpositive or nonfinite dimensions"
        invalid_status = AssessmentStatus.INVALID
    else:
        invalid_reason = None
        invalid_status = None

    if supported_geometry:
        clearance_samples = []
        overlap_samples = []
        for row in snapshots:
            if not row["geometry_pairs"]:
                continue
            closest = min(row["geometry_pairs"], key=lambda pair: pair["clearance_m"])
            overlap_rows = [pair for pair in row["geometry_pairs"] if pair["overlap"]]
            clearance_samples.append({"step": row["step"], "time_s": row["time_s"],
                                      "clearance_m": closest["clearance_m"],
                                      "closest_actor": closest["actor"],
                                      "dimensions_m": closest["dimensions_m"],
                                      "dimension_source": closest["dimension_source"],
                                      "dimension_imputed_fields": closest["dimension_imputed_fields"],
                                      "eligible_pair_count": len(row["geometry_pairs"]),
                                      "expected_pair_count": row["expected_pairs"],
                                      "coverage_complete": row["coverage_complete"]})
            for pair in overlap_rows:
                overlap_samples.append({"step": row["step"], "time_s": row["time_s"],
                                        "actor": pair["actor"],
                                        "dimensions_m": pair["dimensions_m"],
                                        "dimension_source": pair["dimension_source"]})
        min_sample = min(clearance_samples, key=lambda row: row["clearance_m"])
        if invalid_status:
            metrics.append(_status_metric(
                "safety.footprint_clearance", version, invalid_status, invalid_reason,
                units="m", window=window, eligible_samples=supported_geometry,
                actors=actor_refs, limitations=invalid_limitation,
            ))
        else:
            metrics.append(_status_metric(
                "safety.footprint_clearance", version, AssessmentStatus.VALID,
                "Minimum simultaneous oriented-footprint gap among supported present actor pairs",
                {"minimum_gap_m": min_sample["clearance_m"],
                 "minimum_sample": min_sample,
                 "samples": clearance_samples,
                 "coverage": {"expected_pair_samples": expected_geometry,
                              "eligible_pair_samples": supported_geometry,
                              "fraction": supported_geometry / expected_geometry if expected_geometry else None,
                              "complete": supported_geometry == expected_geometry,
                              "missing_reasons": geometry_missing}},
                units="m", window=window, eligible_samples=len(clearance_samples),
                actors=actor_refs,
                limitations=("Minimum describes only eligible pairs when coverage is incomplete",
                             "Source-held and parked present actors are included"),
            ))
        dt_total = 0.0
        expected_duration = 0.0
        complete_duration = 0.0
        overlap_pair_duration = 0.0
        scene_overlap_duration = 0.0
        overlap_supported_intervals = 0
        overlap_expected_intervals = 0
        overlap_complete_intervals = 0
        for row in snapshots:
            index = row["index"]
            if (not row["ego_present"] or not row["expected_pairs"]
                    or index + 1 >= len(frames)
                    or window == "primary" and index >= last):
                continue
            dt = _interval_dt(index, frames, times)
            if dt is None:
                continue
            current_map, following_map = _actor_map(frames[index]), _actor_map(frames[index + 1])
            ego_next = following_map.get(ego_id)
            if not _identity_continuous(current_map.get(ego_id), ego_next):
                continue
            overlap_expected_intervals += 1
            expected_duration += dt
            supported_pairs = [pair for pair in row["geometry_pairs"]
                               if _identity_continuous(current_map.get(pair["actor"]["source_id"]),
                                                       following_map.get(pair["actor"]["source_id"]))]
            if not supported_pairs:
                continue
            overlap_supported_intervals += 1
            dt_total += dt
            if len(supported_pairs) == row["expected_pairs"]:
                overlap_complete_intervals += 1
                complete_duration += dt
            overlapped = [pair for pair in supported_pairs if pair["overlap"]]
            overlap_pair_duration += dt * len(overlapped)
            scene_overlap_duration += dt if overlapped else 0.0
        if invalid_status:
            metrics.append(_status_metric(
                "safety.footprint_overlap", version, invalid_status, invalid_reason,
                units="pair-observations", window=window, eligible_samples=supported_geometry,
                actors=actor_refs, limitations=invalid_limitation,
            ))
        else:
            metrics.append(_status_metric(
                "safety.footprint_overlap", version, AssessmentStatus.VALID,
                "Sampled geometric rectangle overlap, separate from native collision flags",
                {"overlap_pair_observations": len(overlap_samples),
                 "overlap_samples": overlap_samples,
                 "overlap_pair_duration_s": float(overlap_pair_duration),
                 "scene_overlap_duration_s": float(scene_overlap_duration),
                 "duration_method": "left_observation_sampled_interval_approximation",
                 "count_is_lower_bound": supported_geometry != expected_geometry,
                 "supported_interval_count": overlap_supported_intervals,
                 "supported_interval_duration_s": float(dt_total),
                 "expected_interval_count": overlap_expected_intervals,
                 "expected_interval_duration_s": float(expected_duration),
                 "complete_coverage_interval_count": overlap_complete_intervals,
                 "complete_coverage_duration_s": float(complete_duration),
                 "coverage": {"expected_pair_samples": expected_geometry,
                              "eligible_pair_samples": supported_geometry,
                              "complete": supported_geometry == expected_geometry,
                              "interval_complete": overlap_complete_intervals == overlap_expected_intervals,
                              "missing_reasons": geometry_missing}},
                units={"overlap_pair_observations": "pair-observations",
                       "overlap_pair_duration_s": "pair-seconds",
                       "scene_overlap_duration_s": "s"},
                eligible_samples=supported_geometry, eligible_duration_s=dt_total,
                window=window, actors=actor_refs,
                limitations=("Interval durations are sampled approximations at left observations",
                             "Unobserved contacts between samples are not inferred"),
            ))
    else:
        no_counterpart = not any_counterpart and any(row["ego_present"] for row in snapshots)
        status = AssessmentStatus.NOT_APPLICABLE if no_counterpart else invalid_status or AssessmentStatus.UNAVAILABLE
        reason = ("No simultaneous present counterpart exists in the selected window"
                  if no_counterpart else invalid_reason or
                  "No simultaneous present actor pairs have supported pose, heading, and dimensions")
        for metric_id, units in (("safety.footprint_clearance", "m"),
                                 ("safety.footprint_overlap", "m")):
            metrics.append(_status_metric(metric_id, version, status, reason, units=units,
                                          window=window, actors=actor_refs,
                                          eligible_samples=supported_geometry,
                                          limitations=invalid_limitation + (
                                              f"expected_pair_samples={expected_geometry}",
                                              f"eligible_pair_samples={supported_geometry}",
                                              f"missing_reasons={geometry_missing}",
                                          )))

    if supported_ttc:
        horizon_results = {}
        primary_interpretation = None
        primary_min = None
        for horizon in horizon_values:
            label = str(float(horizon))
            finite_values = [pair["horizons"][label]["ttc_s"]
                             for row in snapshots for pair in row["ttc_pairs"]
                             if pair["horizons"][label]["ttc_s"] is not None]
            overlap_now = any(pair["horizons"][label]["interpretation"] == "overlap_now"
                              for row in snapshots for pair in row["ttc_pairs"])
            horizon_complete = supported_ttc == expected_ttc
            if overlap_now:
                meaning = "overlap_now"
            elif finite_values:
                meaning = "finite_future_overlap"
            elif horizon_complete:
                meaning = "no_overlap_predicted_within_horizon"
            else:
                meaning = "partial_coverage_no_observed_finite_prediction"
            horizon_results[label] = {
                "minimum_ttc_s": float(min(finite_values)) if finite_values else None,
                "interpretation": meaning,
                "horizon_s": float(horizon),
                "eligible_pair_samples": supported_ttc,
                "expected_pair_samples": expected_ttc,
                "scene_coverage_complete": horizon_complete,
            }
            if math.isclose(horizon, primary_horizon):
                primary_interpretation = meaning
                primary_min = min(finite_values) if finite_values else None
        partial_rows = sum(not row["ttc_coverage_complete"] and row["expected_pairs"] > 0
                           for row in snapshots)
        if invalid_status:
            metrics.append(_status_metric(
                "safety.ttc", version, invalid_status, invalid_reason, units="s",
                eligible_samples=supported_ttc, window=window, actors=actor_refs,
                limitations=invalid_limitation,
            ))
        else:
            metrics.append(_status_metric(
                "safety.ttc", version, AssessmentStatus.VALID,
                "Continuous first overlap from fixed-heading, constant-world-velocity rectangle SAT",
                {"minimum_ttc_s": float(primary_min) if primary_min is not None else None,
                 "interpretation": primary_interpretation,
                 "primary_horizon_s": float(primary_horizon),
                 "horizon_sensitivity": horizon_results,
                 "pair_samples": [
                     {"step": row["step"], "time_s": row["time_s"],
                      "actor_pairs": row["ttc_pairs"]}
                     for row in snapshots if row["ttc_pairs"]
                 ],
                 "eligible_pair_samples": supported_ttc,
                 "expected_pair_samples": expected_ttc,
                 "coverage": {"fraction": supported_ttc / expected_ttc if expected_ttc else None,
                              "complete": supported_ttc == expected_ttc,
                              "partial_observation_count": partial_rows,
                              "missing_reasons": ttc_missing}},
                units="s", interpretation=primary_interpretation,
                eligible_samples=supported_ttc, window=window, actors=actor_refs,
                limitations=("No-overlap interpretation applies only with complete present-counterpart coverage",
                             "Prediction uses current observed velocity only; it is not a safety guarantee"),
            ))
    else:
        no_counterpart = not any_counterpart and any(row["ego_present"] for row in snapshots)
        status = AssessmentStatus.NOT_APPLICABLE if no_counterpart else invalid_status or AssessmentStatus.UNAVAILABLE
        reason = ("No simultaneous present counterpart exists in the selected window"
                  if no_counterpart else invalid_reason or
                  "No present counterpart pair has supported dimensions and motion")
        metrics.append(_status_metric("safety.ttc", version, status, reason, units="s",
                                      eligible_samples=supported_ttc,
                                      window=window, actors=actor_refs,
                                      limitations=invalid_limitation + (
                                          f"expected_pair_samples={expected_ttc}",
                                          f"eligible_pair_samples={supported_ttc}",
                                          f"missing_reasons={ttc_missing}",
                                      )))

    # Threshold exposure uses supported left-observation intervals. Positive
    # findings on an evaluated subset remain lower bounds; missing pairs never
    # produce a window-wide zero or a safety pass.
    near = values["safety"]["near_miss"]
    ttc_thresholds = sorted(set([near["ttc_below_s"], *near["ttc_sensitivity_s"]]))
    clearance_thresholds = sorted(set([near["footprint_clearance_below_m"],
                                       *near["clearance_sensitivity_m"]]))
    near_data = {"ttc": {}, "clearance": {}}
    total_interval_s = 0.0
    complete_ttc_s = complete_clearance_s = 0.0
    for row in snapshots:
        index = row["index"]
        if (not row["ego_present"] or index + 1 >= len(frames)
                or window == "primary" and index >= last):
            continue
        dt = _interval_dt(index, frames, times)
        if dt is None:
            continue
        current_map, following_map = _actor_map(frames[index]), _actor_map(frames[index + 1])
        ego_next = following_map.get(ego_id)
        if not _identity_continuous(current_map.get(ego_id), ego_next):
            continue
        geometry_pairs = [pair for pair in row["geometry_pairs"]
                          if _identity_continuous(current_map.get(pair["actor"]["source_id"]),
                                                  following_map.get(pair["actor"]["source_id"]))]
        ttc_pairs = [pair for pair in row["ttc_pairs"]
                     if _identity_continuous(current_map.get(pair["actor"]["source_id"]),
                                             following_map.get(pair["actor"]["source_id"]))]
        expected = row["expected_pairs"]
        if not expected:
            continue
        total_interval_s += dt
        complete_clearance = len(geometry_pairs) == expected
        complete_ttc = len(ttc_pairs) == expected
        complete_clearance_s += dt if complete_clearance else 0.0
        complete_ttc_s += dt if complete_ttc else 0.0
        min_gap = min((pair["clearance_m"] for pair in geometry_pairs), default=None)
        primary_ttc_key = str(float(primary_horizon))
        finite_ttc = [pair["horizons"][primary_ttc_key]["ttc_s"] for pair in ttc_pairs
                      if pair["horizons"][primary_ttc_key]["ttc_s"] is not None]
        min_ttc = min(finite_ttc) if finite_ttc else None
        for threshold in ttc_thresholds:
            key = f"below_{threshold:g}s"
            record = near_data["ttc"].setdefault(key, {
                "threshold_s": float(threshold), "observed_lower_bound_duration_s": 0.0,
                "complete_coverage_duration_s": 0.0,
                "complete_coverage_below_duration_s": 0.0,
                "eligible_interval_count": 0,
            })
            if ttc_pairs:
                record["eligible_interval_count"] += 1
                if min_ttc is not None and min_ttc < threshold:
                    record["observed_lower_bound_duration_s"] += dt
                if complete_ttc:
                    record["complete_coverage_duration_s"] += dt
                    if min_ttc is not None and min_ttc < threshold:
                        record["complete_coverage_below_duration_s"] += dt
                    # A complete no-future-prediction interval is a supported
                    # known false for a short-TTC criterion.
            # With no eligible pair the interval contributes no positive or
            # negative threshold evidence; it remains in coverage accounting.
        for threshold in clearance_thresholds:
            key = f"below_{threshold:g}m"
            record = near_data["clearance"].setdefault(key, {
                "threshold_m": float(threshold), "observed_lower_bound_duration_s": 0.0,
                "complete_coverage_duration_s": 0.0,
                "complete_coverage_below_duration_s": 0.0,
                "eligible_interval_count": 0,
            })
            if geometry_pairs:
                record["eligible_interval_count"] += 1
                if min_gap is not None and min_gap < threshold:
                    record["observed_lower_bound_duration_s"] += dt
                if complete_clearance:
                    record["complete_coverage_duration_s"] += dt
                    if min_gap is not None and min_gap < threshold:
                        record["complete_coverage_below_duration_s"] += dt
    for family in near_data.values():
        for record in family.values():
            record["observed_lower_bound_duration_s"] = float(record["observed_lower_bound_duration_s"])
            record["complete_coverage_duration_s"] = float(record["complete_coverage_duration_s"])
            record["complete_coverage_below_duration_s"] = float(record["complete_coverage_below_duration_s"])
            record["duration_method"] = "left_observation_sampled_interval_approximation"
            record["window_wide_zero_supported"] = (
                record["complete_coverage_duration_s"] >= total_interval_s - _EPS
                and record["observed_lower_bound_duration_s"] == 0.0
            )
            if record["observed_lower_bound_duration_s"] == 0.0 and not record["window_wide_zero_supported"]:
                record["observed_lower_bound_duration_s"] = None
                record["observed_duration_status"] = "unavailable_partial_coverage"
            else:
                record["observed_duration_status"] = "valid"
    no_counterpart = not any_counterpart and any(row["ego_present"] for row in snapshots)
    if no_counterpart:
        metrics.append(_status_metric(
            "safety.near_miss_exposure", version, AssessmentStatus.NOT_APPLICABLE,
            "No simultaneous present counterpart exists in the selected window",
            units={"TTC": "s", "clearance": "s"}, window=window,
            limitations=("TTC and clearance thresholds are reported separately",),
        ))
    elif invalid_status:
        metrics.append(_status_metric(
            "safety.near_miss_exposure", version, invalid_status, invalid_reason,
            units={"TTC": "s", "clearance": "s"}, window=window,
            eligible_samples=supported_geometry + supported_ttc,
            limitations=invalid_limitation,
        ))
    elif total_interval_s > 0 and (supported_geometry or supported_ttc):
        metrics.append(_status_metric(
            "safety.near_miss_exposure", version, AssessmentStatus.VALID,
            "Separate TTC and sampled-clearance threshold durations on supported intervals",
            {"ttc_thresholds": near_data["ttc"],
             "clearance_thresholds": near_data["clearance"],
             "supported_scene_interval_duration_s": float(total_interval_s),
             "complete_ttc_coverage_duration_s": float(complete_ttc_s),
             "complete_clearance_coverage_duration_s": float(complete_clearance_s),
             "expected_geometry_pair_samples": expected_geometry,
             "eligible_geometry_pair_samples": supported_geometry,
             "geometry_missing_reasons": geometry_missing,
             "expected_ttc_pair_samples": expected_ttc,
             "eligible_ttc_pair_samples": supported_ttc,
             "ttc_missing_reasons": ttc_missing,
             "coverage_is_complete": complete_ttc_s >= total_interval_s - _EPS
             and complete_clearance_s >= total_interval_s - _EPS},
            units={"TTC": "s", "clearance": "s"},
            eligible_samples=sum(row["expected_pairs"] for row in snapshots),
            eligible_duration_s=float(total_interval_s), window=window, actors=actor_refs,
            limitations=("A positive subset duration is a supported lower bound",
                         "No window-wide zero is reported without complete counterpart coverage",
                         "Threshold durations use left-observation sampled approximation"),
        ))
    else:
        metrics.append(_status_metric(
            "safety.near_miss_exposure", version, AssessmentStatus.UNAVAILABLE,
            "No timed interval supports a present counterpart threshold exposure",
            units={"TTC": "s", "clearance": "s"},
            eligible_samples=supported_geometry + supported_ttc, window=window,
            limitations=("Missing counterpart motion or dimensions are not treated as safe",
                         f"expected_geometry_pair_samples={expected_geometry}",
                         f"eligible_geometry_pair_samples={supported_geometry}",
                         f"geometry_missing_reasons={geometry_missing}",
                         f"expected_ttc_pair_samples={expected_ttc}",
                         f"eligible_ttc_pair_samples={supported_ttc}",
                         f"ttc_missing_reasons={ttc_missing}"),
        ))
    return metrics


def measure_safety(frames, ego_id, report, profile, events, exposure, *,
                   evaluation_capture=None, evaluation_capture_bound=False):
    """Measure saved-trace collision, clearance, overlap, TTC, and exposure."""
    frames = list(frames)
    capture_by_step = _event_capture_index(evaluation_capture, evaluation_capture_bound)
    times = _time_values(frames, profile, exposure)
    _enrich_collision_events(events, frames, ego_id, report, capture_by_step,
                             evaluation_capture_bound, times)
    metrics = []
    for window in ("full", "primary"):
        metrics.extend(_window_metrics(frames, ego_id, report, profile, events,
                                       exposure, times, window))
    return {"metrics": metrics}
