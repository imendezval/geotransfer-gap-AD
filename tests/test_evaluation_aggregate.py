import copy

import pytest

from geotransfer_gap.evaluation.aggregate import (
    _bootstrap,
    _load_evaluation,
    aggregate_records,
    _paired_intersections,
    paired_cluster_bootstrap,
    paired_condition_summary,
    sensitivity_records,
)
from geotransfer_gap.artifacts import sha256, write_json


PROFILE = {
    "uncertainty": {"cluster_unit": "recording_or_sequence", "bootstrap_seed": 7,
                    "bootstrap_resamples": 200, "confidence_level": 0.95},
}


def metric(metric_id, value, *, status="valid", window="full", units="s", version="1.0.0"):
    return {"metric_id": metric_id, "window": window, "status": status,
            "definition_version": version, "units": units, "value": value,
            "criterion_outcome": "not_assessed"}


def episode(episode_id, recording, *, distance=10, duration=10, collisions=0,
            evidence="valid", metric_status="valid", metric_version="1.0.0", location=1):
    metrics = [
        metric("trajectory.observed_distance", {"distance_m": distance},
               status=metric_status, units="m", version=metric_version),
        metric("exposure.controlled_duration", {"duration_s": duration},
               status=metric_status, window="full", units="s"),
        metric("safety.native_vehicle_collision_onsets",
               {"observed_onset_count": collisions, "count_is_lower_bound": False},
               status=metric_status, units="onsets"),
        metric("safety.native_offroad_onsets",
               {"observed_onset_count": 0, "count_is_lower_bound": False},
               status=metric_status, units="onsets"),
        metric("task.outcome", {"outcome": "completed"}, status=metric_status, units="category"),
        metric("trajectory.route_progress", {"net_progress_m": distance},
               status=metric_status, units="m"),
        metric("efficiency.low_progress_candidate", {"candidate": False},
               status=metric_status, units={"route_advance": "m", "window": "s"}),
    ]
    return {
        "episode_id": episode_id, "scene_id": episode_id,
        "protocol": {"ego": "planner-A", "traffic": "SMART", "startup": "immediate"},
        "accounting": {"execution_status": "passed"},
        "evidence": {"status": evidence, "level": "archived_attested" if evidence == "valid" else None},
        "input_profile": {"effective_sha256": "profile-hash"},
        "episode_metrics": {
            "input": {"protocol": {"ego_controller": "planner-A", "traffic_controller": "SMART",
                                    "traffic_startup": "immediate"}},
            "evaluator": {"effective_profile_sha256": "profile-hash", "definition_version": "1.0.0"},
            "exposure": {"censoring": {"requested_observations": 91}},
            "task": {"outcome": {"outcome": "completed"}, "context": {"identity": {
                "recording": recording, "location": location}}},
            "interactions": {"results": [{"family": "crossing_pedestrian", "actual_realization": "unrealized"}]},
            "metrics": metrics,
        },
        "task_result": {"outcome": "completed"}, "failure_taxonomy": [],
    }


def find_stratum(aggregate):
    assert len(aggregate["strata"]) == 1
    return aggregate["strata"][0]


def find_metric(stratum, metric_id):
    return next(row for row in stratum["metric_summaries"] if row["metric_id"] == metric_id)


def test_mixed_denominators_event_exposure_and_macro_ratio_are_distinct():
    one = episode("a", 1, distance=10, duration=10, collisions=1)
    two = episode("b", 1, distance=20, duration=30, collisions=0)
    three = episode("c", 2, distance=30, duration=0, collisions=1, metric_status="unavailable")
    records = [(one, []), (two, []), (three, [])]
    report = aggregate_records(records, uncertainty_profile=PROFILE)
    stratum = find_stratum(report)
    distance = find_metric(stratum, "trajectory.observed_distance")
    assert distance["submitted"] == 3
    assert distance["applicable"] == 3
    assert distance["valid"] == 2
    assert distance["per_episode_scalar"]["mean"] == 15
    progress = find_metric(stratum, "trajectory.route_progress")
    assert progress["per_episode_scalar"]["mean"] == 15
    low_progress = find_metric(stratum, "efficiency.low_progress_candidate")
    assert low_progress["categorical_value_counts"] == {"candidate": {"False": 2}}
    collision = stratum["outcomes"]["event_exposure"]["safety.native_vehicle_collision_onsets:full"]
    assert collision["total_events"] == 1
    assert collision["total_exposure_s"] == 40
    assert collision["pooled_events_per_exposure_second"] == pytest.approx(1 / 40)
    assert collision["mean_episode_events_per_exposure_second"] == pytest.approx(0.05)
    assert collision["episode_event_rate"] == pytest.approx(0.5)
    assert stratum["accounting"] == {"submitted": 3, "executed_with_valid_saved_evidence": 3,
                                     "execution_failed": 0, "excluded_without_valid_saved_evidence": 0,
                                     "partition_check": True}


