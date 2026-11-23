"""Analytical offline checks for PE04 saved-trace safety measurements."""

import math

import pytest

from geotransfer_gap.evaluation.kinematics import measure_kinematics
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.evaluation.safety import measure_safety


EGO = 41
OTHER = 7
PROFILE = load_profile()


def actor(source_id, x, y, vx, vy, *, heading=0.0, length=2.0, width=1.0,
          present=True, generation=0, actor_type=1, source_valid=False,
          collision=0):
    return {
        "id": source_id,
        "binary_index": 1 if source_id == EGO else 0,
        "type": actor_type,
        "present": present,
        "x": float(x) if present else None,
        "y": float(y) if present else None,
        "vx": float(vx) if present and vx is not None else None,
        "vy": float(vy) if present and vy is not None else None,
        "heading": float(heading) if present and heading is not None else None,
        "length": length,
        "width": width,
        "lifetime_generation": generation,
        "source_valid": source_valid,
        "effective_owner": "ego:ppo" if source_id == EGO else "traffic:source_hold",
        "collision_state": collision,
        "reached_goal": False,
    }


def evaluate(frames, *, terminal="horizon", capture=None, capture_bound=False):
    report = {
        "schema_version": 3,
        "planner": "controller_matrix",
        "ego_binary_index": 1,
        "requested_observation_frames": len(frames),
        "terminal_reason": terminal,
    }
    measured = measure_kinematics(frames, EGO, report, PROFILE)
    safety = measure_safety(frames, EGO, report, PROFILE, measured["events"],
                            measured["exposure"], evaluation_capture=capture,
                            evaluation_capture_bound=capture_bound)
    return safety, measured["events"]


def two_actor_frames(ego_states, other_states, *, dt=0.1, order="ego_first"):
    frames = []
    for index, (ego_state, other_state) in enumerate(zip(ego_states, other_states)):
        rows = [actor(EGO, **ego_state), actor(OTHER, **other_state)]
        if order == "other_first":
            rows.reverse()
        frames.append({"step": index, "time_s": index * dt,
                       "transition_applied": index < len(ego_states) - 1,
                       "actors": rows})
    return frames


def state(x, y=0.0, vx=0.0, vy=0.0, **kwargs):
    return {"x": x, "y": y, "vx": vx, "vy": vy, **kwargs}


def metric(result, metric_id, window="full"):
    return next(row for row in result["metrics"]
                if row["metric_id"] == metric_id and row["window"] == window)


def ttc(frames):
    result, _ = evaluate(frames)
    return metric(result, "safety.ttc")


def test_head_on_and_crossing_ttc_match_analytic_first_overlap():
    head_on = two_actor_frames(
        [state(0, vx=2)] * 2,
        [state(10, vx=-2, heading=math.pi)] * 2,
    )
    result = ttc(head_on)
    assert result["status"] == "valid"
    assert result["value"]["minimum_ttc_s"] == pytest.approx(2.0)
    assert result["value"]["interpretation"] == "finite_future_overlap"

    crossing = two_actor_frames(
        [state(0, 0, 1, 0, length=2, width=2)] * 2,
        [state(5, -5, 0, 1, heading=math.pi / 2, length=2, width=2)] * 2,
    )
    crossing_ttc = ttc(crossing)
    assert crossing_ttc["value"]["minimum_ttc_s"] == pytest.approx(3.0)


def test_rotated_shapes_use_sat_and_are_rigid_transform_invariant():
    rotated = two_actor_frames(
        [state(0, 0, 0, 0, heading=0, length=4, width=1)] * 2,
        [state(0, 4, 0, -1, heading=math.pi / 2, length=4, width=1)] * 2,
    )
    base = ttc(rotated)["value"]["minimum_ttc_s"]
    assert base == pytest.approx(1.5)

    angle, dx, dy = 0.73, 123.4, -51.2
    c, s = math.cos(angle), math.sin(angle)
    transformed = []
    for frame in rotated:
        actors = []
        for row in frame["actors"]:
            copy = dict(row)
            copy["x"] = c * row["x"] - s * row["y"] + dx
            copy["y"] = s * row["x"] + c * row["y"] + dy
            copy["vx"] = c * row["vx"] - s * row["vy"]
            copy["vy"] = s * row["vx"] + c * row["vy"]
            copy["heading"] = row["heading"] + angle
            actors.append(copy)
        transformed.append({**frame, "actors": actors})
    assert ttc(transformed)["value"]["minimum_ttc_s"] == pytest.approx(base)


