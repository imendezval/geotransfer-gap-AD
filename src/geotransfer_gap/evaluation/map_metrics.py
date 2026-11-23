"""Spatial measurements against hash-bound, source-mapped Lanelet surfaces."""

from __future__ import annotations

import math

from geotransfer_gap.evaluation.context import MapContext
from geotransfer_gap.evaluation.contracts import (
    AssessmentStatus,
    CriterionOutcome,
    MetricResult,
)


_AREA_EPS_M2 = 1e-9
_BOUNDARY_SAMPLE_SPACING_M = 0.02
_ASSIGNMENT_DISTANCE_TIE_M = 0.25
_HEADING_TIE_RAD = 0.1
_GEOMETRY_EQUIVALENCE_RAD = 0.05
_GEOMETRY_EQUIVALENCE_OFFSET_M = 0.1


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _actor(frame, ego_id):
    return next((row for row in frame.get("actors", ()) if row.get("id") == ego_id), None)


def _present_pose(actor):
    return bool(actor and actor.get("present") is True
                and _number(actor.get("x")) and _number(actor.get("y")))


def _generation(actor):
    value = actor.get("lifetime_generation") if actor else None
    return value if type(value) is int and value >= 0 else None


def _actor_refs(actors):
    """Return stable source-identity references, ordering unknown generations first."""
    refs = {(row.get("id"), _generation(row)) for row in actors if row is not None}
    return tuple(sorted(refs, key=lambda ref: (ref[0], -1 if ref[1] is None else ref[1])))


def _same_lifetime(first, second):
    if not first or not second or first.get("id") != second.get("id"):
        return False
    left, right = _generation(first), _generation(second)
    return left == right if left is not None or right is not None else True


def _times(frames, exposure):
    masks = exposure.get("observation_masks", ())
    if len(masks) == len(frames):
        return [row.get("time_s") for row in masks]
    return [frame.get("time_s") for frame in frames]


def _footprint(actor, shapely_polygon, dimension_observations):
    # Reuse PE04's same-lifetime-only dimension support and invalidity checks.
    from geotransfer_gap.evaluation.safety import _dimensions

    dimensions, source, imputed, invalid_dimensions = _dimensions(actor, dimension_observations)
    if dimensions is None:
        return None, ("invalid_nonpositive_or_nonfinite_footprint_dimension"
                      if invalid_dimensions else "footprint_dimensions_missing"), None
    if not _number(actor.get("heading")):
        return None, "footprint_heading_missing", None
    # PE04's audited helper owns the actor footprint corner convention.
    from geotransfer_gap.validation.audit_physical_source import corners

    box = {
        "position": [{"x": float(actor["x"]), "y": float(actor["y"])}],
        "heading": [float(actor["heading"])],
        "length": dimensions[0],
        "width": dimensions[1],
    }
    polygon = shapely_polygon(corners(box, 0))
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        return None, "invalid_ego_footprint_geometry", None
    return polygon, None, {
        "source": source,
        "imputed_fields": list(imputed),
        "length_m": dimensions[0],
        "width_m": dimensions[1],
    }


def _boundary_excursion(footprint, road_union, point_type):
    """Max boundary distance outside road union, sampled at <=2 cm spacing.

    The distance-to-set function is 1-Lipschitz. Every point on the closed
    footprint boundary is within half a sample interval (<=1 cm) of one of
    the generated samples, bounding the sampled maximum's under-estimate.
    """
    maximum = 0.0
    boundary = footprint.exterior
    rings = [boundary, *(footprint.interiors or ())]
    for ring in rings:
        coords = list(ring.coords)
        for start, end in zip(coords, coords[1:]):
            length = math.dist(start, end)
            count = max(1, math.ceil(length / _BOUNDARY_SAMPLE_SPACING_M))
            for index in range(count):
                fraction = index / count
                point = point_type(
                    start[0] + fraction * (end[0] - start[0]),
                    start[1] + fraction * (end[1] - start[1]),
                )
                if not road_union.covers(point):
                    maximum = max(maximum, float(point.distance(road_union)))
    return float(maximum)


def _interval_support(index, frames, actors, times):
    if index >= len(frames) - 1:
        return None, "no_outgoing_observation_interval"
    left_frame, right_frame = frames[index], frames[index + 1]
    left, right = actors[index], actors[index + 1]
    if not (_present_pose(left) and _present_pose(right) and _same_lifetime(left, right)):
        return None, "ego_pose_absent_or_lifetime_boundary"
    if left_frame.get("transition_applied") is False:
        return None, "transition_not_applied"
    left_valid, right_valid = left.get("source_valid"), right.get("source_valid")
    if type(left_valid) is bool or type(right_valid) is bool:
        if type(left_valid) is not bool or type(right_valid) is not bool or left_valid != right_valid:
            return None, "source_validity_boundary_or_unknown"
    start, end = times[index], times[index + 1]
    if not (_number(start) and _number(end) and end > start):
        return None, "time_missing_or_nonincreasing"
    return float(end - start), None