def test_all_unavailable_and_no_exposure_remain_null_not_zero():
    row = episode("a", 1, duration=0, metric_status="unavailable")
    metrics = row["episode_metrics"]["metrics"]
    for item in metrics:
        if item["metric_id"] in ("exposure.controlled_duration", "safety.native_vehicle_collision_onsets"):
            item["status"] = "valid"
    result = aggregate_records([(row, [])], uncertainty_profile=PROFILE)
    stratum = find_stratum(result)
    distance = find_metric(stratum, "trajectory.observed_distance")
    assert distance["valid"] == 0
    assert distance["per_episode_scalar"]["status"] == "unavailable"
    exposure = stratum["outcomes"]["event_exposure"]["safety.native_vehicle_collision_onsets:full"]
    assert exposure["status"] == "not_applicable"
    assert exposure["pooled_events_per_exposure_second"] is None
    assert exposure["episode_event_rate"] == 0


def test_bootstrap_clusters_repeated_scenes_missing_and_degenerate_are_explicit():
    repeated = _bootstrap([("recording:1", 1), ("recording:1", 3)], seed=7,
                         resamples=50, confidence_level=.95)
    assert repeated["status"] == "unavailable"
    assert "fewer than two" in repeated["reason"]
    missing = _bootstrap([(None, 1), ("recording:2", 3)], seed=7,
                         resamples=50, confidence_level=.95)
    assert missing["interval"] is None and "missing" in missing["reason"]
    degenerate = _bootstrap([("one", 0), ("two", 0)], seed=7,
                            resamples=50, confidence_level=.95)
    assert degenerate["status"] == "degenerate_resamples"
    assert degenerate["interval"] is None
    all_events = _bootstrap([("one", 1), ("two", 1)], seed=7,
                            resamples=50, confidence_level=.95)
    assert all_events["status"] == "degenerate_resamples"
    assert all_events["interval"] is None


def test_paired_bootstrap_is_deterministic_and_reports_few_cluster_limits():
    pairs = [{"episode_id": "a", "cluster_id": "rec-1", "difference": .2},
             {"episode_id": "b", "cluster_id": "rec-2", "difference": .4}]
    first = paired_cluster_bootstrap(pairs, seed=13, resamples=200)
    second = paired_cluster_bootstrap(pairs, seed=13, resamples=200)
    assert first == second
    assert first["status"] == "exploratory_few_clusters"
    assert first["interval"]["lower"] <= first["interval"]["upper"]


def test_paired_conditions_use_exact_scene_intersection_and_keep_cluster_blocks():
    records = []
    for scene, recording, base, delta in (("s1", 1, 10, 1), ("s1b", 1, 20, 5),
                                          ("s2", 2, 30, 4)):
        left = episode(f"{scene}-immediate", recording, distance=base)
        right = episode(f"{scene}-source-hold", recording, distance=base + delta)
        left["scene_id"] = right["scene_id"] = scene
        left["protocol"]["startup"] = "immediate"
        right["protocol"]["startup"] = "source_hold"
        records.extend(((left, []), (right, [])))
    unmatched = episode("s3-immediate", 3, distance=10)
    unmatched["scene_id"] = "s3"
    unmatched["protocol"]["startup"] = "immediate"
    records.append((unmatched, []))
    comparison = paired_condition_summary(
        records, dimension="startup", left="immediate", right="source_hold",
        metric_id="trajectory.observed_distance", window="full",
        definition_version="1.0.0", units="m", uncertainty_profile=PROFILE)
    assert len(comparison["comparisons"]) == 1
    result = comparison["comparisons"][0]
    assert result["shared_logical_scene_ids"] == ["s1", "s1b", "s2"]
    assert result["left_only_logical_scene_ids"] == ["s3"]
    assert result["paired_valid_scene_ids"] == ["s1", "s1b", "s2"]
    assert result["paired_difference_summary"]["mean"] == pytest.approx(10 / 3)
    assert result["uncertainty"]["clusters"] == 2
    assert result["uncertainty"]["status"] == "exploratory_few_clusters"
    assert "equal cluster weighting" in result["uncertainty"]["method"]
    integrated = _paired_intersections(records, PROFILE)
    assert any(item["dimension"] == "startup"
               and item["left_condition"] == "immediate"
               and item["right_condition"] == "source_hold"
               for item in integrated)


