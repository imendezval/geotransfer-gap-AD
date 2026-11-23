"""Conditional rule assessments over saved poses and reviewed rule evidence.

This module consumes PE05 directed-lane assignments and the already validated
PE06 sparse annotation. It does not infer traffic rules from signs, source
driver behavior, or source-route certificates.
"""

from __future__ import annotations

import math

from geotransfer_gap.evaluation.contracts import (
    AssessmentStatus,
    CriterionOutcome,
    MetricResult,
)
from geotransfer_gap.evaluation.map_metrics import _point_projection
from geotransfer_gap.evaluation.safety import _dimension_observations, _dimensions


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _actor(frame, source_id):
    return next((row for row in frame.get("actors", ())
                 if row.get("id") == source_id), None)


def _generation(actor):
    value = actor.get("lifetime_generation") if actor else None
    return value if type(value) is int and value >= 0 else None


def _same_lifetime(left, right):
    if not left or not right or left.get("id") != right.get("id"):
        return False
    a, b = _generation(left), _generation(right)
    return a == b if a is not None or b is not None else True


def _present_pose(actor):
    return bool(actor and actor.get("present") is True
                and _finite(actor.get("x")) and _finite(actor.get("y")))


def _metric(metric_id, version, *, status, reason, value=None, units=None,
            samples=None, duration=None, criterion=CriterionOutcome.NOT_ASSESSED,
            evidence_refs=(), limitations=()):
    return MetricResult(
        metric_id=metric_id, definition_version=version, status=status,
        reason=reason, value=value, units=units, eligible_samples=samples,
        eligible_duration_s=duration, window="primary",
        criterion_outcome=criterion, evidence_refs=tuple(evidence_refs),
        limitations=tuple(limitations),
    ).to_dict()


def _claims(annotation, claim_type):
    if annotation.get("status") != "valid":
        return []
    return [row for row in annotation.get("claims_data", ())
            if row.get("claim", {}).get("claim_type") == claim_type
            and row.get("claim", {}).get("decision_status") == "supported"
            and row.get("claim", {}).get("review", {}).get("status") == "reviewed"]


def _evidence_bound(decision, selected):
    """Require each operational decision field to occur in selected evidence."""
    if type(decision) is not dict or not selected:
        return False
    return all(any(type(value) is dict and key in value and value[key] == item
                   for value in selected)
               for key, item in decision.items())


def _valid_steps(decision):
    value = decision.get("valid_step_range")
    return (isinstance(value, list) and len(value) == 2
            and all(type(item) is int and item >= 0 for item in value)
            and value[0] <= value[1])


def _valid_rule_decision(rule, decision):
    if (type(decision) is not dict or decision.get("rule") != rule
            or not isinstance(decision.get("approach_lanelet_ids"), list)
            or not decision["approach_lanelet_ids"]
            or any(type(item) is not int for item in decision["approach_lanelet_ids"])
            or len(set(decision["approach_lanelet_ids"])) != len(decision["approach_lanelet_ids"])
            or not _valid_steps(decision)):
        return False
    if ("safe_completion_critical" in decision
            and type(decision["safe_completion_critical"]) is not bool):
        return False
    if decision.get("applicability") == "not_applicable":
        expected = {"rule", "applicability", "approach_lanelet_ids",
                    "valid_step_range", "reason"}
        return (set(decision) in (expected, expected | {"safe_completion_critical"})
                and isinstance(decision["reason"], str) and bool(decision["reason"].strip()))
    if decision.get("applicability") != "applicable":
        return False
    if rule == "wrong_way":
        expected = {"rule", "applicability", "approach_lanelet_ids",
                    "valid_step_range"}
        return set(decision) in (expected, expected | {"safe_completion_critical"})
    if rule == "speed_limit":
        expected = {"rule", "applicability", "approach_lanelet_ids",
                    "limit_kmh", "valid_step_range"}
        return (set(decision) in (expected, expected | {"safe_completion_critical"})
                and _finite(decision["limit_kmh"]) and decision["limit_kmh"] > 0)
    if rule == "stop_sign":
        line, direction = decision.get("stop_line_world_xy"), decision.get("approach_direction")
        expected = {"rule", "applicability", "approach_lanelet_ids",
                    "valid_step_range", "stop_line_world_xy", "approach_direction",
                    "required_stop_speed_m_s", "required_dwell_s", "stop_zone_m",
                    "line_tolerance_m"}
        return (set(decision) in (expected, expected | {"safe_completion_critical"})
                and isinstance(line, list) and len(line) == 2
                and all(isinstance(point, list) and len(point) == 2
                        and all(_finite(value) for value in point) for point in line)
                and math.dist(*line) > 0
                and isinstance(direction, list) and len(direction) == 2
                and all(_finite(value) for value in direction)
                and math.hypot(*direction) > 0
                and abs((line[1][0] - line[0][0]) * direction[0]
                        + (line[1][1] - line[0][1]) * direction[1])
                    <= 0.25 * math.dist(*line) * math.hypot(*direction)
                and _finite(decision["required_stop_speed_m_s"])
                and decision["required_stop_speed_m_s"] >= 0
                and _finite(decision["required_dwell_s"])
                and decision["required_dwell_s"] > 0
                and _finite(decision["stop_zone_m"]) and decision["stop_zone_m"] > 0
                and _finite(decision["line_tolerance_m"])
                and decision["line_tolerance_m"] > 0)
    if rule == "priority_yield":
        polygon, actor_ids = (decision.get("conflict_polygon_world_xy"),
                              decision.get("priority_actor_source_ids"))
        expected = {"rule", "applicability", "approach_lanelet_ids",
                    "valid_step_range", "conflict_polygon_world_xy",
                    "priority_actor_source_ids", "required_behavior"}
        return (set(decision) in (expected, expected | {"safe_completion_critical"})
                and isinstance(polygon, list) and len(polygon) >= 3
                and all(isinstance(point, list) and len(point) == 2
                        and all(_finite(value) for value in point) for point in polygon)
                and isinstance(actor_ids, list) and bool(actor_ids)
                and all(type(item) is int for item in actor_ids)
                and len(set(actor_ids)) == len(actor_ids)
                and decision["required_behavior"] == "ego_clear_while_priority_occupies")
    return False