@pytest.mark.parametrize("other_x,other_vx,other_y,other_vy,expected", [
    (10, 2, 0, 0, "no_overlap_predicted_within_horizon"),  # parallel
    (-5, -1, 0, 0, "no_overlap_predicted_within_horizon"),  # separating
    (10, 0, 0, 0, "no_overlap_predicted_within_horizon"),  # stationary
    (0, 0, 0, 0, "overlap_now"),
])
def test_parallel_separating_stationary_and_overlap_now(other_x, other_vx,
                                                          other_y, other_vy, expected):
    frames = two_actor_frames(
        [state(0, vx=1)] * 2,
        [state(other_x, other_y, other_vx, other_vy)] * 2,
    )
    result = ttc(frames)
    assert result["value"]["interpretation"] == expected
    if expected == "overlap_now":
        assert result["value"]["minimum_ttc_s"] == 0
    else:
        assert result["value"]["minimum_ttc_s"] is None


def test_horizon_boundary_is_inclusive_and_beyond_it_is_not_a_collision():
    exactly_five = two_actor_frames(
        [state(0, vx=1)] * 2,
        [state(12, vx=-1, heading=math.pi)] * 2,
    )
    exact = ttc(exactly_five)
    assert exact["value"]["minimum_ttc_s"] == pytest.approx(5.0)
    assert exact["value"]["interpretation"] == "finite_future_overlap"

    beyond = two_actor_frames(
        [state(0, vx=1)] * 2,
        [state(12.02, vx=-1, heading=math.pi)] * 2,
    )
    result = ttc(beyond)
    assert result["value"]["minimum_ttc_s"] is None
    assert result["value"]["interpretation"] == "no_overlap_predicted_within_horizon"


def test_crossing_paths_without_simultaneous_footprint_contact_have_no_ttc():
    frames = two_actor_frames(
        [state(step, 0, 1, 0, length=2, width=2) for step in (0, 0)],
        [state(8, -5, 0, 1, heading=math.pi / 2, length=2, width=2)] * 2,
    )
    result = ttc(frames)
    assert result["value"]["minimum_ttc_s"] is None
    assert result["value"]["interpretation"] == "no_overlap_predicted_within_horizon"


def test_source_vru_velocity_fallback_is_causal_and_same_lifetime_only():
    ego = [state(0, vx=0), state(0.1, vx=0)]
    vru = [state(4, vx=None, actor_type=2, source_valid=True),
           state(3.9, vx=None, actor_type=2, source_valid=True)]
    frames = two_actor_frames(ego, vru)
    frames[0]["actors"][1]["vy"] = None
    frames[1]["actors"][1]["vy"] = None
    result = ttc(frames)
    assert result["status"] == "valid"
    pair = result["value"]["horizon_sensitivity"]["5.0"]
    assert pair["interpretation"] == "finite_future_overlap"
    safety, _ = evaluate(frames)
    pair_sample = metric(safety, "safety.ttc")["value"]["pair_samples"][0]["actor_pairs"][0]
    assert pair_sample["velocity_support"]["actor"] == \
        "observed_position_backward_difference_same_lifetime"
    assert metric(safety, "safety.ttc")["value"]["eligible_pair_samples"] == 1

    unknown_lifetime = [dict(frame) for frame in frames]
    for frame in unknown_lifetime:
        frame["actors"] = [dict(row) for row in frame["actors"]]
        next(row for row in frame["actors"] if row["id"] == OTHER).pop("lifetime_generation")
    first_other = next(row for row in unknown_lifetime[0]["actors"] if row["id"] == OTHER)
    first_other["vx"], first_other["vy"] = -1.0, 0.0
    missing = ttc(unknown_lifetime)
    assert missing["status"] == "valid"
    assert missing["value"]["coverage"]["complete"] is False

    changed_lifetime = [{**frame, "actors": [dict(row) for row in frame["actors"]]}
                        for frame in frames]
    initial_other = next(row for row in changed_lifetime[0]["actors"] if row["id"] == OTHER)
    initial_other["vx"], initial_other["vy"] = -1.0, 0.0
    next(row for row in changed_lifetime[1]["actors"] if row["id"] == OTHER)[
        "lifetime_generation"] = 1
    changed = ttc(changed_lifetime)
    assert changed["status"] == "valid"
    assert changed["value"]["coverage"]["complete"] is False