def _metric(metric_id, version, *, status, reason, value=None, units=None,
            samples=0, duration=None, window=None, limitations=(), evidence_refs=(),
            actors=()):
    return MetricResult(
        metric_id=metric_id,
        definition_version=version,
        status=status,
        reason=reason,
        value=value,
        units=units,
        criterion_outcome=CriterionOutcome.NOT_ASSESSED,
        eligible_samples=samples,
        eligible_duration_s=duration,
        window=window,
        actors=tuple(actors),
        limitations=tuple(limitations),
        evidence_refs=tuple(evidence_refs),
    ).to_dict()


def _window_indices(count, window, warmup, last):
    return [index for index in range(count)
            if window == "full" or warmup <= index <= last]


def _measure_road_metric(frames, actors, times, context, version, window,
                         selected, interval_indices, *, exposure,
                         polygon_type, point_type):
    if context.status != "valid" or context.road_union is None or context.coverage_union is None:
        status = AssessmentStatus.INVALID if context.status == "invalid" else AssessmentStatus.UNAVAILABLE
        return _metric(
            "safety.map_footprint_outside", version, status=status,
            reason=context.reason, units={"outside_area": "m^2", "duration": "s",
                                          "maximum_boundary_excursion": "m"},
            window=window, evidence_refs=context.evidence_refs,
            limitations=("Native off-road event measurements remain an independent channel",),
            actors=_actor_refs(actors),
        )

    samples = []
    samples_by_index = {}
    from geotransfer_gap.evaluation.safety import _dimension_observations

    dimension_observations = _dimension_observations(frames)
    counts = {"valid": 0, "map_coverage_gap": 0, "missing_pose": 0,
              "invalid_footprint": 0, "unavailable_footprint": 0}
    for index in selected:
        frame, actor = frames[index], actors[index]
        step = frame.get("step", index)
        time_s = times[index] if _number(times[index]) else None
        if not _present_pose(actor):
            counts["missing_pose"] += 1
            row = {"step": step, "time_s": time_s, "status": "unavailable",
                   "reason": "ego pose is absent"}
            samples.append(row)
            continue
        center = point_type(float(actor["x"]), float(actor["y"]))
        if not context.coverage_union.covers(center):
            counts["map_coverage_gap"] += 1
            row = {"step": step, "time_s": time_s, "status": "unavailable",
                   "reason": "ego centre is outside explicitly mapped surface coverage; outside area is unknown"}
            samples.append(row)
            continue
        footprint, problem, dimension_source = _footprint(
            actor, polygon_type, dimension_observations
        )
        if problem:
            invalid = problem.startswith("invalid")
            counts["invalid_footprint" if invalid else "unavailable_footprint"] += 1
            row = {"step": step, "time_s": time_s,
                   "status": "invalid" if invalid else "unavailable",
                   "reason": problem}
            samples.append(row)
            continue
        outside = footprint.difference(context.road_union)
        outside_area = float(outside.area)
        is_outside = outside_area > _AREA_EPS_M2
        excursion = _boundary_excursion(footprint, context.road_union, point_type)
        row = {
            "step": step,
            "time_s": time_s,
            "status": "valid",
            "outside_indicator": bool(is_outside),
            "outside_area_m2": outside_area,
            "maximum_footprint_boundary_excursion_m": excursion,
            "boundary_excursion_method": "closed_boundary_samples_at_most_0.02m_spacing",
            "boundary_excursion_sampling_underestimate_bound_m": 0.01,
            "area_method": "exact_polygon_difference_from_mapped_road_union",
            "dimension_support": dimension_source,
        }
        samples.append(row)
        samples_by_index[index] = row
        counts["valid"] += 1

    valid_rows = list(samples_by_index.values())
    supported_intervals = []
    outside_duration = 0.0
    interval_exclusions = {}
    for index in interval_indices:
        dt, exclusion = _interval_support(index, frames, actors, times)
        row = samples_by_index.get(index)
        if dt is None:
            interval_exclusions[exclusion] = interval_exclusions.get(exclusion, 0) + 1
            continue
        if row is None:
            interval_exclusions["left_observation_map_coverage_unavailable"] = \
                interval_exclusions.get("left_observation_map_coverage_unavailable", 0) + 1
            continue
        supported_intervals.append(dt)
        if row["outside_indicator"]:
            outside_duration += dt
    supported_duration = float(sum(supported_intervals)) if supported_intervals else None
    outside_duration_value = float(outside_duration) if supported_intervals else None
    any_coverage = bool(valid_rows)
    if not any_coverage:
        status = AssessmentStatus.INVALID if counts["invalid_footprint"] else AssessmentStatus.UNAVAILABLE
        reason = ("No valid footprint states could be assessed against the selected map coverage"
                  if status is AssessmentStatus.UNAVAILABLE
                  else "Supplied footprint dimensions or geometry are invalid")
        value = None
    else:
        status = AssessmentStatus.VALID
        reason = "Exact footprint difference against the source-mapped road-surface union"
        value = {
            "outside_observation_count": sum(row["outside_indicator"] for row in valid_rows),
            "assessed_observation_count": len(valid_rows),
            "outside_area_m2": {
                "maximum": float(max(row["outside_area_m2"] for row in valid_rows)),
                "mean": float(sum(row["outside_area_m2"] for row in valid_rows) / len(valid_rows)),
            },
            "maximum_footprint_boundary_excursion_m": float(max(
                row["maximum_footprint_boundary_excursion_m"] for row in valid_rows)),
            "observed_outside_duration_s": outside_duration_value,
            "observed_outside_duration_status": (
                "valid" if supported_intervals else "unavailable_no_supported_pose_intervals"
            ),
            "pose_supported_duration_s": supported_duration,
            "pose_duration_status": "valid" if supported_intervals else "unavailable_no_supported_pose_intervals",
            "duration_method": "left_observation_sampled_approximation_over_valid_consecutive_pose_intervals",
            "time_source": exposure.get("time_source", "recorded_or_unavailable"),
            "interval_support": {
                "eligible_intervals": len(supported_intervals),
                "excluded_intervals": interval_exclusions,
            },
            "coverage": {
                "scope": context.coverage_scope,
                "map_completeness_attested": False,
                "assessed_observations": len(valid_rows),
                "unavailable_map_gap_observations": counts["map_coverage_gap"],
                "unavailable_missing_pose_observations": counts["missing_pose"],
                "invalid_footprint_observations": counts["invalid_footprint"],
                "unavailable_footprint_observations": counts["unavailable_footprint"],
                "complete_for_selected_window": counts["valid"] == len(selected),
            },
            "samples": samples,
            "native_offroad_channel": "safety.native_offroad_onsets",
            "legal_access_status": "not_assessed",
        }
    limitations = [
        "This is membership in the hash-bound mapped Lanelet road/bus-lane/crosswalk surface union, not a legal-access verdict.",
        "Bus-lane polygons describe physical mapped surface; permission to use them is not assessed.",
        "Coverage completeness beyond explicitly mapped Lanelet surfaces is not attested.",
        "Boundary excursion is sampled at <=0.02 m; the 1-Lipschitz distance gives a <=0.01 m under-estimate bound.",
        "A terminal absent pose contributes no post-removal footprint or duration; observed duration is censored.",
    ]
    if counts["map_coverage_gap"]:
        limitations.append(f"{counts['map_coverage_gap']} observations fell outside mapped surface coverage and remain unavailable")
    if counts["unavailable_footprint"]:
        limitations.append(f"{counts['unavailable_footprint']} observations lacked supported footprint dimensions/heading")
    if counts["invalid_footprint"]:
        limitations.append(f"{counts['invalid_footprint']} observations supplied invalid footprint data")
    summary = exposure.get("windows", {}).get(window, {})
    if summary.get("post_terminal_trajectory_unobserved"):
        limitations.append("Trajectory duration after the recorded terminal event is censored")
    return _metric(
        "safety.map_footprint_outside", version, status=status, reason=reason,
        value=value,
        units={"outside_area": "m^2", "duration": "s",
               "maximum_boundary_excursion": "m"},
        samples=len(valid_rows), duration=supported_duration, window=window,
        limitations=limitations, evidence_refs=context.evidence_refs,
        actors=_actor_refs(actors),
    )


