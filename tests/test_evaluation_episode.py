"""Analytical saved-state measurements and trace-only CLI behavior."""

import math
import sys

import pytest

from geotransfer_gap.artifacts import write_json
from geotransfer_gap.cli import main
from geotransfer_gap.evaluation.kinematics import measure_kinematics
from geotransfer_gap.evaluation.profile import load_profile


EGO = 41
OTHER = 7
SCENE = {"root": "artifacts", "path": "synthetic"}


def point(step, *, time=None, x=None, y=0.0, vx=1.0, vy=0.0, heading=0.0,
          present=True, generation=0, owner="ego:ppo", source_valid=True,
          collision=0, goal=False):
    return {
        "id": EGO, "binary_index": 1, "present": present,
        "x": float(step if x is None and present else x) if present else None,
        "y": float(y) if present else None,
        "vx": float(vx) if present and vx is not None else None,
        "vy": float(vy) if present and vy is not None else None,
        "heading": float(heading) if present and heading is not None else None,
        "length": 4.5, "width": 1.8,
        "lifetime_generation": generation,
        "effective_owner": owner,
        "source_valid": source_valid,
        "collision_state": collision,
        "reached_goal": goal,
    }


def measured(actors, *, times=None, schema=3, report=None, applied=True):
    frames = []
    for i, actor in enumerate(actors):
        frames.append({"step": i, "time_s": times[i] if times is not None else i * 0.1,
                       "transition_applied": (i < len(actors) - 1) if applied else None,
                       "actors": [dict(actor)]})
    info = {"schema_version": schema, "requested_observation_frames": len(frames),
            "terminal_reason": "horizon"}
    info.update(report or {})
    return measure_kinematics(frames, EGO, info, load_profile())


def metric(result, name, window="full"):
    return next(item for item in result["metrics"]
                if item["metric_id"] == name and item["window"] == window)


def values(result, name, window="full"):
    record = metric(result, name, window)
    assert record["status"] == "valid", record
    return record["value"]


def matrix_trace(path, *, count=91, state_fn=None, owner_fn=None,
                 terminal="horizon", requested=None):
    requested = count if requested is None else requested
    frames = []
    for step in range(count):
        actor = (state_fn(step) if state_fn else point(step, x=float(step), vx=10.0))
        actor = dict(actor, id=EGO, binary_index=1)
        lifetime = actor.get("lifetime_generation")
        actor.pop("lifetime_generation", None)
        actor.pop("effective_owner", None)
        actor.pop("source_valid", None)
        other = dict(id=OTHER, binary_index=0, present=True, x=0.0, y=0.0,
                     vx=0.0, vy=0.0, heading=0.0, length=4.0, width=1.5)
        state = {"step": step, "time_s": step / 10, "actors": [other, actor]
                 if step % 2 else [actor, other]}
        ego_owner = owner_fn(step) if owner_fn else (
            "warmup_replay" if step < 10 else "ego:ppo")
        assignments = [
            {"source_id": EGO, "binary_index": 1, "lifetime_generation": lifetime,
             "role": "ego", "effective_owner": ego_owner},
            {"source_id": OTHER, "binary_index": 0, "lifetime_generation": 0,
             "role": "traffic", "effective_owner": "traffic:idm"},
        ]
        frames.append({"step": step, "state": state, "actors": assignments,
                       "transition_applied": step < count - 1})
    report = {
        "schema_version": 3, "planner": "controller_matrix", "scene": SCENE,
        "binary_sha256": "a" * 64, "ego_binary_index": 1, "ego_source_id": EGO,
        "ego_controller": "ppo", "traffic_controller": "idm", "traffic_startup": "immediate",
        "warmup_replay_frames": 10, "steps_semantics": "observation_frames",
        "requested_observation_frames": requested, "observation_frames": count,
        "transitions": max(0, count - 1), "terminal_reason": terminal, "frames": frames,
    }
    write_json(path, report)
    return report


def test_complete_matrix_exposure_and_nonzero_ego_identity(tmp_path):
    from geotransfer_gap.runtime.trace_io import load_saved_trace

    trace = tmp_path / "trace.json"
    matrix_trace(trace)
    saved = load_saved_trace(trace)
    result = measure_kinematics(list(saved.frames()), saved.ego_source_id,
                                saved.playback.report, load_profile())
    full = result["exposure"]["windows"]["full"]
    primary = result["exposure"]["windows"]["primary"]
    assert full["observation_count"] == 91
    assert full["transition_count"] == 90
    assert full["recorded_duration_s"] == pytest.approx(9.0)
    assert full["pose_duration_s"] == pytest.approx(9.0)
    assert full["observed_distance_m"] == pytest.approx(90.0)
    assert primary["observation_count"] == 81
    assert primary["transition_count"] == 80
    assert primary["recorded_duration_s"] == pytest.approx(8.0)
    assert primary["controlled_duration_s"] == pytest.approx(8.0)
    assert len(result["exposure"]["effective_owner_segments"]) == 2
    assert [row["effective_owner"] for row in result["exposure"]["effective_owner_segments"]] == [
        "warmup_replay", "ego:ppo"]
    assert result["exposure"]["transition_counts"]["applied"] == 90
    assert metric(result, "trajectory.speed")["actors"] == [[EGO, 0]]
    assert result["exposure"]["event_observation_coverage"]["windows"]["full"]["observation_count"] == 91
    assert result["exposure"]["event_observation_coverage"]["windows"]["primary"]["observation_count"] == 81


