"""Offline evidence matrix for the frozen German-200 B/C primary cases.

This module reads saved ledgers and reports only. It does not invoke admission,
conversion, simulation, selection, or planner code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


STATUSES = {
    "passed",
    "failed",
    "not_established",
    "not_applicable",
    "pending_human_review",
}

DEFAULT_BATCHES = {
    "B": Path("artifacts/german_200_v1_workstream_b"),
    "C": Path("artifacts/german_200_v1_runs/workstream_c_batch_001"),
}
DEFAULT_OUTPUT = Path(
    "artifacts/german_200_v1_runs/workstream_a_yield_diagnostics/matrix.json"
)

EVIDENCE_FILES = (
    "validation.json",
    "map_audit.json",
    "map_semantics_audit.json",
    "physical_source_audit.json",
    "rule_applicability_audit.json",
    "evaluation_contract_expert.json",
    "replay_validation.json",
    "evaluation_replay_probe.json",
    "lifecycle_trace_expert.json",
    "spawn_evaluation_validation.json",
    "parked_evaluation_validation.json",
    "reset_evaluation_probe.json",
    "lifecycle_trace_idm.json",
    "interaction_fidelity_audit.json",
    "counterfactual_probe.json",
    "lifecycle_trace_hybrid_startup.json",
    "interaction_fidelity_audit_hybrid_startup.json",
    "counterfactual_hybrid_probe.json",
    "admission_hybrid_startup.json",
    "source_image_registration.json",
)
EVIDENCE_BLOBS = (
    "conversion.log",
    "admit_scene.py.log",
    "testing/map_000000.bin",
    "testing/manifest.csv",
)

TRAFFIC_CHECKS = (
    "births_and_exits",
    "counterfactual_lifecycle",
    "hybrid_lifecycle",
    "hybrid_counterfactual",
)


def status_from_boolean_evidence(values: Iterable[Any]) -> str:
    """Classify only explicit, consistent booleans; missing/conflicting is unknown."""
    values = list(values)
    if not values or any(not isinstance(value, bool) for value in values):
        return "not_established"
    if len(set(values)) != 1:
        return "not_established"
    return "passed" if values[0] else "failed"


def map_route_status(reachable: Any, outside_steps: Any) -> str:
    """Map route passes only when both explicit geometry conditions pass."""
    if reachable is False or (isinstance(outside_steps, list) and outside_steps):
        return "failed"
    if reachable is True and outside_steps == []:
        return "passed"
    return "not_established"


def required_boolean_groups_status(groups: Iterable[Iterable[Any]]) -> str:
    """Require one consistent explicit result in every evidence group."""
    statuses = []
    for group in groups:
        values = list(group)
        if not values:
            return "not_established"
        status = status_from_boolean_evidence(values)
        if status == "not_established":
            return status
        statuses.append(status)
    return "failed" if "failed" in statuses else "passed"


def lifecycle_compatibility_status(trace_hash_verified: bool, gate_value: Any) -> tuple[str, str]:
    """Keep a saved gate marker separate from independently verified trace evidence."""
    marker = status_from_boolean_evidence([gate_value])
    if not trace_hash_verified:
        return "not_established", marker
    return marker, marker


def physical_source_status(
    physical: dict[str, Any], original_status: str, overlap_review: Any
) -> str:
    """Classify source-box evidence without clearing unresolved overlaps."""
    if (
        physical.get("ego_boundary_contact") is True
        or (physical.get("unreviewable_overlap_count") or 0) > 0
        or original_status == "source_physical_rejection"
    ):
        return "failed"
    overlap_count = physical.get("overlap_pair_count")
    if isinstance(overlap_count, int) and overlap_count > 0:
        return "passed" if overlap_review is True else "pending_human_review"
    if (
        physical.get("ego_boundary_contact") is False
        and physical.get("unreviewable_overlap_count") == 0
        and overlap_count == 0
    ):
        return "passed"
    return "not_established"


def register_unique_candidate_id(candidate_ids: set[str], candidate_id: Any) -> None:
    """Reject missing or duplicate candidate identities while building the matrix."""
    if not candidate_id or candidate_id in candidate_ids:
        raise ValueError(f"missing or ambiguous primary candidate identity: {candidate_id!r}")
    candidate_ids.add(candidate_id)


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _saved_file_hash_status(row: dict[str, Any], candidate_root: Path, rel: str) -> tuple[str, str | None]:
    path = candidate_root / rel
    if not path.is_file():
        return "not_established", None
    actual = _sha256(path)
    expected = (row.get("output_tree_sha256") or {}).get(rel)
    if not isinstance(expected, str):
        return "not_established", actual
    if actual != expected:
        raise ValueError(f"saved evidence hash mismatch for {path}: expected {expected}, got {actual}")
    return "passed", actual


def _same_identity(recorded: Any, frozen: Any) -> bool | None:
    if not isinstance(recorded, dict) or not isinstance(frozen, dict):
        return None
    keys = ("recording", "location", "ego_track_id", "first_frame", "last_frame")
    if any(key not in recorded or key not in frozen for key in keys):
        return None
    return all(recorded[key] == frozen[key] for key in keys)


def _source_hash_match(frozen: dict[str, Any], fingerprint: dict[str, Any]) -> bool | None:
    old = frozen.get("source_hashes")
    new = fingerprint.get("source_hashes")
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    old_keys = {
        "background_png_sha256": "background",
        "lanelet2_map_sha256": "lanelet_map",
        "opendrive_map_sha256": "opendrive_map",
        "recording_meta_csv_sha256": "recording_meta",
        "tracks_csv_sha256": "tracks",
        "tracks_meta_csv_sha256": "tracks_meta",
    }
    if any(old.get(old_key) is None or new.get(new_key) is None
           for old_key, new_key in old_keys.items()):
        return None
    return all(old[old_key] == new[new_key] for old_key, new_key in old_keys.items())


def _status_object(status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    return {"status": status, "evidence": evidence or {}}


def _evidence_refs(batch_name: str, batch_root: Path, row: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_root = Path(row.get("root", ""))
    testing = candidate_root / "testing"
    saved_tree = row.get("output_tree_sha256") or {}
    refs = []
    for name in EVIDENCE_FILES:
        path = testing / name
        rel = f"testing/{name}"
        if not path.is_file():
            refs.append({"path": f"{batch_name}/candidate_runs/{candidate_root.name}/{rel}", "status": "not_established"})
            continue
        actual = _sha256(path)
        recorded = saved_tree.get(rel)
        if name == "admission_hybrid_startup.json" and not isinstance(recorded, str):
            recorded = (row.get("technical_admission") or {}).get("gate_sha256")
        integrity = status_from_boolean_evidence(
            [actual == recorded] if isinstance(recorded, str) else []
        )
        refs.append({
            "path": f"{batch_name}/candidate_runs/{candidate_root.name}/{rel}",
            "sha256": actual,
            "ledger_sha256": recorded,
            "integrity_status": integrity,
            "interpreted": integrity == "passed",
        })
    for rel in EVIDENCE_BLOBS:
        path = candidate_root / rel
        if not path.is_file():
            refs.append({"path": f"{batch_name}/candidate_runs/{candidate_root.name}/{rel}", "status": "not_established"})
            continue
        actual = _sha256(path)
        recorded = saved_tree.get(rel)
        integrity = status_from_boolean_evidence(
            [actual == recorded] if isinstance(recorded, str) else []
        )
        refs.append({
            "path": f"{batch_name}/candidate_runs/{candidate_root.name}/{rel}",
            "sha256": actual,
            "ledger_sha256": recorded,
            "integrity_status": integrity,
            "interpreted": integrity == "passed",
        })
    return refs


def _validated_reports(row: dict[str, Any], testing: Path) -> dict[str, Any | None]:
    """Load only reports whose bytes are bound by the saved ledger fingerprints."""
    output_tree = row.get("output_tree_sha256") or {}
    reports = {}
    for name in EVIDENCE_FILES:
        path = testing / name
        if not path.is_file():
            reports[name] = None
            continue
        rel = f"testing/{name}"
        expected = output_tree.get(rel)
        if name == "admission_hybrid_startup.json" and not isinstance(expected, str):
            expected = (row.get("technical_admission") or {}).get("gate_sha256")
        if not isinstance(expected, str):
            reports[name] = None
            continue
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"saved evidence hash mismatch for {path}: expected {expected}, got {actual}"
            )
        reports[name] = _read_json(path)
    candidate_root = Path(row.get("root", ""))
    for rel in EVIDENCE_BLOBS:
        _saved_file_hash_status(row, candidate_root, rel)
    tech = row.get("technical_admission") or {}
    gate_hash = tech.get("gate_sha256")
    admission_hash = output_tree.get("testing/admission_hybrid_startup.json")
    if isinstance(gate_hash, str) and isinstance(admission_hash, str) and gate_hash != admission_hash:
        raise ValueError(f"gate hash disagrees with output-tree hash under {row.get('candidate_id')}")
    for failure in row.get("structured_failure_reports") or []:
        report_path = Path(failure.get("report", ""))
        if not report_path.is_absolute():
            report_path = testing / report_path.name
        if not report_path.is_file():
            raise ValueError(f"structured failure report missing: {report_path}")
        actual = _sha256(report_path)
        if actual != failure.get("report_sha256"):
            raise ValueError(f"structured failure report hash mismatch: {report_path}")
        rel = f"testing/{report_path.name}"
        saved = output_tree.get(rel)
        if not isinstance(saved, str) or saved != actual:
            raise ValueError(f"structured failure report is not output-tree bound: {report_path}")
    return reports


def _mode_probe_status(probe: dict[str, Any] | None, mode: str) -> tuple[str, dict[str, Any]]:
    if not isinstance(probe, dict):
        return "not_established", {"evidence_missing": True}
    modes = probe.get("modes")
    if not isinstance(modes, dict) or mode not in modes or not isinstance(modes[mode], dict):
        return "not_established", {"mode_result_missing": mode}
    result = modes[mode]
    passed = result.get("lifecycle_passed")
    status = status_from_boolean_evidence([passed])
    events = result.get("source_valid_missing")
    ghosts = result.get("prebirth_ghosts")
    postexit = result.get("postexit_presence")
    return status, {
        "lifecycle_passed": passed if isinstance(passed, bool) else None,
        "observed_steps": result.get("observed_steps"),
        "source_valid_missing_count": result.get("source_valid_missing_count"),
        "first_source_valid_missing": events[:5] if isinstance(events, list) else None,
        "prebirth_ghosts": ghosts[:5] if isinstance(ghosts, list) else None,
        "postexit_presence": postexit[:5] if isinstance(postexit, list) else None,
        "ego_first_terminal_step": result.get("ego_first_terminal_step"),
        "ego_terminal_state": result.get("ego_terminal_state"),
    }


def _spawn_mode_status(spawn: dict[str, Any] | None, mode: str) -> tuple[str, dict[str, Any]]:
    if not isinstance(spawn, dict):
        return "not_established", {"evidence_missing": True}
    result = (spawn.get("modes") or {}).get(mode)
    if not isinstance(result, dict):
        return "not_established", {"mode_result_missing": mode}
    passed = result.get("birth_passed")
    return status_from_boolean_evidence([passed]), {
        "birth_passed": passed if isinstance(passed, bool) else None,
        "late_tracks": result.get("late_tracks"),
        "first_step_displacement_m": result.get("first_step_displacement_m"),
        "max_birth_position_error_m": result.get("max_birth_position_error_m"),
        "post_goal_untested_birth_track_ids": result.get("post_goal_untested_birth_track_ids"),
        "preentry_events": result.get("preentry_events"),
        "postexit_appearances": result.get("postexit_appearances"),
    }


def _task_family(frozen: dict[str, Any]) -> str:
    families = frozen.get("source_task_families") or []
    return families[0] if families else "unreviewed_random_source_candidate"


def _case(batch_name: str, batch_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    frozen = row.get("frozen_row") or {}
    testing = Path(row.get("root", "")) / "testing"
    read = _validated_reports(row, testing)
    evidence_refs = _evidence_refs(batch_name, batch_root, row)
    validation = read["validation.json"]
    map_audit = read["map_audit.json"]
    physical_audit = read["physical_source_audit.json"]
    rule_audit = read["rule_applicability_audit.json"]
    admission = read["admission_hybrid_startup.json"]
    spawn = read["spawn_evaluation_validation.json"]
    input_fingerprint = row.get("input_fingerprint") or {}

    source_identity_ok = _same_identity(row.get("source_identity"), frozen)
    frozen_identity_ok = (
        row.get("input_fingerprint", {}).get("source_window_identity_sha256")
        == frozen.get("source_window_identity_sha256")
        if frozen.get("source_window_identity_sha256") else None
    )
    source_hashes_ok = _source_hash_match(frozen, input_fingerprint)
    context_ok = (row.get("context_identity") or {}).get("passed")
    round_trip_ok = validation.get("binary_round_trip") == "passed" if isinstance(validation, dict) else None
    conversion_hash_status, conversion_log_hash = _saved_file_hash_status(row, Path(row.get("root", "")), "conversion.log")
    binary_hash_status, converted_binary_hash = _saved_file_hash_status(row, Path(row.get("root", "")), "testing/map_000000.bin")
    conversion_hash_ok = True if conversion_hash_status == "passed" else None
    binary_hash_ok = True if binary_hash_status == "passed" else None
    validation_binary_hash = validation.get("binary_sha256") if isinstance(validation, dict) else None
    binary_digest_ok = (
        converted_binary_hash == validation_binary_hash
        if isinstance(converted_binary_hash, str) and isinstance(validation_binary_hash, str)
        else None
    )
    source_status = status_from_boolean_evidence(
        [source_identity_ok, frozen_identity_ok, source_hashes_ok, context_ok, round_trip_ok,
         conversion_hash_ok, binary_hash_ok, binary_digest_ok]
    )

    preflight_geometry = (row.get("source_preflight") or {}).get("geometry") or {}
    map_reachable = (
        map_audit.get("occupied_start_to_occupied_goal_reachable")
        if isinstance(map_audit, dict)
        else preflight_geometry.get("occupied_start_to_occupied_goal_reachable")
    )
    outside = (
        map_audit.get("ego_samples_outside_lanelet_polygons")
        if isinstance(map_audit, dict)
        else preflight_geometry.get("outside_lanelet_steps")
    )
    map_status = map_route_status(map_reachable, outside)

    preflight_physical = (row.get("source_preflight") or {}).get("physical") or {}
    gate_checks = admission.get("checks") if isinstance(admission, dict) else {}
    overlap_count = preflight_physical.get("overlap_pair_count")
    overlap_review = gate_checks.get("source_box_overlaps_resolved") if isinstance(gate_checks, dict) else None
    physical_status = physical_source_status(preflight_physical, row.get("status", ""), overlap_review)

    replay = read["replay_validation.json"]
    evaluation_replay = read["evaluation_replay_probe.json"]
    replay_gate = gate_checks.get("round_trip_replay") if isinstance(gate_checks, dict) else None
    evaluation_gate = gate_checks.get("evaluation_replay") if isinstance(gate_checks, dict) else None
    replay_report_value = replay.get("replay_passed") if isinstance(replay, dict) else None
    eval_report_value = evaluation_replay.get("evaluation_traffic_replay_passed") if isinstance(evaluation_replay, dict) else None
    replay_group = [value for value in (replay_report_value, replay_gate) if isinstance(value, bool)]
    eval_group = [value for value in (eval_report_value, evaluation_gate) if isinstance(value, bool)]
    expert_status = required_boolean_groups_status([replay_group, eval_group])

    spawn_dynamics = _spawn_mode_status(spawn, "dynamics")
    spawn_idm = _spawn_mode_status(spawn, "idm")
    cf_probe = read["counterfactual_probe.json"]
    cf_hybrid = read["counterfactual_hybrid_probe.json"]
    cf_modes = {}
    for mode in ("expert", "idm", "zero_action_dynamics"):
        status, details = _mode_probe_status(cf_probe, mode)
        cf_modes[f"counterfactual.{mode}"] = _status_object(status, details)
    hybrid_cf_status, hybrid_cf_details = _mode_probe_status(cf_hybrid, "hybrid_startup")
    cf_modes["counterfactual_hybrid_startup"] = _status_object(hybrid_cf_status, hybrid_cf_details)

    expert_trace = read["lifecycle_trace_expert.json"]
    idm_trace = read["lifecycle_trace_idm.json"]
    hybrid_trace = read["lifecycle_trace_hybrid_startup.json"]
    gate_values = admission.get("checks") if isinstance(admission, dict) else {}
    lifecycle_statuses = {}
    for mode, check, trace in (
        ("expert", "expert_lifecycle", expert_trace),
        ("hybrid_startup", "hybrid_lifecycle", hybrid_trace),
    ):
        value = gate_values.get(check) if isinstance(gate_values, dict) else None
        losses = (trace or {}).get("first_source_valid_losses") if isinstance(trace, dict) else None
        trace_hash_verified = read["lifecycle_trace_expert.json" if mode == "expert" else "lifecycle_trace_hybrid_startup.json"] is not None
        independent_status, gate_marker_status = lifecycle_compatibility_status(trace_hash_verified, value)
        lifecycle_statuses[mode] = _status_object(
            independent_status,
            {
                "gate_check": check,
                "gate_check_value": value if isinstance(value, bool) else None,
                "original_gate_marker": gate_marker_status,
                "trace_hash_verified": trace_hash_verified,
                "trace_observed_steps": (trace or {}).get("observed_steps") if isinstance(trace, dict) else None,
                "first_source_valid_losses": losses,
                "evidence_missing": not isinstance(trace, dict),
            },
        )
    idm_mode_status, idm_mode_details = _mode_probe_status(cf_probe, "idm")
    interaction = read["interaction_fidelity_audit.json"]
    interaction_hybrid = read["interaction_fidelity_audit_hybrid_startup.json"]

    rule_status = "pending_human_review" if isinstance(rule_audit, dict) else "not_established"
    if row.get("status") not in ("awaiting_human_review", "review_blocked") and not isinstance(rule_audit, dict):
        rule_status = "not_established"
    family = _task_family(frozen)
    task_status = "pending_human_review" if frozen.get("arm") == "Interactive100" else "not_applicable"
    rule_task = {
        "status": rule_status if rule_status == "pending_human_review" else task_status,
        "rule_review": _status_object(rule_status, {
            "review_status": (rule_audit or {}).get("review_status"),
            "applicability_flags": (row.get("semantic_applicability") or {}).get("applicability_flags"),
            "technical_gate_effect": (row.get("semantic_applicability") or {}).get("technical_gate_effect"),
        }),
        "task_claim": _status_object(task_status, {
            "arm": frozen.get("arm"),
            "family": family,
            "interaction_kinds": frozen.get("source_interaction_kinds", []),
            "actor_track_id": frozen.get("actor"),
            "selector_names": frozen.get("source_selector_names", []),
        }),
    }

    observed_types = (rule_audit or {}).get("planner_map_observation_types") if isinstance(rule_audit, dict) else None
    rules_visible = (rule_audit or {}).get("rules_7_8_visible_in_current_observation") if isinstance(rule_audit, dict) else None
    legacy_visibility_status = status_from_boolean_evidence([rules_visible])

    original_status = row.get("status", "not_established")
    tech = row.get("technical_admission")
    if isinstance(tech, dict) and isinstance(tech.get("technical_admitted"), bool):
        technical_status = "passed" if tech["technical_admitted"] else "failed"
    elif original_status in ("source_physical_rejection", "source_geometry_rejection"):
        technical_status = "not_applicable"
    else:
        technical_status = "not_established"
    research_flag = tech.get("research_admitted") if isinstance(tech, dict) else None
    if research_flag is True:
        research_status = "passed"
    elif original_status == "awaiting_human_review":
        research_status = "pending_human_review"
    elif original_status == "review_blocked":
        research_status = "pending_human_review"
    elif original_status == "technical_rejection":
        research_status = "not_applicable"
    elif original_status in ("source_physical_rejection", "source_geometry_rejection"):
        research_status = "not_applicable"
    else:
        research_status = "not_established"
    if original_status in ("awaiting_human_review", "review_blocked"):
        manual_status = "pending_human_review"
    elif original_status in ("source_physical_rejection", "source_geometry_rejection", "technical_rejection"):
        manual_status = "not_applicable"
    else:
        manual_status = "not_established"

    admission_checks = gate_checks if isinstance(gate_checks, dict) else None
    false_checks = sorted(key for key, value in admission_checks.items() if value is False) if admission_checks else []
    false_traffic_checks = [name for name in TRAFFIC_CHECKS if admission_checks and admission_checks.get(name) is False]
    output_tree = row.get("output_tree_sha256") or {}
    gate_hash = (tech or {}).get("gate_sha256") if isinstance(tech, dict) else None

    def trace_losses(trace: Any) -> list[dict[str, Any]] | None:
        if not isinstance(trace, dict):
            return None
        losses = trace.get("first_source_valid_losses")
        if not isinstance(losses, dict):
            return None
        result = []
        ego = frozen.get("ego_track_id")
        for actor, item in losses.items():
            if str(actor) == str(ego):
                continue
            current = item.get("current") or {}
            result.append({
                "track_id": int(actor) if str(actor).isdigit() else actor,
                "step": item.get("step"),
                "cause": item.get("cause"),
                "collision_state": current.get("collision_state"),
                "collided_with_index": current.get("collided_with_index"),
                "removed": current.get("removed"),
            })
        return result

    birth_failures = {}
    if isinstance(spawn, dict):
        for mode in ("dynamics", "idm"):
            state = spawn_mode = (spawn.get("modes") or {}).get(mode) or {}
            if spawn_mode.get("birth_passed") is False:
                birth_failures[mode] = {
                    "late_tracks": spawn_mode.get("late_tracks"),
                    "first_step_displacement_m": spawn_mode.get("first_step_displacement_m"),
                    "max_birth_position_error_m": spawn_mode.get("max_birth_position_error_m"),
                    "post_goal_untested_birth_track_ids": spawn_mode.get("post_goal_untested_birth_track_ids"),
                }

    attribution = None
    if original_status == "technical_rejection":
        counterfactual_failures = {
            key: value["evidence"]
            for key, value in cf_modes.items()
            if value["status"] == "failed"
        }
        attribution = {
            "gate_sha256": gate_hash,
            "gate_returncode": (tech or {}).get("gate_returncode") if isinstance(tech, dict) else None,
            "false_gate_checks": false_checks,
            "technical_traffic_failure_markers": false_traffic_checks,
            "gate_exclusion_reasons": (tech or {}).get("exclusion_reasons", []),
            "structured_failure_reports": row.get("structured_failure_reports"),
            "structured_birth_failures": birth_failures,
            "counterfactual_failed_mode_evidence": counterfactual_failures,
            "counterfactual_mode_status": {
                key: val["status"] for key, val in cf_modes.items()
            },
            "hybrid_startup_background_losses": trace_losses(hybrid_trace),
            "idm_background_losses": trace_losses(idm_trace),
            "hash_bound_evidence": {
                ref["path"]: ref["sha256"]
                for ref in evidence_refs
                if ref.get("integrity_status") == "passed"
                and ref["path"].split("/")[-1] in {
                    "admission_hybrid_startup.json",
                    "spawn_evaluation_validation.json",
                    "counterfactual_probe.json",
                    "counterfactual_hybrid_probe.json",
                    "lifecycle_trace_idm.json",
                    "lifecycle_trace_hybrid_startup.json",
                }
            },
        }

    dimensions = {
        "source_conversion_integrity": _status_object(source_status, {
            "source_identity_matches_frozen_row": source_identity_ok,
            "source_window_identity_sha256_matches": frozen_identity_ok,
            "source_hashes_match_frozen_row": source_hashes_ok,
            "context_identity_passed": context_ok if isinstance(context_ok, bool) else None,
            "binary_round_trip": validation.get("binary_round_trip") if isinstance(validation, dict) else None,
            "binary_sha256": validation.get("binary_sha256") if isinstance(validation, dict) else None,
            "conversion_log_sha256": conversion_log_hash,
            "converted_binary_sha256": converted_binary_hash,
            "converted_binary_hash_status": binary_hash_status,
            "conversion_log_hash_status": conversion_hash_status,
            "binary_report_digest_matches_file": binary_digest_ok,
            "source_hashes": input_fingerprint.get("source_hashes"),
            "source_window_identity_sha256": input_fingerprint.get("source_window_identity_sha256"),
        }),
        "map_route": _status_object(map_status, {
            "occupied_start_to_occupied_goal_reachable": map_reachable,
            "ego_samples_outside_lanelet_polygons": outside,
            "map_source_sha256": map_audit.get("source_map_sha256") if isinstance(map_audit, dict) else None,
            "binary_sha256": map_audit.get("binary_sha256") if isinstance(map_audit, dict) else None,
            "route_identity": {
                "start_lane": (validation or {}).get("ego_start_lane") if isinstance(validation, dict) else None,
                "goal_lane": (validation or {}).get("ego_goal_lane") if isinstance(validation, dict) else None,
                "reachable_by_successors": (validation or {}).get("ego_goal_lane_reachable_by_successors") if isinstance(validation, dict) else None,
            },
        }),
        "physical_source": _status_object(physical_status, {
            "ego_boundary_contact": preflight_physical.get("ego_boundary_contact"),
            "overlap_pair_count": overlap_count,
            "unreviewable_overlap_count": preflight_physical.get("unreviewable_overlap_count"),
            "physical_audit_sha256": preflight_physical.get("physical_audit_sha256"),
            "physical_reasons": (row.get("source_preflight") or {}).get("physical_reasons"),
            "unresolved_reviewable_pairs": (admission.get("details") or {}).get("source_box_overlaps_resolved") if isinstance(admission, dict) else None,
            "binary_sha256": physical_audit.get("binary_sha256") if isinstance(physical_audit, dict) else None,
        }),
        "expert_replay": _status_object(expert_status, {
            "replay_passed": replay.get("replay_passed") if isinstance(replay, dict) else None,
            "evaluation_traffic_replay_passed": evaluation_replay.get("evaluation_traffic_replay_passed") if isinstance(evaluation_replay, dict) else None,
            "round_trip_replay_gate_check": replay_gate if isinstance(replay_gate, bool) else None,
            "evaluation_replay_gate_check": evaluation_gate if isinstance(evaluation_gate, bool) else None,
            "both_replay_evidence_groups_available": bool(replay_group and eval_group),
            "strict_expert_match": evaluation_replay.get("strict_expert_match") if isinstance(evaluation_replay, dict) else None,
            "runtime_source_sha256": (read["evaluation_contract_expert.json"] or {}).get("runtime_source_sha256") if isinstance(read["evaluation_contract_expert.json"], dict) else None,
        }),
        "birth_exit_by_mode": {
            "dynamics": _status_object(*spawn_dynamics),
            "idm": _status_object(*spawn_idm),
            "expert_lifecycle": lifecycle_statuses["expert"],
            "hybrid_startup_lifecycle": lifecycle_statuses["hybrid_startup"],
        },
        "idm_native": _status_object(idm_mode_status, {
            **idm_mode_details,
            "idm_interaction_actor_opportunities": (interaction or {}).get("actor_opportunities") if isinstance(interaction, dict) else None,
            "interaction_audit_mode": (interaction or {}).get("traffic_mode") if isinstance(interaction, dict) else None,
            "hybrid_interaction_audit_mode": (interaction_hybrid or {}).get("traffic_mode") if isinstance(interaction_hybrid, dict) else None,
        }),
        "hybrid_startup_counterfactual": cf_modes["counterfactual_hybrid_startup"],
        "counterfactual_by_mode": cf_modes,
        "rule_task": rule_task,
        "manual_review": _status_object(manual_status, {
            "original_ledger_status": original_status,
            "review_manifest_entry_expected": original_status in ("awaiting_human_review", "review_blocked"),
        }),
        "planner_observability": _status_object("not_established", {
            "planner_map_observation_types": observed_types,
            "rules_7_8_visible_in_current_observation": rules_visible,
            "planner_specific_eligibility_evidence": "not_established",
            "review_status": rule_audit.get("review_status") if isinstance(rule_audit, dict) else None,
            "interpretation": "saved rule-audit observation fields only; no planner outcome used",
        }),
        "legacy_rule_visibility": _status_object(legacy_visibility_status, {
            "rules_7_8_visible_in_current_observation": rules_visible,
            "planner_map_observation_types": observed_types,
            "interpretation": "legacy map-observation field; not a planner eligibility result",
        }),
        "original_technical_research": _status_object(
            "pending_human_review" if original_status in ("awaiting_human_review", "review_blocked") else technical_status,
            {
                "original_ledger_status": original_status,
                "technical_status": technical_status,
                "technical_admitted": tech.get("technical_admitted") if isinstance(tech, dict) else None,
                "research_status": research_status,
                "research_admitted": research_flag if isinstance(research_flag, bool) else None,
                "gate_returncode": tech.get("gate_returncode") if isinstance(tech, dict) else None,
                "gate_sha256": gate_hash,
                "gate_exclusion_reasons": tech.get("exclusion_reasons") if isinstance(tech, dict) else None,
                "admission_checks": admission_checks,
                "diagnostic_findings": admission.get("diagnostic_findings") if isinstance(admission, dict) else None,
            },
        ),
    }

    root_name = Path(row.get("root", "")).name
    return {
        "batch": batch_name,
        "candidate_id": row.get("candidate_id"),
        "queue_index": row.get("queue_index"),
        "recording": frozen.get("recording"),
        "ego_track_id": frozen.get("ego_track_id"),
        "actor_track_id": frozen.get("actor"),
        "first_frame": frozen.get("first_frame"),
        "last_frame": frozen.get("last_frame"),
        "location": frozen.get("location"),
        "arm": frozen.get("arm"),
        "family": family,
        "interaction_kinds": frozen.get("source_interaction_kinds", []),
        "original_ledger_status": original_status,
        "technical_gate_evaluated": isinstance(tech, dict),
        "dimensions": dimensions,
        "technical_rejection_attribution": attribution,
        "evidence_files": evidence_refs,
        "integrity": {
            "output_tree_hash_count": len(output_tree),
            "selected_evidence_hash_count": sum(
                1 for ref in evidence_refs
                if "integrity_status" in ref
            ),
            "selected_evidence_hashes_matching": sum(
                1 for ref in evidence_refs
                if ref.get("integrity_status") == "passed"
            ),
            "selected_evidence_hash_mismatches": sum(
                1 for ref in evidence_refs
                if ref.get("integrity_status") == "failed"
            ),
            "selected_evidence_hashes_not_recorded": sum(
                1 for ref in evidence_refs
                if ref.get("integrity_status") == "not_established"
            ),
            "candidate_root": f"{batch_name}/candidate_runs/{root_name}",
        },
    }


def _counter_by(cases: list[dict[str, Any]], field: str) -> dict[str, dict[str, int]]:
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        key = str(case.get(field) or "unknown")
        groups[key][case["original_ledger_status"]] += 1
    return {key: dict(sorted(counter.items())) for key, counter in sorted(groups.items())}


def _ref(path: Path, expected_key: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "status": "not_established"}
    data = _read_json(path)
    if expected_key is None:
        return {"path": str(path), "sha256": _sha256(path), "status": "passed"}
    raw = data.get(expected_key) if isinstance(data, dict) else None
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "check": expected_key,
        "check_value": raw if isinstance(raw, bool) else None,
        "status": status_from_boolean_evidence([raw]),
    }


def build_matrix(batch_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    batch_roots = batch_roots or DEFAULT_BATCHES
    cases: list[dict[str, Any]] = []
    batch_records: dict[str, Any] = {}
    candidate_ids: set[str] = set()
    for name in ("B", "C"):
        root = Path(batch_roots[name])
        ledger_path = root / "batch_ledger.json"
        ledger = _read_json(ledger_path)
        if not isinstance(ledger, dict) or not isinstance(ledger.get("results"), list):
            raise ValueError(f"missing or malformed saved ledger: {ledger_path}")
        if len(ledger["results"]) != 24:
            raise ValueError(f"expected 24 primary results in {ledger_path}, got {len(ledger['results'])}")
        rows = ledger["results"]
        for row in rows:
            candidate_id = row.get("candidate_id")
            register_unique_candidate_id(candidate_ids, candidate_id)
            cases.append(_case(name, root, row))
        run_report_path = root / "batch_run_report.json"
        run_report = _read_json(run_report_path)
        manual_flag = run_report.get("manual_reviews_created") if isinstance(run_report, dict) else None
        batch_records[name] = {
            "batch_root": str(root),
            "queue_path": ledger.get("queue_path"),
            "queue_sha256": ledger.get("queue_sha256"),
            "primary_count": len(rows),
            "ledger": _ref(ledger_path),
            "batch_run_report": _ref(run_report_path),
            "manual_reviews_created": manual_flag if isinstance(manual_flag, bool) else None,
            "descriptive_report": _ref(root / "batch_descriptive_report.json") if name == "C" else None,
        }
    if len(cases) != 48:
        raise ValueError(f"expected 48 primary rows, got {len(cases)}")

    statuses = Counter(case["original_ledger_status"] for case in cases)
    gate_cases = [case for case in cases if case["technical_gate_evaluated"]]
    technical_pass = sum(case["dimensions"]["original_technical_research"]["evidence"]["technical_admitted"] is True for case in gate_cases)
    technical_fail = sum(case["dimensions"]["original_technical_research"]["evidence"]["technical_admitted"] is False for case in gate_cases)
    pending_research = sum(case["dimensions"]["original_technical_research"]["evidence"]["research_status"] == "pending_human_review" for case in cases)
    manual_flags = [batch_records[name]["manual_reviews_created"] for name in ("B", "C")]
    manual_reviews_created = (
        manual_flags[0]
        if all(isinstance(value, bool) for value in manual_flags) and len(set(manual_flags)) == 1
        else None
    )
    source_map_valid = [case for case in cases if case["dimensions"]["source_conversion_integrity"]["status"] == "passed" and case["dimensions"]["map_route"]["status"] == "passed"]
    tech_rejections = [case for case in cases if case["original_ledger_status"] == "technical_rejection"]
    failed_gate_counts = Counter()
    for case in tech_rejections:
        for check in (case.get("technical_rejection_attribution") or {}).get("technical_traffic_failure_markers", []):
            failed_gate_counts[check] += 1

    support_root = Path(batch_roots["B"])
    support_refs = {
        "source_lane_change_native_oracle": _ref(support_root / "audits/source_lane_change_native_oracle.json", "passed"),
        "hybrid_protocol_us_parity": _ref(support_root / "audits/hybrid_protocol_us_parity.json", "mechanical_parity_pass"),
        "source_support_provenance": _ref(support_root / "source_support_provenance.json"),
        "workstream_c_queue_verification": _ref(Path(batch_roots["C"]) / "source_queue_verification.json"),
    }
    return {
        "schema_version": 1,
        "producer": "geotransfer_gap.corpus.german_200_yield",
        "analysis_only": True,
        "scope": "48 frozen B/C primary cases only; alternates excluded; no population inference",
        "status_vocabulary": sorted(STATUSES),
        "batch_records": batch_records,
        "supporting_evidence": support_refs,
        "summary": {
            "primary_count": len(cases),
            "original_ledger_status_counts": dict(sorted(statuses.items())),
            "technical_gate_evaluated_count": len(gate_cases),
            "technical_gate_passed_count": technical_pass,
            "technical_gate_failed_count": technical_fail,
            "technical_gate_pass_fraction_all_primary": technical_pass / len(cases),
            "technical_gate_pass_fraction_gate_evaluated": technical_pass / len(gate_cases) if gate_cases else None,
            "research_pending_human_review_count": pending_research,
            "manual_reviews_created": manual_reviews_created,
            "source_conversion_and_map_route_passed_count": len(source_map_valid),
            "technical_rejection_count": len(tech_rejections),
            "technical_rejection_source_conversion_and_map_route_passed_count": sum(
                1 for case in tech_rejections
                if case["dimensions"]["source_conversion_integrity"]["status"] == "passed"
                and case["dimensions"]["map_route"]["status"] == "passed"
            ),
            "technical_rejection_physical_status_counts": dict(Counter(
                case["dimensions"]["physical_source"]["status"] for case in tech_rejections
            )),
            "technical_rejection_traffic_failure_marker_counts": dict(sorted(failed_gate_counts.items())),
            "by_batch": {
                name: dict(Counter(case["original_ledger_status"] for case in cases if case["batch"] == name))
                for name in ("B", "C")
            },
            "by_arm": _counter_by(cases, "arm"),
            "by_location": _counter_by(cases, "location"),
            "by_family": _counter_by(cases, "family"),
        },
        "cases": cases,
    }


def compact_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    """Small versioned row index suitable for tracking with the concise report."""
    compact_cases = []
    for case in matrix["cases"]:
        dimensions = case["dimensions"]
        compact_cases.append({
            "id": case["candidate_id"],
            "batch": case["batch"],
            "location": case["location"],
            "arm": case["arm"],
            "family": case["family"],
            "recording_ego_actor_frame": [case["recording"], case["ego_track_id"], case["actor_track_id"], case["first_frame"]],
            "original": case["original_ledger_status"],
            "source": dimensions["source_conversion_integrity"]["status"],
            "map_route": dimensions["map_route"]["status"],
            "physical": dimensions["physical_source"]["status"],
            "expert": dimensions["expert_replay"]["status"],
            "dynamics_birth": dimensions["birth_exit_by_mode"]["dynamics"]["status"],
            "idm_birth": dimensions["birth_exit_by_mode"]["idm"]["status"],
            "idm_native": dimensions["idm_native"]["status"],
            "hybrid_lifecycle": dimensions["birth_exit_by_mode"]["hybrid_startup_lifecycle"]["status"],
            "hybrid_counterfactual": dimensions["hybrid_startup_counterfactual"]["status"],
            "rule_review": dimensions["rule_task"]["rule_review"]["status"],
            "task_claim": dimensions["rule_task"]["task_claim"]["status"],
            "manual_review": dimensions["manual_review"]["status"],
            "planner_observability": dimensions["planner_observability"]["status"],
            "legacy_rule_visibility": dimensions["legacy_rule_visibility"]["status"],
            "technical": dimensions["original_technical_research"]["evidence"]["technical_status"],
            "research": dimensions["original_technical_research"]["evidence"]["research_status"],
            "gate_sha256": dimensions["original_technical_research"]["evidence"]["gate_sha256"],
        })
    return {
        "schema_version": 1,
        "source_matrix_schema_version": matrix["schema_version"],
        "scope": matrix["scope"],
        "summary": matrix["summary"],
        "cases": compact_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--compact-output", type=Path)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    compact = None
    if args.compact_output:
        compact = args.compact_output if args.compact_output.is_absolute() else root / args.compact_output
    targets = [output] + ([compact] if compact else [])
    if len(set(targets)) != len(targets):
        raise ValueError("matrix and compact output paths must be different")
    occupied = [path for path in targets if path.exists()]
    if occupied:
        raise FileExistsError(f"refusing to overwrite output path: {occupied[0]}")
    batch_roots = {key: root / value for key, value in DEFAULT_BATCHES.items()}
    matrix = build_matrix(batch_roots)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    if compact:
        compact.parent.mkdir(parents=True, exist_ok=True)
        compact.write_text(json.dumps(compact_matrix(matrix), indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "primary_count": len(matrix["cases"]), "summary": matrix["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
