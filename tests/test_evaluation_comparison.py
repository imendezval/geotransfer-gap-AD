import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tomllib

import pytest

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.evaluation import comparison
from geotransfer_gap.evaluation.comparison import (
    compare_records,
    load_comparison_config,
)


def _record(scene, recording, location, binary, progress, *, planner="SMART", startup="immediate"):
    return {
        "episode_id": f"{scene}:{planner}", "scene_id": scene,
        "protocol": {"ego": planner, "traffic": "IDM", "startup": startup},
        "accounting": {"execution_status": "passed", "campaign_status": None,
                       "campaign_integration_validity": None},
        "evidence": {"status": "valid", "level": "archived_attested"},
        "input_profile": {"effective_sha256": "profile-sha"},
        "episode_metrics": {
            "input": {
                "protocol": {"ego_controller": planner, "traffic_controller": "IDM",
                             "traffic_startup": startup},
                "planner_layout": "controller_matrix", "trace_schema_version": 3,
                "live_validation_status": "passed",
                "checkpoint_identity": {"ego": {"status": "recorded_hash_bound", "sha256": "a" * 64},
                                         "traffic": {"status": "not_applicable", "sha256": None}},
            },
            "evaluator": {"effective_profile_sha256": "profile-sha", "definition_version": "1.0.0"},
            "exposure": {"censoring": {"requested_observations": 91}},
        "task": {
                "context": {"task_id": "source_bounded_goal", "completion_radius_m": 2.0,
                             "deadline_s": None, "route": {"task_span_m": 48.0},
                             "status": "valid", "annotation": {"status": "absent", "claims": []},
                             "identity": {"recording": recording, "location": location,
                                          "binary_sha256": binary,
                                          "source_scene_sha256": "3" * 64}},
                "planner_goal_visibility": {"status": "not_applicable", "value": None},
            },
            "map_context": {"status": "valid", "identity": {
                "source_map_sha256": "4" * 64, "map_semantics_sha256": "5" * 64,
            }},
            "metrics": [{"metric_id": "trajectory.route_progress", "window": "primary",
                          "status": "valid", "definition_version": "1.0.0", "units": "m",
                          "value": {"net_progress_m": progress}}],
        },
    }


def _feature_row(scene, binary, *, speed=4.0, family="longitudinal_following"):
    return {
        "name": scene, "binary_sha256": binary,
        "source_tracks_sha256": "6" * 64, "source_map_sha256": "4" * 64,
        "dimension_provenance": "measured_source_boxes",
        "legal_semantics": ["reviewed_priority_scope"],
        "interaction_type_families": [family],
        "comparison_features": {
            "interaction_subtype": "lead_vehicle_stop_and_restart",
            "initial_speed_m_s": speed,
            "route_length_m": 48.0,
            "route_curvature_per_m": 0.01,
            "traffic_composition": "vehicles_only",
            "traffic_density_actors_per_km": 10.0,
            "horizon_observations": 91,
            "geometry_class": "two_lane_urban",
        },
    }


def _config():
    value, _ = load_comparison_config()
    value = copy.deepcopy(value)
    value["cohorts"]["left"]["status"] = "research_candidate"
    value["cohorts"]["right"]["status"] = "research_candidate"
    value["_uncertainty"] = {"bootstrap_seed": 11, "bootstrap_resamples": 100,
                             "confidence_level": 0.95}
    return value


def test_matched_synthetic_gap_is_directional_and_clustered():
    left_rows, right_rows, left, right = {}, {}, [], []
    for side, rows, records, values, prefix in (
        ("left", left_rows, left, [1.0, 2.0, 2.0], "de"),
        ("right", right_rows, right, [5.0, 4.0, 6.0], "us"),
    ):
        for index, progress in enumerate(values):
            scene, binary = f"{prefix}{index}", hashlib.sha256(f"{side}{index}".encode()).hexdigest()
            rows[scene] = _feature_row(scene, binary)
            records.append((_record(scene, index + 1, index + 1, binary, progress), []))
    result = compare_records(left, right, left_rows, right_rows, _config())
    assert result["matching"]["matched_stratum_count"] == 1
    metric = next(row for row in result["metrics"]
                  if row["metric_id"] == "trajectory.route_progress")
    assert metric["estimate_right_minus_left"] == pytest.approx(10 / 3)
    assert metric["improvement"] is True
    assert metric["uncertainty"]["status"] == "exploratory_few_clusters"
    assert metric["uncertainty"]["stratum_support"][0]["left"]["clusters"] == 3
    assert "equal-stratum" in metric["uncertainty"]["method"]