def test_constant_velocity_acceleration_and_jerk_are_zero():
    result = measured([point(i, x=i * 0.3, vx=3.0) for i in range(6)])
    assert values(result, "trajectory.speed")["distribution"]["mean"] == pytest.approx(3.0)
    assert values(result, "trajectory.acceleration_longitudinal")["distribution"]["maximum"] == pytest.approx(0)
    assert values(result, "trajectory.acceleration_lateral")["distribution"]["maximum"] == pytest.approx(0)
    jerk = values(result, "trajectory.jerk_world_norm")
    assert jerk["distribution"]["maximum"] == pytest.approx(0)
    assert jerk["samples"][0]["stencil_steps"] == [0, 2]


def test_analytical_changing_acceleration_gives_constant_jerk():
    dt = 0.1
    actors = [point(i, x=0.0, vx=1 + 2 * (i * dt) + (i * dt) ** 2)
              for i in range(6)]
    result = measured(actors)
    assert [row["value"] for row in values(result, "trajectory.jerk_longitudinal")["samples"]] == pytest.approx([2] * 4)
    assert [row["value"] for row in values(result, "trajectory.jerk_world_norm")["samples"]] == pytest.approx([2] * 4)


def test_known_constant_acceleration_is_preserved_with_braking_sign():
    dt = 0.1
    actors = [point(i, x=0.0, vx=2 - 3 * i * dt) for i in range(5)]
    result = measured(actors)
    samples = values(result, "trajectory.acceleration_longitudinal")["samples"]
    assert [row["value"] for row in samples] == pytest.approx([-3] * 4)


def test_constant_speed_circular_motion_uses_midpoint_heading():
    dt, omega = 0.1, 0.4
    actors = []
    for i in range(6):
        angle = omega * i * dt
        actors.append(point(i, x=0.0, vx=-math.sin(angle), vy=math.cos(angle),
                            heading=angle + math.pi / 2))
    result = measured(actors)
    assert [row["value"] for row in values(result, "trajectory.yaw_rate")["samples"]] == pytest.approx([omega] * 5)
    expected_lateral = 2 * math.sin(omega * dt / 2) / dt
    assert [row["value"] for row in values(result, "trajectory.acceleration_lateral")["samples"]] == pytest.approx([expected_lateral] * 5)
    assert max(abs(row["value"]) for row in values(result, "trajectory.acceleration_longitudinal")["samples"]) < 1e-12
    expected_jerk = 4 * math.sin(omega * dt / 2) ** 2 / dt**2
    assert [row["value"] for row in values(result, "trajectory.jerk_world_norm")["samples"]] == pytest.approx([expected_jerk] * 4)


def test_irregular_intervals_preserve_exact_threshold_exposure():
    result = measured([point(0, x=0, vx=0), point(1, x=0, vx=0.4),
                       point(2, x=0, vx=1.4)], times=[0.0, 0.1, 0.6])
    acceleration = values(result, "trajectory.acceleration_longitudinal")
    assert [row["value"] for row in acceleration["samples"]] == pytest.approx([4.0, 2.0])
    assert acceleration["exceedance_samples"] == 1
    assert acceleration["exceedance_duration_s"] == pytest.approx(0.1)


def test_yaw_and_world_jerk_do_not_require_recorded_heading_or_velocity():
    headings = [math.pi - 0.1, -math.pi + 0.1, -math.pi + 0.3]
    heading_only = measured([point(i, vx=None, vy=None, heading=angle)
                             for i, angle in enumerate(headings)])
    assert [row["value"] for row in values(heading_only, "trajectory.yaw_rate")["samples"]] == pytest.approx([2, 2])
    assert values(heading_only, "trajectory.yaw_acceleration")["distribution"]["maximum"] == pytest.approx(0)
    assert metric(heading_only, "trajectory.acceleration_longitudinal")["status"] == "unavailable"

    varying_velocity = [point(i, vx=1 + 2 * (i * 0.1) + (i * 0.1)**2,
                              heading=None) for i in range(5)]
    world = measured(varying_velocity)
    assert [row["value"] for row in values(world, "trajectory.jerk_world_norm")["samples"]] == pytest.approx([2] * 3)
    assert metric(world, "trajectory.acceleration_longitudinal")["status"] == "unavailable"