def _decision_claims(annotation, rule, applicability="applicable",
                     claim_types=("rule_applicability",)):
    output = []
    for claim_type in claim_types:
        for row in _claims(annotation, claim_type):
            claim, decision = row["claim"], row["claim"].get("decision")
            if (type(decision) is dict and decision.get("rule") == rule
                    and decision.get("applicability") == applicability
                    and _valid_rule_decision(rule, decision)
                    and _evidence_bound(decision, row.get("selected_evidence", ()))):
                output.append(row)
    return output


def _has_malformed_claim(annotation, rule, claim_types=("rule_applicability",)):
    for claim_type in claim_types:
        for row in _claims(annotation, claim_type):
            decision = row["claim"].get("decision")
            if (type(decision) is dict and decision.get("rule") == rule
                    and decision.get("applicability") in {"applicable", "not_applicable"}
                    and (not _valid_rule_decision(rule, decision)
                         or not _evidence_bound(decision, row.get("selected_evidence", ())))):
                return True
    return False


def _contradictory_claims(applicable, explicit_na):
    for left in applicable:
        a = left["claim"]["decision"]
        for right in explicit_na:
            b = right["claim"]["decision"]
            if (set(a["approach_lanelet_ids"]) & set(b["approach_lanelet_ids"])
                    and max(a["valid_step_range"][0], b["valid_step_range"][0])
                    <= min(a["valid_step_range"][1], b["valid_step_range"][1])):
                return True
    return False


def _uncovered_rule_scope(rows, first, last, applicable, explicit_na):
    if last < first:
        return True
    for row in rows[first:last + 1]:
        if row["status"] != "valid":
            return True
        step, lane_ids = row["step"], set(row["lanelet_ids"])
        covered = False
        for claim in (*applicable, *explicit_na):
            decision = claim["claim"]["decision"]
            if (decision["valid_step_range"][0] <= step <= decision["valid_step_range"][1]
                    and lane_ids & set(decision["approach_lanelet_ids"])):
                covered = True
                break
        if not covered:
            return True
    return False


def _rule_rows(frames, ego_id, map_context, lane_assignment_samples):
    samples = {}
    for sample in lane_assignment_samples or ():
        step = sample.get("step")
        if type(step) is not int or step in samples:
            continue
        samples[step] = sample
    lanes = {lane.lanelet_id: lane for lane in map_context.lanes}
    output = []
    for index, frame in enumerate(frames):
        actor = _actor(frame, ego_id)
        step = frame.get("step", index)
        sample = samples.get(step)
        ids = sample.get("lanelet_ids", ()) if sample else ()
        candidates = []
        if (_present_pose(actor) and sample and sample.get("status") == "valid"
                and map_context.status == "valid"):
            for lane_id in ids:
                lane = lanes.get(lane_id)
                projection = (_point_projection((float(actor["x"]), float(actor["y"])), lane)
                              if lane else None)
                if projection:
                    candidates.append((projection[0], lane.lanelet_id, lane,
                                       projection[2]))
        if candidates:
            _, _, lane, tangent = min(candidates, key=lambda row: (row[0], row[1]))
            output.append({"index": index, "step": step,
                           "time_s": frame.get("time_s"), "actor": actor,
                           "lanelet_ids": sorted(set(ids)),
                           "lane": lane, "tangent": tangent, "status": "valid"})
        else:
            reason = (sample.get("reason") if sample and sample.get("reason") else
                      "PE05 directed-lane assignment is unavailable for this observation")
            output.append({"index": index, "step": step,
                           "time_s": frame.get("time_s"), "actor": actor,
                           "lanelet_ids": [], "status": "unavailable", "reason": reason})
    return output


