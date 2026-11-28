#!/usr/bin/env python3
"""Build an offline, identity-keyed location-2 baseline from saved B1-B4 evidence.

This is a reader only. It consumes pinned ledgers, saved scene/audit outputs,
the retention review index, and the existing A4 technical-reject reproduction.
It never runs conversion, native gates, or review workflows.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
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
}
PINNED_LEDGER_SHA256 = {
    "B1": "4076644465ae3d7a9483499bad9ab28b37a2e5effadc32a43bbba98a36dcdf4a",
    "B2": "a6d36cd0e13375d4236b0a19cf393990e9fc0da1aaa6eb9df8f67e270329ac78",
    "B3": "4f6e3ba0acf1d5eb44ba7fba457414b826344a1740d5411b371beb8da6a710af",
    "B4": "b966b91bead60b76e0cf56edb8b21db5bb949efa9c5e584da8fdc031b76fe3f6",
}
PINNED_RECORD_SHA256 = {
    "B1": "ab65e52b09c597c6c663bafe046cb79434ce4f87595c1527fea09e5c80b902fc",
    "B2": "40bafed89a5f1ca33b33856b693a1f92d5aedbd7cd91efe3f39ebecda7650432",
    "B3": "b7f3256a323d4d0b9a5f256346cf55c84297e6b48ada89f5b632f8ebd02ebf6c",
    "B4": "874dcdd62f06e19878a2d964866619d8fe0d8af9b7581edcfa762f0cf527014d",
}
EXPECTED_L2_N = {"B1": 9, "B2": 16, "B3": 17, "B4": 15}
HISTORY = "artifacts/german_200_v1_runs/retention_v1/retention_history.jsonl"
TIP = "artifacts/german_200_v1_runs/retention_v1/retention_tip.json"
REVIEW_INDEX = "artifacts/german_200_v1_runs/retention_review_index_v1.json"
REPRO_SUMMARY = "artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/summary_v1.json"
REPRO_MANIFEST = "artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/machine_outcomes/native_current_v1/run_manifest.json"
REPRO_CANDIDATE = "Interactive100-0-a386442265d8"
EXPECTED_REPRO_SUMMARY_SHA256 = "d833c2e925be7b42c4c5fa461228a1cc22930eafe82b8872c72a5c84d84d8a56"
EXPECTED_REPRO_MANIFEST_SHA256 = "9e6f1689e95518a52856bccdbc8f078d1055ab20ce788e2b8f56850a3b3f47e8"
FORENSICS_SOURCE_COMMIT = "2d0a498af1832a4f6b9087e556d55de9f6030c0d"
FORENSICS_PRODUCER_PATH = "src/geotransfer_gap/corpus/diagnose_german_200_physical.py"
FORENSICS_PRODUCER_SHA256 = "e53a1733f8732043442cbfeccf1d0e14c6eaa650773c6394589029c8e6d36abb"
EXPECTED_B1_B4_HISTORY_PREFIX_SHA256 = "860c5a5b1a9e3942fa43be7f1d8c49d738d97139c4ee99ee38e437d3f88d71a2"
DT_DEFAULT_S = 0.1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def finite_stats(values: list[float | int]) -> dict[str, Any]:
    vals = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(vals), "mean": round(math.fsum(vals) / len(vals), 3),
        "median": round(statistics.median(vals), 3), "min": min(vals), "max": max(vals),
    }


def mode_class(actor_rows: list[dict[str, Any]]) -> str:
    states = []
    for actor in actor_rows:
        roles = actor.get("roles") or []
        states.append("moving" if "moving" in roles else "stationary" if "stationary" in roles else "motion_unknown")
    if len(states) != 2:
        return "unknown_pair"
    return "_and_".join(sorted(states))


def class_overlap_pair(pair: dict[str, Any]) -> dict[str, Any]:
    actors = pair.get("actors") or []
    motion = mode_class(actors)
    ego_ids = [a.get("track_id") for a in actors if "ego" in (a.get("roles") or [])]
    task_ids = [a.get("track_id") for a in actors if "designated_task_actor" in (a.get("roles") or [])]
    near_ids = [a.get("track_id") for a in actors if "near_ego_center_le_12m" in (a.get("roles") or [])]
    count = pair.get("sampled_overlap_count")
    return {
        **pair,
        "pair_motion_class": motion,
        "pair_role_class": "ego_pair" if ego_ids else "context_pair",
        "ego_endpoint_track_ids": ego_ids,
        "task_endpoint_track_ids": task_ids,
        "near_ego_center_endpoint_track_ids": near_ids,
        "contiguous_overlap_span_seconds": (round((count - 1) / 10.0, 3) if isinstance(count, int) and count == 91 else None),
        "contiguous_span_known_reason": (
            "all 91 samples overlap; 9.0 seconds between first and last 10 Hz sample"
            if isinstance(count, int) and count == 91 else
            "saved physical audit stores overlap count and a leading step sample only; complete contiguous span is unavailable"
        ),
    }


def get_actor_id(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("track_id", value.get("id", value.get("actor")))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def task_proximity(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    task_id = get_actor_id(case.get("designated_task_actor_id"))
    if task_id is None:
        return {"status": "unavailable_no_designated_task_actor", "task_actor_id": None}
    scene_path = root / case["output_paths"]["scene_json"]
    scene = read_json(scene_path)
    validation = read_json(root / case["output_paths"]["validation"])
    hz = validation.get("scenario_hz")
    dt = 1.0 / float(hz) if isinstance(hz, (int, float)) and hz > 0 else DT_DEFAULT_S
    objects = {int(o["id"]): o for o in scene.get("objects", []) if isinstance(o, dict) and isinstance(o.get("id"), int)}
    ego_id = case["ego_track_id"]
    if ego_id not in objects or task_id not in objects:
        return {
            "status": "unavailable_actor_missing_from_converted_scene", "task_actor_id": task_id,
            "ego_actor_present": ego_id in objects, "task_actor_present": task_id in objects,
        }
    ego, task = objects[ego_id], objects[task_id]
    closest: tuple[float, int] | None = None
    common = 0
    for step, (ep, tp) in enumerate(zip(ego.get("position", []), task.get("position", []))):
        if ego.get("valid", [])[step] != 1 or task.get("valid", [])[step] != 1:
            continue
        common += 1
        distance = math.dist((ep["x"], ep["y"]), (tp["x"], tp["y"]))
        if closest is None or distance < closest[0]:
            closest = (distance, step)
    if closest is None:
        return {"status": "no_common_valid_scene_sample", "task_actor_id": task_id, "common_valid_samples": 0}
    return {
        "status": "measured_from_hash_bound_converted_scene_positions",
        "coordinate_frame": "converted scene local XY metres; source-derived samples",
        "task_actor_id": task_id, "common_valid_samples": common,
        "minimum_timed_center_distance_m": round(closest[0], 6),
        "scene_step": closest[1], "elapsed_seconds_from_scene_start": round(closest[1] * dt, 3),
    }


def output_json(case_root: Path, name: str) -> tuple[dict[str, Any] | None, Path | None]:
    path = case_root / "testing" / name
    return (read_json(path), path) if path.is_file() else (None, None)


def trace_summary(root: Path, case: dict[str, Any], name: str) -> dict[str, Any] | None:
    case_root = Path(case["candidate_root"])
    data, path = output_json(case_root, name)
    if data is None or path is None:
        return None
    losses = data.get("first_source_valid_losses") or {}
    loss_rows = []
    for track_id, row in losses.items():
        loss_rows.append({"track_id": int(track_id), "step": row.get("step"), "cause": row.get("cause")})
    cause_counts = collections.Counter(row["cause"] for row in loss_rows)
    collision_events = []
    for track_id, rows in (data.get("timeline") or {}).items():
        for sample in rows if isinstance(rows, list) else []:
            if sample.get("collision_state", 0):
                collision_events.append({
                    "track_id": int(track_id), "step": sample.get("step"),
                    "collision_state": sample.get("collision_state"),
                    "collided_with_binary_index": sample.get("collided_with_index"),
                })
    return {
        "path": str(path), "sha256": sha256(path), "traffic_mode": data.get("traffic_mode"),
        "observed_steps": data.get("observed_steps"), "episode_steps": data.get("episode_steps"),
        "justified_goal_terminal_step": data.get("justified_goal_terminal_step"),
        "reset_steps": data.get("reset_steps", []), "losses_by_cause": dict(sorted(cause_counts.items())),
        "collision_actor_events": collision_events,
        "first_source_valid_losses": sorted(loss_rows, key=lambda x: (x.get("step") or -1, x["track_id"])),
    }


def hybrid_gate(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    case_root = Path(case["candidate_root"])
    data, path = output_json(case_root, "admission_hybrid_startup.json")
    if data is None or path is None:
        return {"status": "not_present_or_not_run", "reason": "saved hybrid admission report absent"}
    checks = data.get("checks") or {}
    failed = sorted(name for name, value in checks.items() if value is False)
    return {
        "status": "saved_hybrid_admission_report", "path": str(path), "sha256": sha256(path),
        "traffic_protocol": data.get("traffic_protocol"), "technical_admitted": data.get("technical_admitted"),
        "research_admitted": data.get("research_admitted"), "failed_checks": failed,
        "exclusion_reasons": data.get("exclusion_reasons", []),
        "lifecycle_failures": [name for name in failed if "lifecycle" in name or "birth" in name or "counterfactual" in name],
        "semantic_support_unknown_or_pending": any(
            name in failed for name in ("semantic_screen", "source_supported_irrelevance_plausible")
        ) or any("semantic_review" in name for name in failed),
    }


def raw_track_window(root: Path, row: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    frozen = row.get("frozen_row") or {}
    paths = ((frozen.get("source_hashes") or {}).get("source_paths") or {})
    track_path = Path(paths.get("tracks_csv") or "")
    if not track_path.is_file():
        return {"status": "raw_tracks_unavailable", "path": str(track_path)}
    actors = [case.get("ego_track_id")]
    task_id = get_actor_id(case.get("designated_task_actor_id"))
    if task_id is not None and task_id not in actors:
        actors.append(task_id)
    first, last = int(case["first_frame"]), int(case["last_frame"])
    found: dict[int, list[dict[str, Any]]] = {int(a): [] for a in actors if a is not None}
    with track_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"trackId", "frame", "xCenter", "yCenter"}
        if not required.issubset(reader.fieldnames or []):
            return {"status": "raw_tracks_schema_missing_fields", "missing": sorted(required - set(reader.fieldnames or []))}
        for item in reader:
            try:
                track_id, frame = int(item["trackId"]), int(item["frame"])
            except (ValueError, TypeError):
                continue
            if track_id not in found or not first <= frame <= last:
                continue
            found[track_id].append({"frame": frame, "xCenter": float(item["xCenter"]), "yCenter": float(item["yCenter"])})
    actors_out = {}
    for track_id, records in found.items():
        records.sort(key=lambda x: x["frame"])
        actors_out[str(track_id)] = {
            "rows_in_frozen_frame_window": len(records),
            "first_frame": records[0]["frame"] if records else None,
            "last_frame": records[-1]["frame"] if records else None,
            "first_xy_m": [records[0]["xCenter"], records[0]["yCenter"]] if records else None,
            "last_xy_m": [records[-1]["xCenter"], records[-1]["yCenter"]] if records else None,
        }
    return {
        "status": "direct_raw_csv_rows_read; source byte identity independently hash-verified by forensic helper",
        "tracks_csv": str(track_path), "tracks_csv_sha256": sha256(track_path),
        "frozen_source_window_frames": [first, last], "actors": actors_out,
    }


def verify_review_index(root: Path, index_case: dict[str, Any]) -> dict[str, Any]:
    verified = []
    mismatches = []
    for label, item in (index_case.get("evidence") or {}).items():
        if not isinstance(item, dict):
            continue
        path_value = item.get("path")
        if not path_value:
            continue
        path = root / path_value
        actual = sha256(path) if path.is_file() else None
        expected = item.get("sha256")
        if actual == expected:
            verified.append(label)
        else:
            mismatches.append({"label": label, "path": path_value, "expected": expected, "actual": actual})
    return {"entry_present": True, "evidence_hashes_verified": verified, "evidence_hash_mismatches": mismatches}


def review_semantics(index_case: dict[str, Any] | None, row: dict[str, Any]) -> dict[str, Any]:
    semantic = row.get("semantic_applicability") or {}
    flags = semantic.get("applicability_flags") or []
    if index_case is None:
        return {
            "status": semantic.get("status", "not_saved"),
            "technical_gate_effect": semantic.get("technical_gate_effect"),
            "applicability_flag_count": len(flags), "applicability_flags": flags,
            "manual_review_created": row.get("manual_review_created", False),
            "review_index_entry_present": False,
            "interpretation": "spatial/applicability flags are prompts; semantic support remains unknown without an adjudicated review",
        }
    return {
        "status": semantic.get("status", "not_saved"),
        "technical_gate_effect": semantic.get("technical_gate_effect"),
        "applicability_flag_count": len(flags), "applicability_flags": flags,
        "manual_review_created": index_case.get("manual_review_created", row.get("manual_review_created", False)),
        "review_index_entry_present": True, "review_category": index_case.get("category"),
        "review_blockers": index_case.get("review_blockers", []),
        "review_questions": index_case.get("questions", []),
        "interpretation": "index presence is routing only; no human semantic finding is recorded",
    }


def enrich_case(root: Path, batch: str, row: dict[str, Any], diag_case: dict[str, Any], index_case: dict[str, Any] | None) -> dict[str, Any]:
    frozen = row.get("frozen_row") or {}
    candidate_root = Path(row.get("root") or "")
    dt = 1.0 / 10.0
    validation_path = candidate_root / "testing" / "validation.json"
    if validation_path.is_file():
        validation = read_json(validation_path)
        hz = validation.get("scenario_hz")
        if isinstance(hz, (int, float)) and hz > 0:
            dt = 1.0 / float(hz)
    if index_case is not None:
        require(index_case.get("source_window_identity_sha256") == diag_case["source_window_identity_sha256"],
                f"retention review index identity mismatch for {row.get('candidate_id')}")
    diag_case["candidate_root"] = str(candidate_root)
    for pair in diag_case["physical_source"]["overlap_pair_details"]:
        pair.update(class_overlap_pair(pair))
        if pair.get("sampled_overlap_count") is not None:
            pair["sampled_occupancy_seconds_at_source_rate"] = round(pair["sampled_overlap_count"] * dt, 3)
        if pair.get("sampled_overlap_count") == 91:
            pair["contiguous_overlap_span_seconds"] = round((91 - 1) * dt, 3)
            pair["contiguous_span_known_reason"] = "all 91 samples overlap; elapsed time from first to last sample"
        elif pair.get("sampled_overlap_count") == len(pair.get("sampled_first_steps") or []):
            steps = pair.get("sampled_first_steps") or []
            best = run = 1 if steps else 0
            for prior, current in zip(steps, steps[1:]):
                run = run + 1 if current == prior + 1 else 1
                best = max(best, run)
            pair["contiguous_overlap_span_seconds"] = round(max(0, best - 1) * dt, 3)
            pair["contiguous_span_known_reason"] = "all saved overlap steps are present; calculated from consecutive steps"
        pair.pop("contiguous_span_known_reason", None) if False else None
    case = {
        **diag_case,
        "identity_key": diag_case["source_window_identity_sha256"],
        "candidate_id": row.get("candidate_id"), "batch": batch,
        "queue_index": row.get("queue_index"), "ledger_status": row.get("status"),
        "fallback": False, "candidate_root": str(candidate_root),
        "source_task_families": frozen.get("source_task_families") or [],
        "technical_gate": row.get("technical_admission"),
        "semantic_applicability": review_semantics(index_case, row),
        "ego_task_proximity": task_proximity(root, diag_case),
        "saved_hybrid_admission": hybrid_gate(root, diag_case),
        "native_lifecycle": {},
        "review_index_reconciliation": verify_review_index(root, index_case) if index_case is not None else {"entry_present": False},
    }
    require(not case["review_index_reconciliation"].get("evidence_hash_mismatches"),
            f"retention review index evidence mismatch for {row.get('candidate_id')}")
    case["raw_track_window_sample"] = None
    return case


def collect_repro(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    summary_path, manifest_path = root / REPRO_SUMMARY, root / REPRO_MANIFEST
    summary_sha, manifest_sha = sha256(summary_path), sha256(manifest_path)
    require(summary_sha == EXPECTED_REPRO_SUMMARY_SHA256, "A4 summary hash differs from the documented saved reproduction")
    require(manifest_sha == EXPECTED_REPRO_MANIFEST_SHA256, "A4 run manifest hash differs from the documented saved reproduction")
    summary = read_json(summary_path)
    manifest = read_json(manifest_path)
    freeze_path = root / "artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/protocol_freeze_v1.json"
    support_path = root / "artifacts/german_200_v1_runs/workstream_a_technical_reject_repro_v1/support_addendum_20261127_v1.json"
    require(sha256(freeze_path) == "d17c51f88194249621c7210d147ca9205e44f3dd108e93de5a222826585440de", "A4 original freeze hash mismatch")
    require(sha256(support_path) == "71af3b1eebffdf11c41ad554bd34ae59bd4b6ac39ceebb4612a972b0ed2171cf", "A4 support addendum hash mismatch")
    match = [item for item in summary.get("cases", []) if item.get("candidate") == REPRO_CANDIDATE]
    require(len(match) == 1, "expected exactly one L2 saved A4 reproduction candidate")
    item = match[0]
    expected_hashes = [
        (item.get("current_hybrid_startup_gate") or {}).get("admission_report_path"),
        (item.get("current_legacy_immediate_idm_gate") or {}).get("admission_report_path"),
    ]
    for path_value in expected_hashes:
        require(path_value and Path(path_value).is_file(), f"A4 report missing: {path_value}")
    # The summary binds report bytes; the manifest binds each exact command and report hash.
    for section in ("current_hybrid_startup_gate", "current_legacy_immediate_idm_gate"):
        detail = item[section]
        path = Path(detail["admission_report_path"])
        require(sha256(path) == detail["admission_report_sha256"], f"A4 saved report hash mismatch: {path}")
        manifest_matches = [
            command for command in manifest.get("commands", [])
            if command.get("candidate") == REPRO_CANDIDATE
            and command.get("admission_report_path") == detail["admission_report_path"]
        ]
        require(len(manifest_matches) == 1, f"A4 manifest command binding absent/duplicated for {path}")
        require(manifest_matches[0].get("admission_report_sha256") == detail["admission_report_sha256"],
                f"A4 manifest report SHA mismatch for {path}")
    return item, {
        "summary_path": REPRO_SUMMARY, "summary_sha256": summary_sha,
        "run_manifest_path": REPRO_MANIFEST, "run_manifest_sha256": manifest_sha,
        "protocol_freeze_path": str(freeze_path.relative_to(root)), "protocol_freeze_sha256": sha256(freeze_path),
        "support_addendum_path": str(support_path.relative_to(root)), "support_addendum_sha256": sha256(support_path),
        "report_type": summary.get("report_type"), "native_run_status": summary.get("native_run_status"),
    }


def grouped_metrics(cases: list[dict[str, Any]], key_fn) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for case in cases:
        for key in key_fn(case):
            groups[str(key)].append(case)
    metrics = (
        "source_context_actor_count", "moving_actor_count", "stationary_actor_count",
        "moving_pair_opportunity_count", "moving_stationary_pair_opportunity_count",
        "stationary_pair_opportunity_count", "mean_concurrent_active_actor_count",
        "peak_concurrent_active_actor_count", "mean_concurrent_moving_actor_count",
    )
    return {
        key: {"denominator_primary_rows": len(rows), **{m: finite_stats([r[m] for r in rows]) for m in metrics}}
        for key, rows in sorted(groups.items())
    }


def make_summary(cases: list[dict[str, Any]], fallbacks: list[dict[str, Any]], reconciliation: dict[str, Any], review_index: dict[str, Any], repro: dict[str, Any]) -> dict[str, Any]:
    status_counts = collections.Counter(case["ledger_status"] for case in cases)
    arm_counts = collections.Counter(case["arm"] for case in cases)
    batch_status = {
        batch: dict(sorted(collections.Counter(c["ledger_status"] for c in cases if c["batch"] == batch).items()))
        for batch in LEDGERS
    }
    pair_rows = []
    pair_status_motion = collections.defaultdict(collections.Counter)
    pair_status_reviewability = collections.defaultdict(collections.Counter)
    recurrent: dict[tuple[int, tuple[int, int]], list[dict[str, Any]]] = collections.defaultdict(list)
    for case in cases:
        for pair in case["physical_source"]["overlap_pair_details"]:
            pair_rows.append((case, pair))
            pair_status_motion[case["ledger_status"]][pair["pair_role_class"] + "/" + pair["pair_motion_class"]] += 1
            pair_status_reviewability[case["ledger_status"]][str(pair["reviewable_annotation_overlap"])] += 1
            pair_key = (int(case["recording"]), tuple(sorted(map(int, pair["track_ids"]))))
            recurrent[pair_key].append({
                "candidate_id": case["candidate_id"], "batch": case["batch"], "status": case["ledger_status"],
                "first_frame": case["first_frame"], "sampled_overlap_count": pair["sampled_overlap_count"],
                "sampled_occupancy_seconds_at_source_rate": pair.get("sampled_occupancy_seconds_at_source_rate"),
                "maximum_penetration_m": pair.get("maximum_penetration_m"),
                "both_stationary_expert": pair["both_stationary_expert"],
                "reviewable_annotation_overlap": pair["reviewable_annotation_overlap"],
            })
    recurrence = [
        {"recording": rec, "track_ids": list(ids), "primary_occurrences": len(rows), "occurrences": rows,
         "stationary_in_all_occurrences": all(r["both_stationary_expert"] is True for r in rows)}
        for (rec, ids), rows in sorted(recurrent.items()) if len(rows) > 1
    ]
    physical_cases = [c for c in cases if c["ledger_status"] == "source_physical_rejection"]
    unreviewable_cases = [c for c in cases if c["physical_source"]["unreviewable_pair_count"] > 0]
    boundary_cases = [c for c in cases if c["physical_source"]["ego_boundary_contact_count"] > 0]
    physical_pair_trigger_cases = [c for c in physical_cases if c["physical_source"]["unreviewable_pair_count"] > 0]
    physical_boundary_trigger_cases = [c for c in physical_cases if c["physical_source"]["ego_boundary_contact_count"] > 0]
    physical_both_trigger_cases = [c for c in physical_cases if c["physical_source"]["unreviewable_pair_count"] > 0 and c["physical_source"]["ego_boundary_contact_count"] > 0]
    physical_boundary_only_cases = [c for c in physical_cases if c["physical_source"]["unreviewable_pair_count"] == 0 and c["physical_source"]["ego_boundary_contact_count"] > 0]
    route_false = [c for c in cases if c["route_reachable"] is False]
    nearest_disagreements = [c for c in cases if c["route_representation_disagreement"]]
    hybrid_present = [c for c in cases if c["saved_hybrid_admission"].get("status") == "saved_hybrid_admission_report"]
    hybrid_failure_counts = collections.Counter(
        failed for c in hybrid_present for failed in c["saved_hybrid_admission"].get("failed_checks", [])
    )
    trace_hybrid = [c for c in cases if "hybrid_startup" in c["native_lifecycle"]]
    semantic_status = collections.Counter(c["semantic_applicability"]["status"] for c in cases)
    semantic_index = sum(c["semantic_applicability"].get("review_index_entry_present") is True for c in cases)
    manual_review_created_n = sum(c["semantic_applicability"].get("manual_review_created") is True for c in cases)
    review_entries = {x.get("candidate_id"): x for x in review_index.get("cases", []) if x.get("location") == 2}
    family_arms = collections.defaultdict(int)
    def grouped_status(keys_fn):
        groups: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for case in cases:
            for key in keys_fn(case):
                groups[str(key)][case["ledger_status"]] += 1
        return {key: {"denominator_primary_rows": sum(counts.values()), "status_counts": dict(sorted(counts.items()))}
                for key, counts in sorted(groups.items())}

    trace_loss_causes = collections.defaultdict(collections.Counter)
    trace_loss_rows = 0
    non_goal_loss_case_ids = set()
    collision_case_ids = collections.defaultdict(set)
    collision_actor_events = collections.defaultdict(int)
    for case in cases:
        for mode, trace in case["native_lifecycle"].items():
            if trace is None:
                continue
            for loss in trace.get("first_source_valid_losses", []):
                trace_loss_causes[mode][loss.get("cause", "unknown")] += 1
                trace_loss_rows += 1
                if loss.get("cause") != "goal":
                    non_goal_loss_case_ids.add(case["candidate_id"])
            events = trace.get("collision_actor_events", [])
            if events:
                collision_case_ids[mode].add(case["candidate_id"])
                collision_actor_events[mode] += len(events)
    task_distance_rows = [c for c in cases if c["ego_task_proximity"].get("status") == "measured_from_hash_bound_converted_scene_positions"]
    def task_distance_groups(keys_fn):
        groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for case in task_distance_rows:
            for key in keys_fn(case):
                groups[str(key)].append(case)
        return {
            key: {"denominator_measured_cases": len(rows), "minimum_timed_center_distance_m": finite_stats([
                r["ego_task_proximity"]["minimum_timed_center_distance_m"] for r in rows
            ])}
            for key, rows in sorted(groups.items())
        }
    for case in cases:
        families = case["source_task_families"] or (["unreviewed_random_source_candidate"] if case["arm"] == "Random100" else ["unknown"])
        for family in families:
            family_arms[(case["arm"], family)] += 1
    return {
        "primary_denominator": len(cases), "fallback_denominator_separate": len(fallbacks),
        "primary_status_counts": dict(sorted(status_counts.items())), "primary_status_counts_by_batch": batch_status,
        "primary_arm_denominators": dict(sorted(arm_counts.items())),
        "primary_family_arm_denominators": {f"{arm}/{family}": n for (arm, family), n in sorted(family_arms.items())},
        "primary_recording_denominators": dict(sorted(collections.Counter(str(c["recording"]) for c in cases).items(), key=lambda x: int(x[0]))),
        "primary_outcomes_by_arm": grouped_status(lambda c: [c["arm"]]),
        "primary_outcomes_by_family_arm": grouped_status(lambda c: [
            f"{c['arm']}/{family}" for family in (c["source_task_families"] or (["unreviewed_random_source_candidate"] if c["arm"] == "Random100" else ["unknown"]))
        ]),
        "primary_outcomes_by_recording": grouped_status(lambda c: [c["recording"]]),
        "source_geometry_route": {
            "occupied_lane_route_unreachable_primary_n": len(route_false), "denominator": len(cases),
            "nearest_lane_vs_occupied_lane_disagreement_n": len(nearest_disagreements),
            "outside_lane_sample_case_n": sum(c["outside_lanelet_sample_count"] > 0 for c in cases),
            "by_batch": {
                b: {"denominator": sum(c["batch"] == b for c in cases),
                    "occupied_route_unreachable": sum(c["batch"] == b and c["route_reachable"] is False for c in cases),
                    "outside_lane_sample_case_n": sum(c["batch"] == b and c["outside_lanelet_sample_count"] > 0 for c in cases)}
                for b in LEDGERS
            },
        },
        "ego_task_proximity": {
            "cases_with_designated_task_actor_n": sum(c["designated_task_actor_id"] is not None for c in cases),
            "measured_cases_n": len(task_distance_rows),
            "unavailable_no_designated_task_actor_n": sum(c["ego_task_proximity"].get("status") == "unavailable_no_designated_task_actor" for c in cases),
            "minimum_timed_center_distance_m": finite_stats([c["ego_task_proximity"]["minimum_timed_center_distance_m"] for c in task_distance_rows]),
            "by_family_arm": task_distance_groups(lambda c: [
                f"{c['arm']}/{family}" for family in (c["source_task_families"] or (["unreviewed_random_source_candidate"] if c["arm"] == "Random100" else ["unknown"]))
            ]),
            "by_status": task_distance_groups(lambda c: [c["ledger_status"]]),
            "measurement_scope": "minimum timed centers from hash-bound converted-scene source-derived samples; unavailable rows remain explicit",
        },
        "physical_blockers": {
            "physical_rejection_primary_n": len(physical_cases), "physical_rejection_denominator": len(cases),
            "physical_rejection_with_unreviewable_pair_n": len(physical_pair_trigger_cases),
            "physical_rejection_with_ego_boundary_contact_n": len(physical_boundary_trigger_cases),
            "physical_rejection_with_both_trigger_types_n": len(physical_both_trigger_cases),
            "physical_rejection_boundary_only_n": len(physical_boundary_only_cases),
            "physical_rejection_by_batch": {
                b: {
                    "denominator_primary_rows": sum(c["batch"] == b for c in cases),
                    "physical_rejection_n": sum(c["batch"] == b for c in physical_cases),
                    "with_unreviewable_pair_n": sum(c["batch"] == b and c["physical_source"]["unreviewable_pair_count"] > 0 for c in physical_cases),
                    "with_ego_boundary_contact_n": sum(c["batch"] == b and c["physical_source"]["ego_boundary_contact_count"] > 0 for c in physical_cases),
                }
                for b in LEDGERS
            },
            "cases_with_unreviewable_pair_n": len(unreviewable_cases),
            "cases_with_ego_boundary_contact_n": len(boundary_cases),
            "pair_finding_occurrence_n": len(pair_rows),
            "pair_finding_by_case_status_and_motion": {k: dict(sorted(v.items())) for k, v in sorted(pair_status_motion.items())},
            "pair_finding_by_case_status_and_annotation_reviewability": {k: dict(sorted(v.items())) for k, v in sorted(pair_status_reviewability.items())},
            "unreviewable_pair_finding_n": sum(pair["reviewable_annotation_overlap"] is not True for _, pair in pair_rows),
            "reviewable_pair_finding_n": sum(pair["reviewable_annotation_overlap"] is True for _, pair in pair_rows),
            "max_penetration_distribution_m": finite_stats([pair["maximum_penetration_m"] for _, pair in pair_rows if pair.get("maximum_penetration_m") is not None]),
            "minimum_ego_box_gap_distribution_m": finite_stats([pair["minimum_ego_box_gap_m"] for _, pair in pair_rows if pair.get("minimum_ego_box_gap_m") is not None]),
            "sampled_overlap_count_distribution": finite_stats([pair["sampled_overlap_count"] for _, pair in pair_rows if pair.get("sampled_overlap_count") is not None]),
        },
        "pair_identity_recurrence": {
            "unique_recording_pair_identities": len(recurrent), "recurrent_identities": len(recurrence),
            "occurrences_in_recurrent_identities": sum(x["primary_occurrences"] for x in recurrence),
            "all_stationary_recurrent_identities": sum(x["stationary_in_all_occurrences"] for x in recurrence),
            "recurrent_pair_details": recurrence,
        },
        "complexity_distributions": {
            "by_arm": grouped_metrics(cases, lambda c: [c["arm"]]),
            "by_family": grouped_metrics(cases, lambda c: c["source_task_families"] or (["unreviewed_random_source_candidate"] if c["arm"] == "Random100" else ["unknown"])),
            "by_recording": grouped_metrics(cases, lambda c: [c["recording"]]),
            "by_batch": grouped_metrics(cases, lambda c: [c["batch"]]),
            "by_status": grouped_metrics(cases, lambda c: [c["ledger_status"]]),
        },
        "native_hybrid_lifecycle": {
            "saved_hybrid_admission_reports_present_n": len(hybrid_present), "primary_denominator": len(cases),
            "hybrid_lifecycle_trace_present_n": len(trace_hybrid), "trace_denominator": len(cases),
            "false_saved_hybrid_gate_checks": dict(sorted(hybrid_failure_counts.items())),
            "lifecycle_false_check_class_counts": {
                "hybrid_lifecycle": hybrid_failure_counts.get("hybrid_lifecycle", 0),
                "hybrid_counterfactual": hybrid_failure_counts.get("hybrid_counterfactual", 0),
                "counterfactual_lifecycle": hybrid_failure_counts.get("counterfactual_lifecycle", 0),
                "births_and_exits": hybrid_failure_counts.get("births_and_exits", 0),
            },
            "saved_first_source_valid_loss_causes_by_mode": {mode: dict(sorted(counts.items())) for mode, counts in sorted(trace_loss_causes.items())},
            "saved_first_source_valid_loss_row_count_across_available_traces": trace_loss_rows,
            "cases_with_non_goal_first_source_valid_loss": len(non_goal_loss_case_ids),
            "cases_with_collision_actor_events_by_mode": {mode: len(ids) for mode, ids in sorted(collision_case_ids.items())},
            "collision_actor_event_count_by_mode": dict(sorted(collision_actor_events.items())),
            "interpretation": "saved gate false checks are reported as classifications; absent reports are unrun/unknown and are not counted as passes",
        },
        "semantic_support": {
            "status_counts": dict(sorted(semantic_status.items())), "review_index_entries_present_n": semantic_index,
            "review_index_denominator": len(cases), "manual_reviews_created_n": manual_review_created_n,
            "applicability_flag_case_count": sum(c["semantic_applicability"]["applicability_flag_count"] > 0 for c in cases),
            "interpretation": "spatial flags and gate checks do not establish semantic applicability; absent review remains unknown",
        },
        "fallback_attempts_separate": {
            "l2_attempt_count": len(fallbacks), "by_batch_status": {
                f"{batch}/{status}": n for (batch, status), n in sorted(collections.Counter((f["batch"], f["status"]) for f in fallbacks).items())
            },
        },
        "review_index_l2_entries_including_fallbacks": len(review_entries),
        "review_index_l2_primary_entries": sum(not bool(x.get("phase_fallback")) for x in review_entries.values()),
        "review_index_l2_fallback_entries": sum(bool(x.get("phase_fallback")) for x in review_entries.values()),
        "reproduction": {
            "candidate": REPRO_CANDIDATE, "current_hybrid_technical_admitted": repro["current_hybrid_startup_gate"].get("technical_admitted"),
            "current_hybrid_failed_checks": repro["current_hybrid_startup_gate"].get("failed_checks", []),
            "current_immediate_idm_technical_admitted": repro["current_legacy_immediate_idm_gate"].get("technical_admitted"),
            "current_immediate_idm_failed_checks": repro["current_legacy_immediate_idm_gate"].get("failed_checks", []),
            "expert_ego_idm_matrix_status": repro["current_exact_expert_ego_idm_matrix"].get("status"),
            "expert_ego_idm_task_view_status": repro["current_exact_expert_ego_idm_matrix"].get("task_view_status"),
        },
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True, help="pinned B1-B4 source checkout/worktree")
    parser.add_argument("--evidence-root", type=Path, required=True, help="shared repository root containing saved ignored artifacts")
    parser.add_argument("--output-dir", type=Path, required=True, help="new or empty dedicated ignored output directory")
    args = parser.parse_args()
    source_root = args.repo_root.resolve()
    root = args.evidence_root.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    producer_path = source_root / FORENSICS_PRODUCER_PATH
    producer_sha = sha256(producer_path)
    require(producer_sha == FORENSICS_PRODUCER_SHA256, f"physical-forensics producer bytes differ from {FORENSICS_SOURCE_COMMIT}")
    sys.path.insert(0, str(source_root / "src"))
    from geotransfer_gap.corpus import diagnose_german_200_physical as diag

    head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    history_path, tip_path, index_path = root / HISTORY, root / TIP, root / REVIEW_INDEX
    history_bytes = history_path.read_bytes()
    history_lines = history_bytes.splitlines(keepends=True)
    history = [json.loads(line) for line in history_bytes.decode("utf-8").splitlines() if line.strip()]
    batch_history = history[:len(LEDGERS)]
    require([x["batch_label"] for x in batch_history] == list(LEDGERS), "retention history B1-B4 order mismatch")
    b1_b4_prefix = b"".join(history_lines[:len(LEDGERS)])
    b1_b4_prefix_sha = hashlib.sha256(b1_b4_prefix).hexdigest()
    require(b1_b4_prefix_sha == EXPECTED_B1_B4_HISTORY_PREFIX_SHA256, "retention history B1-B4 prefix changed")
    prior = None
    for record in batch_history:
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        actual_record = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        require(actual_record == record["record_sha256"] == PINNED_RECORD_SHA256[record["batch_label"]], f"history record hash mismatch for {record['batch_label']}")
        require(record.get("previous_record_sha256") == prior, f"retention chain link mismatch for {record['batch_label']}")
        prior = record["record_sha256"]
    tip = read_json(tip_path)
    require(tip.get("batch_number", 0) >= 4, "retention tip precedes the pinned B4 prefix")
    review_index = read_json(index_path)
    review_index_sha = sha256(index_path)
    index_by_candidate = {item["candidate_id"]: item for item in review_index.get("cases", [])}
    review_batch_checks = {}
    history_by_batch = {x["batch_label"]: x for x in batch_history}
    for source in review_index.get("batch_sources", []):
        batch = source.get("batch_label")
        if batch not in history_by_batch:
            continue
        hist = history_by_batch[batch]
        require(source.get("record_sha256") == hist.get("record_sha256"), f"review index retention record mismatch for {batch}")
        manifest_path = root / source["manifest_path"]
        queue_path = root / source["queue_path"]
        manifest_sha = sha256(manifest_path)
        queue_sha = sha256(queue_path)
        require(manifest_sha == source.get("manifest_sha256") == hist.get("review_manifest_sha256"), f"review manifest hash mismatch for {batch}")
        require(queue_sha == source.get("queue_sha256") == hist.get("queue_sha256"), f"source queue hash mismatch for {batch}")
        require(source.get("manual_reviews_created") is False, f"unexpected manual review state in {batch} index")
        review_batch_checks[batch] = {
            "record_sha256_matches_retention_history": True,
            "review_manifest_sha256": manifest_sha, "source_queue_sha256": queue_sha,
            "manifest_entry_count": source.get("manifest_entry_count"), "manual_reviews_created": False,
        }
    require(set(review_batch_checks) == set(LEDGERS), "review index does not pin all B1-B4 sources")
    a4_repro, repro_binding = collect_repro(root)
    all_cases: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    ledger_evidence = {}
    source_hash_cache: dict[str, str] = {}
    row_by_candidate: dict[str, dict[str, Any]] = {}
    identity_order_checks = {}
    for batch, rel_path in LEDGERS.items():
        ledger_path = root / rel_path
        ledger_sha = sha256(ledger_path)
        require(ledger_sha == PINNED_LEDGER_SHA256[batch], f"ledger SHA-256 mismatch for {batch}")
        ledger = read_json(ledger_path)
        rows = ledger.get("results", [])
        require(len(rows) == 24, f"{batch} primary row count is not 24")
        history_record = batch_history[list(LEDGERS).index(batch)]
        identities = [((r.get("frozen_row") or {}).get("source_window_identity_sha256")) for r in rows]
        require(identities == history_record.get("ordered_primary_identity_sha256"), f"ordered primary identity mismatch for {batch}")
        l2_rows = [r for r in rows if str((r.get("frozen_row") or {}).get("location")) == "2"]
        require(len(l2_rows) == EXPECTED_L2_N[batch], f"L2 primary denominator mismatch for {batch}")
        identity_order_checks[batch] = {"all_primary_rows": len(rows), "location_2_primary_rows": len(l2_rows), "ordered_identity_hashes_match_history": True}
        ledger_evidence[batch] = {"path": rel_path, "sha256": ledger_sha, "record_sha256": history_record["record_sha256"]}
        for row in l2_rows:
            candidate_id = row["candidate_id"]
            require(candidate_id not in row_by_candidate, f"duplicate L2 primary candidate: {candidate_id}")
            row_by_candidate[candidate_id] = row
            base_case = diag._case_record(batch, row, root, source_hash_cache)
            enriched = enrich_case(root, batch, row, base_case, index_by_candidate.get(candidate_id))
            all_cases.append(enriched)
        for row in rows:
            phase = row.get("phase_fallback") or {}
            fallback = phase.get("result")
            if not isinstance(fallback, dict):
                continue
            fallback_frozen = fallback.get("frozen_row") or {}
            if str(fallback_frozen.get("location")) != "2":
                continue
            fallback_index = index_by_candidate.get(fallback.get("candidate_id"))
            if fallback_index is not None:
                require(fallback_index.get("source_window_identity_sha256") == fallback_frozen.get("source_window_identity_sha256"),
                        f"fallback review index identity mismatch for {fallback.get('candidate_id')}")
                fallback_index_check = verify_review_index(root, fallback_index)
                require(not fallback_index_check.get("evidence_hash_mismatches"),
                        f"fallback review index evidence mismatch for {fallback.get('candidate_id')}")
            else:
                fallback_index_check = {"entry_present": False}
            # Keep alternate identity and outcome out of primary denominators and pair recurrences.
            fallbacks.append({
                "batch": batch, "primary_candidate_id": row.get("candidate_id"),
                "candidate_id": fallback.get("candidate_id"), "status": fallback.get("status"),
                "source_window_identity_sha256": fallback_frozen.get("source_window_identity_sha256"),
                "location": fallback_frozen.get("location"), "recording": fallback_frozen.get("recording"),
                "arm": fallback_frozen.get("arm"), "first_frame": fallback_frozen.get("first_frame"),
                "reasons": fallback.get("reasons", []), "phase_status": phase.get("status"),
                "review_index_entry_present": fallback_index is not None,
                "review_index_reconciliation": fallback_index_check,
                "included_in_primary_counts": False,
            })
    require(len(all_cases) == 57, f"expected exactly 57 L2 primaries, found {len(all_cases)}")
    require(len({c["identity_key"] for c in all_cases}) == 57, "L2 source window identity is duplicated")
    require(len({c["candidate_id"] for c in all_cases}) == 57, "L2 candidate id is duplicated")
    representatives = {REPRO_CANDIDATE}
    for predicate in (
        lambda c: c["route_reachable"] is False,
        lambda c: c["ledger_status"] == "source_physical_rejection",
        lambda c: c["ledger_status"] == "review_blocked",
    ):
        match = next((c for c in all_cases if predicate(c)), None)
        if match is not None:
            representatives.add(match["candidate_id"])
    for case in all_cases:
        if case["candidate_id"] in representatives:
            case["raw_track_window_sample"] = raw_track_window(root, row_by_candidate[case["candidate_id"]], case)
            case["representative_raw_map_conversion_evidence"] = {
                "source_map_path": case["source_map"], "source_map_sha256": case["source_map_sha256"],
                "source_map_hash_verified": case["source_map_hash_verified"],
                "occupied_start_to_occupied_goal_reachable": case["route_reachable"],
                "outside_lanelet_sample_count": case["outside_lanelet_sample_count"],
                "converted_scene": case["converted_scene"],
                "output_tree_hashes_verified": case["output_tree_hashes_verified"],
            }
        else:
            case["raw_track_window_sample"] = None
        for name in ("lifecycle_trace_expert.json", "lifecycle_trace_idm.json", "lifecycle_trace_hybrid_startup.json"):
            trace = trace_summary(root, case, name)
            if trace is not None:
                case["native_lifecycle"][name.removesuffix(".json").removeprefix("lifecycle_trace_")] = trace
        if case["candidate_id"] == REPRO_CANDIDATE:
            case["saved_a4_technical_reproduction"] = {
                "summary_binding": repro_binding,
                "candidate_row_sha256": a4_repro.get("candidate_row_sha256"),
                "current_hybrid_startup_gate": a4_repro.get("current_hybrid_startup_gate"),
                "current_legacy_immediate_idm_gate": a4_repro.get("current_legacy_immediate_idm_gate"),
                "current_exact_expert_ego_idm_matrix": {
                    "status": (a4_repro.get("current_exact_expert_ego_idm_matrix") or {}).get("status"),
                    "task_view_status": (a4_repro.get("current_exact_expert_ego_idm_matrix") or {}).get("task_view_status"),
                    "task_view_reasons": (a4_repro.get("current_exact_expert_ego_idm_matrix") or {}).get("task_view_reasons"),
                    "report_sha256": (a4_repro.get("current_exact_expert_ego_idm_matrix") or {}).get("report_sha256"),
                },
                "native_lifecycle_summary": a4_repro.get("native_lifecycle"),
                "late_native_births_idm_gate_probe": a4_repro.get("late_native_births_idm_gate_probe"),
                "source_task_selector_evidence": a4_repro.get("source_task_selector_evidence"),
                "task_suitability": a4_repro.get("task_suitability"),
            }
        else:
            case["saved_a4_technical_reproduction"] = None
    reconciliation = {
        "forensics_producer_source_commit": FORENSICS_SOURCE_COMMIT,
        "forensics_producer_path": FORENSICS_PRODUCER_PATH,
        "forensics_producer_sha256": producer_sha,
        "pinned_b1_b4_history_prefix_sha256": b1_b4_prefix_sha,
        "retention_review_index_sha256": review_index_sha,
        "history_chain_records_verified": len(batch_history), "b1_b4_prefix_matches_pinned_sha": True,
        "ledgers": ledger_evidence, "primary_identity_order_checks": identity_order_checks,
        "primary_row_count": len(all_cases), "unique_primary_candidate_ids": len({c["candidate_id"] for c in all_cases}),
        "unique_primary_source_window_identities": len({c["identity_key"] for c in all_cases}),
        "helper_verified_case_count": len(all_cases), "raw_input_groups_hash_verified": len(all_cases),
        "unique_raw_source_files_hash_verified": len(source_hash_cache),
        "review_index_l2_entries_including_fallbacks": sum(x.get("location") == 2 for x in review_index.get("cases", [])),
        "review_index_l2_primary_entries": sum(x.get("location") == 2 and not bool(x.get("phase_fallback")) for x in review_index.get("cases", [])),
        "review_index_l2_fallback_entries": sum(x.get("location") == 2 and bool(x.get("phase_fallback")) for x in review_index.get("cases", [])),
        "review_index_batch_source_checks": review_batch_checks,
        "manual_reviews_created": False,
        "a4_reproduction": repro_binding,
    }
    summary = make_summary(all_cases, fallbacks, reconciliation, review_index, a4_repro)
    report = {
        "schema_version": 1, "analysis_only": True, "protocol": "german_200_location2_retention_baseline_v1",
        "scope": "57 primary location-2 rows from immutable B1-B4 ledgers; location-2 fallbacks are listed separately; no native execution or review action",
        "evidence_inputs": {
            "existing_physical_forensics_producer": {
                "path": FORENSICS_PRODUCER_PATH, "source_commit": FORENSICS_SOURCE_COMMIT,
                "sha256": producer_sha,
            },
            "retention_history_b1_b4_prefix": {"path": HISTORY, "record_count": len(LEDGERS), "sha256": b1_b4_prefix_sha},
            "retention_review_index": {"path": REVIEW_INDEX, "sha256": review_index_sha},
            "retention_review_index_report": {"path": "docs/audits/german_200_retention_review_index.md", "sha256": sha256(root / "docs/audits/german_200_retention_review_index.md")},
            "technical_reject_reproduction": repro_binding,
            "technical_reject_reproduction_report": {"path": "docs/plans/step_2/2_german_200_workstream_a_a4_reproduction_report_20261127.md", "sha256": sha256(root / "docs/plans/step_2/2_german_200_workstream_a_a4_reproduction_report_20261127.md")},
            "retention_batch_report": {"path": "docs/audits/german_200_retention_batch_004.md", "sha256": sha256(root / "docs/audits/german_200_retention_batch_004.md")},
            "prior_bc_physical_forensics": {"path": "docs/audits/german_200_bc_physical_forensics.md", "sha256": sha256(root / "docs/audits/german_200_bc_physical_forensics.md")},
        },
        "definitions": {
            "primary_identity_key": "frozen source_window_identity_sha256; candidate_id is retained as a human-readable join key",
            "pair_identity": "recording plus sorted pair of source track IDs; recurring windows are listed, not treated as independent events",
            "unreviewable_pair": "saved physical_source_audit reviewable_annotation_overlap is not true; no physical truth is inferred",
            "pair_depth": "saved maximum_penetration_m from the physical source audit",
            "pair_duration": "sampled overlap count divided by scene sample rate; contiguous span only emitted where full coverage can be established",
            "ego_task_proximity": "minimum timed center distance from valid converted-scene XY samples, with scene step and denominator; a derived measurement, not a gate result",
            "complexity": "frozen source context moving/stationary actor counts, combinatorial pair opportunities, and saved converted-scene concurrency; descriptive only",
            "semantic_support": "saved flags and admission checks are not human adjudications; absent/pending means unknown",
        },
        "summary": summary,
        "primary_cases": {case["identity_key"]: case for case in sorted(all_cases, key=lambda c: (c["batch"], c["queue_index"]))},
        "fallback_attempts_location_2_separate": fallbacks,
        "representative_raw_csv_map_and_conversion_cases": sorted(representatives),
        "same_recording_recurrent_overlap_pair_identities": summary["pair_identity_recurrence"],
        "incidental_provenance": {
            "actual_source_checkout_head": head,
            "current_retention_history_sha256": sha256(history_path),
            "retention_history_batches_after_b4_excluded": [x.get("batch_label") for x in history[len(LEDGERS):]],
            "current_retention_tip_batch_number": tip.get("batch_number"),
            "current_retention_tip_sha256": sha256(tip_path),
            "executed_argv": sys.argv,
            "note": "These mutable checkout and later-tip observations are incidental; summary, primary_cases, and fallback_attempts_location_2_separate are the stable B1-B4 comparison sections.",
        },
        "commands": [
            "python scripts/location2_baseline.py --repo-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/worktrees/location2 --evidence-root /home/inigo/data/git/repo/student-project/geotransfer-gap-AD --output-dir /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline_rerun",
            "sha256sum /home/inigo/data/git/repo/student-project/geotransfer-gap-AD/runs/german_200_overnight/location2_baseline_rerun/location2_baseline.json",
        ],
    }
    output = output_dir / "location2_baseline.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(output), "sha256": sha256(output)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
