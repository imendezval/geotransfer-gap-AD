"""Synthetic conditional-rule cases; no source dataset or simulator required."""

import math

import pytest

from geotransfer_gap.evaluation.context import LaneCenterline, MapContext
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.evaluation.semantics import measure_semantics


EGO = 41
PRIORITY = 99
PROFILE = load_profile()


def actor(source_id, x, y=0.0, *, speed=1.0, heading=0.0, present=True,
          generation=0):
    return {"id": source_id, "present": present,
            "x": float(x) if present else None, "y": float(y) if present else None,
            "vx": float(speed * math.cos(heading)) if present else None,
            "vy": float(speed * math.sin(heading)) if present else None,
            "heading": heading if present else None,
            "length": 2.0, "width": 1.0,
            "lifetime_generation": generation}


def frames(count=31, *, ego_x=None, ego_y=None, ego_speed=None,
           priority_x=None, priority_y=None):
    ego_x = ego_x or [i * 0.2 for i in range(count)]
    ego_y = ego_y or [0.0] * count
    ego_speed = ego_speed or [2.0] * count
    priority_x = priority_x or [5.0] * count
    priority_y = priority_y or [0.0] * count
    rows = []
    for i in range(count):
        rows.append({"step": i, "time_s": i / 10,
                     "transition_applied": i < count - 1,
                     "actors": [actor(EGO, ego_x[i], ego_y[i], speed=ego_speed[i]),
                                actor(PRIORITY, priority_x[i], priority_y[i], speed=0.0)]})
    return rows


def map_context(*, adjacent=False):
    lanes = [LaneCenterline(7, ((-20.0, 0.0), (30.0, 0.0)), 4.0, ())]
    if adjacent:
        lanes.append(LaneCenterline(8, ((-20.0, 4.0), (30.0, 4.0)), 4.0, ()))
    return MapContext("valid", "synthetic hash-bound directed map",
                      lanes=tuple(lanes),
                      identity={"evidence_refs": []})


def claim(rule, decision, *, evidence=None):
    evidence = decision if evidence is None else evidence
    return {"claim": {"claim_id": f"{rule}-{decision.get('approach_lanelet_ids')}",
                      "claim_type": "rule_applicability", "decision_status": "supported",
                      "review": {"status": "reviewed"}, "decision": decision,
                      "evidence_refs": [{"kind": "reviewed_semantic_evidence",
                                         "sha256": "a" * 64}]},
            "selected_evidence": [evidence]}


def annotation(*claims):
    return {"status": "valid", "claims_data": list(claims),
            "evidence_ref": {"kind": "sparse_evaluation_annotation",
                             "sha256": "b" * 64}}


def rule(result, name):
    return result["criteria"][name]


def stop_decision(lanes=(7,), *, line_x=0.0):
    return {"rule": "stop_sign", "applicability": "applicable",
            "approach_lanelet_ids": list(lanes), "valid_step_range": [10, 30],
            "stop_line_world_xy": [[line_x, -2.0], [line_x, 2.0]],
            "approach_direction": [-1.0, 0.0],
            "required_stop_speed_m_s": 0.2,
            "required_dwell_s": 1.0, "stop_zone_m": 0.75,
            "line_tolerance_m": 0.5}


def priority_decision():
    return {"rule": "priority_yield", "applicability": "applicable",
            "approach_lanelet_ids": [7], "valid_step_range": [10, 30],
            "conflict_polygon_world_xy": [[-0.5, -1.0], [0.5, -1.0],
                                           [0.5, 1.0], [-0.5, 1.0]],
            "priority_actor_source_ids": [PRIORITY],
            "required_behavior": "ego_clear_while_priority_occupies"}