def _primary_bounds(frames, profile):
    time = profile.values["time"]
    first = time["primary_start_observation"]
    last = min(time["primary_last_observation_index"], len(frames) - 1)
    return first, last


def _wrong_way(frames, rows, profile, version, evidence_refs, window,
               trace_horizon_complete):
    first, last = _primary_bounds(frames, profile)
    expected = max(0, last - first)
    supported, wrong, covered_duration = 0, [], 0.0
    max_interval = (float(profile.values["time"]["nominal_sample_interval_s"])
                    * 1.5)
    moving_floor = float(profile.values["efficiency"]["stationary_speed_below_m_s"])
    for index in range(first, last):
        left, right = rows[index], rows[index + 1]
        a, b = left.get("actor"), right.get("actor")
        if (left["status"] != "valid" or right["status"] != "valid"
                or not _same_lifetime(a, b)
                or frames[index].get("transition_applied") is False
                or not ({*left["lanelet_ids"]} & {*right["lanelet_ids"]})):
            continue
        step_a, step_b = left["step"], right["step"]
        t0, t1 = left.get("time_s"), right.get("time_s")
        if (type(step_a) is not int or type(step_b) is not int or step_b != step_a + 1
                or not _finite(t0) or not _finite(t1) or not 0 < t1 - t0 <= max_interval):
            continue
        dx, dy = float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"])
        longitudinal = dx * math.cos(left["tangent"]) + dy * math.sin(left["tangent"])
        distance = math.hypot(dx, dy)
        supported += 1
        covered_duration += float(t1 - t0)
        if distance / (t1 - t0) > moving_floor and longitudinal < -0.02:
            wrong.append({"from_step": step_a, "to_step": step_b,
                          "duration_s": float(t1 - t0),
                          "distance_m": float(-longitudinal)})
    interval_coverage_complete = expected > 0 and supported == expected
    coverage_complete = interval_coverage_complete and trace_horizon_complete
    total_distance = sum(row["distance_m"] for row in wrong)
    total_duration = sum(row["duration_s"] for row in wrong)
    criterion = (CriterionOutcome.FAIL if wrong else
                 CriterionOutcome.PASS if coverage_complete else
                 CriterionOutcome.NOT_ASSESSED)
    status = AssessmentStatus.VALID if supported else AssessmentStatus.UNAVAILABLE
    reason = ("Observed moving travel opposite to the assigned directed lane"
              if wrong else "Directed-lane observations support no moving wrong-way travel"
              if coverage_complete else
              "Directed-lane or transition coverage is incomplete; absence is not a pass")
    value = ({"distance_m": float(total_distance), "duration_s": float(total_duration),
              "intervals": wrong, "coverage": {"expected_intervals": expected,
                                                 "supported_intervals": supported,
                                                 "intervals_complete": interval_coverage_complete,
                                                 "observation_horizon_complete": trace_horizon_complete,
                                                 "complete": coverage_complete},
              "warmup_observations_excluded": min(first, len(frames)),
              "criterion_window": "primary_policy_observations"}) if supported else None
    limitation = (() if coverage_complete else
                  ("Missing or ambiguous directed-lane intervals remain unassessed",))
    metrics = [
        _metric("rules.wrong_way_distance", version, status=status, reason=reason,
                value=value["distance_m"] if value else None, units="m",
                samples=supported, duration=covered_duration, criterion=criterion,
                evidence_refs=evidence_refs, limitations=limitation),
        _metric("rules.wrong_way_duration", version, status=status, reason=reason,
                value=value["duration_s"] if value else None, units="s",
                samples=supported, duration=covered_duration, criterion=criterion,
                evidence_refs=evidence_refs, limitations=limitation),
    ]
    return metrics, {"status": status.value, "reason": reason,
                     "criterion_outcome": criterion.value,
                     "supported_intervals": supported,
                     "expected_intervals": expected,
                     "observation_horizon_complete": trace_horizon_complete,
                     "wrong_way_distance_m": total_distance if supported else None,
                     "wrong_way_duration_s": total_duration if supported else None,
                     "intervals": wrong, "window": window}


