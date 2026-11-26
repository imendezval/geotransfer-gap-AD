"""Write versioned, outcome-free IDM traffic fidelity evidence.

Task-actor preservation is measured with a reference Expert ego and IDM
traffic, so an IDM ego collision cannot erase the evidence used for its own
admission.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.runtime.native_modes import NativeMovementMode as Mode
from geotransfer_gap.validation import idm_eligibility
from geotransfer_gap.validation.shared_admission import read_shared_admission


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "idm_reference_traffic_fidelity_v1"


def _task_view(shared: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    """Check reviewed task actors and the controlled reference ego at required steps."""
    manual = shared.get("manual_evidence", {})
    task_ids = manual.get("task_actor_ids")
    decision_steps = manual.get("interaction_decision_steps")
    source_steps = manual.get("task_actor_source_steps", {})
    task_types = manual.get("task_types", [])
    if manual.get("status") != "current" or not isinstance(task_ids, list):
        return {"status": "not_established", "reasons": ["current_manual_task_identity_missing"]}
    if not task_ids:
        uncontested = bool(task_types) and all(
            isinstance(name, str) and name.startswith("uncontested_") for name in task_types
        )
        return {
            "status": "not_applicable" if uncontested else "not_established",
            "reasons": [] if uncontested else ["reviewed_task_actors_missing"],
            "task_actor_ids": [],
            "required_steps": [],
            "decision_steps": [],
            "source_actor_context_steps": {},
            "source_identity": shared.get("source_identity"),
            "manual_review_sha256": manual.get("review_sha256"),
            "interaction_audit_sha256": manual.get("interaction_audit_sha256"),
            "observed_owner_coverage": [],
            "outcome_used": False,
        }
    if not isinstance(decision_steps, list) or not decision_steps:
        return {"status": "not_established", "reasons": ["reviewed_task_decision_steps_missing"]}

    source_steps = source_steps if isinstance(source_steps, dict) else {}
    required_steps = {step for step in decision_steps if type(step) is int}
    required_steps.update(step for step in source_steps.values() if type(step) is int)
    if not required_steps or any(not 0 <= step <= 90 for step in required_steps):
        return {"status": "not_established", "reasons": ["reviewed_task_context_steps_invalid"]}
    observations = probe.get("task_view_frames", {})
    ego_id = (probe.get("identity") or {}).get("ego_source_id")
    if ego_id != shared.get("source_identity", {}).get("ego_track_id"):
        return {"status": "not_established", "reasons": ["reference_ego_source_identity_mismatch"]}
    failures = []
    coverage = []

    def at_step(actor_id, step):
        return next((row for row in observations.get(actor_id, [])
                     if row.get("step") == step), None)

    for step in sorted(required_steps):
        ego = at_step(ego_id, step)
        ego_current = bool(
            ego and ego.get("present") is True and ego.get("source_valid") is True
            and ego.get("native_present") is True
            and ego.get("role") == "ego"
            and ego.get("planned_native_mode") == int(Mode.EXPERT_REPLAY)
            and ego.get("mode_readback_matches") is True
        )
        if not ego_current:
            failures.append(f"reference_ego_missing_at_step:{step}")
        else:
            coverage.append({"source_id": ego_id, "step": step, "role": "reference_ego",
                             "planned_native_mode": int(Mode.EXPERT_REPLAY), "source_valid": True,
                             "native_present": True, "present": True, "mode_readback_matches": True,
                             "lifetime_generation": ego.get("lifetime_generation"),
                             "native_route_valid": None})
        for actor_id in task_ids:
            actor = at_step(actor_id, step)
            if (not actor or actor.get("present") is not True
                    or actor.get("native_present") is not True
                    or actor.get("source_valid") is not True
                    or actor.get("mode_readback_matches") is not True):
                failures.append(f"task_actor_or_context_missing:{actor_id}:{step}")
                continue
            role, mode = actor.get("role"), actor.get("planned_native_mode")
            expected_mode = int(Mode.IDM) if role == "traffic" else int(Mode.EXPERT_REPLAY) if role == "context" else None
            if expected_mode is None or mode != expected_mode:
                failures.append(f"task_actor_native_owner_mismatch:{actor_id}:{step}")
                continue
            if role == "traffic":
                if actor.get("native_route_valid") is not True:
                    failures.append(f"task_traffic_route_missing:{actor_id}:{step}")
            coverage.append({"source_id": actor_id, "step": step, "role": role,
                             "planned_native_mode": mode, "source_valid": actor.get("source_valid"),
                             "native_present": actor.get("native_present"), "present": actor.get("present"),
                             "mode_readback_matches": actor.get("mode_readback_matches"),
                             "lifetime_generation": actor.get("lifetime_generation"),
                             "native_route_valid": actor.get("native_route_valid")})
    return {
        "status": "current" if not failures else "not_established",
        "reasons": sorted(set(failures)),
        "reference_ego": {"source_id": ego_id, "controller": "expert", "role": "ego",
                           "steps": sorted(required_steps)},
        "task_actor_ids": task_ids,
        "required_steps": sorted(required_steps),
        "decision_steps": sorted({step for step in decision_steps if type(step) is int}),
        "source_actor_context_steps": {
            str(actor_id): source_steps.get(str(actor_id)) for actor_id in task_ids
        },
        "source_identity": shared.get("source_identity"),
        "manual_review_sha256": manual.get("review_sha256"),
        "interaction_audit_sha256": manual.get("interaction_audit_sha256"),
        "observed_owner_coverage": coverage,
        "outcome_used": False,
    }


def build_record(root: str | Path, traffic_protocol: str,
                 shared_record_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    shared_record_path = Path(shared_record_path).resolve() if shared_record_path else None
    if traffic_protocol not in ("idm", "hybrid_startup"):
        raise ValueError(f"unsupported shared traffic protocol: {traffic_protocol}")
    shared = read_shared_admission(root, traffic_protocol, record_path=shared_record_path)
    try:
        probe = idm_eligibility._native_probe(root, traffic_protocol, ego_controller="expert")
    except Exception as exc:
        probe = {"available": False, "runtime_reasons": [f"native_probe_unavailable:{type(exc).__name__}:{exc}"]}
    tool_hashes = idm_eligibility._tool_hashes()
    startup = probe.get("startup", {})
    task_view = _task_view(shared, probe)
    traffic_rows = probe.get("role_actor_rows", {}).get("traffic", {})
    reasons = list(probe.get("runtime_reasons", []))
    if not probe.get("available"):
        reasons.extend(probe.get("runtime_reasons", ["native_probe_unavailable"]))
    if not probe.get("intent_samples", {}).get("traffic"):
        reasons.append("traffic_idm_intent_missing")
    if not probe.get("effective_mode_samples", {}).get("traffic"):
        reasons.append("traffic_native_idm_mode_missing")
    if probe.get("identity_valid") is not True:
        reasons.append("native_ego_identity_not_current")
    if probe.get("route_failures", {}).get("traffic"):
        reasons.append("traffic_native_route_invalid")
    if probe.get("dynamics_failures"):
        reasons.append("native_dynamics_invalid")
    if probe.get("lifecycle", {}).get("observed_frames") != 91:
        reasons.append("reference_lifecycle_window_incomplete")
    expected_startup = "immediate" if traffic_protocol == "idm" else "source_hold"
    if startup.get("mode") != expected_startup:
        reasons.append("startup_protocol_mismatch")
    if startup.get("status") not in ("current", "not_applicable"):
        reasons.append("startup_release_evidence_not_current")
    if not isinstance(probe.get("idm_parameters"), dict):
        reasons.append("native_idm_parameters_missing")
    lifecycle = probe.get("lifecycle", {})
    if lifecycle.get("idm_actor_frames", {}).get("traffic", 0) <= 0:
        reasons.append("traffic_idm_lifecycle_frames_missing")

    runtime = probe.get("runtime", {})
    binary_hash = probe.get("root_binary_sha256")
    startup_mode = startup.get("mode")
    traffic_route_summary = [
        {"source_id": source_id,
         "route_source_classification_from_coverage": sorted({sample.get("route_source", "not_established")
                                                               for sample in actor.get("route_samples", [])}),
         "source_prior_coverage_guard_passes": any(sample.get("source_prior_used") is True
                                                    for sample in actor.get("route_samples", [])),
         "idm_mode_frames": actor.get("idm_mode_frames", 0)}
        for source_id, actor in sorted(traffic_rows.items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "record_type": ("traffic_protocol_idm_immediate_v1" if startup_mode == "immediate"
                        else "traffic_protocol_idm_source_hold_v1" if startup_mode == "source_hold"
                        else "traffic_protocol_idm_unknown_startup_v1"),
        "scene_root": str(root),
        "traffic_controller": "idm",
        "traffic_protocol": "idm",
        "startup_policy": startup_mode,
        "legacy_shared_protocol": traffic_protocol,
        "source_identity": shared.get("source_identity"),
        "binding": {
            "shared_record_path": str(shared_record_path) if shared_record_path else None,
            "shared_record_sha256": sha256(shared_record_path) if shared_record_path and Path(shared_record_path).is_file() else None,
            "shared_summary": idm_eligibility._shared_summary(shared),
            "technical_gate_sha256": shared.get("shared_validity", {}).get("technical_gate_sha256"),
            "binary_sha256": binary_hash,
            "runtime_source_sha256": runtime.get("runtime_source_sha256"),
            "runtime_binary_sha256": sha256(runtime["runtime_binary"]) if runtime.get("runtime_binary") else None,
            "evaluation_ini_sha256": probe.get("evaluation_ini_sha256"),
            "tool_sha256": tool_hashes,
        },
        "status": "current" if not reasons else "not_established",
        "reasons": sorted(set(reasons)),
        "identity": probe.get("identity"),
        "identity_valid": probe.get("identity_valid") is True,
        "protocol_fidelity": {
            "startup": startup,
            "protocol_compatibility": {
                "status": "current" if traffic_protocol == "idm" else "not_established",
                "reasons": [] if traffic_protocol == "idm" else [
                    "legacy_hybrid_startup_is_not_matrix_source_hold_protocol"
                ],
            },
            "native_idm_traffic_intent_samples": probe.get("intent_samples", {}).get("traffic", 0),
            "effective_native_idm_mode_samples": probe.get("effective_mode_samples", {}).get("traffic", 0),
            "native_route_failures": probe.get("route_failures", {}).get("traffic", []),
            "actor_routes": traffic_route_summary,
            "idm_parameters": probe.get("idm_parameters"),
            "context_replay_samples": lifecycle.get("context_replay_samples", 0),
            "lifecycle": lifecycle,
            "source_prior_scope": {
                "policy": "background traffic only; ego uses native lane route",
                "evidence": "source trajectory coverage/applicability guard",
                "native_route_ancestry": "not separately observed",
            },
        },
        "task_view": task_view,
        "producer_sha256": sha256(Path(__file__)),
        "outcome_used": False,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--traffic-protocol", choices=("idm", "hybrid_startup"), required=True)
    parser.add_argument("--shared-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    root = args.root.resolve()
    artifacts = settings().artifacts.resolve()
    if output.exists():
        raise FileExistsError(f"fresh traffic fidelity output already exists: {output}")
    if output == root or root in output.parents or output == artifacts or artifacts in output.parents:
        raise ValueError("traffic fidelity output must be outside the scene and configured artifacts tree")
    record = build_record(args.root, args.traffic_protocol, args.shared_record)
    write_json(output, record)
    print({"output": str(output), "status": record["status"],
           "startup_policy": record["startup_policy"], "task_view": record["task_view"]["status"]})


if __name__ == "__main__":
    main()