def test_frozen_diagnostic_us_cohort_never_emits_geographic_metric_gap():
    left_rows, right_rows, left, right = {}, {}, [], []
    config, _ = load_comparison_config()
    for side, rows, records, prefix in (("left", left_rows, left, "de"),
                                        ("right", right_rows, right, "us")):
        for index in range(3):
            scene, binary = f"{prefix}{index}", hashlib.sha256(f"{side}{index}".encode()).hexdigest()
            rows[scene] = _feature_row(scene, binary)
            records.append((_record(scene, index + 1, index + 1, binary, float(index)), []))
    result = compare_records(left, right, left_rows, right_rows, config)
    assert result["matching"]["matched_stratum_count"] == 1
    assert result["metric_comparison_status"] == "withheld_diagnostic_only_cohort"
    assert result["metrics"] == []
    assert result["status"] == "baseline_not_ready"


def test_missing_source_stratum_is_reported_and_never_forced():
    left_binary, right_binary = "a" * 64, "b" * 64
    left = [(_record("de", 1, 1, left_binary, 1.0), [])]
    right = [(_record("us", 2, 2, right_binary, 2.0), [])]
    left_rows = {"de": _feature_row("de", left_binary)}
    right_rows = {"us": _feature_row("us", right_binary)}
    del right_rows["us"]["comparison_features"]["initial_speed_m_s"]
    result = compare_records(left, right, left_rows, right_rows, _config())
    assert result["status"] == "baseline_not_ready"
    assert result["cohorts"]["right"]["missing_strata_counts"]["initial_speed_m_s"] == 1
    assert result["matching"]["matched_stratum_count"] == 0
    assert result["metrics"] == []
    assert result["matching"]["unmatched_scenes"]["right"][0]["reason"] == "unsupported_source_stratum"


def test_missing_recording_cluster_keeps_estimate_but_withholds_uncertainty():
    left_binary, right_binary = "c" * 64, "d" * 64
    left = [(_record("de", None, None, left_binary, 1.0), [])]
    right = [(_record("us", None, None, right_binary, 4.0), [])]
    left_rows = {"de": _feature_row("de", left_binary)}
    right_rows = {"us": _feature_row("us", right_binary)}
    result = compare_records(left, right, left_rows, right_rows, _config())
    metric = next(row for row in result["metrics"]
                  if row["metric_id"] == "trajectory.route_progress")
    assert metric["estimate_right_minus_left"] == 3.0
    assert metric["uncertainty"]["status"] == "unavailable"
    assert "missing" in metric["uncertainty"]["reason"]


def test_saved_trace_binary_binding_does_not_invent_missing_task_clusters():
    left_binary, right_binary = "4" * 64, "5" * 64
    left_record = _record("de", 1, 1, left_binary, 2.0)
    right_record = _record("us", 2, 2, right_binary, 5.0)
    right_record["episode_metrics"]["task"]["context"]["identity"] = None
    right_record["episode_metrics"]["input"]["binary_sha256"] = right_binary
    result = compare_records([(left_record, [])], [(right_record, [])],
                             {"de": _feature_row("de", left_binary)},
                             {"us": _feature_row("us", right_binary)}, _config())
    assert not any(item["reason"] == "manifest_or_result_binary_identity_missing"
                   for item in result["matching"]["unmatched_scenes"]["right"])
    assert result["cohorts"]["right"]["recording_sequence_clusters"] == 0
    assert result["status"] == "baseline_not_ready"