def _speed_limit(frames, rows, annotation, profile, version, evidence_refs,
                 trace_horizon_complete):
    if annotation.get("status") == "invalid":
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.INVALID,
                       reason=annotation.get("reason", "Sparse semantic annotation is invalid"),
                       evidence_refs=evidence_refs), {
                           "status": "invalid", "reason": annotation.get("reason")}
    if _has_malformed_claim(annotation, "speed_limit"):
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.INVALID,
                       reason="A supplied speed-limit claim is malformed or not evidence-bound",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "A supplied speed-limit claim is malformed or not evidence-bound"}
    claims = _decision_claims(annotation, "speed_limit")
    explicit_na = _decision_claims(annotation, "speed_limit", "not_applicable")
    if _contradictory_claims(claims, explicit_na):
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.INVALID,
                       reason="Conflicting applicable and not-applicable speed-limit claims overlap",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "Conflicting applicable and not-applicable claims overlap"}
    if not claims and not explicit_na:
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No reviewed, evidence-bound applicable speed limit is supplied",
                       units={"speed_exceedance": "m/s", "duration": "s"},
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No reviewed, evidence-bound applicable speed limit is supplied"}
    first, last = _primary_bounds(frames, profile)
    if last < first:
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No primary policy observation is available",
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No primary policy observation is available"}
    supported, expected, excess_samples, duration, gaps = 0, 0, [], 0.0, 0
    for index in range(first, last + 1):
        row = rows[index]
        step = row["step"]
        if row["status"] != "valid":
            gaps += 1
            continue
        matching = [claim for claim in claims
                    if (claim["claim"]["decision"]["valid_step_range"][0] <= step <=
                        claim["claim"]["decision"]["valid_step_range"][1])
                    and set(row.get("lanelet_ids", ())) & set(
                        claim["claim"]["decision"]["approach_lanelet_ids"])]
        exempt = [claim for claim in explicit_na
                  if claim["claim"]["decision"]["valid_step_range"][0] <= step <=
                     claim["claim"]["decision"]["valid_step_range"][1]
                  and set(row.get("lanelet_ids", ())) & set(
                      claim["claim"]["decision"]["approach_lanelet_ids"])]
        if matching and exempt:
            gaps += 1
            continue
        if not matching:
            if not exempt:
                gaps += 1
            continue
        expected += 1
        limits = {claim["claim"]["decision"].get("limit_kmh") for claim in matching}
        if len(limits) != 1:
            gaps += 1
            continue
        limit_kmh = next(iter(limits))
        actor = row["actor"]
        if (not _finite(limit_kmh) or limit_kmh <= 0
                or not _finite(actor.get("vx")) or not _finite(actor.get("vy"))):
            gaps += 1
            continue
        speed = math.hypot(float(actor["vx"]), float(actor["vy"]))
        excess = max(0.0, speed - float(limit_kmh) / 3.6)
        supported += 1
        if index < last:
            dt = rows[index + 1].get("time_s") - row.get("time_s") if (
                _finite(rows[index + 1].get("time_s")) and _finite(row.get("time_s"))) else None
            if _finite(dt) and dt > 0:
                duration += float(dt)
        if excess > 0:
            excess_samples.append({"step": step, "speed_m_s": float(speed),
                                  "limit_m_s": float(limit_kmh) / 3.6,
                                  "excess_m_s": float(excess)})
    if expected == 0 and gaps == 0:
        refs = tuple(evidence_refs) + tuple(
            ref for claim in explicit_na for ref in claim["claim"].get("evidence_refs", ()))
        return _metric("rules.speed_limit_exceedance", version,
                       status=AssessmentStatus.NOT_APPLICABLE,
                       reason="Reviewed evidence explicitly records no applicable speed limit on the observed route",
                       evidence_refs=refs), {
                           "status": "not_applicable",
                           "reason": "Reviewed evidence explicitly records no applicable speed limit on the observed route"}
    complete = (expected > 0 and supported == expected and gaps == 0
                and trace_horizon_complete)
    outcome = (CriterionOutcome.FAIL if excess_samples else
               CriterionOutcome.PASS if complete else CriterionOutcome.NOT_ASSESSED)
    status = AssessmentStatus.VALID if supported else AssessmentStatus.UNAVAILABLE
    value = ({"maximum_exceedance_m_s": max(row["excess_m_s"] for row in excess_samples)
              if excess_samples else 0.0,
              "exceedance_observation_count": len(excess_samples),
              "exceedance_samples": excess_samples,
              "coverage": {"applicable_observations": expected,
                           "supported_observations": supported,
                           "interval_coverage_complete": supported == expected and gaps == 0,
                           "observation_horizon_complete": trace_horizon_complete,
                           "complete": complete}}) if supported else None
    reason = ("Observed speed above an authoritative applicable lane limit"
              if excess_samples else "Supported observations do not exceed the applicable speed limit"
              if complete else "Speed-limit applicability or observation coverage is incomplete")
    refs = tuple(evidence_refs) + tuple(
        ref for claim in (*claims, *explicit_na)
        for ref in claim["claim"].get("evidence_refs", ()))
    return _metric("rules.speed_limit_exceedance", version, status=status,
                   reason=reason, value=value, units="m/s",
                   samples=supported, duration=duration, criterion=outcome,
                   evidence_refs=refs), {
                       "status": status.value, "reason": reason,
                       "criterion_outcome": outcome.value,
                       "supported_observations": supported,
                       "applicable_observations": expected,
                       "exceedance_observation_count": len(excess_samples),
                       "coverage_complete": complete}