def test_lifetime_gap_source_gap_and_owner_handover_break_stencils():
    life = [point(i, vx=float(i), generation=0 if i < 2 else 1) for i in range(4)]
    result = measured(life)
    assert metric(result, "trajectory.acceleration_longitudinal")["eligible_samples"] == 2
    assert metric(result, "trajectory.jerk_longitudinal")["status"] == "undefined"
    assert any("lifetime_boundary=1" in item for item in metric(result, "trajectory.acceleration_longitudinal")["limitations"])

    owners = [point(i, vx=float(i), owner="ego:a" if i < 2 else "ego:b") for i in range(4)]
    result = measured(owners)
    jerk = metric(result, "trajectory.jerk_longitudinal")
    assert jerk["status"] == "valid"
    assert jerk["eligible_samples"] == 1
    assert any("owner_handover=1" in item for item in jerk["limitations"])

    source_gap = [point(0, source_valid=True), point(1, source_valid=False),
                  point(2, source_valid=True)]
    result = measured(source_gap)
    assert metric(result, "exposure.pose_duration")["status"] == "unavailable"
    assert metric(result, "exposure.pose_duration")["value"] is None
    assert result["exposure"]["windows"]["full"]["interval_exclusions"]["source_validity_boundary"] == 2
    assert [segment["boundary_before"] for segment in result["exposure"]["effective_owner_segments"]][1:] == [
        "source_validity_gap_or_reentry", "source_validity_gap_or_reentry"]

    presence_gap = [point(0, x=0), point(1, present=False, vx=None, vy=None, heading=None),
                    point(2, x=5, generation=1), point(3, x=6, generation=1)]
    result = measured(presence_gap)
    assert metric(result, "trajectory.observed_distance")["value"]["distance_m"] == pytest.approx(1)
    assert metric(result, "exposure.pose_duration")["eligible_samples"] == 1


def test_missing_event_flag_does_not_acquire_known_transition_attribution():
    actors = [point(i, collision=0) for i in range(12)]
    actors[10].pop("collision_state")
    actors[11]["collision_state"] = 1
    result = measured(actors, report={"terminal_reason": "ego_collision"})
    event = next(row for row in result["events"] if row["channel"] == "native_vehicle_collision")
    assert event["observation"] == "active_after_unknown_prior"
    assert event["attribution"] == "unattributed"
    assert result["exposure"]["event_observation_coverage"]["windows"]["full"]["channels"]["collision_state"]["observations_with_field"] == 11


def test_observation_ten_event_is_warmup_initial_condition():
    actors = [point(i, collision=0) for i in range(12)]
    actors[10]["collision_state"] = 1
    result = measured(actors)
    event = next(row for row in result["events"] if row["channel"] == "native_vehicle_collision")
    assert event["step"] == 10
    assert event["attribution"] == "warmup_or_initial_condition"


def test_legacy_adjacent_observations_do_not_create_an_extra_final_transition():
    result = measured([point(i, vx=1) for i in range(3)], schema=2,
                      times=[None, None, None], applied=False)
    window = result["exposure"]["windows"]["full"]
    assert window["recorded_duration_s"] == pytest.approx(0.2)
    assert window["transition_count"] == 0
    assert window["unknown_transition_count"] == 2
    assert result["exposure"]["transition_counts"]["observed_adjacent_intervals"] == 2
    assert metric(result, "exposure.controlled_duration")["status"] == "unavailable"
    assert result["exposure"]["time_source"] == "inferred_legacy_10hz_step"
    assert any("owner is unknown" in item for item in metric(result, "trajectory.speed")["limitations"])


def test_malformed_time_short_trace_and_terminal_event_keep_missing_distinct():
    bad_time = measured([point(0), point(1), point(2)], times=[0.0, float("nan"), 0.2])
    assert metric(bad_time, "exposure.recorded_duration")["status"] == "unavailable"
    assert metric(bad_time, "exposure.recorded_duration")["value"] is None
    short = measured([point(0)])
    assert metric(short, "exposure.recorded_duration")["status"] == "unavailable"
    assert metric(short, "trajectory.acceleration_longitudinal")["status"] == "unavailable"

    collision_actors = [point(i, collision=0) for i in range(12)]
    terminal = point(11, present=False, vx=None, vy=None, heading=None, collision=1)
    collision_actors[11] = terminal
    result = measured(collision_actors, report={"terminal_reason": "ego_collision"})
    collision = next(row for row in result["events"] if row["channel"] == "native_vehicle_collision")
    assert collision["pose_present"] is False
    assert collision["attribution"] == "recorded_controlled_transition"
    assert metric(result, "trajectory.speed")["eligible_samples"] == 11


