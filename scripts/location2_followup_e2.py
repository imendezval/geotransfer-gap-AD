#!/usr/bin/env python3
"""Offline E2 measurements over authenticated German-200 B1-B9 evidence.

The collector and physical geometry implementation are reused from the E1
reader and existing source diagnostics. This module reads saved outputs only;
it does not execute native gates or change admission/review state.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any


LEDGERS = {
    "B1": "artifacts/german_200_v1_workstream_b/batch_ledger.json",
    "B2": "artifacts/german_200_v1_runs/workstream_c_batch_001/batch_ledger.json",
    "B3": "artifacts/german_200_v1_runs/workstream_d_batch_003_corrected/batch_ledger.json",
    "B4": "artifacts/german_200_v1_runs/workstream_d_batch_004/batch_ledger.json",
    "B5": "artifacts/german_200_v1_runs/overnight_batch_005/batch_ledger.json",
    "B6": "artifacts/german_200_v1_runs/overnight_batch_006/batch_ledger.json",
    "B7": "artifacts/german_200_v1_runs/overnight_batch_007/batch_ledger.json",
    "B8": "artifacts/german_200_v1_runs/overnight_batch_008/batch_ledger.json",
    "B9": "artifacts/german_200_v1_runs/overnight_batch_009/batch_ledger.json",
}
LEDGER_SHA256 = {
    "B1": "4076644465ae3d7a9483499bad9ab28b37a2e5effadc32a43bbba98a36dcdf4a",
    "B2": "a6d36cd0e13375d4236b0a19cf393990e9fc0da1aaa6eb9df8f67e270329ac78",
    "B3": "4f6e3ba0acf1d5eb44ba7fba457414b826344a1740d5411b371beb8da6a710af",
    "B4": "b966b91bead60b76e0cf56edb8b21db5bb949efa9c5e584da8fdc031b76fe3f6",
    "B5": "adf2b34e6975a197fa27d9ef5afb64b49dff4c7d02166f71f65e8e0bc818bd6c",
    "B6": "0cd4f48e5aff8a8ddf7bed23f3c3764826b1a9cc0dba5869326f87f887bac0d3",
    "B7": "adbd93284257bbda5ed301e2337519f6912cf423666a02e463b1d3f1a02fa32e",
    "B8": "787cfe013870208c4ee61151e990d8e4ae01178347dbd7fc949510a6995e09ef",
    "B9": "bd05c277730b7916db5aa68be7a55236c57d09bc089e14c6255a6470bf9ac13c",
}
RECORD_SHA256 = {
    "B1": "ab65e52b09c597c6c663bafe046cb79434ce4f87595c1527fea09e5c80b902fc",
    "B2": "40bafed89a5f1ca33b33856b693a1f92d5aedbd7cd91efe3f39ebecda7650432",
    "B3": "b7f3256a323d4d0b9a5f256346cf55c84297e6b48ada89f5b632f8ebd02ebf6c",
    "B4": "874dcdd62f06e19878a2d964866619d8fe0d8af9b7581edcfa762f0cf527014d",
    "B5": "168db0d1c22ac2983c7dc2b95b8ebc92844f62be40925da74f1cccc461bdf6be",
    "B6": "457ac29929943540f18220c81d797eb8b70f2552883dc0fdd281ee87ea6d464f",
    "B7": "012aedaaff05a54ec5343edf9ac37c9cd002eb717ebdfd08fffc33f5c2aefba9",
    "B8": "aa1250f49289f64f26ed8a122c36448fc51f3d70ba086ea23222d1b5c3d8ae96",
    "B9": "05d898b174bccaebab6a1a804344e69d4eadef082254ad425a713530085c9aa6",
}
REVIEW_INDEX_SHA256 = "32d2a0acb1b031a69423ebc08e4466dbe00f6f402edc761edb0cc866e431b168"
E1_BASELINE_PATH = "runs/german_200_overnight/location2_baseline_correction_run/location2_baseline.json"
E1_BASELINE_SHA256 = "d969088279f96ef188a97d3d6c18d3f6540dd02d9b7e1dc9a653b7b2c69b6593"
HISTORY = "artifacts/german_200_v1_runs/retention_v1/retention_history.jsonl"
EXPECTED_B1_B9_PREFIX_SHA256 = "27df52d6410f141c903e38a389e6dc746d13530241c7e39973ec810ec3e533d9"
EXPECTED_B1_B4_PREFIX_SHA256 = "860c5a5b1a9e3942fa43be7f1d8c49d738d97139c4ee99ee38e437d3f88d71a2"
EXPECTED_B9_ACCEPTED_RECORD_SHA256 = "05d898b174bccaebab6a1a804344e69d4eadef082254ad425a713530085c9aa6"
E1_PATH = "scripts/location2_baseline.py"
PHYSICAL_PRODUCER = "src/geotransfer_gap/corpus/diagnose_german_200_physical.py"
PHYSICAL_PRODUCER_SHA256 = "e53a1733f8732043442cbfeccf1d0e14c6eaa650773c6394589029c8e6d36abb"
E2_PATH = "scripts/location2_followup_e2.py"
PRIMARY_ROWS = {batch: (8 if batch == "B9" else 24) for batch in LEDGERS}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_e1(source_root: Path):
    spec = importlib.util.spec_from_file_location("location2_baseline_e1", source_root / E1_PATH)
    require(spec is not None and spec.loader is not None, "cannot import E1 collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_history(root: Path, e1: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = root / HISTORY
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    require(len(lines) >= 9, "retention history has fewer than nine records")
    records = [json.loads(line) for line in lines[:9]]
    require([r.get("batch_label") for r in records] == list(LEDGERS), "B1-B9 prefix order changed")
    require(hashlib.sha256(b"".join(lines[:4])).hexdigest() == EXPECTED_B1_B4_PREFIX_SHA256,
            "pinned B1-B4 history prefix changed")
    prefix_sha = hashlib.sha256(b"".join(lines[:9])).hexdigest()
    require(prefix_sha == EXPECTED_B1_B9_PREFIX_SHA256, "accepted B1-B9 history prefix changed")
    tip_path = root / "artifacts/german_200_v1_runs/retention_v1/retention_tip.json"
    tip = read_json(tip_path)
    require(tip.get("batch_number") == 9 and tip.get("record_sha256") == EXPECTED_B9_ACCEPTED_RECORD_SHA256,
            "retention tip does not identify accepted B9")
    prior = None
    checks = {}
    for record in records:
        label = record["batch_label"]
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        require(actual == record["record_sha256"] == RECORD_SHA256[label], f"retention record hash mismatch: {label}")
        require(record.get("previous_record_sha256") == prior, f"retention chain link mismatch: {label}")
        prior = actual
        if label == "B9":
            require(actual == EXPECTED_B9_ACCEPTED_RECORD_SHA256, "B9 accepted digest mismatch")
        ledger_path = root / LEDGERS[label]
        require(sha256(ledger_path) == record["ledger_sha256"] == LEDGER_SHA256[label], f"ledger digest mismatch: {label}")
        # Verify every byte-level chain reference present in the historical record.
        refs = {
            "queue_path": "queue_sha256", "source_queue_path": "source_queue_sha256",
            "queue_receipt_path": "queue_receipt_sha256", "retention_plan_path": "retention_plan_sha256",
            "review_manifest_path": "review_manifest_sha256", "owner_path": "owner_sha256",
            "run_report_path": "run_report_sha256", "summary_path": "summary_sha256",
        }
        verified_refs = {}
        for path_field, digest_field in refs.items():
            rel = record.get(path_field)
            expected = record.get(digest_field)
            if rel is None and expected is None:
                continue
            if rel is None:
                # B1-B4 records name manifest in the batch output rather than the record.
                if path_field == "review_manifest_path":
                    rel = str(Path(record["output_root"]).relative_to(root) / "human_review_manifest.json")
                elif path_field == "owner_path":
                    rel = str(Path(record["output_root"]).relative_to(root) / "batch_owner.json")
                elif path_field == "run_report_path":
                    rel = str(Path(record["output_root"]).relative_to(root) / "batch_run_report.json")
                elif path_field == "summary_path":
                    rel = str(Path(record["output_root"]).relative_to(root) / "batch_summary.json")
                else:
                    raise ValueError(f"missing path for digest {digest_field} in {label}")
            target = root / rel
            actual_ref = sha256(target) if target.is_file() else None
            require(actual_ref == expected, f"{label} evidence ref mismatch: {path_field}")
            verified_refs[path_field] = {"path": rel, "sha256": actual_ref}
        rows = read_json(ledger_path).get("results", [])
        require(len(rows) == PRIMARY_ROWS[label], f"{label} primary row count mismatch")
        identities = [(row.get("frozen_row") or {}).get("source_window_identity_sha256") for row in rows]
        require(identities == record.get("ordered_primary_identity_sha256"), f"ordered identities mismatch: {label}")
        checks[label] = {
            "record_sha256": actual, "ledger_path": LEDGERS[label], "ledger_sha256": sha256(ledger_path),
            "primary_rows": len(rows), "ordered_primary_identities_match": True,
            "verified_record_references": verified_refs,
        }
    return records, {
        "path": HISTORY, "authenticated_record_count": 9, "b1_b4_prefix_sha256": EXPECTED_B1_B4_PREFIX_SHA256,
        "b1_b9_prefix_sha256": prefix_sha, "batch_checks": checks,
        "retention_tip": {"path": str(tip_path.relative_to(root)), "sha256": sha256(tip_path), "batch_number": 9,
                          "record_sha256": EXPECTED_B9_ACCEPTED_RECORD_SHA256},
        "later_records_after_b9_excluded": [r.get("batch_label") for r in (json.loads(x) for x in lines[9:])],
    }


def grouped_summary(cases: list[dict[str, Any]], group_fields: tuple[str, ...]) -> dict[str, Any]:
    def dist(values: list[float]) -> dict[str, Any]:
        ordered = sorted(float(v) for v in values)
        if not ordered:
            return {"n": 0, "mean": None, "min": None, "q1": None, "median": None, "q3": None, "max": None}
        def quantile(q: float) -> float:
            position = (len(ordered) - 1) * q
            low, high = math.floor(position), math.ceil(position)
            if low == high:
                return ordered[low]
            return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
        return {"n": len(ordered), "mean": round(math.fsum(ordered) / len(ordered), 3),
                "min": ordered[0], "q1": round(quantile(0.25), 3), "median": round(quantile(0.5), 3),
                "q3": round(quantile(0.75), 3), "max": ordered[-1]}
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for case in cases:
        for field in group_fields:
            groups[(field, str(case[field]))].append(case)
    out = {}
    for (field, key), rows in sorted(groups.items()):
        status = collections.Counter(c["status"] for c in rows)
        boundary = sum(c["physical_source"]["ego_boundary_contact_count"] > 0 for c in rows)
        pair_findings = [p for c in rows for p in c["physical_source"]["overlap_pair_details"]]
        moving_pairs = collections.Counter(p["pair_motion_class"] for p in pair_findings)
        pair_roles = collections.Counter(p.get("pair_role_class", "unknown") for p in pair_findings)
        out[f"{field}:{key}"] = {
            "primary_denominator": len(rows), "status_counts": dict(sorted(status.items())),
            "ego_boundary_contact_cases_n": boundary,
            "ego_boundary_contact_cases_denominator": len(rows),
            "overlap_pair_findings_n": len(pair_findings), "pair_motion_class_counts": dict(sorted(moving_pairs.items())),
            "pair_role_class_counts": dict(sorted(pair_roles.items())),
            "unreviewable_pair_findings_n": sum(p["reviewable_annotation_overlap"] is not True for p in pair_findings),
            "maximum_penetration_m": {
                "n": len([p for p in pair_findings if p.get("maximum_penetration_m") is not None]),
                "median": round(statistics.median([p["maximum_penetration_m"] for p in pair_findings if p.get("maximum_penetration_m") is not None]), 6)
                if any(p.get("maximum_penetration_m") is not None for p in pair_findings) else None,
                "max": max([p["maximum_penetration_m"] for p in pair_findings if p.get("maximum_penetration_m") is not None], default=None),
            },
            "sampled_overlap_occupancy_seconds": {
                "n": len([p for p in pair_findings if p.get("sampled_occupancy_seconds_at_source_rate") is not None]),
                "median": round(statistics.median([p["sampled_occupancy_seconds_at_source_rate"] for p in pair_findings if p.get("sampled_occupancy_seconds_at_source_rate") is not None]), 3)
                if any(p.get("sampled_occupancy_seconds_at_source_rate") is not None for p in pair_findings) else None,
            },
            "contiguous_overlap_elapsed_seconds_when_observable": {
                "n": len([p for p in pair_findings if p.get("contiguous_overlap_span_seconds") is not None]),
                "median": round(statistics.median([p["contiguous_overlap_span_seconds"] for p in pair_findings if p.get("contiguous_overlap_span_seconds") is not None]), 3)
                if any(p.get("contiguous_overlap_span_seconds") is not None for p in pair_findings) else None,
            },
            "mean_moving_actors": round(statistics.mean(c["moving_actor_count"] for c in rows), 3),
            "mean_stationary_actors": round(statistics.mean(c["stationary_actor_count"] for c in rows), 3),
            "mean_moving_stationary_pair_opportunities": round(statistics.mean(c["moving_stationary_pair_opportunity_count"] for c in rows), 3),
            "mean_stationary_pair_opportunities": round(statistics.mean(c["stationary_pair_opportunity_count"] for c in rows), 3),
            "complexity_distributions": {
                metric: dist([c[metric] for c in rows]) for metric in (
                    "source_context_actor_count", "moving_actor_count", "stationary_actor_count",
                    "moving_pair_opportunity_count", "moving_stationary_pair_opportunity_count",
                    "stationary_pair_opportunity_count", "mean_concurrent_active_actor_count",
                    "peak_concurrent_active_actor_count"
                )
            },
        }
    return out


def trace_evidence(root: Path, case: dict[str, Any], e1: Any) -> dict[str, Any]:
    case_root = Path(case["candidate_root"])
    testing = case_root / "testing"
    traces = {}
    for mode in ("expert", "idm", "hybrid_startup"):
        name = f"lifecycle_trace_{mode}.json"
        data, path = e1.output_json(case_root, name)
        if data is None or path is None:
            traces[mode] = {"present": False}
            continue
        summary = e1.trace_summary(root, case, name)
        traces[mode] = {
            "present": True, "sha256": summary["sha256"], "path": str(path.relative_to(root)),
            "observed_steps": summary.get("observed_steps"), "episode_steps": summary.get("episode_steps"),
            "justified_goal_terminal_step": summary.get("justified_goal_terminal_step"),
            "first_source_valid_losses": summary.get("first_source_valid_losses"),
            "collision_actor_event_n": len(summary.get("collision_actor_events", [])),
        }
    spawn_path = testing / "spawn_evaluation_validation.json"
    if spawn_path.is_file():
        spawn = read_json(spawn_path)
        modes = spawn.get("modes", {})
        traces["structured_spawn_report"] = {
            "present": True, "path": str(spawn_path.relative_to(root)), "sha256": sha256(spawn_path),
            "report_passed": spawn.get("passed"), "binary_sha256": spawn.get("binary_sha256"),
            "modes": {
                mode: {
                    "birth_passed": info.get("birth_passed"), "max_birth_position_error_m": info.get("max_birth_position_error_m"),
                    "max_birth_heading_error_rad": info.get("max_birth_heading_error_rad"),
                    "max_birth_velocity_error_mps": info.get("max_birth_velocity_error_mps"),
                    "late_tracks": info.get("late_tracks"), "first_step_displacement_m": info.get("first_step_displacement_m"),
                    "observed_steps": info.get("observed_steps"),
                    "justified_goal_terminal_step": info.get("justified_goal_terminal_step"),
                    "post_goal_untested_birth_track_ids": info.get("post_goal_untested_birth_track_ids"),
                } for mode, info in modes.items()
            },
        }
    else:
        traces["structured_spawn_report"] = {"present": False}
    spawn_modes = (traces.get("structured_spawn_report") or {}).get("modes") or {}
    birth_ids = sorted({str(track_id) for info in spawn_modes.values() for track_id in (info.get("late_tracks") or {})})
    birth_trace_samples = {}
    for mode in ("expert", "idm", "hybrid_startup"):
        trace_path = testing / f"lifecycle_trace_{mode}.json"
        if not trace_path.is_file():
            continue
        timeline = (read_json(trace_path).get("timeline") or {})
        per_track = {}
        for track_id in birth_ids:
            birth_step = None
            for spawn_mode in spawn_modes.values():
                late_track = (spawn_mode.get("late_tracks") or {}).get(track_id)
                if late_track is not None:
                    birth_step = late_track.get("birth_step")
                    break
            samples = timeline.get(track_id) or []
            steps = {birth_step, birth_step + 1} if isinstance(birth_step, int) else set()
            selected = [sample for sample in samples if sample.get("step") in steps]
            per_track[track_id] = {
                "reported_birth_step": birth_step,
                "saved_timeline_samples": [{key: sample.get(key) for key in (
                    "step", "source_valid", "present", "source_local_position", "position_error_m",
                    "heading_error_rad", "sim_speed_mps"
                )} for sample in selected],
            }
        birth_trace_samples[mode] = per_track
    traces["saved_late_birth_trace_samples"] = birth_trace_samples
    hybrid_path = testing / "admission_hybrid_startup.json"
    if hybrid_path.is_file():
        hybrid = read_json(hybrid_path)
        checks = hybrid.get("checks") or {}
        traces["hybrid_admission"] = {
            "present": True, "path": str(hybrid_path.relative_to(root)), "sha256": sha256(hybrid_path),
            "technical_admitted": hybrid.get("technical_admitted"), "research_admitted": hybrid.get("research_admitted"),
            "checks": checks, "failed_checks": sorted(k for k, v in checks.items() if v is False),
            "semantic_support_unknown_or_pending": any("semantic" in k and v is False for k, v in checks.items()),
            "counterfactual_lifecycle": (hybrid.get("details") or {}).get("counterfactual_lifecycle"),
            "hybrid_lifecycle": (hybrid.get("details") or {}).get("hybrid_lifecycle"),
            "source_box_overlaps_resolved": (hybrid.get("details") or {}).get("source_box_overlaps_resolved"),
            "diagnostic_findings": hybrid.get("diagnostic_findings"),
            "exclusion_reasons": hybrid.get("exclusion_reasons"),
        }
    else:
        traces["hybrid_admission"] = {"present": False}
    return traces


def pair_recurrences(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[tuple[int, tuple[int, int]], list[dict[str, Any]]] = collections.defaultdict(list)
    for case in cases:
        if int(case["location"]) != 2:
            continue
        for pair in case["physical_source"]["overlap_pair_details"]:
            key = (int(case["recording"]), tuple(sorted(map(int, pair["track_ids"]))))
            by_id[key].append({
                "candidate_id": case["candidate_id"], "batch": case["batch"], "status": case["status"],
                "first_frame": case["first_frame"], "pair_motion_class": pair["pair_motion_class"],
                "sampled_overlap_count": pair["sampled_overlap_count"], "sampled_first_steps": pair["sampled_first_steps"],
                "sampled_occupancy_seconds_at_source_rate": pair.get("sampled_occupancy_seconds_at_source_rate"),
                "contiguous_overlap_span_seconds": pair.get("contiguous_overlap_span_seconds"),
                "maximum_penetration_m": pair["maximum_penetration_m"],
                "reviewable_annotation_overlap": pair["reviewable_annotation_overlap"],
                "candidate_root": case["candidate_root"], "output_paths": case["output_paths"],
                "raw_source_input_hashes": case["raw_source_input_hashes"], "scene": case["converted_scene"],
            })
    return [
        {"recording": recording, "track_ids": list(track_ids), "primary_occurrences": len(rows),
         "occurrences": rows, "stationary_in_all_occurrences": all(r["pair_motion_class"] == "stationary_and_stationary" for r in rows)}
        for (recording, track_ids), rows in sorted(by_id.items()) if len(rows) > 1
    ]


def interpolate_rows(rows: list[dict[str, str]], frame: float, meta: dict[str, str]) -> dict[str, Any]:
    import numpy as np
    rows = sorted(rows, key=lambda r: int(r["frame"]))
    src_frames = np.array([int(r["frame"]) for r in rows])
    at = lambda key: float(np.interp(frame, src_frames, [float(r[key]) for r in rows]))
    heading = np.unwrap(np.deg2rad([float(r["heading"]) for r in rows]))
    yaw = float(np.interp(frame, src_frames, heading))
    return {"x": at("xCenter"), "y": at("yCenter"), "heading": yaw,
            "length": float(meta["length"]), "width": float(meta["width"])}


def direct_box_comparison(root: Path, chosen: dict[str, Any], e1: Any) -> dict[str, Any]:
    from geotransfer_gap.validation import audit_physical_source as geom
    case_root = Path(chosen["candidate_root"])
    scene_path = root / chosen["output_paths"]["scene_json"]
    scene = read_json(scene_path)
    track_path = Path(chosen["raw_source_input_hashes"]["tracks_csv"]["path"])
    meta_path = Path(chosen["raw_source_input_hashes"]["tracks_meta_csv"]["path"])
    ids = list(map(int, chosen["track_ids"]))
    first = int(chosen["first_frame"])
    sample_step = 0
    if 0 not in (chosen["sampled_first_steps"] or []):
        sample_step = int(min(chosen["sampled_first_steps"]))
    source_frame = first + 2.5 * sample_step
    target_rows: dict[int, list[dict[str, str]]] = {track_id: [] for track_id in ids}
    with track_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            try:
                tid, frame = int(row["trackId"]), int(row["frame"])
            except (TypeError, ValueError):
                continue
            if tid in target_rows and first <= frame <= int(chosen["last_frame"]):
                target_rows[tid].append(row)
    metadata = {}
    with meta_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            try:
                tid = int(row["trackId"])
            except (TypeError, ValueError):
                continue
            if tid in ids:
                metadata[tid] = row
    scene_by_id = {int(obj["id"]): obj for obj in scene.get("objects", [])}
    result = {"candidate_id": chosen["candidate_id"], "recording": chosen["recording"], "track_ids": ids,
              "pair_motion_class": chosen["pair_motion_class"], "scene_step": sample_step,
              "recurrent_identity_primary_occurrences": chosen.get("recurrent_identity_primary_occurrences"),
              "source_frame_interpolated_at": source_frame, "source_tracks_sha256": sha256(track_path),
              "source_tracks_meta_sha256": sha256(meta_path), "converted_scene_sha256": sha256(scene_path),
              "direct_actor_measurements": []}
    raw_boxes, converted_boxes = {}, {}
    for track_id in ids:
        source = interpolate_rows(target_rows[track_id], source_frame, metadata[track_id])
        converted = scene_by_id[track_id]
        converted_pos = converted["position"][sample_step]
        converted_yaw = float(converted["heading"][sample_step])
        item = {
            "track_id": track_id, "source_center_xy_m": [source["x"], source["y"]],
            "converted_center_xy_m": [converted_pos["x"], converted_pos["y"]],
            "center_delta_m": round(math.dist((source["x"], source["y"]), (converted_pos["x"], converted_pos["y"])), 9),
            "source_heading_rad": source["heading"], "converted_heading_rad": converted_yaw,
            "wrapped_heading_delta_rad": round(math.atan2(math.sin(source["heading"] - converted_yaw), math.cos(source["heading"] - converted_yaw)), 9),
            "source_dimensions_m": [source["length"], source["width"]],
            "converted_dimensions_m": [converted["length"], converted["width"]],
            "dimension_delta_m": [round(source["length"] - converted["length"], 9), round(source["width"] - converted["width"], 9)],
            "source_raw_frame_row_count": len(target_rows[track_id]),
        }
        result["direct_actor_measurements"].append(item)
        raw_boxes[track_id] = {"position": [{"x": source["x"], "y": source["y"], "z": 0.0}], "heading": [source["heading"]],
                               "length": source["length"], "width": source["width"]}
        converted_boxes[track_id] = {"position": [converted_pos], "heading": [converted_yaw],
                                     "length": converted["length"], "width": converted["width"]}
    a, b = ids
    def relation(boxes):
        ac, bc = geom.corners(boxes[a], 0), geom.corners(boxes[b], 0)
        overlaps = geom.boxes_overlap(boxes[a], boxes[b], 0)
        return {"overlaps": overlaps, "penetration_m": round(geom.overlap_penetration_m(boxes[a], boxes[b], 0), 9) if overlaps else 0.0,
                "oriented_box_gap_m": round(geom.polygon_gap(ac, bc), 9)}
    result["source_recorded_geometry"] = relation(raw_boxes)
    result["converted_scene_geometry"] = relation(converted_boxes)
    result["interpretation"] = "direct source rows/meta and hash-bound converted scene at one shared source-time sample; box relations are recomputed with existing audit geometry helpers"
    return result


def route_connectivity(case: dict[str, Any], root: Path) -> dict[str, Any]:
    scene = read_json(root / case["output_paths"]["scene_json"])
    lanes = {int(r["id"]): sorted(map(int, r.get("exit_lanes", []))) for r in scene.get("roads", [])
             if r.get("type") == "lane" and isinstance(r.get("id"), int)}
    def path(start: int, targets: set[int]) -> list[int] | None:
        todo = collections.deque([(start, [start])])
        seen = {start}
        while todo:
            here, route = todo.popleft()
            if here in targets:
                return route
            for nxt in lanes.get(here, []):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append((nxt, route + [nxt]))
        return None
    start = int(case["validation_nearest_start_lane"])
    nearest_goal = int(case["validation_nearest_goal_lane"])
    occ_start = set(map(int, (case["map_audit_ego_start_occupancy"] or {}).get("occupied_lanelets", [])))
    occ_goal = set(map(int, (case["map_audit_ego_goal_occupancy"] or {}).get("occupied_lanelets", [])))
    nearest_path = path(start, {nearest_goal})
    occupied_paths = {str(a): path(a, occ_goal) for a in sorted(occ_start)}
    return {
        "candidate_id": case["candidate_id"], "map_path": case["source_map"], "map_sha256": case["source_map_sha256"],
        "converted_scene_sha256": case["converted_scene"]["sha256"],
        "occupied_start_lanelets": sorted(occ_start), "occupied_goal_lanelets": sorted(occ_goal),
        "nearest_centerline_start_lane": start, "nearest_centerline_goal_lane": nearest_goal,
        "nearest_centerline_directed_path": nearest_path,
        "occupied_start_to_occupied_goal_paths": occupied_paths,
        "route_reachable_from_source_preflight": case["route_reachable"],
        "route_reachable_from_nearest_centerline_validation": case["validation_nearest_lane_route_reachable"],
        "note": "directed connectivity recomputed from saved converted lane exit_lanes, whose scene is output-tree hash bound to the pinned Lanelet2 map"
    }


def compact_case(case: dict[str, Any]) -> dict[str, Any]:
    physical = case["physical_source"]
    return {
        "source_window_identity_sha256": case["source_window_identity_sha256"],
        "candidate_id": case["candidate_id"], "batch": case["batch"], "queue_index": case.get("queue_index"),
        "location": case["location"], "recording": case["recording"], "arm": case["arm"],
        "family": case["family"], "source_task_families": case.get("source_task_families"),
        "ego_track_id": case["ego_track_id"], "designated_task_actor_id": case["designated_task_actor_id"],
        "first_frame": case["first_frame"], "last_frame": case["last_frame"], "status": case["status"],
        "reason_markers": case["reason_markers"], "source_map": case["source_map"],
        "source_map_sha256": case["source_map_sha256"], "route_reachable": case["route_reachable"],
        "validation_nearest_lane_route_reachable": case["validation_nearest_lane_route_reachable"],
        "route_representation_disagreement": case["route_representation_disagreement"],
        "validation_nearest_start_lane": case["validation_nearest_start_lane"],
        "validation_nearest_goal_lane": case["validation_nearest_goal_lane"],
        "map_audit_ego_start_occupancy": case["map_audit_ego_start_occupancy"],
        "map_audit_ego_goal_occupancy": case["map_audit_ego_goal_occupancy"],
        "outside_lanelet_sample_count": case["outside_lanelet_sample_count"],
        "source_context_actor_count": case["source_context_actor_count"],
        "moving_actor_count": case["moving_actor_count"], "stationary_actor_count": case["stationary_actor_count"],
        "moving_pair_opportunity_count": case["moving_pair_opportunity_count"],
        "moving_stationary_pair_opportunity_count": case["moving_stationary_pair_opportunity_count"],
        "stationary_pair_opportunity_count": case["stationary_pair_opportunity_count"],
        "mean_concurrent_active_actor_count": case["mean_concurrent_active_actor_count"],
        "peak_concurrent_active_actor_count": case["peak_concurrent_active_actor_count"],
        "ego_boundary_contact_count": physical["ego_boundary_contact_count"],
        "unreviewable_pair_count": physical["unreviewable_pair_count"],
        "overlap_pairs": [{k: pair.get(k) for k in (
            "pair", "track_ids", "pair_motion_class", "pair_role_class", "sampled_overlap_count",
            "sampled_first_steps", "sampled_occupancy_seconds_at_source_rate", "contiguous_overlap_span_seconds",
            "maximum_penetration_m", "minimum_ego_box_gap_m",
            "both_stationary_expert", "reviewable_annotation_overlap", "actors"
        )} for pair in physical["overlap_pair_details"]],
        "source_hashes": case["raw_source_input_hashes"], "physical_audit_sha256": case["physical_audit_sha256"],
        "converted_scene": case["converted_scene"], "output_tree_hashes_verified": case["output_tree_hashes_verified"],
        "output_paths": case["output_paths"], "saved_evidence": case["e2_saved_evidence"],
        "ego_task_proximity": case.get("ego_task_proximity"),
        "semantic_applicability": case.get("semantic_applicability"),
        "saved_hybrid_admission": case.get("saved_hybrid_admission"),
    }


def compare_e1_stable_baseline(root: Path, cases: list[dict[str, Any]], e1: Any, review_index: dict[str, Any]) -> dict[str, Any]:
    path = root / E1_BASELINE_PATH
    require(sha256(path) == E1_BASELINE_SHA256, "preserved E1 B1-B4 artifact hash changed")
    old = read_json(path)
    old_cases = old["primary_cases"]
    new_cases = [c for c in cases if c["batch"] in {"B1", "B2", "B3", "B4"} and int(c["location"]) == 2]
    require(len(new_cases) == 57 and len(old_cases) == 57, "E1 stable comparison denominator is not 57")
    require({c["source_window_identity_sha256"] for c in new_cases} == set(old_cases), "E1 primary identities differ from reread B1-B4 output")
    case_fields = (
        "candidate_id", "batch", "fallback", "candidate_run_directory", "ledger_status", "recording", "location",
        "arm", "family", "ego_track_id", "designated_task_actor_id", "first_frame", "last_frame",
        "source_window_identity_sha256", "reason_markers", "physical_audit_sha256", "source_map", "source_map_sha256",
        "source_map_hash_verified", "source_map_lanelet_count", "raw_source_input_hashes", "route_reachable",
        "validation_nearest_lane_route_reachable", "route_representation_disagreement", "validation_nearest_start_lane",
        "validation_nearest_goal_lane", "map_audit_ego_start_occupancy", "map_audit_ego_goal_occupancy",
        "outside_lanelet_sample_count", "source_context_actor_count", "moving_actor_count", "stationary_actor_count",
        "moving_pair_opportunity_count", "moving_stationary_pair_opportunity_count", "stationary_pair_opportunity_count",
        "source_context_actors", "converted_scene", "physical_source", "output_tree_hashes_verified", "output_paths",
        "source_task_families", "technical_gate", "semantic_applicability", "ego_task_proximity",
        "saved_hybrid_admission", "native_lifecycle", "review_index_reconciliation",
    )
    case_differences = []
    for case in new_cases:
        prior_case = old_cases[case["source_window_identity_sha256"]]
        for key in case_fields:
            if prior_case.get(key) != case.get(key):
                case_differences.append({"identity": case["source_window_identity_sha256"], "field": key})
    require(not case_differences, f"E1 stable case fields differ: {case_differences[:12]}")
    # Recompute each stable summary section with the existing E1 summary function.
    old_fallbacks = [{"batch": f["batch"], "status": f["status"]}
                     for f in old.get("fallback_attempts_location_2_separate", [])]
    old_reconciliation = old["summary"]["reconciliation"]
    a4_repro, _ = e1.collect_repro(root)
    recomputed = e1.make_summary(new_cases, old_fallbacks, old_reconciliation, review_index, a4_repro)
    stable_sections = (
        "primary_denominator", "fallback_denominator_separate", "primary_status_counts",
        "primary_status_counts_by_batch", "primary_arm_denominators", "primary_family_arm_denominators",
        "primary_recording_denominators", "primary_outcomes_by_arm", "primary_outcomes_by_family_arm",
        "primary_outcomes_by_recording", "source_geometry_route", "ego_task_proximity",
        "physical_blockers", "pair_identity_recurrence", "complexity_distributions",
        "native_hybrid_lifecycle", "semantic_support", "fallback_attempts_separate",
        "review_index_l2_entries_including_fallbacks", "review_index_l2_primary_entries",
        "review_index_l2_fallback_entries", "reproduction", "reconciliation",
    )
    mismatches = [key for key in stable_sections if recomputed.get(key) != old["summary"].get(key)]
    require(not mismatches, f"B1-B4 stable E1 summary sections changed: {mismatches}")
    packed = json.dumps({key: recomputed[key] for key in stable_sections}, sort_keys=True, separators=(",", ":")).encode()
    return {
        "preserved_e1_artifact_path": E1_BASELINE_PATH, "preserved_e1_artifact_sha256": E1_BASELINE_SHA256,
        "location2_primary_identity_denominator": len(new_cases),
        "identity_keys_match": True, "stable_summary_sections_equal": list(stable_sections),
        "stable_primary_case_fields_equal": list(case_fields), "primary_case_field_differences": [],
        "stable_summary_mismatches": [], "recomputed_stable_summary_sha256": hashlib.sha256(packed).hexdigest(),
        "stable_sections_compared_byte_normalized": True,
    }


def make_markdown(report: dict[str, Any], output_sha: str, command: str) -> str:
    s = report["summary"]
    primary_by_location = s["primary_denominators_by_location"]
    lines = [
        "# Location-2 E2 offline follow-up", "",
        "This is a saved-evidence measurement report over the authenticated B1–B9 prefix. It does not run native gates, alter screening, change thresholds, or request a review. Later history is excluded.", "",
        f"Machine evidence: `location2_followup_e2.json` SHA-256 `{output_sha}`.",
        f"Reproduction command: `{command}`", "",
        "## Denominators and screening outcomes", "",
        f"The nine accepted ledgers contain {s['all_site_primary_denominator']} primary rows and {s['location2_primary_denominator']} location-2 rows. {s['fallback_denominator_all_sites_separate']} fallback attempts are separate from those primary denominators ({s['location2_fallback_denominator']} at L2); L2 rows by batch: " + ", ".join(f"{b} {n}" for b,n in s['location2_by_batch'].items()) + ".",
        "",
        "| Location | Primary rows | Physical rejection | Geometry rejection | Review blocked | Technical rejection | Awaiting review |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for loc, entry in primary_by_location.items():
        st = entry["status_counts"]
        lines.append(f"| {loc} | {entry['denominator']} | {st.get('source_physical_rejection',0)} | {st.get('source_geometry_rejection',0)} | {st.get('review_blocked',0)} | {st.get('technical_rejection',0)+st.get('source_technical_rejection',0)} | {st.get('awaiting_human_review',0)} |")
    lines += ["", "Location groups are descriptive for these selected batches. Differences can reflect batch composition and do not estimate site populations.", "",
        "## Physical and complexity measurements", "",
              "Boundary-contact and overlap results below count saved source-geometry findings. A non-reviewable pair marks the saved annotation criterion as unmet; it is not a human physical adjudication. Pair recurrence uses recording plus sorted track IDs, so repeated windows are not independent events.", "",
        "| Location | N | Boundary-contact cases / N | Pair findings | Non-reviewable | Moving / stationary pair counts | Mean moving actors | Median stationary actors |",
        "|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    grouped = s["grouped_location_batch_arm_family_recording_status"]
    for loc in primary_by_location:
        metrics = grouped[f"location:{loc}"]
        d = metrics["complexity_distributions"]
        lines.append(f"| {loc} | {metrics['primary_denominator']} | {metrics['ego_boundary_contact_cases_n']} / {metrics['ego_boundary_contact_cases_denominator']} | {metrics['overlap_pair_findings_n']} | {metrics['unreviewable_pair_findings_n']} | `{metrics['pair_motion_class_counts']}` | {d['moving_actor_count']['mean']:.2f} | {d['stationary_actor_count']['median']:.2f} |")
    lines += ["", "Site distributions reflect only the B1–B9 selected windows. Counts and complexity are correlated with batch, family, and recording composition; they are not site-wide rates. Recording and family quantiles, pair role and motion classes, penetration depth, and sampled occupancy duration remain available in the machine summary.", "",
              "| L2 batch | N | Boundary-contact cases / N | Overlap pairs | Non-reviewable pairs | Mean moving actors | Mean stationary actors |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for b, m in s["l2_physical_by_batch"].items():
        lines.append(f"| {b} | {m['denominator']} | {m['boundary_cases']} / {m['denominator']} | {m['overlap_pair_findings']} | {m['unreviewable_pair_findings']} | {m['mean_moving_actors']:.2f} | {m['mean_stationary_actors']:.2f} |")
    lines += ["", "L2 moving actor mean is 12.50 and stationary actor mean is 17.49 over 132 primary rows. Boundary contact appears in 16/132 L2 rows (12.1%); the corresponding saved-row counts are shown for other locations above. Location 4 has 22 rows, while location 3 has 10, so cross-site contrasts are descriptive only.",
              "", "### Sampled source-versus-converted cases", "",
              "The representative pair checks align raw CSV rows and tracksMeta dimensions to the hash-bound converted-scene time sample. Center, wrapped heading, dimensions, and oriented-box gap/overlap are direct measurements. They characterize these sampled cases; they do not establish a systemic converter defect.", ""]
    for item in s["raw_converted_pair_comparisons"]:
        measurements = item["direct_actor_measurements"]
        max_center = max((a["center_delta_m"] for a in measurements), default=0)
        max_yaw = max((abs(a["wrapped_heading_delta_rad"]) for a in measurements), default=0)
        dimensions = "; ".join(f"track {a['track_id']} source {a['source_dimensions_m']} m → converted {a['converted_dimensions_m']} m" for a in measurements)
        recurrence = f"; recurrent identity occurrences {item['recurrent_identity_primary_occurrences']}" if item.get("recurrent_identity_primary_occurrences") is not None else ""
        lines.append(f"- `{item['candidate_id']}` recording {item['recording']} pair {item['track_ids']} ({item['pair_motion_class']}{recurrence}): max center delta {max_center:.9f} m; max wrapped heading delta {max_yaw:.9f} rad; {dimensions}; source boxes {item['source_recorded_geometry']}; converted boxes {item['converted_scene_geometry']}.")
    lines += ["", "In the contrast pair, track 420 has source dimensions [0.0, 0.0] m and converts to the pedestrian default [0.6, 0.6] m; at sampled step 4 this changes the computed relation from a 0.379 m gap to a 0.0047 m overlap. This is a direct measurement of the stored zero dimensions and configured fallback behavior, not evidence that a zero-size source box is physical truth or that the fallback is generically wrong.", ""]
    lines += ["", "## Map route representation cases", ""]
    for route in s["route_connectivity_cases"]:
        lines.append(f"- `{route['candidate_id']}`: occupied start {route['occupied_start_lanelets']} to occupied goal {route['occupied_goal_lanelets']} has saved connectivity paths {route['occupied_start_to_occupied_goal_paths']}; nearest-centerline route {route['nearest_centerline_start_lane']}→{route['nearest_centerline_goal_lane']} has path `{route['nearest_centerline_directed_path']}`. Pinned map SHA `{route['map_sha256']}`. The two representations answer different geometric queries; neither alone identifies which source representation is semantically preferable.")
    lines += ["", "## Task proximity, lifecycle, and semantic support", "",
              "Ego/task distance uses minimum timed center distance from valid hash-bound converted scene positions; it is a measurement, not a gate. Saved trace counts use all primary rows at each location as the availability denominator.", "",
              f"L2 designated-task rows: {s['ego_task_proximity_by_location']['2']['designated_task_actor_n']}/132; measurable timed-distance rows: {s['ego_task_proximity_by_location']['2']['measured_n']}/132. The per-location values and unavailable reasons are recorded in the machine report.", "",
              "| Location | Expert traces / N | IDM traces / N | Hybrid traces / N | Hybrid admission reports / N |",
              "|---:|---:|---:|---:|---:|"]
    for loc, cov in s["trace_coverage_by_location"].items():
        lines.append(f"| {loc} | {cov['expert']['present']} / {cov['expert']['denominator_all_primary_rows']} | {cov['idm']['present']} / {cov['idm']['denominator_all_primary_rows']} | {cov['hybrid_startup']['present']} / {cov['hybrid_startup']['denominator_all_primary_rows']} | {cov['hybrid_admission']['present']} / {cov['hybrid_admission']['denominator_all_primary_rows']} |")
    lines += ["", "Hybrid failure classifications distinguish lifecycle, source-box, missing-review-artifact, refresh-command, and semantic checks; missing semantic review leaves support unknown. The machine record includes by-location counts and counterfactual lifecycle fields.", "",
              "## Structured birth failures and hypotheses", "",
              "Eligibility is explicit as saved-report availability divided by the full primary denominator; a missing trace is unavailable, not a pass. Structured spawn reports and saved lifecycle traces are evidence from prior runs. No native execution occurred during this follow-up.", ""]
    for case_id, evidence in s["birth_failure_cases"].items():
        spawn = evidence.get("structured_spawn_report", {})
        modes = spawn.get("modes", {})
        dynamics = modes.get("dynamics", {})
        idm = modes.get("idm", {})
        hybrid = evidence.get("hybrid_admission", {})
        birth_samples = evidence.get("saved_late_birth_trace_samples", {})
        expert_births = (birth_samples.get("expert") or {})
        birth_summary = []
        for actor_id, actor_evidence in expert_births.items():
            samples = actor_evidence.get("saved_timeline_samples") or []
            first = samples[0] if samples else None
            if first:
                birth_summary.append(f"{actor_id}@{first.get('step')}:valid={first.get('source_valid')},present={first.get('present')},position_error={first.get('position_error_m')} m")
            else:
                birth_summary.append(f"{actor_id}@{actor_evidence.get('reported_birth_step')}:no saved sample (trace ended before birth)")
        lines.append(f"- `{case_id}` ({evidence['batch']}, status `{evidence['status']}`): dynamics birth pass `{dynamics.get('birth_passed')}`, max position error `{dynamics.get('max_birth_position_error_m')}` m, late actors `{sorted((dynamics.get('late_tracks') or {}).keys())}`; IDM birth pass `{idm.get('birth_passed')}`, max position error `{idm.get('max_birth_position_error_m')}` m, observed steps `{idm.get('observed_steps')}`, justified goal terminal `{idm.get('justified_goal_terminal_step')}`, untested post-goal actors `{idm.get('post_goal_untested_birth_track_ids')}`. Saved Expert late-actor samples: {'; '.join(birth_summary)}. Hybrid counterfactual summary `{hybrid.get('counterfactual_lifecycle')}`; failed checks `{hybrid.get('failed_checks')}.` The large dynamics error is consistent with the validator's use of an initial trajectory offset for actors invalid at step 0 interacting with the -10000 invalid-position sentinel, but the saved report omits those exact native operands, so this remains a hypothesis requiring a focused source and dimensions capture.")
    lines += ["", "Automated follow-up should record source and dimension measurements and hypotheses against frozen outputs. Human adjudication is outside this overnight scope. Any code fix remains a proposal pending independent generic-defect review and separability from frozen screening.", "",
              "## Reproduction and evidence", "",
              f"The E2 reader SHA is `{report['evidence']['e2_reader']['sha256']}`. It authenticates B1–B9 retention record digests, chain links, ordered identities, ledger hashes, queue/source queue/receipt/plan/manifest/owner/report/summary hashes where recorded, the B9 accepted digest `{EXPECTED_B9_ACCEPTED_RECORD_SHA256}`, and the exact existing producer SHA `{PHYSICAL_PRODUCER_SHA256}`. The actual source checkout HEAD at run time was `{report['incidental_provenance']['actual_source_checkout_head']}` and is recorded as incidental provenance.", "",
              f"The preserved E1 artifact SHA `{E1_BASELINE_SHA256}` was unchanged. Re-reading the B1–B4 L2 rows reproduced all 57 identity keys, all listed stable case fields, and all 23 stable E1 summary sections with zero differences.", "",
              "## Focused follow-up measurements", "",
              "1. For B5 actor 111 and B8 actors 321–323, preserve the saved Expert/IDM/hybrid traces and capture each actor's source scene position at step 0, validity at step 0, native initial traj_x/traj_y, computed origin offset, native birth state, and expected source position at birth. The overnight summary supports the sentinel-offset hypothesis but does not expose these operands.",
              "2. Compare the captured offset with the existing spawn check's transformed native position on both rows, then run a diagnostic-only reproduction on a fresh candidate copy. Keep the frozen technical screen and thresholds unchanged; any proposed correction needs independent generic-defect review before it can be separated from screening.",
              "3. For track 420 in recording 23, measure source dimension validity, selected fallback dimensions, and source/converted box gap over the full overlap sample set. The current sample shows a zero-dimension metadata value and a one-step geometry change; this does not determine the intended physical dimension.",
              "4. For both route representation cases, retain the exact pinned map and occupancy lanelet IDs and compare occupied polygon and nearest-centerline directed paths in a dedicated map diagnostic. The current connectivity paths are direct saved-scene measurements, not a semantic adjudication.", "",
              f"Command: `{command}`", "",
              f"Output SHA-256: `{output_sha}`", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True, help="checked-out reader source worktree")
    parser.add_argument("--evidence-root", type=Path, required=True, help="shared repository with immutable ledgers and saved outputs")
    parser.add_argument("--output-dir", type=Path, required=True, help="new or empty ignored output directory")
    args = parser.parse_args()
    source_root, root, output_dir = args.repo_root.resolve(), args.evidence_root.resolve(), args.output_dir.resolve()
    require(not output_dir.exists() or not any(output_dir.iterdir()), f"refusing to overwrite nonempty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    e1 = load_e1(source_root)
    producer = source_root / PHYSICAL_PRODUCER
    require(sha256(producer) == PHYSICAL_PRODUCER_SHA256, "physical producer no longer matches its authenticated B1-B4 bytes")
    sys.path.insert(0, str(source_root / "src"))
    from geotransfer_gap.corpus import diagnose_german_200_physical as diag
    history, history_evidence = verify_history(root, e1)
    history_by_batch = {record["batch_label"]: record for record in history}
    review_index_path = root / e1.REVIEW_INDEX
    require(sha256(review_index_path) == REVIEW_INDEX_SHA256, "pinned B1-B4 review index changed")
    review_index = read_json(review_index_path)
    review_index_by_candidate = {item["candidate_id"]: item for item in review_index.get("cases", [])}
    cases: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    input_checks = {}
    for batch, rel in LEDGERS.items():
        ledger_path = root / rel
        ledger = read_json(ledger_path)
        rows = ledger["results"]
        rec = history_by_batch[batch]
        require(sha256(ledger_path) == LEDGER_SHA256[batch], f"pinned ledger mismatch {batch}")
        require([r["frozen_row"]["source_window_identity_sha256"] for r in rows] == rec["ordered_primary_identity_sha256"],
                f"identity order mismatch {batch}")
        for row in rows:
            case = diag._case_record(batch, row, root, hashes)
            identity = case["source_window_identity_sha256"]
            require(identity == row["frozen_row"]["source_window_identity_sha256"], f"collector identity mismatch {row['candidate_id']}")
            index_case = review_index_by_candidate.get(row["candidate_id"]) if batch in {"B1", "B2", "B3", "B4"} else None
            case = e1.enrich_case(root, batch, row, case, index_case)
            case["ledger_status"] = row.get("status")
            case["queue_index"] = row.get("queue_index")
            cases.append(case)
            phase = row.get("phase_fallback") or {}
            fallback = phase.get("result")
            frozen = fallback.get("frozen_row") if isinstance(fallback, dict) else None
            if isinstance(frozen, dict):
                fallbacks.append({
                    "batch": batch, "primary_candidate_id": row.get("candidate_id"),
                    "candidate_id": fallback.get("candidate_id"), "status": fallback.get("status"),
                    "location": frozen.get("location"), "recording": frozen.get("recording"),
                    "source_window_identity_sha256": frozen.get("source_window_identity_sha256"),
                    "included_in_primary_denominators": False,
                })
        input_checks[batch] = {"ledger_sha256": sha256(ledger_path), "primary_rows": len(rows),
                               "location_counts": dict(sorted(collections.Counter(str(r["frozen_row"].get("location")) for r in rows).items()))}
    require(len(cases) == 200, f"expected 200 B1-B9 primary rows, found {len(cases)}")
    require(len({c["source_window_identity_sha256"] for c in cases}) == 200, "primary identity duplicated across B1-B9")
    actual_head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()

    for case in cases:
        case["native_lifecycle"] = {}
        for mode, filename in (("expert", "lifecycle_trace_expert.json"),
                               ("idm", "lifecycle_trace_idm.json"),
                               ("hybrid_startup", "lifecycle_trace_hybrid_startup.json")):
            saved_trace = e1.trace_summary(root, case, filename)
            if saved_trace is not None:
                case["native_lifecycle"][mode] = saved_trace
        case["e2_saved_evidence"] = trace_evidence(root, case, e1)
    stable_e1_comparison = compare_e1_stable_baseline(root, cases, e1, review_index)
    all_l2 = [c for c in cases if int(c["location"]) == 2]
    recurrence = pair_recurrences(all_l2)
    recurrent_stationary = next((r for r in recurrence if r["stationary_in_all_occurrences"]), None)
    candidate_pair = None
    if recurrent_stationary:
        occ = recurrent_stationary["occurrences"]
        chosen_occ = next((o for o in occ if 0 in (o.get("sampled_first_steps") or [])), occ[0])
        candidate_pair = {**chosen_occ, "recording": recurrent_stationary["recording"],
                          "track_ids": recurrent_stationary["track_ids"], "first_frame": chosen_occ["first_frame"],
                          "last_frame": int(chosen_occ["first_frame"]) + 225,
                          "recurrent_identity_primary_occurrences": recurrent_stationary["primary_occurrences"]}
    contrast = next((
        {"candidate_id": c["candidate_id"], "recording": c["recording"], "track_ids": p["track_ids"],
         "pair_motion_class": p["pair_motion_class"], "sampled_first_steps": p["sampled_first_steps"],
         "first_frame": c["first_frame"], "last_frame": c["last_frame"], "candidate_root": c["candidate_root"],
         "output_paths": c["output_paths"], "raw_source_input_hashes": c["raw_source_input_hashes"]}
        for c in all_l2 for p in c["physical_source"]["overlap_pair_details"]
        if p["pair_motion_class"] == "moving_and_stationary" and p.get("sampled_first_steps")
    ), None)
    direct = []
    if candidate_pair:
        direct.append(direct_box_comparison(root, candidate_pair, e1))
    if contrast:
        direct.append(direct_box_comparison(root, contrast, e1))

    by_location: dict[str, Any] = {}
    route_geometry_by_location: dict[str, Any] = {}
    for loc in sorted({str(c["location"]) for c in cases}, key=int):
        rows = [c for c in cases if str(c["location"]) == loc]
        by_location[loc] = {"denominator": len(rows), "status_counts": dict(sorted(collections.Counter(c["status"] for c in rows).items()))}
        route_geometry_by_location[loc] = {
            "primary_denominator": len(rows),
            "occupied_lane_route_unreachable_n": sum(c["route_reachable"] is False for c in rows),
            "nearest_centerline_representation_disagreement_n": sum(c["route_representation_disagreement"] is True for c in rows),
            "outside_lane_sample_case_n": sum(c["outside_lanelet_sample_count"] > 0 for c in rows),
        }
    l2_batch = {}
    for batch in LEDGERS:
        rows = [c for c in all_l2 if c["batch"] == batch]
        pairs = [p for c in rows for p in c["physical_source"]["overlap_pair_details"]]
        l2_batch[batch] = {
            "denominator": len(rows), "boundary_cases": sum(c["physical_source"]["ego_boundary_contact_count"] > 0 for c in rows),
            "overlap_pair_findings": len(pairs), "unreviewable_pair_findings": sum(p["reviewable_annotation_overlap"] is not True for p in pairs),
            "mean_moving_actors": statistics.mean(c["moving_actor_count"] for c in rows) if rows else 0.0,
            "mean_stationary_actors": statistics.mean(c["stationary_actor_count"] for c in rows) if rows else 0.0,
        }
    trace_coverage = {}
    hybrid_classification = {}
    lifecycle_classification = {}
    semantic_support = {}
    ego_task_proximity = {}
    for loc in sorted({str(c["location"]) for c in cases}, key=int):
        rows = [c for c in cases if str(c["location"]) == loc]
        trace_coverage[loc] = {mode: {"present": sum(c["e2_saved_evidence"][mode].get("present") is True for c in rows),
                                      "denominator_all_primary_rows": len(rows)} for mode in ("expert", "idm", "hybrid_startup")}
        trace_coverage[loc]["structured_spawn_report"] = {"present": sum(c["e2_saved_evidence"]["structured_spawn_report"].get("present") is True for c in rows),
                                                           "denominator_all_primary_rows": len(rows)}
        trace_coverage[loc]["hybrid_admission"] = {"present": sum(c["e2_saved_evidence"]["hybrid_admission"].get("present") is True for c in rows),
                                                    "denominator_all_primary_rows": len(rows)}
        saved_hybrid = [c["e2_saved_evidence"]["hybrid_admission"] for c in rows
                        if c["e2_saved_evidence"]["hybrid_admission"].get("present") is True]
        failures = collections.Counter(name for item in saved_hybrid for name in item.get("failed_checks", []))
        cf_states = collections.Counter(str(item.get("counterfactual_lifecycle")) for item in saved_hybrid)
        hybrid_classification[loc] = {
            "saved_admission_report_n": len(saved_hybrid), "denominator_all_primary_rows": len(rows),
            "failed_check_counts_among_saved_reports": dict(sorted(failures.items())),
            "counterfactual_lifecycle_values_among_saved_reports": dict(sorted(cf_states.items())),
            "semantic_unknown_or_pending_saved_reports_n": sum(item.get("semantic_support_unknown_or_pending") is True for item in saved_hybrid),
        }
        lifecycle_classification[loc] = {}
        for mode in ("expert", "idm", "hybrid_startup"):
            saved = [c["e2_saved_evidence"][mode] for c in rows if c["e2_saved_evidence"][mode].get("present") is True]
            cause_counts = collections.Counter(loss.get("cause", "unknown") for item in saved
                                               for loss in item.get("first_source_valid_losses", []))
            lifecycle_classification[loc][mode] = {
                "saved_trace_n": len(saved), "denominator_all_primary_rows": len(rows),
                "first_source_valid_loss_causes": dict(sorted(cause_counts.items())),
                "saved_trace_count_with_any_collision": sum(item.get("collision_actor_event_n", 0) > 0 for item in saved),
            }
        sem = collections.Counter(str(c.get("semantic_applicability", {}).get("status", "not_saved")) for c in rows)
        semantic_support[loc] = {
            "denominator_all_primary_rows": len(rows), "saved_semantic_status_counts": dict(sorted(sem.items())),
            "review_index_entry_n": sum(c.get("semantic_applicability", {}).get("review_index_entry_present") is True for c in rows),
            "human_adjudication_recorded_n": 0,
            "interpretation": "saved applicability status and review-index routing are not human findings; absent adjudication remains unknown",
        }
        prox_rows = [c["ego_task_proximity"] for c in rows]
        measured = [p["minimum_timed_center_distance_m"] for p in prox_rows
                    if p.get("status") == "measured_from_hash_bound_converted_scene_positions"]
        ego_task_proximity[loc] = {
            "denominator_all_primary_rows": len(rows), "designated_task_actor_n": sum(c["designated_task_actor_id"] is not None for c in rows),
            "measured_n": len(measured), "unavailable_n": len(rows) - len(measured),
            "minimum_timed_center_distance_m": {
                "min": min(measured) if measured else None,
                "median": statistics.median(measured) if measured else None,
                "max": max(measured) if measured else None,
            },
        }

    route_cases = []
    for candidate_id in ("Interactive100-21-d0d1690740f0", "Random100-23-7989a39a8fac"):
        case = next((c for c in all_l2 if c["candidate_id"] == candidate_id), None)
        if case:
            route_cases.append(route_connectivity(case, root))
    require(len(route_cases) == 2, "expected both pinned E1 route-disagreement cases")
    birth_failures = {}
    for case in all_l2:
        spawn = case["e2_saved_evidence"]["structured_spawn_report"]
        if not spawn.get("present"):
            continue
        dyn = (spawn.get("modes") or {}).get("dynamics") or {}
        if dyn.get("birth_passed") is False:
            birth_failures[case["candidate_id"]] = {
                "batch": case["batch"], "status": case["status"], "source_window_identity_sha256": case["source_window_identity_sha256"],
                **case["e2_saved_evidence"],
            }
    task_proximity_groups: dict[str, dict[str, Any]] = {}
    for field in ("location", "batch", "arm", "family", "status"):
        groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for case in cases:
            groups[str(case[field])].append(case)
        for key, rows in sorted(groups.items()):
            measured_cases = [c for c in rows if c["ego_task_proximity"].get("status") == "measured_from_hash_bound_converted_scene_positions"]
            distances = [c["ego_task_proximity"]["minimum_timed_center_distance_m"] for c in measured_cases]
            task_proximity_groups[f"{field}:{key}"] = {
                "primary_denominator": len(rows),
                "designated_task_actor_n": sum(c["designated_task_actor_id"] is not None for c in rows),
                "measured_timed_distance_n": len(measured_cases),
                "unavailable_reason_counts": dict(sorted(collections.Counter(
                    c["ego_task_proximity"].get("status", "unknown") for c in rows
                    if c["ego_task_proximity"].get("status") != "measured_from_hash_bound_converted_scene_positions"
                ).items())),
                "minimum_timed_center_distance_m": {
                    "min": min(distances) if distances else None,
                    "median": statistics.median(distances) if distances else None,
                    "max": max(distances) if distances else None,
                },
            }
    summary = {
        "all_site_primary_denominator": len(cases), "location2_primary_denominator": len(all_l2),
        "fallback_denominator_all_sites_separate": len(fallbacks),
        "location2_fallback_denominator": sum(str(f.get("location")) == "2" for f in fallbacks),
        "fallback_attempts_by_location_separate": dict(sorted(collections.Counter(str(f.get("location")) for f in fallbacks).items(), key=lambda item: int(item[0]))),
        "location2_by_batch": {b: m["denominator"] for b, m in l2_batch.items()},
        "primary_denominators_by_location": by_location,
        "source_geometry_route_by_location": route_geometry_by_location,
        "batch_location_input_counts": input_checks,
        "grouped_location_batch_arm_family_recording_status": grouped_summary(cases, ("location", "batch", "arm", "family", "recording", "status")),
        "l2_physical_by_batch": l2_batch,
        "pair_identity_recurrence": {"unique_pair_identities": len({(c["recording"], tuple(sorted(p["track_ids"]))) for c in all_l2 for p in c["physical_source"]["overlap_pair_details"]}),
                                     "recurrent_identity_count": len(recurrence),
                                     "all_stationary_recurrent_identity_count": sum(r["stationary_in_all_occurrences"] for r in recurrence),
                                     "occurrence_count_within_recurrent_identities": sum(r["primary_occurrences"] for r in recurrence),
                                     "recurrent_identities": recurrence},
        "raw_converted_pair_comparisons": direct,
        "route_connectivity_cases": route_cases,
        "trace_coverage_by_location": trace_coverage,
        "hybrid_failure_classification_by_location": hybrid_classification,
        "native_lifecycle_classification_by_location": lifecycle_classification,
        "semantic_support_by_location": semantic_support,
        "ego_task_proximity_by_location": ego_task_proximity,
        "ego_task_proximity_by_location_batch_arm_family_status": task_proximity_groups,
        "birth_failure_cases": birth_failures,
    }
    report = {
        "schema_version": 1, "analysis_only": True, "protocol": "german_200_location2_followup_e2_v1",
        "scope": "authenticated B1-B9 primary rows at all sites, with location-2 analyses and fallback attempts separated; later records excluded",
        "evidence": {
            "retention_history": history_evidence,
            "retention_review_index_b1_b4": {"path": e1.REVIEW_INDEX, "sha256": REVIEW_INDEX_SHA256},
            "physical_forensics_producer": {"path": PHYSICAL_PRODUCER, "sha256": PHYSICAL_PRODUCER_SHA256},
            "e2_reader": {"path": E2_PATH, "sha256": sha256(source_root / E2_PATH)},
            "e1_reader": {"path": E1_PATH, "sha256": sha256(source_root / E1_PATH)},
            "oriented_box_geometry_helper": {"path": "src/geotransfer_gap/validation/audit_physical_source.py",
                                                "sha256": sha256(source_root / "src/geotransfer_gap/validation/audit_physical_source.py")},
            "spawn_validator_source": {"path": "src/geotransfer_gap/validation/validate_spawn.py",
                                        "sha256": sha256(source_root / "src/geotransfer_gap/validation/validate_spawn.py")},
            "stable_e1_b1_b4_comparison": stable_e1_comparison,
            "source_checkout_head_incidental": actual_head,
            "ledgers": input_checks,
            "source_raw_hash_verified_files": len(hashes),
            "primary_rows": len(cases), "unique_primary_identities": len({c["source_window_identity_sha256"] for c in cases}),
        },
        "definitions": {
            "primary_identity": "frozen source_window_identity_sha256; unique across B1-B9",
            "pair_identity": "recording plus sorted track IDs; recurrence counts windows and does not imply independent events",
            "physical_blockers": "source physical audit boundary contacts and overlap pair reviewability flags, directly read and verified by the existing E1 collector",
            "source_converted_geometry": "raw tracks/track metadata interpolated at a sampled source time and compared with the exact hash-bound converted scene using existing oriented rectangle helpers",
            "route_connectivity": "directed BFS over exit_lanes in each hash-bound converted scene; pinned map SHA is recorded from the audit; occupied polygon and nearest-centerline routes stay distinct",
            "trace_eligibility": "saved report present divided by all primary rows in the location group; absence is unavailable and not a pass",
            "semantic_support": "admission flags and source-applicability output do not record human adjudication; support remains unknown without an adjudicated review",
        },
        "summary": summary,
        "primary_cases": {c["source_window_identity_sha256"]: compact_case(c) for c in cases},
        "fallback_attempts_separate": fallbacks,
        "commands": [
            sys.executable + " " + str(source_root / "scripts/location2_followup_e2.py") + " --repo-root " + str(source_root) + " --evidence-root " + str(root) + " --output-dir " + str(output_dir),
            "sha256sum " + str(output_dir / "location2_followup_e2.json"),
        ],
        "incidental_provenance": {"actual_source_checkout_head": actual_head,
            "current_retention_history_sha256": sha256(root / HISTORY),
            "later_history_records_observed_but_excluded": history_evidence["later_records_after_b9_excluded"]},
    }
    output = output_dir / "location2_followup_e2.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    output_sha = sha256(output)
    command = sys.executable + " " + str(source_root / "scripts/location2_followup_e2.py") + " --repo-root " + str(source_root) + " --evidence-root " + str(root) + " --output-dir " + str(output_dir)
    md = make_markdown(report, output_sha, command)
    (output_dir / "location2_followup_e2.md").write_text(md, encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": output_sha,
                      "denominators": {"all_sites": len(cases), "location_2": len(all_l2),
                                       "location_2_fallback_separate": sum(str(f.get("location")) == "2" for f in fallbacks)},
                      "locations": {key: value["denominator"] for key, value in by_location.items()},
                      "recurrent_pair_identities": summary["pair_identity_recurrence"]["recurrent_identity_count"],
                      "birth_failure_case_ids": sorted(birth_failures)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