def measure(observations, claims, *, ctx=None, horizon_complete=True):
    selected_map = ctx or map_context()
    lane_assignment_samples = []
    for i, frame in enumerate(observations):
        ego = next(row for row in frame["actors"] if row["id"] == EGO)
        if not ego["present"] or abs(ego["y"]) > 10:
            lane_assignment_samples.append({"step": frame["step"], "status": "unavailable",
                                            "reason": "synthetic map coverage gap"})
            continue
        lane_id = (8 if abs(ego["y"] - 4.0) < abs(ego["y"]) and
                   any(lane.lanelet_id == 8 for lane in selected_map.lanes) else 7)
        lane_assignment_samples.append({"step": frame["step"], "status": "valid",
                                        "lanelet_ids": [lane_id]})
    return measure_semantics(observations, EGO, PROFILE,
                             selected_map, annotation(*claims),
                             lane_assignment_samples=lane_assignment_samples,
                             evidence_refs=(),
                             trace_horizon_complete=horizon_complete)


def test_moving_wrong_way_needs_directed_assignment_and_low_speed_is_not_wrong_way():
    reverse_x = [12.0 - i * 0.2 for i in range(31)]
    reverse_speed = [-2.0] * 31
    reverse = measure(frames(ego_x=reverse_x, ego_speed=reverse_speed), [])
    assert rule(reverse, "wrong_way")["criterion_outcome"] == "fail"
    assert rule(reverse, "wrong_way")["wrong_way_distance_m"] == pytest.approx(4.0)
    assert rule(reverse, "wrong_way")["wrong_way_duration_s"] == pytest.approx(2.0)

    stopped = measure(frames(ego_x=[1.0] * 31, ego_speed=[0.0] * 31), [])
    assert rule(stopped, "wrong_way")["criterion_outcome"] == "pass"
    assert rule(stopped, "wrong_way")["wrong_way_distance_m"] == 0.0


def test_incomplete_directed_lane_coverage_never_passes_absence_of_wrong_way():
    rows = frames(ego_x=[12.0 - i * 0.2 for i in range(31)],
                  ego_speed=[-2.0] * 31)
    rows[18]["actors"][0]["y"] = 30.0
    result = measure(rows, [])
    assert rule(result, "wrong_way")["criterion_outcome"] == "fail"
    assert rule(result, "wrong_way")["supported_intervals"] < rule(result, "wrong_way")["expected_intervals"]


def test_warmup_is_excluded_and_truncated_horizon_cannot_pass_absence():
    x = [12.0 - i * 0.2 for i in range(11)]
    x.extend([x[-1] + i * 0.2 for i in range(1, 21)])
    trace = frames(ego_x=x, ego_speed=[2.0] * len(x))
    complete = measure(trace, [])
    assert rule(complete, "wrong_way")["criterion_outcome"] == "pass"
    truncated = measure(trace, [], horizon_complete=False)
    assert rule(truncated, "wrong_way")["criterion_outcome"] == "not_assessed"


def test_speed_limit_requires_reviewed_lane_scoped_evidence_and_detects_overspeed():
    decision = {"rule": "speed_limit", "applicability": "applicable",
                "approach_lanelet_ids": [7], "limit_kmh": 36.0,
                "valid_step_range": [10, 30]}
    fast = measure(frames(ego_speed=[15.0] * 31), [claim("speed_limit", decision)])
    assert rule(fast, "speed_limit")["criterion_outcome"] == "fail"
    assert rule(fast, "speed_limit")["exceedance_observation_count"] == 21

    compliant = measure(frames(ego_speed=[5.0] * 31), [claim("speed_limit", decision)])
    assert rule(compliant, "speed_limit")["criterion_outcome"] == "pass"
    truncated = measure(frames(ego_speed=[5.0] * 31), [claim("speed_limit", decision)],
                        horizon_complete=False)
    assert rule(truncated, "speed_limit")["criterion_outcome"] == "not_assessed"
    missing = measure(frames(), [])
    assert rule(missing, "speed_limit")["status"] == "unavailable"
    assert rule(missing, "speed_limit").get("criterion_outcome") is None