def test_episode_cli_writes_trace_only_bundle_and_refuses_unsafe_targets(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import read_json, sha256

    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    trace = tmp_path / "trace.json"
    matrix_trace(trace, count=12, terminal="ego_removed", requested=20)
    output = runs / "episode-01"
    main(["evaluate", "episode", "--trace", str(trace), "--output", str(output)])
    saved = read_json(output / "episode.json")
    assert saved["result_schema_version"] == 1
    assert saved["input"]["evidence_level"] == "trace_only_diagnostic"
    assert saved["input"]["producer_revision_status"] == "not_recorded_by_saved_trace_contract"
    assert saved["evaluator"]["evaluator_code"]["sha256"]
    assert saved["input"]["live_validation_status"] == "not_run_offline_evaluation"
    assert saved["metrics"][0]["evidence_refs"][0]["sha256"] == saved["input"]["trace_sha256"]
    assert (output / "events.json").is_file()
    assert saved["observed_events"]["count"] > 0
    assert saved["observed_events"]["sha256"] == sha256(output / "events.json")
    assert any("task outcomes are not assessed" in item for item in saved["context_limitations"])
    with pytest.raises(FileExistsError):
        main(["evaluate", "episode", "--trace", str(trace), "--output", str(output)])
    with pytest.raises(ValueError, match="beneath configured runs"):
        main(["evaluate", "episode", "--trace", str(trace), "--output", str(tmp_path / "elsewhere")])


def test_cli_accepts_safe_output_sibling_of_loose_trace_in_runs(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    trace = runs / "loose-trace.json"
    matrix_trace(trace, count=2, terminal="ego_removed", requested=4)
    destination = runs / "new-evaluation"
    main(["evaluate", "episode", "--trace", str(trace), "--output", str(destination)])
    assert (destination / "episode.json").is_file()


def test_missing_event_channels_do_not_emit_zero_event_count(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import read_json

    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    trace = tmp_path / "trace.json"
    report = matrix_trace(trace, count=2, terminal="horizon", requested=2)
    for record in report["frames"]:
        for actor in record["state"]["actors"]:
            actor.pop("collision_state", None)
            actor.pop("reached_goal", None)
    write_json(trace, report)
    main(["evaluate", "episode", "--trace", str(trace), "--output", str(runs / "unknown-events")])
    result = read_json(runs / "unknown-events" / "episode.json")
    assert result["observed_events"]["status"] == "unavailable"
    assert result["observed_events"]["count"] is None
    assert result["observed_events"]["file"] is None


def test_cli_scene_context_validates_binary_and_output_is_offline(tmp_path, monkeypatch):
    from geotransfer_gap.artifacts import read_json, sha256

    artifacts = tmp_path / "artifacts"
    scene = artifacts / "scene-a"
    (scene / "testing").mkdir(parents=True)
    binary = scene / "testing" / "map_000000.bin"
    binary.write_bytes(b"synthetic binary")
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("GEOTRANSFER_ARTIFACTS", str(artifacts))
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    trace = tmp_path / "trace.json"
    report = matrix_trace(trace, count=2, terminal="ego_removed", requested=4)
    report["scene"] = {"root": "artifacts", "path": "scene-a"}
    report["binary_sha256"] = sha256(binary)
    write_json(trace, report)
    modules_before = set(sys.modules)
    main(["evaluate", "episode", "--trace", str(trace), "--output", str(runs / "checked"),
          "--scene", str(scene)])
    assert read_json(runs / "checked" / "episode.json")["scene_context"]["status"] == "scene_and_binary_identity_checked"
    heavy_roots = {"torch", "pufferlib", "lanelet2"}
    newly_loaded_heavy_modules = sorted(
        name for name in set(sys.modules) - modules_before
        if name.split(".", 1)[0] in heavy_roots
    )
    assert not newly_loaded_heavy_modules, newly_loaded_heavy_modules


def test_ancestor_run_marker_and_trace_overlap_are_refused(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    run = runs / "archived"
    run.mkdir(parents=True)
    (run / "run.json").write_text("{}")
    trace = tmp_path / "trace.json"
    matrix_trace(trace, count=2, terminal="ego_removed", requested=4)
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    with pytest.raises(ValueError, match="existing run/evidence directory"):
        main(["evaluate", "episode", "--trace", str(trace), "--output", str(run / "evaluation")])


def test_trace_run_directory_cannot_contain_its_evaluation(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    run = runs / "saved-episode"
    run.mkdir(parents=True)
    trace = run / "trace.json"
    matrix_trace(trace, count=2, terminal="ego_removed", requested=4)
    monkeypatch.setenv("GEOTRANSFER_RUNS", str(runs))
    with pytest.raises(ValueError, match="saved run input directory"):
        main(["evaluate", "episode", "--trace", str(trace), "--output", str(run / "evaluation")])
