"""Synthetic cases for the PE07 saved-evidence interaction owner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from geotransfer_gap.artifacts import sha256 as sha, write_json
from geotransfer_gap.evaluation.context import LaneCenterline, MapContext
from geotransfer_gap.evaluation.interactions import (
    InteractionContext,
    _crossing_measure,
    _following_measure,
    build_interaction_context,
    measure_interactions,
)
from geotransfer_gap.evaluation.profile import load_profile


EGO, OTHER = 41, 8
PROFILE = load_profile()


def source_actor(actor_id, actor_type, positions, headings):
    return {"id": actor_id, "type": actor_type, "position": positions,
            "heading": headings, "valid": [1] * len(positions),
            "length": 1.0, "width": 0.5}


def cross_source():
    positions_ego, positions_other = [], []
    headings_ego, headings_other = [], []
    for index in range(30):
        value = max(-3.0, min(3.0, (index - 15) * 0.3))
        positions_ego.append({"x": value, "y": 0.0})
        positions_other.append({"x": 0.0, "y": -value})
        headings_ego.append(0.0)
        headings_other.append(1.5707963267948966)
    return {"objects": [source_actor(EGO, 1, positions_ego, headings_ego),
                        source_actor(OTHER, 2, positions_other, headings_other)]}


def actor(actor_id, x, y, *, vx=0.0, vy=0.0, heading=0.0, present=True,
          generation=0, length=1.0, width=0.5):
    return {"id": actor_id, "binary_index": 0 if actor_id == EGO else 1,
            "present": present,
            "x": float(x) if present else None, "y": float(y) if present else None,
            "vx": float(vx) if present else None, "vy": float(vy) if present else None,
            "heading": float(heading) if present else None,
            "length": length, "width": width, "lifetime_generation": generation,
            "source_valid": True}


def crossing_frames(ego_xy, actor_xy, *, actor_missing=False, actor_presence=None):
    frames = []
    for index, (ego_pos, other_pos) in enumerate(zip(ego_xy, actor_xy)):
        ego = actor(EGO, *ego_pos, heading=0.0, vx=0.0)
        other = None if actor_missing else actor(
            OTHER, *other_pos, heading=1.5707963267948966,
            present=(actor_presence[index] if actor_presence else True),
        )
        rows = [ego] + ([other] if other is not None else [])
        frames.append({"step": index, "time_s": index / 10,
                       "transition_applied": index < len(ego_xy) - 1,
                       "actors": rows})
    return frames


def direct_crossing(frames, *, subtype="pedestrian_crossing", context=None,
                    task=None, events=()):
    context = context or InteractionContext(
        "valid", "synthetic source context", scene_id="synthetic",
        specs=({"family": "pedestrian_crossing", "subtype": subtype,
                "source_opportunity": True, "actor_ids": [OTHER], "supported": True},),
        source_scene=cross_source(), certificates={
            "source_body_path_conflict": {"status": "absent", "actors": {}}})
    task = task or SimpleNamespace(start_source_step=0, goal_source_step=29, identity={})
    exposure = {"observation_masks": [{"time_s": row["time_s"]} for row in frames]}
    measured, _, _ = _crossing_measure(
        frames, [row["time_s"] for row in frames], context.specs[0], context, task,
        {"ego_source_id": EGO, "terminal_reason": "horizon"}, events,
        dimensions=None, profile=PROFILE)
    return measured


def path(n, fn):
    return [fn(index) for index in range(n)]


def test_ego_never_reaches_source_crossing_and_progress_failure_is_retained():
    frames = crossing_frames(path(14, lambda i: (-8 + i * 0.1, 0)),
                             path(14, lambda i: (0, 6)))
    event = {"step": 13, "channel": "native_offroad", "observation": "active"}
    result = direct_crossing(frames, events=[event])
    assert result["realization"] == "not_reached"
    assert result["outcome"] == "not_assessed"
    assert "ego failure occurred" in result["reason"]
    assert event["channel"] == "native_offroad"  # caller's progress/safety evidence is untouched


def test_absent_traffic_is_indeterminate_not_a_pass():
    frames = crossing_frames(path(12, lambda i: (-2 + i * 0.3, 0)),
                             path(12, lambda i: (0, 0)), actor_presence=[False] * 12)
    result = direct_crossing(frames)
    assert result["realization"] == "indeterminate"
    assert result["outcome"] == "indeterminate"


def test_missing_ego_footprint_is_indeterminate_not_not_reached():
    frames = crossing_frames(path(12, lambda i: (-2 + i * 0.3, 0)),
                             path(12, lambda i: (0, 0)))
    for frame in frames:
        ego = next(item for item in frame["actors"] if item["id"] == EGO)
        ego.update(present=False, x=None, y=None)
    result = direct_crossing(frames)
    assert result["realization"] == "indeterminate"
    assert result["outcome"] == "indeterminate"


def test_actor_loss_and_missing_footprints_are_indeterminate():
    frames = crossing_frames(path(12, lambda i: (-5, 0)), path(12, lambda i: (0, 0)),
                             actor_presence=[True] * 5 + [False] * 7)
    result = direct_crossing(frames)
    assert result["realization"] == "indeterminate"

    frames = crossing_frames(path(12, lambda i: (-5, 0)), path(12, lambda i: (0, 0)))
    for row in frames:
        next(item for item in row["actors"] if item["id"] == OTHER).pop("length")
        next(item for item in row["actors"] if item["id"] == OTHER).pop("width")
    result = direct_crossing(frames)
    assert result["realization"] == "indeterminate"


@pytest.mark.parametrize("actor_first", [False, True])
def test_ordered_crossing_emits_pet_for_ego_first_and_actor_first(actor_first):
    n = 16
    ego_xy = path(n, lambda i: ((0, 0) if (3 <= i <= 5 if not actor_first else 9 <= i <= 11)
                               else (-5, 0)))
    actor_xy = path(n, lambda i: ((0, 0) if (9 <= i <= 11 if not actor_first else 3 <= i <= 5)
                                 else (0, 5)))
    result = direct_crossing(crossing_frames(ego_xy, actor_xy))
    row = result["actors"][0]
    assert result["realization"] == "encountered"
    assert result["outcome"] == "resolved"
    assert len(row["post_encroachment_times"]) == 1
    assert row["post_encroachment_times"][0]["pet_s"] >= 0


def test_simultaneous_and_repeated_occupancy_are_not_collapsed_to_pet():
    n = 16
    simultaneous = crossing_frames(
        path(n, lambda i: (0, 0) if 4 <= i <= 7 else (-5, 0)),
        path(n, lambda i: (0, 0) if 5 <= i <= 8 else (0, 5)))
    result = direct_crossing(simultaneous)
    assert result["outcome"] == "unresolved"
    assert result["actors"][0]["simultaneous_occupancy"] is True
    assert result["actors"][0]["pet_status"] == "undefined"

    repeated = crossing_frames(
        path(n, lambda i: (0, 0) if i in {2, 3, 7, 8} else (-5, 0)),
        path(n, lambda i: (0, 0) if i in {10, 11} else (0, 5)))
    result = direct_crossing(repeated)
    assert result["actors"][0]["repeated_occupancy"] is True
    assert result["outcome"] == "unresolved"


def test_ordered_passage_without_supported_clock_has_null_pet():
    frames = crossing_frames(path(16, lambda i: (0, 0) if 3 <= i <= 5 else (-5, 0)),
                             path(16, lambda i: (0, 0) if 9 <= i <= 11 else (0, 5)))
    for frame in frames:
        frame["time_s"] = None
    result = direct_crossing(frames)
    row = result["actors"][0]
    assert result["outcome"] == "resolved"
    assert row["pet_status"] == "unavailable"
    assert row["post_encroachment_times"][0]["pet_s"] is None


def test_after_ego_cyclist_has_no_yielding_obligation():
    context = InteractionContext(
        "valid", "synthetic source context", scene_id="synthetic",
        specs=({"family": "cyclist_crossing", "subtype": "cyclist_crossing_after_ego",
                "source_opportunity": True, "actor_ids": [OTHER], "supported": True},),
        source_scene={"objects": [source_actor(EGO, 1,
            [{"x": 0.0, "y": 0.0}] * 30, [0.0] * 30),
            source_actor(OTHER, 3, [{"x": 0.0, "y": 0.0}] * 30, [1.5] * 30)]},
        certificates={"source_body_path_conflict": {"status": "absent", "actors": {}}})
    frames = crossing_frames(path(12, lambda i: (0, 0) if 2 <= i <= 4 else (-5, 0)),
                             path(12, lambda i: (0, 0) if 7 <= i <= 9 else (0, 5)))
    result, _, _ = _crossing_measure(
        frames, [row["time_s"] for row in frames], context.specs[0], context,
        SimpleNamespace(start_source_step=0, goal_source_step=29, identity={}),
        {"ego_source_id": EGO, "terminal_reason": "horizon"}, (), None, PROFILE)
    assert result["outcome"] == "resolved"
    assert result["actors"][0]["yielding_compliance"]["status"] == "not_applicable"


def lane_map(*, second_lane=False):
    lanes = [LaneCenterline(1, ((-20.0, 0.0), (20.0, 0.0)), 4.0, ())]
    if second_lane:
        lanes.append(LaneCenterline(2, ((-20.0, 5.0), (20.0, 5.0)), 4.0, ()))
    return MapContext("valid", "synthetic", lanes=tuple(lanes),
                      identity={"source_map_sha256": "map-hash"})


def test_following_reports_stopped_gap_undefined_headway_and_restart():
    n = 18
    frames = []
    for index in range(n):
        leader_v = 0.0 if index <= 12 else 2.0
        frames.append({"step": index, "time_s": index / 10,
                       "transition_applied": index < n - 1,
                       "actors": [actor(EGO, index * 0.1, 0, vx=0.0),
                                  actor(OTHER, 8 + index * (0 if index <= 12 else 0.2),
                                        0, vx=leader_v)]})
    context = InteractionContext("valid", "synthetic")
    spec = {"family": "longitudinal_following", "subtype": "lead_vehicle_stop_and_restart",
            "source_map_sha256": "map-hash", "actor_ids": [OTHER]}
    measured, _, duration = _following_measure(
        frames, [row["time_s"] for row in frames], spec, context,
        {"ego_source_id": EGO, "terminal_reason": "horizon"}, PROFILE, lane_map())
    assert measured["realization"] == "encountered"
    assert duration and duration > 0
    sample = measured["actors"][0]["samples"][0]
    assert sample["physical_gap_m"] > 0
    assert sample["moving_time_headway_s"] is None
    assert sample["headway_status"] == "undefined_at_standstill"
    assert measured["actors"][0]["stop_restart"]["restarted"] is True


def test_wrong_route_leader_is_not_following():
    n = 14
    frames = [{"step": i, "time_s": i / 10, "transition_applied": i < n - 1,
               "actors": [actor(EGO, 0.0, 0.0, vx=2.0),
                          actor(OTHER, 8.0, 5.0, vx=2.0)]} for i in range(n)]
    spec = {"family": "longitudinal_following", "subtype": "lead_vehicle_constrained_following",
            "source_map_sha256": "map-hash", "actor_ids": [OTHER]}
    measured, _, _ = _following_measure(
        frames, [row["time_s"] for row in frames], spec,
        InteractionContext("valid", "synthetic"),
        {"ego_source_id": EGO, "terminal_reason": "horizon"}, PROFILE,
        lane_map(second_lane=True))
    assert measured["realization"] == "not_reached"
    assert measured["actors"][0]["samples"] == []


def test_ambiguous_directed_successor_path_is_indeterminate():
    lanes = (
        LaneCenterline(1, ((-10.0, 0.0), (10.0, 0.0)), 4.0, (2, 3)),
        LaneCenterline(2, ((10.0, 0.0), (20.0, 2.0)), 4.0, (4,)),
        LaneCenterline(3, ((10.0, 0.0), (20.0, -2.0)), 4.0, (4,)),
        LaneCenterline(4, ((20.0, 0.0), (35.0, 0.0)), 4.0, ()),
    )
    context = MapContext("valid", "synthetic", lanes=lanes,
                         identity={"source_map_sha256": "map-hash"})
    n = 14
    frames = [{"step": i, "time_s": i / 10, "transition_applied": i < n - 1,
               "actors": [actor(EGO, 0.0, 0.0, vx=2.0),
                          actor(OTHER, 25.0, 0.0, vx=2.0)]} for i in range(n)]
    spec = {"family": "longitudinal_following", "subtype": "lead_vehicle_constrained_following",
            "source_map_sha256": "map-hash", "actor_ids": [OTHER]}
    measured, _, _ = _following_measure(
        frames, [row["time_s"] for row in frames], spec,
        InteractionContext("valid", "synthetic"),
        {"ego_source_id": EGO, "terminal_reason": "horizon"}, PROFILE, context)
    assert measured["realization"] == "indeterminate"
    assert measured["outcome"] == "indeterminate"
    assert measured["route_compatibility_status"] == "ambiguous"
    assert measured["actors"][0]["route_observation_counts"]["ambiguous"] > 0


@pytest.mark.parametrize("subtype", [
    "uncontested_turn_with_adjacent_parallel_traffic",
    "uncontested_turn_with_nearby_vrus",
    "uncontested_goal_approach_ending_before_queue",
])
def test_control_family_marks_interaction_not_applicable(monkeypatch, subtype):
    context = InteractionContext("valid", "synthetic", specs=(
        {"family": "control", "subtype": subtype,
         "source_opportunity": False, "actor_ids": []},), evidence_refs=())
    monkeypatch.setattr("geotransfer_gap.evaluation.interactions.build_interaction_context",
                        lambda *args, **kwargs: context)
    frames = [{"step": i, "time_s": i / 10, "actors": [actor(EGO, i, 0)]}
              for i in range(12)]
    result = measure_interactions(
        frames, EGO, {"schema_version": 3, "ego_source_id": EGO}, PROFILE,
        {"observation_masks": [{"time_s": row["time_s"]} for row in frames]},
        SimpleNamespace(status="valid"), lane_map(), (), scene_root=Path("."))
    assert result["interactions"][0]["actual_realization"] == "not_applicable"
    assert {row["status"] for row in result["metrics"]} == {"not_applicable"}


def test_episode_keeps_task_failure_when_encounter_was_not_reached(monkeypatch):
    from geotransfer_gap.evaluation import episode

    task = SimpleNamespace(status="valid", evidence_refs=(), summary=lambda: {})
    monkeypatch.setattr(episode, "measure_kinematics", lambda *args, **kwargs: {
        "metrics": [], "events": [{"step": 11, "channel": "native_offroad"}],
        "exposure": {"event_observation_coverage": {"windows": {"full": {
            "channels": {"collision_state": {"status": "valid", "fraction": 1.0}}}}}},
    })
    monkeypatch.setattr(episode, "measure_safety", lambda *args, **kwargs: {"metrics": []})
    monkeypatch.setattr(episode, "measure_map_metrics", lambda *args, **kwargs: {
        "metrics": [], "context": {"status": "unavailable"}})
    monkeypatch.setattr(episode, "measure_tasks", lambda *args, **kwargs: {
        "metrics": [], "task": {"context": {"annotation": {"status": "absent"}},
            "bounded_task_completion": {"outcome": "failed", "reason": "progress failure"}}})
    monkeypatch.setattr(episode, "measure_interactions", lambda *args, **kwargs: {
        "status": "valid", "reason": "source opportunity retained", "timebase": "recorded_time_s",
        "interactions": [{"actual_realization": "not_reached",
                          "interaction_outcome": "not_assessed"}], "metrics": [],
    })
    report = {"schema_version": 3, "planner": "controller_matrix", "ego_binary_index": 0,
              "binary_sha256": "a" * 64, "ego_source_id": EGO,
              "requested_observation_frames": 1, "terminal_reason": "horizon"}
    playback = SimpleNamespace(report=report, hashes={"trace": "b" * 64}, bound=False,
                               evaluation_capture=None, evaluation_capture_bound=False)
    saved = SimpleNamespace(playback=playback, ego_source_id=EGO,
                             producer_revision=None,
                             evidence_level=SimpleNamespace(value="trace_only_diagnostic"),
                             frames=lambda: [{"step": 0, "actors": []}])
    result, _ = episode.evaluate_episode(saved, PROFILE, task_context=task,
                                         map_context=MapContext("unavailable", "no map"))
    assert result["task"]["bounded_task_completion"]["outcome"] == "failed"
    assert result["interactions"]["results"][0]["actual_realization"] == "not_reached"


def test_source_context_binds_manifest_scene_binary_and_fidelity(tmp_path, monkeypatch):
    testing = tmp_path / "testing"
    testing.mkdir()
    binary = testing / "map_000000.bin"
    binary.write_bytes(b"synthetic binary")
    scene_path = testing / "ind_synthetic.json"
    scene = {"objects": [source_actor(EGO, 1, [{"x": 0, "y": 0}] * 20, [0.0] * 20),
                         source_actor(OTHER, 2, [{"x": 0, "y": 1}] * 20, [0.0] * 20)]}
    write_json(scene_path, scene)
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, {"schema_version": 2, "scenes": []})
    rule_path = testing / "rule_applicability_audit.json"
    write_json(rule_path, {"schema_version": 1})
    lifecycle_path = testing / "lifecycle_trace_hybrid_startup.json"
    lifecycle = {"binary_sha256": sha(binary), "traffic_mode": "hybrid_startup",
                 "evaluation_ini_sha256": "a" * 64,
                 "runtime_source_sha256": "runtime-id", "observed_steps": 20}
    write_json(lifecycle_path, lifecycle)
    from geotransfer_gap.validation.audit_interaction_fidelity import source_evidence_digest

    fidelity = {"schema_version": 3, "traffic_mode": "hybrid_startup",
                "binary_sha256": sha(binary), "ego_track_id": EGO,
                "rule_audit_sha256": sha(rule_path), "idm_trace_sha256": sha(lifecycle_path),
                "evaluation_ini_sha256": "a" * 64,
                "runtime_source_sha256": "runtime-id", "idm_observed_steps": 20,
                "actor_opportunities": [{"track_id": OTHER, "type": "pedestrian",
                    "source_box_step": 12, "source_timed_box_gap_m": 1.0,
                    "source_speed_mps": 1.0, "source_close_steps_after_warmup": 5,
                    "longest_source_close_run_steps": 5,
                    "preserved_for_claimed_interaction": True}]}
    fidelity["source_evidence_digest"] = source_evidence_digest(fidelity)
    write_json(testing / "interaction_fidelity_audit_hybrid_startup.json", fidelity)
    conflict = {"schema_version": 1, "source_scene_sha256": sha(scene_path),
                "audit_sha256": "b" * 64,
                "actors": [{"actor_id": OTHER, "actor_type": "pedestrian",
                            "source_task_end_step": 19,
                            "source_path_box_evidence": {"minimum_spatial_box_gap_m": 0.0,
                                "minimum_timed_box_gap_m": 1.0},
                            "crossing_corridors_overlap": True}]}
    write_json(testing / "source_task_interaction_audit.json", conflict)
    row = {"name": "synthetic", "root": str(tmp_path), "binary_sha256": sha(binary),
           "ego_track_id": EGO, "ego_binary_index": 0, "interaction_opportunity": True,
           "interaction_type_families": ["pedestrian_crossing"],
           "interaction_types": ["pedestrian_crossing_ahead"],
           "interaction_actor_ids": [OTHER], "traffic_protocol": "hybrid_startup",
           "source_map_sha256": "map-hash", "source_tracks_sha256": "tracks-hash"}
    monkeypatch.setattr("geotransfer_gap.evaluation.interactions._scene_row",
                        lambda root, binary_hash: (row, manifest_path, None))
    task = SimpleNamespace(status="valid", scene_id="synthetic", identity={
        "binary_sha256": sha(binary), "source_scene_sha256": sha(scene_path),
        "manifest_sha256": sha(manifest_path)})
    context = build_interaction_context(tmp_path, task, {
        "ego_source_id": EGO, "ego_binary_index": 0})
    assert context.status == "valid", context.reason
    assert context.specs[0]["actor_ids"] == [OTHER]
    assert context.specs[0]["subtype"] == "pedestrian_crossing_ahead"
    assert context.specs[0]["fidelity_by_actor"][str(OTHER)] == "preserved"
    assert {row["kind"] for row in context.evidence_refs} >= {
        "source_interaction_fidelity", "source_body_path_conflict"}

    scene["objects"][1]["position"][0]["x"] = 999
    write_json(scene_path, scene)
    invalid = build_interaction_context(tmp_path, task, {
        "ego_source_id": EGO, "ego_binary_index": 0})
    assert invalid.status == "invalid"
    assert "source scene differs" in invalid.reason