def _line_side(point, line, direction):
    return ((point[0] - line[0][0]) * direction[0]
            + (point[1] - line[0][1]) * direction[1])


def _point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 0:
        return math.dist(point, start)
    fraction = max(0.0, min(1.0, ((point[0] - start[0]) * dx
                                 + (point[1] - start[1]) * dy) / length2))
    return math.dist(point, (start[0] + fraction * dx, start[1] + fraction * dy))


def _stop_assessment(frames, rows, annotation, profile, version, evidence_refs,
                     trace_horizon_complete):
    if annotation.get("status") == "invalid":
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.INVALID,
                       reason=annotation.get("reason", "Sparse semantic annotation is invalid"),
                       evidence_refs=evidence_refs), {
                           "status": "invalid", "reason": annotation.get("reason")}
    if _has_malformed_claim(annotation, "stop_sign"):
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.INVALID,
                       reason="A supplied stop criterion is malformed or not evidence-bound",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "A supplied stop criterion is malformed or not evidence-bound"}
    claims = _decision_claims(annotation, "stop_sign")
    explicit_na = _decision_claims(annotation, "stop_sign", "not_applicable")
    if _contradictory_claims(claims, explicit_na):
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.INVALID,
                       reason="Conflicting applicable and not-applicable stop claims overlap",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "Conflicting applicable and not-applicable claims overlap"}
    if not claims and not explicit_na:
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No reviewed, evidence-bound stop approach and line criterion is supplied",
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No reviewed, evidence-bound stop approach and line criterion is supplied"}
    first, last = _primary_bounds(frames, profile)
    matched = []
    exempt = []
    for claim in (*claims, *explicit_na):
        d = claim["claim"]["decision"]
        if (set(d["approach_lanelet_ids"]) &
                {lid for row in rows[first:last + 1] for lid in row.get("lanelet_ids", ())}):
            if d["applicability"] == "applicable":
                matched.append(claim)
            else:
                exempt.append(claim)
    if not matched and not exempt:
        if any(row["status"] != "valid" for row in rows[first:last + 1]):
            return _metric("rules.stop_sign_compliance", version,
                           status=AssessmentStatus.UNAVAILABLE,
                           reason="Directed-lane coverage is incomplete for the annotated stop approach",
                           evidence_refs=evidence_refs), {
                               "status": "unavailable",
                               "reason": "Directed-lane coverage is incomplete for the annotated stop approach"}
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No reviewed stop claim covers the actual directed-lane approach",
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No reviewed stop claim covers the actual directed-lane approach"}
    scope_incomplete = _uncovered_rule_scope(rows, first, last, claims, explicit_na)
    if not matched and exempt:
        if scope_incomplete:
            return _metric("rules.stop_sign_compliance", version,
                           status=AssessmentStatus.UNAVAILABLE,
                           reason="The reviewed no-stop scope does not cover every observed directed approach",
                           evidence_refs=evidence_refs), {
                               "status": "unavailable",
                               "reason": "The reviewed no-stop scope does not cover every observed directed approach"}
        return _metric("rules.stop_sign_compliance", version,
                       status=AssessmentStatus.NOT_APPLICABLE,
                       reason="Reviewed evidence explicitly records no stop obligation on the actual approach",
                       evidence_refs=evidence_refs), {
                           "status": "not_applicable",
                           "reason": "Reviewed evidence explicitly records no stop obligation on the actual approach"}
    observed = []
    uncovered = scope_incomplete
    for claim in matched:
        d = claim["claim"]["decision"]
        line, direction = d["stop_line_world_xy"], d["approach_direction"]
        direction_norm = math.hypot(*direction)
        if direction_norm <= 0:
            uncovered = True
            continue
        direction = (direction[0] / direction_norm, direction[1] / direction_norm)
        applicable_indices = [i for i in range(first, last + 1)
                              if rows[i]["status"] == "valid"
                              and d["valid_step_range"][0] <= rows[i]["step"] <=
                                  d["valid_step_range"][1]
                              and set(rows[i]["lanelet_ids"]) & set(d["approach_lanelet_ids"])]
        if not applicable_indices:
            uncovered = True
            continue
        sides = {i: _line_side((float(rows[i]["actor"]["x"]),
                                 float(rows[i]["actor"]["y"])), line, direction)
                 for i in applicable_indices}
        plane_crossings = [i for i in applicable_indices if i > first and i - 1 in sides
                           and sides[i - 1] > 0 >= sides[i]]
        crossings = []
        for index in plane_crossings:
            points = [(float(rows[i]["actor"]["x"]), float(rows[i]["actor"]["y"]))
                      for i in (index - 1, index)]
            if min(_point_segment_distance(point, line[0], line[1]) for point in points) <= d["line_tolerance_m"]:
                crossings.append(index)
            else:
                uncovered = True
        if not crossings:
            near_line = any(0 <= sides[index] <= d["stop_zone_m"]
                            for index in applicable_indices if index in sides)
            if near_line and not trace_horizon_complete:
                uncovered = True
            continue
        for crossing in crossings:
            accumulated = 0.0
            best_dwell = 0.0
            previous_low = False
            crossing_incomplete = False
            for index in range(first, crossing):
                left, right = rows[index], rows[index + 1]
                dt = right.get("time_s") - left.get("time_s") if (
                    _finite(right.get("time_s")) and _finite(left.get("time_s"))) else None
                if (left["status"] != "valid" or right["status"] != "valid"
                        or not d["valid_step_range"][0] <= left["step"] <= d["valid_step_range"][1]
                        or not d["valid_step_range"][0] <= right["step"] <= d["valid_step_range"][1]
                        or left["step"] + 1 != right["step"]
                        or frames[index].get("transition_applied") is False
                        or not _finite(dt) or dt <= 0
                        or dt > float(profile.values["time"]["nominal_sample_interval_s"]) * 1.5
                        or not _same_lifetime(left.get("actor"), right.get("actor"))
                        or not ({*left["lanelet_ids"]} & {*right["lanelet_ids"]})):
                    uncovered = True
                    crossing_incomplete = True
                    previous_low = False
                    accumulated = 0.0
                    continue
                vx, vy = left["actor"].get("vx"), left["actor"].get("vy")
                speed = math.hypot(float(vx), float(vy)) if _finite(vx) and _finite(vy) else None
                side = sides.get(index)
                in_stop_zone = side is not None and 0 <= side <= d["stop_zone_m"]
                low = (_finite(dt) and dt > 0 and speed is not None
                       and speed <= d["required_stop_speed_m_s"] and in_stop_zone)
                if low:
                    accumulated = accumulated + float(dt) if previous_low else float(dt)
                    best_dwell = max(best_dwell, accumulated)
                else:
                    accumulated = 0.0
                previous_low = bool(low)
            met = best_dwell >= d["required_dwell_s"]
            observed.append({"line_crossing_step": rows[crossing]["step"],
                             "dwell_s": float(best_dwell), "required_dwell_s": d["required_dwell_s"],
                             "stop_observed": met,
                             "coverage_complete": not crossing_incomplete})
    if not observed:
        status, outcome = ((AssessmentStatus.UNAVAILABLE, CriterionOutcome.NOT_ASSESSED)
                           if uncovered else
                           (AssessmentStatus.NOT_APPLICABLE, CriterionOutcome.NOT_ASSESSED))
        reason = ("Stop approach evidence or trajectory is incomplete"
                  if uncovered else "The observed route did not cross an annotated stop line")
        value = None
    else:
        failed = any(not row["stop_observed"] and row["coverage_complete"]
                     for row in observed)
        outcome = (CriterionOutcome.FAIL if failed else
                   CriterionOutcome.NOT_ASSESSED
                   if uncovered or not trace_horizon_complete
                   or any(not row["stop_observed"] for row in observed)
                   else CriterionOutcome.PASS)
        status = AssessmentStatus.VALID
        reason = ("Observed stop-line crossing lacked the annotated stop dwell"
                  if failed else "Observed the required stop before crossing the annotated line"
                  if outcome is CriterionOutcome.PASS else
                  "A stop was observed, but some applicable approach evidence is incomplete")
        value = {"line_crossings": observed, "criterion_coverage_complete": not uncovered}
    refs = tuple(evidence_refs) + tuple(
        ref for claim in matched for ref in claim["claim"].get("evidence_refs", ()))
    metric = _metric("rules.stop_sign_compliance", version, status=status,
                     reason=reason, value=value, samples=len(observed) or None,
                     criterion=outcome, evidence_refs=refs)
    return metric, {"status": status.value, "reason": reason,
                    "criterion_outcome": outcome.value,
                    "line_crossings": observed}