def test_incompatible_metric_versions_are_not_pooled():
    first = episode("a", 1, distance=10)
    second = episode("b", 2, distance=30, metric_version="2.0.0")
    report = aggregate_records([(first, []), (second, [])], uncertainty_profile=PROFILE)
    stratum = find_stratum(report)
    distance = [row for row in stratum["metric_summaries"]
                if row["metric_id"] == "trajectory.observed_distance"]
    assert {row["metric_definition_version"] for row in distance} == {"1.0.0", "2.0.0"}
    assert [row["valid"] for row in distance] == [1, 1]
    assert all(row["submitted"] == 2 and row["emitted"] == 2 for row in distance)
    assert all(row["status_counts"]["incompatible_definition_or_units"] == 1 for row in distance)


def test_sensitivity_reuses_saved_series_and_keeps_variant_pairing():
    row = episode("a", 1)
    comfort = metric("trajectory.acceleration_longitudinal", {
        "threshold": 3.0, "exceedance_duration_s": .5,
        "samples": [{"value": 3.1, "exposure_s": .5}, {"value": 2.0, "exposure_s": .5}],
    }, window="primary", units="m/s^2")
    comfort["value"]["threshold"] = 3.0
    row["episode_metrics"]["metrics"].append(comfort)
    report = sensitivity_records([(row, [])], uncertainty_profile=PROFILE,
                                 threshold_scales=[.8, 1.0, 1.2])
    variants = report["groups"][0]["variants"]
    lower = next(item for item in variants
                 if item["variant"] == "comfort_scale:0.8" and item["window"] == "primary")
    primary = next(item for item in variants
                   if item["variant"] == "comfort_scale:1" and item["window"] == "primary")
    higher = next(item for item in variants
                  if item["variant"] == "comfort_scale:1.2" and item["window"] == "primary")
    assert lower["value_summary"]["mean"] == pytest.approx(.5)
    assert primary["value_summary"]["mean"] == pytest.approx(.5)
    assert higher["value_summary"]["mean"] == pytest.approx(0)
    assert lower["paired_episode_ids"] == ["a"]
    assert report["method"].startswith("reused PE09")


def test_sensitivity_does_not_mutate_saved_result_objects():
    row = episode("a", 1)
    before = copy.deepcopy(row)
    sensitivity_records([(row, [])], uncertainty_profile=PROFILE, threshold_scales=[.8, 1.2])
    assert row == before


def test_result_profile_conflicts_are_rejected():
    row = episode("a", 1)
    row["episode_metrics"]["evaluator"]["effective_profile_sha256"] = "other"
    with pytest.raises(ValueError, match="conflicting profile"):
        aggregate_records([(row, [])], uncertainty_profile=PROFILE)


def test_saved_pe09_result_and_event_files_are_hash_checked(tmp_path):
    evaluation = tmp_path / "evaluation"
    episode_dir = evaluation / "episodes"
    episode_dir.mkdir(parents=True)
    snapshot = evaluation / "input_snapshot.json"
    write_json(snapshot, {"schema_version": 1, "files": []})
    event_path = episode_dir / "events.json"
    write_json(event_path, {"schema_version": 1, "events": []})
    event_hash = sha256(event_path)
    result_path = episode_dir / "result.json"
    result = {"result_schema_version": 1,
              "episode_id": "scene:planner-A:SMART:immediate", "events_sha256": event_hash,
              "accounting": {}, "evidence": {},
              "input_profile": {"effective_sha256": "profile-hash"},
              "episode_metrics": {"evaluator": {"effective_profile_sha256": "profile-hash",
                                                 "definition_version": "1.0.0"}}}
    write_json(result_path, result)
    index = {
        "schema_version": 1, "complete": True, "expected_episodes": 1,
        "profile": {"effective_sha256": "profile-hash", "definition_version": "1.0.0"},
        "input_snapshot": {"file": "input_snapshot.json", "sha256": sha256(snapshot)},
        "episodes": [{"episode_id": result["episode_id"], "result_file": "episodes/result.json",
                      "result_sha256": sha256(result_path), "events_file": "episodes/events.json",
                      "events_sha256": event_hash}],
    }
    write_json(evaluation / "index.json", index)
    assert _load_evaluation(evaluation)[2][0][0]["episode_id"] == result["episode_id"]
    write_json(event_path, {"schema_version": 1, "events": [{"tampered": True}]})
    with pytest.raises(ValueError, match="events are missing or have changed"):
        _load_evaluation(evaluation)