def test_protocol_mismatch_suppresses_geographic_metric_difference():
    left_binary, right_binary = "e" * 64, "f" * 64
    left = [(_record("de", 1, 1, left_binary, 1.0), [])]
    right = [(_record("us", 2, 2, right_binary, 7.0, startup="source_hold"), [])]
    result = compare_records(left, right,
                             {"de": _feature_row("de", left_binary)},
                             {"us": _feature_row("us", right_binary)}, _config())
    assert result["protocol_compatibility"]["status"] == "limited"
    assert "startup" in result["protocol_compatibility"]["differences"]
    assert result["metrics"] == []


def test_archived_but_failed_execution_is_not_comparable():
    left_binary, right_binary = "9" * 64, "a" * 64
    left = [(_record("de", 1, 1, left_binary, 1.0), [])]
    failed = _record("us", 2, 2, right_binary, 9.0)
    failed["accounting"]["execution_status"] = "failed"
    result = compare_records(left, [(failed, [])],
                             {"de": _feature_row("de", left_binary)},
                             {"us": _feature_row("us", right_binary)}, _config())
    assert result["protocol_compatibility"]["status"] == "limited"
    assert "right_execution_validity" in result["protocol_compatibility"]["differences"]
    assert result["metrics"] == []


def test_blocked_pe09_row_without_episode_metrics_is_preserved_and_excluded():
    left_binary, right_binary = "b" * 64, "c" * 64
    blocked = {
        "episode_id": "us:blocked", "scene_id": "us",
        "protocol": {"ego": "SMART", "traffic": "IDM", "startup": "immediate"},
        "accounting": {"execution_status": "blocked", "campaign_status": "BLOCKED",
                       "campaign_integration_validity": None},
        "evidence": {"status": "unavailable", "level": None},
        "episode_metrics": None,
    }
    result = compare_records(
        [(_record("de", 1, 1, left_binary, 1.0), [])], [(blocked, [])],
        {"de": _feature_row("de", left_binary)},
        {"us": _feature_row("us", right_binary)}, _config(),
    )
    assert result["status"] == "baseline_not_ready"
    assert result["metrics"] == []
    failure = result["protocol_compatibility"]["differences"]["right_execution_validity"][0]
    assert failure["execution_status"] == "blocked"
    assert failure["campaign_status"] == "BLOCKED"


def test_campaign_pass_with_validated_exact_integration_is_comparable():
    left_binary, right_binary = "d" * 64, "e" * 64
    right = _record("us", 2, 2, right_binary, 4.0)
    right["accounting"]["campaign_status"] = "PASS"
    right["accounting"]["campaign_integration_validity"] = "validated_exact"
    result = compare_records(
        [(_record("de", 1, 1, left_binary, 1.0), [])], [(right, [])],
        {"de": _feature_row("de", left_binary)},
        {"us": _feature_row("us", right_binary)}, _config(),
    )
    assert result["protocol_compatibility"]["status"] == "compatible"
    assert "right_execution_validity" not in result["protocol_compatibility"]["differences"]
    metric = next(row for row in result["metrics"]
                  if row["metric_id"] == "trajectory.route_progress")
    assert metric["estimate_right_minus_left"] == 3.0


def test_invalid_metric_coverage_is_not_emitted_as_zero_or_a_pass():
    left_binary, right_binary = "1" * 64, "2" * 64
    left = [(_record("de", 1, 1, left_binary, 2.0), [])]
    right_record = _record("us", 2, 2, right_binary, 8.0)
    right_record["episode_metrics"]["metrics"][0]["status"] = "unavailable"
    right_record["episode_metrics"]["metrics"][0]["value"] = None
    result = compare_records(left, [(right_record, [])],
                             {"de": _feature_row("de", left_binary)},
                             {"us": _feature_row("us", right_binary)}, _config())
    metric = next(row for row in result["metrics"]
                  if row["metric_id"] == "trajectory.route_progress")
    assert metric["status"] == "incomplete_metric_coverage"
    assert metric["estimate_right_minus_left"] is None
    assert metric["improvement"] is None


