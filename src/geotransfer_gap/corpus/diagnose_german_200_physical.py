"""Offline physical/source diagnostics for the frozen German-200 B/C rows.

This producer reads saved ledgers and candidate outputs only. It does not run
conversion, source-map, physical, admission, planner, or review gates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from geotransfer_gap.config import PROJECT_ROOT


B_LEDGER = Path("artifacts/german_200_v1_workstream_b/batch_ledger.json")
C_LEDGER = Path("artifacts/german_200_v1_runs/workstream_c_batch_001/batch_ledger.json")
NEAR_EGO_DIAGNOSTIC_M = 12.0
FOCUS_STATUSES = {"source_physical_rejection", "source_geometry_rejection", "review_blocked"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    return True


def _scene_checks(scene: dict[str, Any], validation: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    objects = scene.get("objects")
    if not isinstance(objects, list):
        objects = []
    ids = [obj.get("id") for obj in objects if isinstance(obj, dict)]
    expected_ids = sorted(map(int, frozen.get("context_actor_ids", [])))
    object_ids = sorted(int(value) for value in ids if isinstance(value, int) and not isinstance(value, bool))
    per_object = []
    for obj in objects:
        if not isinstance(obj, dict):
            per_object.append({"valid": False, "reason": "object_not_mapping"})
            continue
        arrays = {key: obj.get(key) for key in ("position", "velocity", "heading", "valid")}
        lengths = {key: len(value) for key, value in arrays.items() if isinstance(value, list)}
        dims = [obj.get("length"), obj.get("width"), obj.get("height")]
        dims_valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) and float(v) > 0 for v in dims)
        arrays_valid = len(lengths) == 4 and len(set(lengths.values())) == 1
        pos_valid = isinstance(arrays.get("position"), list) and all(
            isinstance(point, dict) and all(k in point and isinstance(point[k], (int, float)) and math.isfinite(float(point[k])) for k in ("x", "y", "z"))
            for point in arrays["position"]
        )
        per_object.append({
            "track_id": obj.get("id"),
            "dimensions_positive_finite": dims_valid,
            "trajectory_arrays_equal_length": arrays_valid,
            "position_coordinates_finite": pos_valid,
            "sample_count": lengths.get("position"),
            "dimension_imputed": obj.get("dimension_imputed"),
        })
    sample_lengths = [item.get("sample_count") for item in per_object if item.get("sample_count") is not None]
    ego_index = (scene.get("metadata") or {}).get("sdc_track_index")
    ego_id = objects[ego_index].get("id") if isinstance(ego_index, int) and 0 <= ego_index < len(objects) and isinstance(objects[ego_index], dict) else None
    checks = {
        "json_top_level_schema": all(key in scene for key in ("name", "scenario_id", "metadata", "objects", "roads", "tl_states")),
        "object_count_matches_validation": len(objects) == validation.get("objects"),
        "object_ids_unique": len(ids) == len(set(ids)),
        "object_ids_match_frozen_context": object_ids == expected_ids,
        "sdc_index_resolves_to_frozen_ego": ego_id == frozen.get("ego_track_id"),
        "all_object_dimensions_positive_finite": all(item.get("dimensions_positive_finite") is True for item in per_object),
        "all_object_arrays_aligned": all(item.get("trajectory_arrays_equal_length") is True for item in per_object),
        "all_objects_share_sample_grid": len(set(sample_lengths)) <= 1 and len(sample_lengths) == len(objects),
        "all_position_coordinates_finite": all(item.get("position_coordinates_finite") is True for item in per_object),
        "all_json_numeric_fields_finite": _finite(scene),
        "road_geometry_present": bool(scene.get("roads")),
    }
    return {"checks": checks, "passed": all(checks.values()), "object_details": per_object}


def _concurrency_metrics(scene: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    objects = scene.get("objects", [])
    step_count = len(objects[0].get("valid", [])) if objects else 0
    moving_ids = set(map(int, frozen.get("moving_track_ids", [])))
    active_by_step = []
    moving_by_step = []
    stationary_by_step = []
    for step in range(step_count):
        active = [obj for obj in objects if isinstance(obj, dict) and obj.get("valid", [])[step] == 1]
        active_by_step.append(len(active))
        moving_by_step.append(sum(int(obj["id"]) in moving_ids for obj in active))
        stationary_by_step.append(sum(int(obj["id"]) not in moving_ids for obj in active))
    def result(values: list[int]) -> dict[str, Any]:
        peak = max(values, default=0)
        return {"mean_per_sampled_step": round(sum(values) / len(values), 3) if values else None,
                "peak_simultaneous": peak, "peak_steps": [i for i, value in enumerate(values) if value == peak] if values else []}
    return {"sampled_step_count": step_count, "active_actors": result(active_by_step),
            "moving_actors": result(moving_by_step), "stationary_actors": result(stationary_by_step)}


def _actor_role(track_id: int, frozen: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    actors = {int(actor["track_id"]): actor for actor in frozen.get("source_context_actors", []) if "track_id" in actor}
    near = {
        int(actor["track_id"]): actor
        for actor in (frozen.get("source_catalog_metadata") or {}).get("catalog_nearest_actors_within_12m", [])
        if "track_id" in actor
    }
    metadata = actors.get(track_id, {})
    role = []
    is_ego = track_id == int(frozen.get("ego_track_id", -1))
    if is_ego:
        role.append("ego")
    designated = frozen.get("source_actor", frozen.get("actor"))
    if isinstance(designated, dict):
        designated = designated.get("track_id", designated.get("id"))
    if designated is not None and int(designated) == track_id:
        role.append("designated_task_actor")
    if not is_ego:
        role.append("near_ego_center_le_12m" if track_id in near else "far_or_not_cataloged_within_12m")
    role.append("moving" if metadata.get("moving") is True else "stationary" if metadata.get("moving") is False else "motion_unknown")
    return {"track_id": track_id, "roles": role, "class": metadata.get("class"),
            "source_path_m": metadata.get("source_window_path_m"),
            "source_max_speed_mps": metadata.get("source_window_max_speed_mps"),
            "nearest_ego_center_distance_m": (near.get(track_id) or {}).get("minimum_timed_center_distance_m")}


def _case_record(batch: str, result: dict[str, Any], root: Path, source_hash_cache: dict[str, str], *, fallback: bool = False) -> dict[str, Any]:
    case_root = Path(result.get("root") or "")
    if not case_root.is_absolute():
        case_root = root / case_root
    frozen = result.get("frozen_row") or {}
    testing = case_root / "testing"
    scene_paths = sorted(testing.glob("ind_*.json"))
    if len(scene_paths) != 1:
        raise ValueError(f"expected one converted scene JSON for {result.get('candidate_id')}, found {len(scene_paths)}")
    scene_path = scene_paths[0]
    physical_path = testing / "physical_source_audit.json"
    validation_path = testing / "validation.json"
    map_path = testing / "map_audit.json"
    physical = read_json(physical_path)
    validation = read_json(validation_path)
    map_audit = read_json(map_path)
    scene = read_json(scene_path)
    tree = result.get("output_tree_sha256") or {}
    checked_paths = {
        "testing/physical_source_audit.json": physical_path,
        "testing/validation.json": validation_path,
        "testing/map_audit.json": map_path,
        "testing/map_000000.bin": testing / "map_000000.bin",
        scene_path.relative_to(case_root).as_posix(): scene_path,
    }
    hash_checks = {}
    for path_key, path in checked_paths.items():
        expected = tree.get(path_key)
        actual = sha256(path) if path.is_file() else None
        if expected is None or actual != expected:
            raise ValueError(f"output-tree hash mismatch or absent binding for {result.get('candidate_id')}:{path_key}")
        hash_checks[path_key] = {"sha256": actual, "matches_output_tree": True}

    pf = (result.get("source_preflight") or {}).get("physical") or {}
    geom = (result.get("source_preflight") or {}).get("geometry") or {}
    context_identity = result.get("context_identity") or {}
    ego_id = int(frozen.get("ego_track_id", -1))
    boundary = physical.get("source_box_boundary_contacts", {}).get(str(ego_id), {})
    overlaps = physical.get("source_box_actor_overlaps") or {}
    details = physical.get("source_box_actor_overlap_details") or {}
    overlap_rows = []
    for pair, data in sorted(overlaps.items()):
        ids = [int(part) for part in pair.split("-")]
        detail = details.get(pair, {})
        overlap_rows.append({
            "pair": pair,
            "track_ids": ids,
            "sampled_overlap_count": data.get("count"),
            "sampled_first_steps": data.get("first_steps", []),
            "maximum_penetration_m": detail.get("maximum_penetration_m"),
            "minimum_ego_box_gap_m": detail.get("minimum_ego_box_gap_m"),
            "within_12m_ego_box_gap_diagnostic": (detail.get("minimum_ego_box_gap_m") is not None and detail.get("minimum_ego_box_gap_m") <= NEAR_EGO_DIAGNOSTIC_M),
            "both_stationary_expert": detail.get("both_stationary_expert"),
            "source_paths_m": detail.get("source_paths_m"),
            "source_max_speeds_mps": detail.get("source_max_speeds_mps"),
            "reviewable_annotation_overlap": detail.get("reviewable_annotation_overlap"),
            "actors": [_actor_role(track_id, frozen, physical) for track_id in ids],
        })

    context = frozen.get("source_context_actors") or []
    moving = [actor for actor in context if actor.get("moving") is True]
    stationary = [actor for actor in context if actor.get("moving") is False]
    n_move, n_stationary = len(moving), len(stationary)
    scene_checks = _scene_checks(scene, validation, frozen)
    simultaneous = _concurrency_metrics(scene, frozen)
    source_map = Path(map_audit.get("source_map") or "")
    source_map_sha = map_audit.get("source_map_sha256")
    source_map_actual = sha256(source_map) if source_map.is_file() else None
    if source_map_actual != source_map_sha:
        raise ValueError(f"source map hash mismatch/unavailable for {result.get('candidate_id')}: {source_map}")
    saved_source_hashes = frozen.get("source_hashes") or {}
    source_paths = saved_source_hashes.get("source_paths") or {}
    source_fields = {
        "background_png": "background_png_sha256", "lanelet2_map": "lanelet2_map_sha256",
        "opendrive_map": "opendrive_map_sha256", "recording_meta_csv": "recording_meta_csv_sha256",
        "tracks_csv": "tracks_csv_sha256", "tracks_meta_csv": "tracks_meta_csv_sha256",
    }
    source_input_hashes = {}
    for name, hash_field in source_fields.items():
        path = Path(source_paths.get(name) or "")
        expected = saved_source_hashes.get(hash_field)
        if not path.is_file() or not isinstance(expected, str):
            raise ValueError(f"missing raw source input/hash for {result.get('candidate_id')}:{name}")
        key = str(path.resolve())
        actual = source_hash_cache.get(key)
        if actual is None:
            actual = sha256(path)
            source_hash_cache[key] = actual
        if actual != expected:
            raise ValueError(f"raw source input hash mismatch for {result.get('candidate_id')}:{name}")
        source_input_hashes[name] = {"path": str(path), "sha256": actual, "matches_frozen_source_hash": True}
    if Path(source_paths["lanelet2_map"]).resolve() != source_map.resolve() or saved_source_hashes.get("lanelet2_map_sha256") != source_map_sha:
        raise ValueError(f"frozen/map-audit source map mismatch for {result.get('candidate_id')}")
    expected_physical_audit_sha = pf.get("physical_audit_sha256")
    overlap_detail_unknown = [pair for pair in overlaps if pair not in details]
    unreviewable = sum(detail.get("reviewable_annotation_overlap") is not True for detail in details.values())
    binary_sha = sha256(testing / "map_000000.bin")
    frozen_ids = sorted(map(int, frozen.get("context_actor_ids", [])))
    frozen_moving_ids = sorted(map(int, frozen.get("moving_track_ids", [])))
    scene_context_matches = sorted(int(obj["id"]) for obj in scene.get("objects", [])) == frozen_ids
    source_context_matches = sorted(int(actor["track_id"]) for actor in context) == frozen_ids
    source_moving_matches = sorted(int(actor["track_id"]) for actor in moving) == frozen_moving_ids
    context_identity_matches = (
        context_identity.get("passed") is True
        and sorted(map(int, context_identity.get("converted_actor_ids", []))) == frozen_ids
        and sorted(map(int, context_identity.get("converted_moving_actor_ids", []))) == frozen_moving_ids
    )
    context_metadata_matches = sorted(context, key=lambda actor: int(actor["track_id"])) == sorted(
        context_identity.get("source_recomputed_actor_metadata", []), key=lambda actor: int(actor["track_id"])
    )
    gate_reasons = result.get("reasons") or []
    expected_boundary_reason = boundary.get("count", 0) > 0
    expected_unreviewable_reason = unreviewable > 0
    gate_reason_matches = (
        ("source_ego_box_boundary_contact" in gate_reasons) == expected_boundary_reason
        and ("unreviewable_source_box_overlap" in gate_reasons) == expected_unreviewable_reason
    ) if result.get("status") == "source_physical_rejection" else True
    physical_concordance = {
        "preflight_audit_sha_matches_file": expected_physical_audit_sha == sha256(physical_path),
        "preflight_overlap_count_matches_file": pf.get("overlap_pair_count") == len(overlaps),
        "preflight_ego_boundary_flag_matches_file": pf.get("ego_boundary_contact") == (boundary.get("count", 0) > 0),
        "preflight_unreviewable_count_matches_file": pf.get("unreviewable_overlap_count") == unreviewable,
        "gate_reasons_match_hash_bound_physical_findings": gate_reason_matches,
        "all_overlap_pairs_have_details": not overlap_detail_unknown,
    }
    if not all(physical_concordance.values()):
        raise ValueError(f"physical gate/audit inconsistency for {result.get('candidate_id')}: {physical_concordance}")
    if not scene_checks["passed"]:
        raise ValueError(f"converted scene structural checks failed for {result.get('candidate_id')}: {scene_checks['checks']}")
    if not (scene_context_matches and source_context_matches and source_moving_matches and context_identity_matches and context_metadata_matches):
        raise ValueError(f"source/converted actor identity mismatch for {result.get('candidate_id')}")
    if validation.get("binary_sha256") != binary_sha or physical.get("binary_sha256") != binary_sha:
        raise ValueError(f"converted binary hash mismatch for {result.get('candidate_id')}")
    if geom.get("map_audit_sha256") != sha256(map_path):
        raise ValueError(f"source-preflight map-audit hash mismatch for {result.get('candidate_id')}")
    outside_map_steps = sorted(item.get("step") for item in map_audit.get("ego_samples_outside_lanelet_polygons", []))
    if outside_map_steps != sorted(geom.get("outside_lanelet_steps", [])):
        raise ValueError(f"map outside-lane evidence mismatch for {result.get('candidate_id')}")
    route_gate_failed = geom.get("occupied_start_to_occupied_goal_reachable") is False
    if route_gate_failed != (result.get("status") == "source_geometry_rejection"):
        raise ValueError(f"source map route verdict/status mismatch for {result.get('candidate_id')}")

    scene_rel = rel(scene_path, root)
    outputs = {
        "scene_json": scene_rel,
        "physical_source_audit": rel(physical_path, root),
        "validation": rel(validation_path, root),
        "map_audit": rel(map_path, root),
        "map_binary": rel(testing / "map_000000.bin", root),
        "overlay": rel(testing / "overlay.png", root) if (testing / "overlay.png").is_file() else None,
        "rule_review_montage": rel(testing / "rule_review_montage.png", root) if (testing / "rule_review_montage.png").is_file() else None,
        "source_image_registration": rel(testing / "source_image_registration.png", root) if (testing / "source_image_registration.png").is_file() else (
            rel(testing / "source_image_registration.json", root) if (testing / "source_image_registration.json").is_file() else None
        ),
    }
    media_hashes = {}
    for name in ("overlay", "rule_review_montage", "source_image_registration"):
        path_text = outputs.get(name)
        if path_text:
            path = root / path_text
            if not path.is_file():
                raise ValueError(f"review media disappeared for {result.get('candidate_id')}: {path_text}")
            actual = sha256(path)
            expected = tree.get(path.relative_to(case_root).as_posix())
            if expected is not None and expected != actual:
                raise ValueError(f"review media output-tree hash mismatch for {result.get('candidate_id')}: {name}")
            media_hashes[name] = {"sha256": actual, "output_tree_sha256": expected}
    return {
        "candidate_id": result.get("candidate_id"), "batch": batch, "fallback": fallback,
        "candidate_run_directory": case_root.name,
        "status": result.get("status"), "recording": frozen.get("recording"), "location": frozen.get("location"),
        "arm": frozen.get("arm"), "family": ",".join(frozen.get("source_task_families") or (["unreviewed_random_source_candidate"] if frozen.get("arm") == "Random100" else ["unknown"])),
        "ego_track_id": ego_id, "designated_task_actor_id": result.get("source_identity", {}).get("actor", frozen.get("actor")),
        "first_frame": frozen.get("first_frame"), "last_frame": frozen.get("last_frame"),
        "source_window_identity_sha256": frozen.get("source_window_identity_sha256"),
        "reason_markers": gate_reasons, "physical_audit_sha256": sha256(physical_path),
        "source_map": map_audit.get("source_map"), "source_map_sha256": source_map_sha,
        "source_map_hash_verified": True, "source_map_lanelet_count": map_audit.get("lanelets"),
        "raw_source_input_hashes": source_input_hashes,
        "route_reachable": geom.get("occupied_start_to_occupied_goal_reachable"),
        "validation_nearest_lane_route_reachable": validation.get("ego_goal_lane_reachable_by_successors"),
        "route_representation_disagreement": geom.get("occupied_start_to_occupied_goal_reachable") != validation.get("ego_goal_lane_reachable_by_successors"),
        "validation_nearest_start_lane": validation.get("ego_start_lane"),
        "validation_nearest_goal_lane": validation.get("ego_goal_lane"),
        "map_audit_ego_start_occupancy": map_audit.get("ego_start_occupancy"),
        "map_audit_ego_goal_occupancy": map_audit.get("ego_goal_occupancy"),
        "outside_lanelet_sample_count": len(map_audit.get("ego_samples_outside_lanelet_polygons", [])),
        "maximum_occupied_heading_error_rad": map_audit.get("ego_max_occupied_heading_error_rad"),
        "source_preflight_route_reachable": geom.get("occupied_start_to_occupied_goal_reachable"),
        "source_preflight_outside_lanelet_steps": geom.get("outside_lanelet_steps"),
        "source_context_actor_count": len(context), "moving_actor_count": n_move, "stationary_actor_count": n_stationary,
        "moving_pair_opportunity_count": n_move * (n_move - 1) // 2,
        "moving_stationary_pair_opportunity_count": n_move * n_stationary,
        "stationary_pair_opportunity_count": n_stationary * (n_stationary - 1) // 2,
        "mean_concurrent_active_actor_count": simultaneous["active_actors"]["mean_per_sampled_step"],
        "peak_concurrent_active_actor_count": simultaneous["active_actors"]["peak_simultaneous"],
        "mean_concurrent_moving_actor_count": simultaneous["moving_actors"]["mean_per_sampled_step"],
        "peak_concurrent_moving_actor_count": simultaneous["moving_actors"]["peak_simultaneous"],
        "mean_concurrent_stationary_actor_count": simultaneous["stationary_actors"]["mean_per_sampled_step"],
        "peak_concurrent_stationary_actor_count": simultaneous["stationary_actors"]["peak_simultaneous"],
        "simultaneous_actor_counts": simultaneous,
        "source_actor_counts_complete": len(context) == len(frozen.get("context_actor_ids", [])),
        "source_context_identity_matches_conversion": True,
        "source_context_moving_ids_match_frozen_list": True,
        "source_actor_metadata_matches_run_recomputation": True,
        "source_context_actors": context,
        "converted_scene": {"path": scene_rel, "sha256": sha256(scene_path), "object_count": len(scene.get("objects", [])),
                            "dimension_imputed_object_count": sum(obj.get("dimension_imputed") is True for obj in scene.get("objects", []) if isinstance(obj, dict)),
                            "checks": scene_checks["checks"]},
        "physical_source": {
            "collision_scale": physical.get("collision_scale"),
            "source_background_pixel_scale_m": physical.get("source_background_pixel_scale_m"),
            "stationary_overlap_tolerance_m": physical.get("stationary_overlap_tolerance_m"),
            "binary_sha256": physical.get("binary_sha256"),
            "ego_boundary_contact_count": boundary.get("count", 0),
            "ego_boundary_contact_samples": boundary.get("first", []),
            "overlap_pair_count": len(overlaps), "unreviewable_pair_count": unreviewable,
            "reviewable_annotation_overlap_pair_count": sum(detail.get("reviewable_annotation_overlap") is True for detail in details.values()),
            "overlap_pair_details": overlap_rows, "physical_gate_concordance": physical_concordance,
        },
        "output_tree_hashes_verified": hash_checks,
        "output_paths": outputs,
        "review_media_hashes": media_hashes,
    }


def _group_metrics(cases: list[dict[str, Any]], field: str) -> dict[str, Any]:
    keys = sorted({str(case[field]) for case in cases})
    result = {}
    metrics = ("source_context_actor_count", "moving_actor_count", "stationary_actor_count", "mean_concurrent_active_actor_count", "peak_concurrent_active_actor_count", "mean_concurrent_moving_actor_count", "peak_concurrent_moving_actor_count", "moving_pair_opportunity_count", "moving_stationary_pair_opportunity_count", "stationary_pair_opportunity_count")
    for key in keys:
        rows = [case for case in cases if str(case[field]) == key]
        result[key] = {"n_primary": len(rows), **{metric: _stable_aggregate(rows, metric) for metric in metrics}}
    return result


def _stable_aggregate(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [row[metric] for row in rows]
    precise_total = math.fsum(values)
    integer_values = all(isinstance(value, int) and not isinstance(value, bool) for value in values)
    total: int | float = sum(values) if integer_values else round(precise_total, 6)
    return {"mean": round(precise_total / len(values), 3), "total": total}


def _mean_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = ("source_context_actor_count", "moving_actor_count", "stationary_actor_count", "mean_concurrent_active_actor_count", "peak_concurrent_active_actor_count", "mean_concurrent_moving_actor_count", "peak_concurrent_moving_actor_count", "moving_pair_opportunity_count", "moving_stationary_pair_opportunity_count", "stationary_pair_opportunity_count")
    return {"n_primary": len(cases), **{metric: _stable_aggregate(cases, metric) for metric in metrics}}


def build(root: Path) -> dict[str, Any]:
    cases = []
    fallback_rows = []
    ledger_evidence = {}
    source_hash_cache: dict[str, str] = {}
    for batch, rel_path in (("B", B_LEDGER), ("C", C_LEDGER)):
        ledger_path = root / rel_path
        ledger = read_json(ledger_path)
        ledger_evidence[batch] = {"path": rel_path.as_posix(), "sha256": sha256(ledger_path)}
        primary = ledger.get("results", [])
        if len(primary) != 24:
            raise ValueError(f"expected 24 {batch} primary rows, got {len(primary)}")
        cases.extend(_case_record(batch, row, root, source_hash_cache) for row in primary)
        if batch == "B":
            for row in primary:
                fallback = (row.get("phase_fallback") or {}).get("result")
                if isinstance(fallback, dict) and fallback.get("status") == "review_blocked":
                    fallback_rows.append(_case_record(batch, fallback, root, source_hash_cache, fallback=True))
    if len(cases) != 48 or len({case["candidate_id"] for case in cases}) != 48:
        raise ValueError("primary rows are not exactly 48 unique cases")
    if len(fallback_rows) != 1:
        raise ValueError(f"expected one retained B fallback review blocker, got {len(fallback_rows)}")

    status_counts = Counter(case["status"] for case in cases)
    focus = [case for case in cases if case["status"] in FOCUS_STATUSES]
    overlap_occurrences = defaultdict(list)
    overlap_flag_counts = Counter()
    role_counts = Counter()
    pair_status_class = defaultdict(Counter)
    map_inventory = defaultdict(int)
    pair_proximity = defaultdict(Counter)
    unreviewable_far_only_cases = 0
    for case in cases + fallback_rows:
        map_inventory[(case["location"], case["source_map"], case["source_map_sha256"])] += 1
        unreviewable_for_case = [pair for pair in case["physical_source"]["overlap_pair_details"] if pair["reviewable_annotation_overlap"] is False]
        if case["status"] == "source_physical_rejection" and unreviewable_for_case and all(pair["minimum_ego_box_gap_m"] is not None and pair["minimum_ego_box_gap_m"] > NEAR_EGO_DIAGNOSTIC_M for pair in unreviewable_for_case):
            unreviewable_far_only_cases += 1
        for overlap in case["physical_source"]["overlap_pair_details"]:
            ids = tuple(sorted(overlap["track_ids"]))
            key = (case["recording"], *ids)
            overlap_occurrences[key].append({"candidate_id": case["candidate_id"], "first_frame": case["first_frame"], "count": overlap["sampled_overlap_count"], "steps": overlap["sampled_first_steps"], "both_stationary_expert": overlap["both_stationary_expert"], "reviewable_annotation_overlap": overlap["reviewable_annotation_overlap"]})
            overlap_flag_counts["both_stationary_expert" if overlap["both_stationary_expert"] else "includes_moving_or_unknown"] += 1
            overlap_flag_counts["reviewable_annotation_overlap" if overlap["reviewable_annotation_overlap"] else "not_reviewable_annotation_overlap"] += 1
            pair_status_class[case["status"]][(
                "reviewable_annotation_overlap" if overlap["reviewable_annotation_overlap"] else "not_reviewable_annotation_overlap",
                "both_stationary_expert" if overlap["both_stationary_expert"] else "includes_moving_or_unknown",
            )] += 1
            pair_proximity[case["status"]][
                f"{'reviewable' if overlap['reviewable_annotation_overlap'] else 'unreviewable'}/"
                f"{'gap_le_12m' if overlap['within_12m_ego_box_gap_diagnostic'] else 'gap_gt_12m_or_unknown'}"
            ] += 1
            for actor in overlap["actors"]:
                for role in actor["roles"]:
                    role_counts[role] += 1
    recurrences = [
        {"recording": key[0], "track_ids": list(key[1:]), "occurrence_count": len(rows),
         "parked_in_all_occurrences": all(row["both_stationary_expert"] is True for row in rows),
         "occurrences": rows}
        for key, rows in sorted(overlap_occurrences.items()) if len(rows) > 1
    ]

    physical_case_rows = [case for case in cases if case["status"] == "source_physical_rejection"]
    physical_totals = {
        "primary_rejections_n": len(physical_case_rows),
        "with_ego_boundary_contact_n": sum(case["physical_source"]["ego_boundary_contact_count"] > 0 for case in physical_case_rows),
        "with_unreviewable_overlap_n": sum(case["physical_source"]["unreviewable_pair_count"] > 0 for case in physical_case_rows),
        "with_boundary_and_unreviewable_overlap_n": sum(case["physical_source"]["ego_boundary_contact_count"] > 0 and case["physical_source"]["unreviewable_pair_count"] > 0 for case in physical_case_rows),
        "pair_only_unreviewable_case_n": sum(case["physical_source"]["ego_boundary_contact_count"] == 0 and case["physical_source"]["unreviewable_pair_count"] > 0 for case in physical_case_rows),
        "overlap_pair_findings_n": sum(case["physical_source"]["overlap_pair_count"] for case in physical_case_rows),
        "unreviewable_overlap_findings_n": sum(case["physical_source"]["unreviewable_pair_count"] for case in physical_case_rows),
        "reviewable_annotation_overlap_findings_n": sum(case["physical_source"]["reviewable_annotation_overlap_pair_count"] for case in physical_case_rows),
    }
    primary_gate_concordance = [case for case in cases if all(case["physical_source"]["physical_gate_concordance"].values())]
    route_disagreements = [case for case in cases if case["route_representation_disagreement"]]
    return {
        "schema_version": 1, "protocol": "german_200_bc_physical_source_forensics_v1", "analysis_only": True,
        "scope": "48 frozen B/C primaries; one retained B fallback only in reviewer index; no population or physical-truth inference",
        "input_ledgers": ledger_evidence,
        "diagnostic_definitions": {
            "near_actor": f"saved nearest-actor catalog threshold <= {NEAR_EGO_DIAGNOSTIC_M:.1f} m timed center distance from ego; diagnostic only, not a corridor or eligibility test",
            "moving": "frozen full-source-context actor metadata moving=true; stationary=moving=false",
            "pair_opportunity": "unordered combinations of moving actors, mixed moving/stationary, or stationary actors in each frozen context; combinatorial exposure counts, not collision probabilities",
            "simultaneous_active_actors": "per-sample counts of converted objects with valid=1; moving/stationary split uses the frozen source movement list; report mean and peak across each shared sample grid",
            "aggregate_precision": "math.fsum; means rounded to 3 decimals, fractional totals rounded to 6 decimals, integer totals exact",
            "overlap_steps": "the saved physical audit's first_steps samples and count; no new physics or collision state inferred",
        },
        "summary": {
            "primary_count": 48, "original_status_counts": dict(sorted(status_counts.items())),
            "source_physical_rejection_metrics": physical_totals,
            "converted_scene_integrity": {
                "valid_scene_json_count": sum(all(case["converted_scene"]["checks"].values()) for case in cases),
                "denominator": 48,
                "converted_object_total": sum(case["converted_scene"]["object_count"] for case in cases),
                "dimension_imputed_object_total": sum(case["converted_scene"]["dimension_imputed_object_count"] for case in cases),
                "physical_collision_scale_values": sorted({case["physical_source"]["collision_scale"] for case in cases}),
            },
            "raw_source_input_integrity": {
                "case_input_groups_verified": sum(all(item["matches_frozen_source_hash"] for item in case["raw_source_input_hashes"].values()) for case in cases),
                "case_denominator": 48,
                "unique_source_files_verified": len(source_hash_cache),
                "full_actor_metadata_recomputation_matches_frozen_context": sum(case["source_actor_metadata_matches_run_recomputation"] for case in cases),
            },
            "review_blocked_primary_count": status_counts["review_blocked"], "retained_fallback_review_blocked_count": len(fallback_rows),
            "geometry_rejection_count": status_counts["source_geometry_rejection"],
            "physical_gate_audit_concordant_primary_count": len(primary_gate_concordance),
            "physical_gate_audit_concordant_denominator": 48,
            "source_map_route_gate_status_concordant_count": 48,
            "nearest_lane_vs_occupied_lane_route_disagreement_count": len(route_disagreements),
            "nearest_lane_vs_occupied_lane_route_disagreements": [
                {"candidate_id": case["candidate_id"], "status": case["status"], "gate_occupied_route_reachable": case["route_reachable"],
                 "validation_nearest_lane_route_reachable": case["validation_nearest_lane_route_reachable"],
                 "nearest_lane_ids": [case["validation_nearest_start_lane"], case["validation_nearest_goal_lane"]],
                 "occupied_start": case["map_audit_ego_start_occupancy"], "occupied_goal": case["map_audit_ego_goal_occupancy"]}
                for case in route_disagreements
            ],
            "overlap_pair_flags_in_48_primaries_and_one_fallback": dict(sorted(overlap_flag_counts.items())),
            "overlap_actor_role_flags_in_48_primaries_and_one_fallback": dict(sorted(role_counts.items())),
            "overlap_pair_classes_by_case_status": {
                status: {f"{reviewability}/{motion}": count for (reviewability, motion), count in sorted(counts.items())}
                for status, counts in sorted(pair_status_class.items())
            },
            "overlap_pair_proximity_by_case_status": {
                status: dict(sorted(counts.items())) for status, counts in sorted(pair_proximity.items())
            },
            "physical_rejection_rows_with_unreviewable_pairs_only_over_12m_ego_box_gap": {
                "count": unreviewable_far_only_cases,
                "denominator": physical_totals["with_unreviewable_overlap_n"],
                "threshold_m": NEAR_EGO_DIAGNOSTIC_M,
                "diagnostic_only": True,
            },
            "map_source_inventory": [
                {"location": location, "source_map": path, "source_map_sha256": digest, "case_rows": count}
                for (location, path, digest), count in sorted(map_inventory.items())
            ],
            "same_recording_recurrent_overlap_pairs": len(recurrences),
            "same_recording_recurrent_pairs_parked_in_all_occurrences": sum(row["parked_in_all_occurrences"] for row in recurrences),
            "same_recording_recurrent_overlap_pair_occurrences": sum(row["occurrence_count"] for row in recurrences),
            "manual_reviews_created": False,
            "source_physical_sensitivity_only": {
                "saved_primary_rejections": len(physical_case_rows),
                "cases_with_an_explicit_ego_boundary_contact_that_persists_if_every_pair_finding_is_cleared": physical_totals["with_ego_boundary_contact_n"],
                "cases_triggered_by_unreviewable_pair_findings": physical_totals["with_unreviewable_overlap_n"],
                "pair_only_cases_that_could_change_source_screen_if_every_unreviewable_pair_were_later_resolved": physical_totals["pair_only_unreviewable_case_n"],
                "interpretation": "This is a bookkeeping bound on the source screen only. Pair review outcomes are unknown; clearing hypothetical pairs would not admit a scene or clear geometry, task, rule, or traffic checks.",
            },
            "by_location": _group_metrics(cases, "location"),
            "by_family": _group_metrics(cases, "family"),
            "by_original_status": _group_metrics(cases, "status"),
            "by_location_and_original_status": {
                str(location): {
                    status: _mean_metrics([case for case in cases if case["location"] == location and case["status"] == status])
                    for status in sorted({case["status"] for case in cases if case["location"] == location})
                }
                for location in sorted({case["location"] for case in cases})
            },
            "by_location_family": {
                f"{location}/{family}": _mean_metrics([case for case in cases if case["location"] == location and case["family"] == family])
                for location in sorted({case["location"] for case in cases})
                for family in sorted({case["family"] for case in cases if case["location"] == location})
            },
        },
        "same_recording_recurrent_overlap_pairs": recurrences,
        "reviewer_index": [
            {
                "candidate_id": case["candidate_id"], "batch": case["batch"], "status": case["status"],
                "recording": case["recording"], "location": case["location"], "family": case["family"],
                "ego_track_id": case["ego_track_id"], "designated_task_actor_id": case["designated_task_actor_id"],
                "first_frame": case["first_frame"], "reason_markers": case["reason_markers"],
                "ego_boundary_contact_samples": case["physical_source"]["ego_boundary_contact_samples"],
                "overlap_pair_details": case["physical_source"]["overlap_pair_details"],
                "output_paths": case["output_paths"], "review_media_hashes": case["review_media_hashes"],
                "existing_b_review_dossier": f"runs/german_200_v1_workstream_b_hardening/v1/reviews/{case['candidate_run_directory'] if case['fallback'] else case['candidate_id']}/review_dossier.md" if case["batch"] == "B" and (root / f"runs/german_200_v1_workstream_b_hardening/v1/reviews/{case['candidate_run_directory'] if case['fallback'] else case['candidate_id']}/review_dossier.md").is_file() else None,
            }
            for case in sorted(focus + fallback_rows, key=lambda row: (row["batch"], row["candidate_id"]))
        ],
        "cases": cases,
        "fallback_review_cases": fallback_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path, required=True, help="new JSON output path; existing paths are refused")
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else args.repo_root / args.output
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    report = build(args.repo_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