def test_stop_line_requires_correct_approach_and_source_scope_cannot_waive_deviation():
    x = [12.0 + i * 0.2 for i in range(31)]
    speed = [2.0] * 31
    for i in range(11, 23):
        x[i], speed[i] = -0.4, 0.0
    x[23], x[24], x[25] = -0.2, 0.2, 0.4
    stopped = frames(ego_x=x, ego_speed=speed)
    criterion = claim("stop_sign", stop_decision())
    result = measure(stopped, [criterion])
    assert rule(result, "stop_sign")["criterion_outcome"] == "pass"

    censored_stop = [dict(frame, actors=[dict(row) for row in frame["actors"]])
                     for frame in stopped]
    censored_stop[16]["time_s"] = None
    censored = measure(censored_stop, [criterion])
    assert rule(censored, "stop_sign")["criterion_outcome"] == "not_assessed"

    no_stop_frames = frames(ego_x=[-4 + i * 0.2 for i in range(31)])
    no_stop = measure(no_stop_frames, [criterion])
    assert rule(no_stop, "stop_sign")["criterion_outcome"] == "fail"

    source_scope = {"rule": "stop_sign", "applicability": "not_applicable",
                    "approach_lanelet_ids": [8], "valid_step_range": [10, 30],
                    "reason": "Source approach had no applicable stop sign"}
    deviated = measure(no_stop_frames, [claim("stop_sign", source_scope), criterion],
                       ctx=map_context(adjacent=True))
    assert rule(deviated, "stop_sign")["criterion_outcome"] == "fail"
    assert deviated["source_route_waiver_used"] is False


def test_stop_criterion_on_adjacent_directed_lane_is_not_applied():
    y = [4.0] * 31
    not_applicable = {"rule": "stop_sign", "applicability": "not_applicable",
                      "approach_lanelet_ids": [8], "valid_step_range": [10, 30],
                      "reason": "Reviewed map record contains no stop obligation on this directed lane"}
    result = measure(frames(ego_y=y), [claim("stop_sign", not_applicable)],
                     ctx=map_context(adjacent=True))
    assert rule(result, "stop_sign")["status"] == "not_applicable"


def test_stop_approach_near_line_with_incomplete_horizon_is_unavailable():
    x = [-5.0] * 31
    x[10:] = [-0.4] * 21
    result = measure(frames(ego_x=x, ego_speed=[0.0] * 31),
                     [claim("stop_sign", stop_decision())], horizon_complete=False)
    assert rule(result, "stop_sign")["status"] == "unavailable"


def test_priority_yielding_uses_explicit_actors_and_conflict_not_collision():
    criterion = claim("priority_yield", priority_decision())
    actor_path = [5.0] * 31
    actor_path[12:15] = [0.0, 0.0, 0.0]
    clear = measure(frames(priority_x=actor_path), [criterion])
    assert rule(clear, "priority_yielding")["criterion_outcome"] == "pass"

    ego_path = [10.0] * 31
    ego_path[12] = 0.0
    concurrent = measure(frames(ego_x=ego_path, priority_x=actor_path), [criterion])
    assert rule(concurrent, "priority_yielding")["criterion_outcome"] == "fail"
    assert concurrent["criteria"]["priority_yielding"]["conflict_occupancy_conflicts"]

    no_conflict = measure(frames(), [criterion])
    assert rule(no_conflict, "priority_yielding")["status"] == "not_applicable"

    unknown_lifetime = frames(priority_x=actor_path)
    for frame in unknown_lifetime:
        next(row for row in frame["actors"] if row["id"] == PRIORITY)["lifetime_generation"] = None
    unresolved = measure(unknown_lifetime, [criterion])
    assert rule(unresolved, "priority_yielding")["status"] == "unavailable"


def test_unbound_semantic_claim_is_invalid_and_dynamic_signal_is_explicitly_unavailable():
    decision = {"rule": "speed_limit", "applicability": "applicable",
                "approach_lanelet_ids": [7], "limit_kmh": 36.0,
                "valid_step_range": [10, 30]}
    result = measure(frames(), [claim("speed_limit", decision,
                                      evidence={"rule": "speed_limit"})])
    assert rule(result, "speed_limit")["status"] == "invalid"
    assert result["capabilities"]["traffic_signal"]["status"] == "unavailable"