def test_same_lifetime_dimension_imputation_is_labeled():
    frames = two_actor_frames(
        [state(0, vx=0)] * 2,
        [state(5, vx=0)] * 2,
    )
    frames[1]["actors"][1]["length"] = None
    frames[1]["actors"][1]["width"] = None
    result, _ = evaluate(frames)
    record = metric(result, "safety.footprint_clearance")
    assert record["status"] == "valid"
    sample = next(row for row in record["value"]["samples"] if row["step"] == 1)
    assert sample["dimension_source"]["actor"] == "same_actor_lifetime_constant_observations"
    assert sample["dimension_imputed_fields"]["actor"] == ["length", "width"]


def test_terminal_collision_without_pose_and_latched_flags_count_once():
    ego, other = [], []
    for step in range(13):
        ego.append(state(step * 0.1, vx=1, collision=1 if step >= 11 else 0))
        other.append(state(5, vx=0))
    frames = two_actor_frames(ego, other)
    terminal = actor(EGO, 0, 0, None, None, present=False, collision=1)
    frames[-1]["actors"][0] = terminal
    result, events = evaluate(frames, terminal="ego_collision")
    native = metric(result, "safety.native_vehicle_collision_onsets")
    assert native["value"]["observed_onset_count"] == 1
    assert native["value"]["count_is_lower_bound"] is True
    onset = next(event for event in events if event["channel"] == "native_vehicle_collision")
    assert onset["collision_details"]["partner_source_id"] is None
    assert onset["collision_details"]["fault_status"] == "unknown"
    assert onset["pose_present"] is True


def test_terminal_collision_flag_is_retained_when_terminal_pose_is_absent():
    ego, other = [], []
    for step in range(12):
        ego.append(state(step * 0.1, vx=1, collision=1 if step == 11 else 0))
        other.append(state(5, vx=0))
    frames = two_actor_frames(ego, other)
    frames[-1]["actors"][0] = actor(EGO, 0, 0, None, None,
                                    present=False, collision=1)
    result, events = evaluate(frames, terminal="ego_collision")
    event = next(row for row in events if row["channel"] == "native_vehicle_collision")
    assert event["pose_present"] is False
    assert metric(result, "safety.native_vehicle_collision_onsets")["value"][
        "observed_onset_count"] == 1


def test_collision_at_primary_start_stays_a_warmup_condition():
    frames = []
    for step in range(12):
        ego_row = actor(EGO, step * 0.1, 0, 1, 0,
                        collision=1 if step >= 10 else 0)
        other = actor(OTHER, 5, 0, 0, 0)
        frames.append({"step": step, "time_s": step / 10,
                       "transition_applied": step < 11,
                       "actors": [ego_row, other]})
    result, events = evaluate(frames)
    event = next(row for row in events if row["channel"] == "native_vehicle_collision")
    assert event["attribution"] == "warmup_or_initial_condition"
    primary = metric(result, "safety.native_vehicle_collision_onsets", "primary")
    assert primary["value"]["observed_onset_count"] == 1
    assert primary["value"]["warmup_or_initial_condition_count"] == 1
    assert primary["value"]["recorded_controlled_transition_count"] == 0


def test_hash_bound_capture_partner_is_exact_and_speed_is_preimpact_proxy():
    frames = []
    for step in range(12):
        ego_row = actor(EGO, step * 0.1, 0, 2, 0,
                        collision=1 if step == 11 else 0)
        partner = actor(OTHER, 20 - step * 0.2, 0, -2, 0)
        decoy = actor(99, 0.25, 0, 0, 0)
        frames.append({"step": step, "time_s": step / 10,
                       "transition_applied": step < 11,
                       "actors": [ego_row, partner, decoy]})
    observations = []
    for step in range(len(frames)):
        is_collision = step == 11
        observations.append({
            "step": step,
            "actors": [{
                "source_id": EGO, "binary_index": 1, "lifetime_generation": 0,
                "collision_partner_status": "mapped" if is_collision else "not_applicable",
                "collision_partner_source_id": OTHER if is_collision else None,
                "collision_partner_binary_index": 0 if is_collision else None,
                "collision_center_world_xy": [2.1, 0.0] if is_collision else None,
                "partner_center_world_xy": [17.8, 0.0] if is_collision else None,
            }, {
                "source_id": OTHER, "binary_index": 0, "lifetime_generation": 0,
            }],
        })
    capture = {"observations": observations}
    result, events = evaluate(frames, terminal="ego_collision", capture=capture,
                              capture_bound=True)
    event = next(row for row in events if row["channel"] == "native_vehicle_collision")
    details = event["collision_details"]
    assert details["partner_source_id"] == OTHER
    assert details["partner_source_id"] != 99
    assert details["collision_centers_world_xy"]["meaning"] == \
        "detector actor centers, not exact impact points"
    assert details["preimpact_relative_speed_proxy_m_s"] == pytest.approx(4.0)
    assert details["fault_status"] == "unknown"
    assert metric(result, "safety.native_vehicle_collision_onsets")["value"][
        "count_is_lower_bound"] is False

    unbound, unbound_events = evaluate(frames, terminal="ego_collision", capture=capture,
                                       capture_bound=False)
    untrusted = next(row for row in unbound_events
                     if row["channel"] == "native_vehicle_collision")["collision_details"]
    assert untrusted["partner_source_id"] is None
    assert untrusted["preimpact_relative_speed_proxy_m_s"] is None
    assert metric(unbound, "safety.native_vehicle_collision_onsets")["value"][
        "count_is_lower_bound"] is True