def _footprint_occupancy(actor, polygon, dimensions):
    if not _present_pose(actor):
        return None
    dims, _, _, _ = _dimensions(actor, dimensions)
    if dims is None or not _finite(actor.get("heading")):
        return None
    # Reuse the source rule auditor's oriented-box/polygon intersection code.
    from geotransfer_gap.maps.audit_rule_applicability import box_hits_polygon

    source_actor = {
        "position": [{"x": float(actor["x"]), "y": float(actor["y"])}],
        "heading": [float(actor["heading"])],
        "length": dims[0], "width": dims[1],
    }
    return box_hits_polygon(source_actor, 0, polygon)


def _priority_assessment(frames, ego_id, rows, annotation, profile, version, evidence_refs,
                         trace_horizon_complete):
    if annotation.get("status") == "invalid":
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.INVALID,
                       reason=annotation.get("reason", "Sparse semantic annotation is invalid"),
                       evidence_refs=evidence_refs), {
                           "status": "invalid", "reason": annotation.get("reason")}
    claim_types = ("rule_applicability", "interaction_criterion")
    if _has_malformed_claim(annotation, "priority_yield", claim_types):
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.INVALID,
                       reason="A supplied priority criterion is malformed or not evidence-bound",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "A supplied priority criterion is malformed or not evidence-bound"}
    claims = _decision_claims(annotation, "priority_yield", claim_types=claim_types)
    explicit_na = _decision_claims(annotation, "priority_yield", "not_applicable",
                                   claim_types=claim_types)
    if _contradictory_claims(claims, explicit_na):
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.INVALID,
                       reason="Conflicting applicable and not-applicable priority claims overlap",
                       evidence_refs=evidence_refs), {
                           "status": "invalid",
                           "reason": "Conflicting applicable and not-applicable claims overlap"}
    if not claims and not explicit_na:
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No reviewed, evidence-bound priority obligation and conflict criterion is supplied",
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No reviewed, evidence-bound priority obligation and conflict criterion is supplied"}
    first, last = _primary_bounds(frames, profile)
    route_lanes = {lid for row in rows[first:last + 1] for lid in row.get("lanelet_ids", ())}
    matched = [claim for claim in claims if route_lanes & set(
        claim["claim"]["decision"]["approach_lanelet_ids"])]
    exempt = [claim for claim in explicit_na if route_lanes & set(
        claim["claim"]["decision"]["approach_lanelet_ids"])]
    if not matched and not exempt:
        if any(row["status"] != "valid" for row in rows[first:last + 1]):
            return _metric("rules.priority_yielding", version,
                           status=AssessmentStatus.UNAVAILABLE,
                           reason="Directed-lane coverage is incomplete for the annotated priority approach",
                           evidence_refs=evidence_refs), {
                               "status": "unavailable",
                               "reason": "Directed-lane coverage is incomplete for the annotated priority approach"}
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.UNAVAILABLE,
                       reason="No reviewed priority claim covers the actual directed-lane approach",
                       evidence_refs=evidence_refs), {
                           "status": "unavailable",
                           "reason": "No reviewed priority claim covers the actual directed-lane approach"}
    if not matched and exempt:
        if _uncovered_rule_scope(rows, first, last, claims, explicit_na):
            return _metric("rules.priority_yielding", version,
                           status=AssessmentStatus.UNAVAILABLE,
                           reason="The reviewed no-priority scope does not cover every observed directed approach",
                           evidence_refs=evidence_refs), {
                               "status": "unavailable",
                               "reason": "The reviewed no-priority scope does not cover every observed directed approach"}
        return _metric("rules.priority_yielding", version,
                       status=AssessmentStatus.NOT_APPLICABLE,
                       reason="Reviewed evidence explicitly records no priority obligation on the actual approach",
                       evidence_refs=evidence_refs), {
                           "status": "not_applicable",
                           "reason": "Reviewed evidence explicitly records no priority obligation on the actual approach"}
    dimensions = _dimension_observations(frames)
    assessments = []
    incomplete = (not trace_horizon_complete
                  or _uncovered_rule_scope(rows, first, last, claims, explicit_na))
    priority_occupied_conflict_region = False
    for claim in matched:
        d = claim["claim"]["decision"]
        conflict = d["conflict_polygon_world_xy"]
        actors = d["priority_actor_source_ids"]
        occupied = []
        actor_supported = 0
        previous_priority = {actor_id: None for actor_id in actors}
        for index in range(first, min(last, len(frames) - 1) + 1):
            row = rows[index]
            frame = frames[index]
            step = row["step"]
            if not d["valid_step_range"][0] <= step <= d["valid_step_range"][1]:
                continue
            if row["status"] != "valid":
                incomplete = True
                continue
            if not set(row["lanelet_ids"]) & set(d["approach_lanelet_ids"]):
                continue
            ego = _actor(frame, ego_id)
            ego_inside = _footprint_occupancy(ego, conflict, dimensions)
            if ego_inside is None:
                incomplete = True
                continue
            for actor_id in actors:
                priority = _actor(frame, actor_id)
                if priority is not None and priority.get("present") is False:
                    known_absence = (
                        priority.get("source_valid") is False
                        and priority.get("native_present") is False
                        and _generation(priority) is not None
                    )
                    if known_absence:
                        inside = False
                        previous_priority[actor_id] = None
                    else:
                        # A stored `present=False` row alone can mean a source
                        # validity gap or missing lifecycle join, not a known
                        # clear conflict region.
                        inside = None
                        incomplete = True
                else:
                    inside = _footprint_occupancy(priority, conflict, dimensions)
                    if priority is not None and priority.get("present") is True:
                        if _generation(priority) is None:
                            incomplete = True
                        previous = previous_priority[actor_id]
                        if (previous is not None and previous[0] == step - 1
                                and not _same_lifetime(previous[1], priority)):
                            incomplete = True
                        previous_priority[actor_id] = (step, priority)
                if inside is None:
                    # Missing actors are not evidence that the conflict was clear.
                    incomplete = True
                    continue
                actor_supported += 1
                if inside:
                    priority_occupied_conflict_region = True
                    if ego_inside:
                        occupied.append({"step": row["step"], "priority_actor_source_id": actor_id,
                                         "ego_and_priority_occupy_conflict": True})
        if actor_supported == 0:
            incomplete = True
        assessments.extend(occupied)
    if assessments:
        status, outcome = AssessmentStatus.VALID, CriterionOutcome.FAIL
        reason = "Ego and an explicitly designated priority actor occupied the annotated conflict region together"
        value = {"conflict_occupancy_conflicts": assessments,
                 "coverage_complete": not incomplete}
    elif incomplete:
        status, outcome = AssessmentStatus.UNAVAILABLE, CriterionOutcome.NOT_ASSESSED
        reason, value = ("Priority conflict or actor coverage is incomplete; yielding is not inferred",
                         None)
    elif not priority_occupied_conflict_region:
        status, outcome = AssessmentStatus.NOT_APPLICABLE, CriterionOutcome.NOT_ASSESSED
        reason = "No designated priority actor occupied the annotated conflict region"
        value = None
    else:
        status, outcome = AssessmentStatus.VALID, CriterionOutcome.PASS
        reason = "Complete supported observations show ego clear while the designated priority actor occupied the conflict"
        value = {"conflict_occupancy_conflicts": [], "coverage_complete": True}
    refs = tuple(evidence_refs) + tuple(
        ref for claim in (*matched, *exempt)
        for ref in claim["claim"].get("evidence_refs", ()))
    return _metric("rules.priority_yielding", version, status=status,
                   reason=reason, value=value, samples=len(assessments) or None,
                   criterion=outcome, evidence_refs=refs), {
                       "status": status.value, "reason": reason,
                       "criterion_outcome": outcome.value,
                       "conflict_occupancy_conflicts": assessments,
                       "coverage_complete": not incomplete}