def _point_projection(point, lane):
    x, y = point
    best = None
    for start, end in zip(lane.points, lane.points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length2 = dx * dx + dy * dy
        if length2 <= 1e-16:
            continue
        fraction = max(0.0, min(1.0, ((x - start[0]) * dx + (y - start[1]) * dy) / length2))
        qx, qy = start[0] + fraction * dx, start[1] + fraction * dy
        distance = math.hypot(x - qx, y - qy)
        tangent = math.atan2(dy, dx)
        signed_offset = (dx * (y - qy) - dy * (x - qx)) / math.sqrt(length2)
        value = (distance, signed_offset, tangent)
        if best is None or distance < best[0]:
            best = value
    return best


def _candidate_assignment(actor, lanes, *, minimum_speed):
    speed_ok = _number(actor.get("vx")) and _number(actor.get("vy"))
    speed = math.hypot(actor["vx"], actor["vy"]) if speed_ok else None
    projections = []
    for lane in lanes:
        if len(lane.points) < 2 or lane.width_m is None:
            continue
        projected = _point_projection((float(actor["x"]), float(actor["y"])), lane)
        if projected is None:
            continue
        distance, offset, tangent = projected
        if distance <= lane.width_m / 2 + 1.0:
            projections.append((lane, distance, offset, tangent))
    if not projections:
        return None, "no_nearby_directed_lanelet"
    nearest = min(row[1] for row in projections)
    candidates = [row for row in projections if row[1] <= nearest + _ASSIGNMENT_DISTANCE_TIE_M]
    # Collapse duplicated/overlapping centerlines that describe the same
    # directed lane; retain multiple source IDs in the recorded assignment.
    clusters = []
    for item in sorted(candidates, key=lambda row: row[0].lanelet_id):
        lane, _, offset, tangent = item
        match = next((cluster for cluster in clusters
                      if abs(_wrap(tangent - cluster[0][3])) <= _GEOMETRY_EQUIVALENCE_RAD
                      and abs(offset - cluster[0][2]) <= _GEOMETRY_EQUIVALENCE_OFFSET_M), None)
        if match is None:
            clusters.append([item])
        else:
            match.append(item)
    if len(clusters) == 1:
        return clusters[0], None
    if not speed_ok:
        return None, "lane_direction_ambiguous_speed_missing"
    if speed <= minimum_speed:
        return None, "low_speed_direction_ambiguous_lane_assignment"
    if not _number(actor.get("heading")):
        return None, "lane_direction_ambiguous_heading_missing"
    scored = []
    for cluster in clusters:
        representative = min(cluster, key=lambda row: (row[1], row[0].lanelet_id))
        error = abs(_wrap(float(actor["heading"]) - representative[3]))
        scored.append((error, representative[1], representative[0].lanelet_id, cluster))
    scored.sort(key=lambda row: (row[0], row[1], row[2]))
    if len(scored) > 1 and scored[1][0] - scored[0][0] < _HEADING_TIE_RAD:
        return None, "contradictory_directed_lane_candidates"
    return scored[0][3], None


def _lane_samples(frames, actors, times, context, selected, minimum_speed):
    output = []
    statuses = {}
    for index in selected:
        frame, actor = frames[index], actors[index]
        step = frame.get("step", index)
        time_s = times[index] if _number(times[index]) else None
        if not _present_pose(actor):
            status, reason, assignment = "unavailable", "ego pose is absent", None
        else:
            from shapely.geometry import Point
            point = Point(float(actor["x"]), float(actor["y"]))
            if context.coverage_union is None or not context.coverage_union.covers(point):
                status, reason, assignment = "unavailable", "map coverage gap at ego centre", None
            else:
                assignment, reason = _candidate_assignment(
                    actor, context.lanes, minimum_speed=minimum_speed
                )
                status = ("valid" if assignment else
                          "unavailable" if "missing" in (reason or "") else "undefined")
        if assignment:
            lane, distance, offset, tangent = min(
                assignment, key=lambda row: (row[1], row[0].lanelet_id))
            ids = sorted({row[0].lanelet_id for row in assignment})
            speed_known = _number(actor.get("vx")) and _number(actor.get("vy"))
            speed = math.hypot(actor["vx"], actor["vy"]) if speed_known else None
            heading_delta = (
                _wrap(float(actor["heading"]) - tangent)
                if _number(actor.get("heading")) and speed is not None
                and speed > minimum_speed else None
            )
            lane_row = {
                "step": step, "time_s": time_s, "status": "valid",
                "lanelet_ids": ids,
                "successor_lanelet_ids": sorted({successor for row in assignment
                                                  for successor in row[0].successors}),
                "centerline_distance_m": float(distance),
                "signed_lateral_offset_m": float(offset),
                "heading_deviation_rad": heading_delta,
                "heading_status": ("valid" if heading_delta is not None else
                                   "undefined_low_speed" if speed is not None else
                                   "unavailable_speed_or_heading"),
                "direction_assignment_method": "unique_nearest_or_heading_resolved_directed_topology",
            }
            output.append(lane_row)
            statuses["valid"] = statuses.get("valid", 0) + 1
        else:
            output.append({"step": step, "time_s": time_s,
                           "status": status, "reason": reason})
            statuses[status] = statuses.get(status, 0) + 1
    return output, statuses


def _lane_metric(metric_id, version, samples, statuses, key, units, window, context, actors=()):
    supported = [row for row in samples if row.get("status") == "valid" and row.get(key) is not None]
    if context.status != "valid":
        status = AssessmentStatus.INVALID if context.status == "invalid" else AssessmentStatus.UNAVAILABLE
        reason = context.reason
        value = None
    elif not supported:
        heading_key = key == "heading_deviation_rad"
        missing_quantity = any(
            row.get("heading_status") == "unavailable_speed_or_heading"
            for row in samples
        ) if heading_key else False
        undefined_quantity = any(
            row.get("heading_status") == "undefined_low_speed"
            for row in samples
        ) if heading_key else False
        status = (AssessmentStatus.UNAVAILABLE
                  if statuses.get("unavailable") or missing_quantity
                  else AssessmentStatus.UNDEFINED)
        row_reasons = sorted({row.get("reason") for row in samples if row.get("reason")})
        if undefined_quantity:
            row_reasons.append("low-speed heading is undefined at or below the configured stationary threshold")
        reason = "No unambiguous lane assignment supports this diagnostic in the selected window"
        if missing_quantity:
            reason = "Lane assignment exists but observed speed or heading is absent"
        if row_reasons:
            reason += "; sample states: " + ", ".join(row_reasons)
        value = None
    else:
        values = [row[key] for row in supported]
        status = AssessmentStatus.VALID
        reason = "Conditional lane geometry diagnostic; no legal or wrong-way criterion is inferred"
        value = {
            "minimum": float(min(values)),
            "maximum": float(max(values)),
            "mean": float(sum(values) / len(values)),
            "samples": samples,
            "assignment_status_counts": statuses,
            "assignment_coverage_complete": len(supported) == len(samples),
            "legal_access_status": "not_assessed",
        }
    limitations = [
        "Lane offset and heading describe geometry only; deviation is not a rule violation.",
        "Assignments require mapped coverage and a defensible directed lane candidate.",
        "Low speed, crossings, overlapping contradictory directions and map gaps remain explicit.",
    ]
    return _metric(metric_id, version, status=status, reason=reason, value=value,
                   units=units, samples=len(supported), window=window,
                   limitations=limitations, evidence_refs=context.evidence_refs,
                   actors=_actor_refs(actors))


def measure_map_metrics(frames, ego_id, profile, exposure, context):
    """Return PE05 road-area and conditional lane diagnostics for saved states."""
    version = profile.values["profile"]["definition_version"]
    timing = profile.values["time"]
    warmup = timing["warmup_transitions"]
    last = timing["primary_last_observation_index"]
    actors = [_actor(frame, ego_id) for frame in frames]
    times = _times(frames, exposure)
    Point = Polygon = None
    if context.status == "valid":
        try:
            from shapely.geometry import Point, Polygon
        except ImportError:
            context = MapContext(
                status="unavailable",
                reason="Install the optional evaluation-geometry extra for spatial metrics",
                identity=context.identity,
                coverage_scope=context.coverage_scope,
                access_status=context.access_status,
            )
    metrics = []
    for window in ("full", "primary"):
        selected = _window_indices(len(frames), window, warmup, last)
        interval_indices = [index for index in range(max(0, len(frames) - 1))
                            if window == "full" or warmup <= index < last]
        metrics.append(_measure_road_metric(
            frames, actors, times, context, version, window, selected,
            interval_indices, exposure=exposure,
            polygon_type=Polygon or (lambda points: None),
            point_type=Point or (lambda *point: None),
        ))
        if context.status == "valid":
            samples, statuses = _lane_samples(
                frames, actors, times, context, selected,
                minimum_speed=profile.values["efficiency"]["stationary_speed_below_m_s"],
            )
        else:
            samples, statuses = [], {}
        metrics.append(_lane_metric(
            "trajectory.lane_lateral_offset", version, samples, statuses,
            "signed_lateral_offset_m", "m", window, context,
            actors=[actors[index] for index in selected],
        ))
        metrics.append(_lane_metric(
            "trajectory.lane_heading_deviation", version, samples, statuses,
            "heading_deviation_rad", "rad", window, context,
            actors=[actors[index] for index in selected],
        ))
    return {"metrics": metrics, "context": context.summary()}