def test_missing_counterpart_dimensions_make_clearance_unavailable_not_zero():
    frames = two_actor_frames([state(0)] * 2, [state(5)] * 2)
    for frame in frames:
        other = next(row for row in frame["actors"] if row["id"] == OTHER)
        other["length"] = other["width"] = None
    result, _ = evaluate(frames)
    clearance = metric(result, "safety.footprint_clearance")
    assert clearance["status"] == "unavailable"
    assert clearance["value"] is None
    assert clearance["criterion_outcome"] == "not_assessed"


def test_invalid_supplied_dimensions_do_not_get_silently_imputed():
    frames = two_actor_frames([state(0)] * 2, [state(5)] * 2)
    next(row for row in frames[0]["actors"] if row["id"] == OTHER)["width"] = 0.0
    result, _ = evaluate(frames)
    clearance = metric(result, "safety.footprint_clearance")
    assert clearance["status"] == "invalid"
    assert clearance["value"] is None
    assert clearance["criterion_outcome"] == "not_assessed"


def test_no_counterpart_is_not_applicable_and_actor_order_does_not_change_metrics():
    lone_frames = []
    for step in range(2):
        lone_frames.append({"step": step, "time_s": step * 0.1,
                            "transition_applied": step == 0,
                            "actors": [actor(EGO, step, 0, 1, 0)]})
    result, _ = evaluate(lone_frames)
    assert metric(result, "safety.ttc")["status"] == "not_applicable"
    assert metric(result, "safety.footprint_clearance")["status"] == "not_applicable"

    base_frames = two_actor_frames([state(0)] * 2, [state(5)] * 2)
    reversed_frames = two_actor_frames([state(0)] * 2, [state(5)] * 2,
                                       order="other_first")
    base, _ = evaluate(base_frames)
    reversed_result, _ = evaluate(reversed_frames)
    for metric_id in ("safety.footprint_clearance", "safety.ttc",
                      "safety.footprint_overlap"):
        assert metric(base, metric_id)["value"] == metric(reversed_result, metric_id)["value"]


def test_clearance_overlap_and_native_collision_are_separate_channels():
    frames = two_actor_frames([state(0)] * 2, [state(1, collision=0)] * 2)
    result, _ = evaluate(frames)
    assert metric(result, "safety.footprint_overlap")["value"]["overlap_pair_observations"] == 2
    assert metric(result, "safety.native_vehicle_collision_onsets")["value"][
        "observed_onset_count"] == 0


def test_near_miss_threshold_exposure_keeps_ttc_and_clearance_separate():
    closing = two_actor_frames(
        [state(0, vx=1), state(0.1, vx=1)],
        [state(5, vx=-2, heading=math.pi), state(4.8, vx=-2, heading=math.pi)],
    )
    ttc_result, _ = evaluate(closing)
    near = metric(ttc_result, "safety.near_miss_exposure")["value"]
    assert near["ttc_thresholds"]["below_1.5s"][
        "observed_lower_bound_duration_s"] == pytest.approx(0.1)
    assert near["clearance_thresholds"]["below_0.5m"][
        "observed_lower_bound_duration_s"] == 0.0

    close_gap = two_actor_frames(
        [state(0), state(0)], [state(2.4), state(2.4)],
    )
    clearance_result, _ = evaluate(close_gap)
    near = metric(clearance_result, "safety.near_miss_exposure")["value"]
    assert near["clearance_thresholds"]["below_0.5m"][
        "observed_lower_bound_duration_s"] == pytest.approx(0.1)