def test_conflicting_source_map_identity_fails_explicitly():
    binary = "7" * 64
    row = _feature_row("de", binary)
    record = _record("de", 1, 1, binary, 1.0)
    record["episode_metrics"]["map_context"]["identity"]["source_map_sha256"] = "8" * 64
    with pytest.raises(ValueError, match="map source identity conflicts"):
        compare_records([(record, [])], [], {"de": row}, {}, _config())


def test_same_scenes_under_planner_conditions_use_pe10_paired_summary():
    rows, left, right = {}, [], []
    for index, (before, after) in enumerate(((1.0, 3.0), (2.0, 5.0), (3.0, 4.0))):
        scene = f"paired{index}"
        binary = hashlib.sha256(scene.encode()).hexdigest()
        rows[scene] = _feature_row(scene, binary)
        left.append((_record(scene, index + 1, index + 1, binary, before, planner="SMART"), []))
        right.append((_record(scene, index + 1, index + 1, binary, after, planner="PPO"), []))
    result = compare_records(left, right, rows, rows, _config())
    assert result["protocol_compatibility"]["status"] == "limited"
    assert result["metrics"] == []
    paired = result["paired_condition_diagnostics"]
    progress = next(row for row in paired if row["metric_id"] == "trajectory.route_progress")
    assert progress["dimension"] == "planner"
    assert progress["direction"] == "higher_is_better"
    comparison_row = progress["comparisons"][0]
    assert comparison_row["paired_difference_summary"]["mean"] == pytest.approx(2.0)
    assert comparison_row["improvement"] is True


def test_config_freeze_and_manifest_bytes_are_checked_before_comparison(tmp_path, monkeypatch):
    original = Path("configs/evaluation/geographic_comparison.toml").read_text()
    left_manifest = tmp_path / "left.json"
    right_manifest = tmp_path / "right.json"
    left_rows = {"scene": _feature_row("scene", "1" * 64)}
    right_rows = {"scene": _feature_row("scene", "2" * 64)}
    write_json(left_manifest, {"schema_version": 2, "scenes": list(left_rows.values())})
    write_json(right_manifest, {"schema_version": 2, "scenes": list(right_rows.values())})
    text = original.replace("configs/current_manifest.json", "left.json")
    text = text.replace("runs/post_m9_hardening/us_generation/manifests/expert_idm_source_hold.json",
                        "right.json")
    text = text.replace("316438458c537adfd6b3347a8387844c95ac806d2067365fdc0d72abe2b3992c",
                        sha256(left_manifest))
    text = text.replace("0fbb2f3f4c89617c2d2e79594b65b7a63bd8705a1e62173292c8042ff9d27f25",
                        sha256(right_manifest))
    config_dict = tomllib.loads(text)
    config_dict["freeze"].pop("canonical_sha256")
    frozen = hashlib.sha256(json.dumps(config_dict, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    text = text.replace("7a1f1338da3be1856748e556d127e21d041badf000fd7889ac6078ca9d0ee869", frozen)
    config_path = tmp_path / "comparison.toml"
    config_path.write_text(text)
    monkeypatch.setattr(comparison, "settings", lambda: SimpleNamespace(project=tmp_path))
    loaded, manifests = load_comparison_config(config_path)
    assert len(manifests["right"]["rows"]) == 1

    tampered = read_json(right_manifest)
    tampered["scenes"][0]["binary_sha256"] = "3" * 64
    write_json(right_manifest, tampered)
    with pytest.raises(ValueError, match="frozen manifest is missing or changed"):
        load_comparison_config(config_path)

    config_path.write_text(text.replace('"trajectory.route_progress" = "higher_is_better"',
                                        '"trajectory.route_progress" = "lower_is_better"'))
    with pytest.raises(ValueError, match="frozen selection/config identity changed"):
        load_comparison_config(config_path)


def test_real_config_freeze_references_existing_manifests():
    config, manifests = load_comparison_config()
    assert config["_freeze_sha256"] == "7a1f1338da3be1856748e556d127e21d041badf000fd7889ac6078ca9d0ee869"
    assert len(manifests["left"]["rows"]) == 16
    assert len(manifests["right"]["rows"]) == 2
    assert config["cohorts"]["right"]["status"] == "diagnostic_only"
