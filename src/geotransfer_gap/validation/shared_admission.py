"""Fail-closed reader and writer for shared scene/task admission evidence.

This module reads the legacy technical gate without refreshing it and checks
the source-linked manual rule/task evidence independently.  Controller input
and traffic protocol evidence remain separate dimensions and never inherit a
pass from the legacy SMART admission.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from geotransfer_gap.artifacts import read_json, sha256, write_json
from geotransfer_gap.config import PROJECT_ROOT
from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.validation import scene_contract
from geotransfer_gap.validation.audit_interaction_fidelity import source_evidence_digest


SCHEMA_VERSION = 1
TRAFFIC_PROTOCOLS = ("idm", "hybrid_startup")

# Keep this set in step with admit_scene.py.  These checks concern technical
# reconstruction/execution; semantic and task evidence is recomputed below.
_RESEARCH_ONLY_CHECKS = {
    "semantic_screen",
    "rule_audit_current",
    "semantic_review_current",
    "semantic_review_complete",
    "source_supported_irrelevance_plausible",
    "interaction_audit_current",
    "interaction_claim_supported",
    "exists:rule_applicability_audit.json",
    "exists:semantic_review.json",
    "exists:interaction_fidelity_audit.json",
    "exists:semantic_review_hybrid_startup.json",
    "exists:interaction_fidelity_audit_hybrid_startup.json",
    "exists:lifecycle_trace_hybrid_startup.json",
    "exists:counterfactual_hybrid_probe.json",
    "hybrid_trace_current",
    "hybrid_lifecycle",
    "hybrid_counterfactual",
    "hybrid_us_mechanical_parity",
    "counterfactual_lifecycle",
}

_REQUIRED_TECHNICAL_CHECKS = {
    "exists:evaluation_contract_expert.json",
    "exists:validation.json",
    "exists:map_audit.json",
    "exists:map_semantics_audit.json",
    "exists:physical_source_audit.json",
    "exists:replay_validation.json",
    "exists:evaluation_replay_probe.json",
    "exists:spawn_evaluation_validation.json",
    "exists:parked_evaluation_validation.json",
    "exists:lifecycle_trace_expert.json",
    "exists:counterfactual_probe.json",
    "contract_current",
    "evaluator_settings",
    "behavior_bench_clean",
    "binary_round_trip",
    "ego_route",
    "no_actor_crop",
    "continuation_goals",
    "goal_placed_near_window_end",
    "background_goals_clear_source",
    "geometry_source_current",
    "legal_lateral_route_permissions_current",
    "geometry",
    "semantics_current",
    "physical_source_current",
    "ego_boundary_clear",
    "source_box_overlaps_resolved",
    "round_trip_replay",
    "evaluation_replay",
    "births_and_exits",
    "parked",
    "expert_trace_current",
    "expert_lifecycle",
    "ego_goal_event",
    "goal_terminal_consistent",
    "refresh_commands",
}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _status(ok: bool, reasons: list[str]) -> str:
    return "current" if ok and not reasons else "not_established"


def _text_at_least(value: Any, minimum: int) -> bool:
    return isinstance(value, str) and len(value) >= minimum


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _step_list(value: Any, *, unique_minimum: int = 1, max_step: int = 90) -> bool:
    if not isinstance(value, list) or not all(type(step) is int for step in value):
        return False
    return len(set(value)) >= unique_minimum and all(0 <= step <= max_step for step in value)


def _technical_status(root: Path, traffic_protocol: str,
                      current_contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    testing = root / "testing"
    gate_path = testing / (
        "admission.json" if traffic_protocol == "idm" else "admission_hybrid_startup.json"
    )
    gate = _read_object(gate_path)
    reasons: list[str] = []
    checks = gate.get("checks") if gate else None
    if not gate:
        reasons.append("technical_gate_missing_or_malformed")
    if gate and gate.get("schema_version") != 1:
        reasons.append("technical_gate_schema_mismatch")
    if gate and gate.get("traffic_protocol") != traffic_protocol:
        reasons.append("technical_gate_protocol_mismatch")
    if gate and not scene_contract.contracts_equal(gate.get("contract"), current_contract):
        reasons.append("technical_contract_stale_or_wrong_scene")
    if not isinstance(checks, dict):
        reasons.append("technical_checks_missing_or_malformed")
        checks = {}
    required_checks = set(_REQUIRED_TECHNICAL_CHECKS)
    research_only_checks = set(_RESEARCH_ONLY_CHECKS)
    if traffic_protocol == "hybrid_startup":
        research_only_checks.add("exists:counterfactual_probe.json")
    validation = _read_object(testing / "validation.json")
    if validation and validation.get("source_late_arriving_track_ids"):
        required_checks.update({"exists:reset_evaluation_probe.json", "repeated_reset"})
    missing = sorted(required_checks - checks.keys())
    if missing:
        reasons.append("technical_checks_missing:" + ",".join(missing))
    technical_checks = {
        name: value for name, value in checks.items()
        if name not in research_only_checks
    }
    failures = sorted(name for name, value in technical_checks.items() if value is not True)
    if failures:
        reasons.append("technical_checks_failed:" + ",".join(failures))
    if gate and gate.get("technical_admitted") is not True:
        reasons.append("legacy_technical_admission_not_passed")
    ok = bool(gate) and not reasons
    return ({
        "status": _status(ok, reasons),
        "reasons": reasons,
        "technical_gate": str(gate_path),
        "technical_gate_sha256": sha256(gate_path) if gate_path.is_file() else None,
        "technical_checks": {k: checks.get(k) for k in sorted(required_checks)},
    }, gate)


def _review_path(testing: Path, traffic_protocol: str) -> Path:
    generic = testing / (
        "semantic_review.json" if traffic_protocol == "idm"
        else "semantic_review_hybrid_startup.json"
    )
    if generic.is_file():
        return generic
    # A current SMART review is accepted as a source of manual evidence only.
    # Its controller admission status is deliberately not read or copied.
    return testing / f"semantic_review_smart_{traffic_protocol}.json"


def _validate_registration(root: Path, current_contract: dict[str, Any], review: dict[str, Any]) -> bool:
    testing = root / "testing"
    registration = _read_object(testing / "source_image_registration.json")
    source_image = testing / str(review.get("source_image", "missing"))
    files = current_contract.get("files", {})
    try:
        with Path(files["source_recording_meta_csv"]["path"]).open(newline="") as stream:
            meta = next(csv.DictReader(stream))
        expected_scale = map_geometry.background_pixel_scale(meta)
    except (KeyError, OSError, StopIteration, ValueError, TypeError):
        return False
    try:
        source_image_is_local = source_image.resolve().is_relative_to(testing.resolve())
        scale_current = math.isclose(registration.get("pixel_scale_m", -1), expected_scale,
                                     abs_tol=1e-10) if registration else False
        image_current = (
            source_image_is_local and source_image.is_file()
            and review.get("source_image_sha256") == sha256(source_image)
        )
    except (TypeError, ValueError, OSError):
        return False
    return bool(
        registration
        and registration.get("schema_version") == 2
        and registration.get("registration_is_estimate") is False
        and registration.get("local_x_at_image_x0_m") == 0.0
        and registration.get("local_y_at_image_y0_m") == 0.0
        and scale_current
        and registration.get("background_sha256")
        == files.get("source_background_image", {}).get("sha256")
        and registration.get("binary_sha256")
        == files.get("scene_binary", {}).get("sha256")
        and registration.get("recording") == current_contract.get("recording")
        and image_current
    )


def _expected_rule_ids(audit: dict[str, Any]) -> dict[str, set[Any]]:
    def identifiers(rows, field):
        result = set()
        for index, item in enumerate(rows):
            value = item.get(field) if isinstance(item, dict) else None
            result.add(value if type(value) in (int, str) else f"<invalid-id:{field}:{index}>")
        return result

    return {
        "regulatory_element": identifiers(_list_or_empty(audit.get("governing_regulatory_elements")), "id"),
        "crosswalk": identifiers(_list_or_empty(audit.get("ego_box_crosswalk_contacts")), "lanelet_id"),
        "sign": identifiers(_list_or_empty(audit.get("nearby_source_signs")), "id"),
        "omitted_marking": identifiers(_list_or_empty(audit.get("nearby_omitted_markings")), "id"),
    }


def _rule_types(kind: str, source_id: Any, audit: dict[str, Any]) -> list[str]:
    if kind == "regulatory_element":
        row = next((item for item in _list_or_empty(audit.get("governing_regulatory_elements"))
                    if isinstance(item, dict) and item.get("id") == source_id), {})
        labels = []
        if any(isinstance(member, dict) and member.get("role") == "yield"
               for member in _list_or_empty(row.get("ego_members"))):
            labels.append("yield_priority")
        if any(isinstance(sign, dict) and sign.get("subtype") == "de206"
               for sign in _list_or_empty(row.get("signs"))):
            labels.append("stop_sign_obligation")
        return labels or ["regulatory_element"]
    return {
        "crosswalk": ["crosswalk_vru_context"],
        "sign": ["source_traffic_sign"],
        "omitted_marking": ["omitted_road_marking"],
    }.get(kind, ["unknown_rule_type"])


def _manual_evidence(root: Path, traffic_protocol: str,
                     current_contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    testing = root / "testing"
    review_path = _review_path(testing, traffic_protocol)
    audit_path = testing / "rule_applicability_audit.json"
    interaction_path = testing / (
        "interaction_fidelity_audit.json" if traffic_protocol == "idm"
        else "interaction_fidelity_audit_hybrid_startup.json"
    )
    lifecycle_path = testing / f"lifecycle_trace_{traffic_protocol}.json"
    review, audit, interaction = (
        _read_object(review_path), _read_object(audit_path), _read_object(interaction_path)
    )
    reasons: list[str] = []
    task_blockers: list[str] = []
    if review is None:
        reasons.append("manual_review_missing_or_malformed")
    if audit is None:
        reasons.append("rule_audit_missing_or_malformed")
    if interaction is None:
        reasons.append("interaction_task_evidence_missing_or_malformed")
    if review is None or audit is None or interaction is None:
        return ({
            "status": "not_established",
            "reasons": reasons,
            "review": str(review_path),
            "review_sha256": sha256(review_path) if review_path.is_file() else None,
            "rule_audit_sha256": sha256(audit_path) if audit_path.is_file() else None,
            "interaction_audit_sha256": sha256(interaction_path) if interaction_path.is_file() else None,
        }, None)

    binary_hash = current_contract.get("files", {}).get("scene_binary", {}).get("sha256")
    source_hashes = current_contract.get("files", {})
    audit_current = bool(
        audit.get("schema_version") == 10
        and audit.get("binary_sha256") == binary_hash
        and audit.get("lanelet_source_sha256")
        == source_hashes.get("source_lanelet2_map", {}).get("sha256")
        and audit.get("opendrive_source_sha256")
        == source_hashes.get("source_opendrive_map", {}).get("sha256")
        and audit.get("source_tracks_sha256")
        == source_hashes.get("source_tracks_csv", {}).get("sha256")
        and audit.get("ego_track_id") == current_contract.get("ego_track_id")
    )
    if not audit_current:
        reasons.append("rule_audit_not_bound_to_current_source_and_scene")
    review_bound = bool(
        review.get("schema_version") == 2
        and review.get("review_status") == "complete"
        and review.get("decision") == "admit"
        and review.get("scope") == "recorded_window_and_tested_interaction"
        and review.get("ego_track_id") == current_contract.get("ego_track_id")
        and review.get("binary_sha256") == binary_hash
        and review.get("rule_audit_sha256") == sha256(audit_path)
        and _validate_registration(root, current_contract, review)
    )
    if not review_bound:
        reasons.append("manual_review_stale_or_not_source_registered")

    expected = _expected_rule_ids(audit)
    resolutions = review.get("rule_resolutions")
    if not isinstance(resolutions, list):
        resolutions = []
    observed: dict[str, list[Any]] = {kind: [] for kind in expected}
    unsupported_rule_details: list[dict[str, Any]] = []
    for resolution in resolutions:
        kind = resolution.get("kind") if isinstance(resolution, dict) else None
        source_id = resolution.get("source_id") if isinstance(resolution, dict) else None
        if kind not in observed:
            reasons.append("manual_review_contains_unknown_rule_resolution")
            continue
        if type(source_id) not in (int, str):
            reasons.append(f"manual_review_invalid_rule_source_id:{kind}")
            continue
        observed[kind].append(source_id)
        rule_types = _rule_types(kind, source_id, audit)
        disposition = resolution.get("resolution")
        evidence_bound = (
            _text_at_least(resolution.get("source_evidence"), 80)
            and _step_list(resolution.get("source_steps"))
        )
        if not evidence_bound or disposition not in (
            "source_supported_irrelevance", "represented_in_planner"
        ):
            reasons.append(f"rule_resolution_missing_source_evidence:{kind}:{source_id}")
            unsupported_rule_details.append({
                "kind": kind, "source_id": source_id, "rule_types": rule_types,
                "reason": "missing_or_invalid_source_bound_resolution",
            })
        elif disposition == "represented_in_planner":
            # A representation claim is valid human evidence, but it is
            # controller-specific and cannot establish a shared PPO task gate.
            task_blockers.append(f"controller_specific_rule_representation:{kind}:{source_id}")
            unsupported_rule_details.append({
                "kind": kind, "source_id": source_id, "rule_types": rule_types,
                "reason": "controller_specific_representation_not_reusable_across_roles",
            })
    for kind, identifiers in expected.items():
        if set(observed[kind]) != identifiers or len(observed[kind]) != len(identifiers):
            reasons.append(f"manual_rule_coverage_incomplete:{kind}")
        for source_id in identifiers - set(observed[kind]):
            unsupported_rule_details.append({
                "kind": kind, "source_id": source_id,
                "rule_types": _rule_types(kind, source_id, audit),
                "reason": "no_manual_resolution",
            })
    expected_boundaries = {
        row.get("way_id") if type(row.get("way_id")) in (int, str)
        else f"<invalid-boundary:{index}>"
        for index, row in enumerate(_list_or_empty(audit.get("ego_lanelet_boundaries")))
        if isinstance(row, dict)
    }
    reviewed_boundaries = review.get("reviewed_boundary_way_ids")
    if (not isinstance(reviewed_boundaries, list)
            or not all(type(value) in (int, str) for value in reviewed_boundaries)
            or set(reviewed_boundaries) != expected_boundaries):
        reasons.append("manual_boundary_review_incomplete")
    surface_steps = review.get("source_surface_steps")
    if (
        not _text_at_least(review.get("source_surface_evidence"), 100)
        or not _step_list(surface_steps, unique_minimum=3)
        or not _text_at_least(review.get("boundary_and_lane_change_evidence"), 80)
    ):
        reasons.append("manual_source_route_or_surface_evidence_incomplete")

    interaction_current = _interaction_bound(
        interaction, review, traffic_protocol, current_contract, audit_path, lifecycle_path
    )
    if not interaction_current:
        reasons.append("source_task_interaction_evidence_stale_or_mismatched")

    task_types = review.get("eligible_interaction_types")
    task_actors = review.get("interaction_actor_ids")
    opportunities = {}
    for row in _list_or_empty(interaction.get("actor_opportunities")):
        if isinstance(row, dict) and type(row.get("track_id")) is int:
            opportunities[row["track_id"]] = row
    if (not isinstance(task_types, list) or not task_types
            or not all(isinstance(item, str) and item for item in task_types)):
        reasons.append("manual_task_type_missing")
    if not isinstance(task_actors, list):
        reasons.append("manual_task_actor_list_malformed")
        task_actors = []
    elif not all(type(actor_id) is int for actor_id in task_actors):
        reasons.append("manual_task_actor_list_malformed")
        task_actors = []
    elif len(set(task_actors)) != len(task_actors):
        reasons.append("manual_task_actor_list_malformed")
        task_actors = []
    if type(review.get("interaction_opportunity")) is not bool:
        reasons.append("manual_task_opportunity_flag_malformed")
    if review.get("interaction_opportunity") is True:
        if not task_actors or not _text_at_least(review.get("interaction_decision_evidence"), 120):
            reasons.append("manual_task_decision_evidence_missing")
        decision_steps = review.get("interaction_decision_steps")
        if not _step_list(decision_steps, unique_minimum=2):
            reasons.append("manual_task_decision_steps_missing")
        else:
            for actor_id in task_actors:
                opportunity = opportunities.get(actor_id)
                if not opportunity or not opportunity.get("preserved_for_claimed_interaction"):
                    reasons.append(f"task_actor_not_source_preserved:{actor_id}")
                    continue
                source_step = opportunity.get("source_box_step")
                if type(source_step) is not int or not any(type(step) is int and abs(step - source_step) <= 10
                           for step in decision_steps):
                    reasons.append(f"task_actor_outside_reviewed_decision_interval:{actor_id}")
    elif task_actors or not all(
        isinstance(item, str) and item.startswith("uncontested_")
        for item in task_types or []
    ):
        reasons.append("manual_task_uncontested_claim_malformed")

    # Candidate rules requiring planner representation are retained as an
    # explicit task block. Source-supported irrelevance is the only reusable
    # resolution in shared admission; SMART representation cannot transfer.
    manual_ok = not reasons
    return ({
        "status": _status(manual_ok, reasons),
        "reasons": sorted(set(reasons)),
        "review": str(review_path),
        "review_sha256": sha256(review_path),
        "review_kind": "generic" if "_smart_" not in review_path.name else "source_bound_manual_only",
        "rule_audit": str(audit_path),
        "rule_audit_sha256": sha256(audit_path),
        "interaction_audit": str(interaction_path),
        "interaction_audit_sha256": sha256(interaction_path),
        "task_types": task_types,
        "task_actor_ids": task_actors,
        "interaction_decision_steps": review.get("interaction_decision_steps", []),
        "task_actor_source_steps": {
            str(actor_id): opportunities.get(actor_id, {}).get("source_box_step")
            for actor_id in task_actors
        },
        "unsupported_rule_reasons": sorted(set(task_blockers)),
        "unsupported_applicable_rule_types": sorted({
            rule_type for item in unsupported_rule_details
            for rule_type in item["rule_types"]
        }),
        "unsupported_applicable_rules": unsupported_rule_details,
    }, review)


def _safe_interaction_digest(interaction: dict[str, Any]) -> str | None:
    try:
        return source_evidence_digest(interaction)
    except (KeyError, TypeError, ValueError):
        return None


def _interaction_bound(interaction: dict[str, Any], review: dict[str, Any],
                       traffic_protocol: str, current_contract: dict[str, Any],
                       audit_path: Path, lifecycle_path: Path) -> bool:
    source_hashes = current_contract.get("files", {})
    binary_hash = source_hashes.get("scene_binary", {}).get("sha256")
    return bool(
        interaction.get("schema_version") == 3
        and interaction.get("traffic_mode") == traffic_protocol
        and interaction.get("binary_sha256") == binary_hash
        and interaction.get("ego_track_id") == current_contract.get("ego_track_id")
        and interaction.get("evaluation_ini_sha256")
        == source_hashes.get("evaluation_ini", {}).get("sha256")
        and interaction.get("runtime_source_sha256")
        == current_contract.get("runtime_source_sha256")
        and audit_path.is_file()
        and interaction.get("rule_audit_sha256") == sha256(audit_path)
        and lifecycle_path.is_file()
        and interaction.get("idm_trace_sha256") == sha256(lifecycle_path)
        and interaction.get("source_evidence_digest") == _safe_interaction_digest(interaction)
        and review.get("interaction_source_digest") == interaction.get("source_evidence_digest")
    )


def _source_rule_blockers(technical_gate: dict[str, Any] | None,
                          *, evidence_current: bool) -> list[str]:
    if not evidence_current:
        return ["source_supported_irrelevance_plausible:stale_or_unknown"]
    checks = technical_gate.get("checks") if isinstance(technical_gate, dict) else None
    if isinstance(checks, dict) and checks.get("source_supported_irrelevance_plausible") is True:
        return []
    details = technical_gate.get("details") if isinstance(technical_gate, dict) else None
    raw = details.get("source_supported_irrelevance_plausible") if isinstance(details, dict) else None
    if isinstance(raw, list):
        named = [f"unresolved_applicable_rule:{value}" for value in raw
                 if isinstance(value, str) and value]
    else:
        named = []
    if not named:
        status = "false" if isinstance(checks, dict) and checks.get(
            "source_supported_irrelevance_plausible") is False else "unknown"
        named.append(f"source_supported_irrelevance_plausible:{status}")
    return named


def _task_eligibility(manual: dict[str, Any],
                      technical_gate: dict[str, Any] | None = None,
                      *, source_rule_evidence_current: bool = False) -> dict[str, Any]:
    if manual.get("status") != "current":
        return {"status": "not_established", "reasons": list(manual.get("reasons", []))}
    blockers = list(manual.get("unsupported_rule_reasons", []))
    blockers.extend(_source_rule_blockers(
        technical_gate, evidence_current=source_rule_evidence_current
    ))
    if blockers:
        return {"status": "blocked", "reasons": sorted(set(blockers))}
    return {"status": "eligible", "reasons": []}


def build_shared_admission(root: str | Path, traffic_protocol: str) -> dict[str, Any]:
    """Build the current shared record in memory without refreshing evidence."""
    if traffic_protocol not in TRAFFIC_PROTOCOLS:
        raise ValueError(f"unsupported traffic protocol: {traffic_protocol}")
    root = Path(root).resolve()
    reasons: list[str] = []
    try:
        current_contract = scene_contract.build(root, "expert")
        contract_hash = _canonical_sha256(scene_contract.identity(current_contract))
    except (OSError, ValueError, KeyError, TypeError) as error:
        current_contract = None
        contract_hash = None
        reasons.append(f"current_scene_contract_unavailable:{type(error).__name__}")

    if current_contract is None:
        shared = {"status": "not_established", "reasons": reasons,
                  "contract_sha256": None, "technical_gate_sha256": None,
                  "technical_checks": {}}
        manual = {"status": "not_established", "reasons": ["current_scene_contract_unavailable"]}
        technical_gate = None
    else:
        shared, technical_gate = _technical_status(root, traffic_protocol, current_contract)
        shared["contract_sha256"] = contract_hash
        manual, _ = _manual_evidence(root, traffic_protocol, current_contract)

    source_rule_evidence_current = bool(
        technical_gate
        and technical_gate.get("traffic_protocol") == traffic_protocol
        and current_contract is not None
        and scene_contract.contracts_equal(technical_gate.get("contract"), current_contract)
    )
    task_status = _task_eligibility(
        manual, technical_gate,
        source_rule_evidence_current=source_rule_evidence_current,
    )
    source_reference = None
    if current_contract is not None:
        source_reference = current_contract.get("scene_reference")
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "scene_admission_shared_v1",
        "traffic_protocol": traffic_protocol,
        "scene_root": str(root),
        "source_identity": {
            "reference": source_reference,
            "recording": current_contract.get("recording") if current_contract else None,
            "ego_track_id": current_contract.get("ego_track_id") if current_contract else None,
            "binary_sha256": (current_contract.get("files", {}).get("scene_binary", {}).get("sha256")
                              if current_contract else None),
            "contract_sha256": contract_hash,
        },
        "source_files": (
            current_contract.get("files", {}) if current_contract else {}
        ),
        "shared_validity": shared,
        "manual_evidence": manual,
        "task_eligibility": task_status,
        "controller_input": {"status": "not_established", "reasons": ["controller_specific_proof_required"]},
        "protocol": {"status": "not_established", "reasons": ["traffic_protocol_evidence_required"]},
        "technical_admission_sha256": shared.get("technical_gate_sha256"),
        "producer_sha256": sha256(Path(__file__)),
    }


def write_shared_admission(root: str | Path, traffic_protocol: str,
                           output_path: str | Path) -> dict[str, Any]:
    """Write only to the explicitly named destination."""
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"fresh shared admission output already exists: {output_path}")
    record = build_shared_admission(root, traffic_protocol)
    write_json(output_path, record)
    return record


def read_shared_admission(root: str | Path, traffic_protocol: str,
                          record_path: str | Path | None = None) -> dict[str, Any]:
    """Return fresh checks, optionally requiring a stored v1 record to match."""
    current = build_shared_admission(root, traffic_protocol)
    if record_path is None:
        return current
    stored = _read_object(Path(record_path))
    reasons: list[str] = []
    if stored is None:
        reasons.append("shared_record_missing_or_malformed")
    elif stored.get("schema_version") != SCHEMA_VERSION:
        reasons.append("shared_record_schema_mismatch")
    elif stored.get("record_type") != "scene_admission_shared_v1":
        reasons.append("shared_record_type_mismatch")
    elif stored.get("traffic_protocol") != traffic_protocol:
        reasons.append("shared_record_protocol_mismatch")
    elif stored.get("producer_sha256") != sha256(Path(__file__)):
        reasons.append("shared_record_producer_stale")
    elif stored.get("source_identity") != current.get("source_identity"):
        reasons.append("shared_record_source_identity_stale")
    else:
        for field in ("shared_validity", "manual_evidence", "task_eligibility"):
            if stored.get(field) != current.get(field):
                reasons.append(f"shared_record_{field}_stale")
    if reasons:
        current["shared_validity"] = {
            **current["shared_validity"], "status": "not_established",
            "reasons": sorted(set(current["shared_validity"].get("reasons", []) + reasons)),
        }
        current["manual_evidence"] = {
            **current["manual_evidence"], "status": "not_established",
            "reasons": sorted(set(current["manual_evidence"].get("reasons", []) + reasons)),
        }
        current["task_eligibility"] = {"status": "not_established", "reasons": reasons}
    return current


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--traffic-protocol", choices=TRAFFIC_PROTOCOLS, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Explicit new output path; existing admission files are never overwritten")
    args = parser.parse_args(argv)
    record = write_shared_admission(args.root, args.traffic_protocol, args.output)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "shared_validity": record["shared_validity"]["status"],
        "manual_evidence": record["manual_evidence"]["status"],
        "task_eligibility": record["task_eligibility"]["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