def measure_semantics(frames, ego_id, profile, map_context, annotation, *,
                      lane_assignment_samples=(), evidence_refs=(),
                      trace_horizon_complete=True):
    """Return supported conditional rule metrics and explicit capability rows."""
    version = profile.definition_version
    annotation_refs = ([annotation["evidence_ref"]] if annotation.get("evidence_ref") else [])
    rule_evidence_refs = tuple(evidence_refs) + tuple(annotation_refs)
    rows = _rule_rows(frames, ego_id, map_context, lane_assignment_samples)
    wrong_metrics, wrong = _wrong_way(frames, rows, profile, version,
                                      evidence_refs, "primary", trace_horizon_complete)
    speed_metric, speed = _speed_limit(frames, rows, annotation, profile,
                                       version, rule_evidence_refs,
                                       trace_horizon_complete)
    stop_metric, stop = _stop_assessment(frames, rows, annotation, profile,
                                         version, rule_evidence_refs,
                                         trace_horizon_complete)
    priority_metric, priority = _priority_assessment(
        frames, ego_id, rows, annotation, profile, version, rule_evidence_refs,
        trace_horizon_complete)
    if map_context.status == "invalid":
        direction = {"status": "invalid", "reason": map_context.reason}
    elif any(row["status"] == "valid" for row in rows):
        direction = {"status": "valid", "reason": "Hash-bound directed lane assignments are available"}
    else:
        direction = {"status": "unavailable", "reason": map_context.reason}
    signal = {"status": "unavailable",
              "reason": "No authoritative dynamic signal-state timeline is available"}
    capabilities = {
        "direction_and_wrong_way": direction,
        "speed_limit": speed,
        "stop_sign": stop,
        "traffic_signal": signal,
        "priority_yielding": priority,
    }
    metrics = wrong_metrics + [speed_metric, stop_metric, priority_metric]
    return {
        "status": "valid" if direction["status"] == "valid" else direction["status"],
        "reason": "Conditional semantic coverage is reported per rule family",
        "capabilities": capabilities,
        "source_route_waiver_used": False,
        "warmup_observations_excluded_from_criterion": min(
            profile.values["time"]["primary_start_observation"], len(frames)),
        "metrics": metrics,
        "criteria": {"wrong_way": wrong, "speed_limit": speed,
                      "stop_sign": stop, "priority_yielding": priority,
                      "traffic_signal": {"status": "unavailable",
                                         "reason": signal["reason"]}},
    }
