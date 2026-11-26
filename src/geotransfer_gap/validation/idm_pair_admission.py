"""Strict derived gate for IDM ego + IDM traffic with immediate startup."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.validation import idm_eligibility, scene_contract
from geotransfer_gap.validation.shared_admission import read_shared_admission


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "controller_pair_idm_idm_immediate_v1"


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _idm_role_check(record: dict[str, Any] | None, role: str, *, root: Path,
                    shared_path: Path, source_identity: dict[str, Any],
                    tool_hashes: dict[str, str], binary_sha256: str | None,
                    runtime_source_sha256: str | None, runtime_binary_sha256: str | None,
                    evaluation_ini_sha256: str | None, technical_gate_sha256: str | None,
                    shared_summary: dict[str, Any]) -> list[str]:
    prefix = f"{role}_"
    if record is None:
        return [prefix + "record_missing_or_malformed"]
    reasons = []
    if record.get("schema_version") != 1 or record.get("protocol_version") != idm_eligibility.PROTOCOL_VERSION:
        reasons.append(prefix + "record_schema_or_protocol_version_mismatch")
    reasons.extend(idm_eligibility.fingerprint_mismatches(
        record, role=role, traffic_protocol="idm", source_identity=source_identity,
        tool_sha256=tool_hashes, binary_sha256=binary_sha256,
        runtime_source_sha256=runtime_source_sha256,
    ))
    binding = _object(record.get("binding"))
    scene_root = record.get("scene_root")
    if not isinstance(scene_root, str) or Path(scene_root).resolve() != root:
        reasons.append(prefix + "scene_root_stale")
    if record.get("startup_policy") != "immediate":
        if record.get("traffic_protocol") == "hybrid_startup" and record.get("startup_policy") == "source_hold":
            reasons.append(prefix + "legacy_hybrid_startup_is_not_matrix_source_hold")
        elif record.get("startup_policy") == "source_hold":
            reasons.append(prefix + "source_hold_is_not_immediate_startup")
        else:
            reasons.append(prefix + "startup_policy_mismatch")
    try:
        bound_shared_path = Path(binding.get("shared_record_path", "")).resolve()
    except (TypeError, ValueError):
        bound_shared_path = None
    if bound_shared_path != shared_path:
        reasons.append(prefix + "shared_record_binding_missing_or_stale")
    if binding.get("shared_source_identity") != source_identity:
        reasons.append(prefix + "shared_source_identity_stale")
    if record.get("shared_admission") != shared_summary:
        reasons.append(prefix + "shared_summary_binding_stale")
    if binding.get("shared_validity_status") != _object(shared_summary.get("shared_validity")).get("status"):
        reasons.append(prefix + "shared_technical_status_binding_stale")
    if binding.get("technical_gate_sha256") != technical_gate_sha256:
        reasons.append(prefix + "technical_gate_binding_stale")
    if binding.get("runtime_binary_sha256") != runtime_binary_sha256:
        reasons.append(prefix + "runtime_binary_stale")
    if binding.get("evaluation_ini_sha256") != evaluation_ini_sha256:
        reasons.append(prefix + "evaluation_ini_stale")
    if _object(record.get("protocol_fidelity")).get("status") != "current":
        reasons.append(prefix + "protocol_fidelity_not_current")
    if _object(record.get("native_proof")).get("status") != "current":
        reasons.append(prefix + "native_role_proof_not_current")
    if _object(record.get("eligibility")).get("controller_input_status") != "current":
        reasons.append(prefix + "controller_input_not_current")
    return sorted(set(reasons))


def _task_view_mismatches(shared: dict[str, Any], view: dict[str, Any]) -> list[str]:
    if not isinstance(view, dict):
        return ["task_view_missing_or_malformed"]
    manual = _object(shared.get("manual_evidence"))
    source = _object(shared.get("source_identity"))
    task_ids = manual.get("task_actor_ids")
    decision_steps = manual.get("interaction_decision_steps")
    source_steps = manual.get("task_actor_source_steps", {})
    reasons = []
    if view.get("source_identity") != source:
        reasons.append("task_view_source_identity_stale")
    for view_field, manual_field in (("manual_review_sha256", "review_sha256"),
                                     ("interaction_audit_sha256", "interaction_audit_sha256")):
        if not manual.get(manual_field) or view.get(view_field) != manual.get(manual_field):
            reasons.append(f"task_view_{view_field}_stale_or_missing")
    if manual.get("status") != "current" or not isinstance(task_ids, list) or not isinstance(source_steps, dict):
        return sorted(set(reasons + ["current_manual_task_context_missing"]))
    if not task_ids:
        uncontested = bool(manual.get("task_types")) and all(
            isinstance(name, str) and name.startswith("uncontested_") for name in manual["task_types"]
        )
        if (view.get("status") != "not_applicable" or not uncontested
                or view.get("task_actor_ids") != [] or view.get("required_steps") != []
                or view.get("observed_owner_coverage") != []):
            reasons.append("task_view_not_applicable_claim_mismatch")
        return sorted(set(reasons))

    steps = {step for step in decision_steps if type(step) is int} if isinstance(decision_steps, list) else set()
    steps.update(step for step in source_steps.values() if type(step) is int)
    required = sorted(steps)
    expected_context = {str(actor_id): source_steps.get(str(actor_id)) for actor_id in task_ids}
    if (view.get("status") != "current" or view.get("task_actor_ids") != task_ids
            or view.get("decision_steps") != sorted({s for s in decision_steps or [] if type(s) is int})
            or view.get("required_steps") != required
            or view.get("source_actor_context_steps") != expected_context):
        reasons.append("task_view_required_actor_or_step_set_mismatch")
    if view.get("reference_ego", {}).get("source_id") != source.get("ego_track_id"):
        reasons.append("task_view_reference_ego_identity_mismatch")
    if view.get("reference_ego", {}).get("steps") != required:
        reasons.append("task_view_reference_ego_steps_mismatch")

    coverage = view.get("observed_owner_coverage")
    if not isinstance(coverage, list):
        return sorted(set(reasons + ["task_view_owner_coverage_missing"]))
    expected = {(source.get("ego_track_id"), step, "reference_ego") for step in required}
    expected.update((actor_id, step, "task_actor") for actor_id in task_ids for step in required)
    actual = []
    generations: dict[int, set[int]] = {}
    owner_roles: dict[int, set[str]] = {}
    for item in coverage:
        if not isinstance(item, dict):
            reasons.append("task_view_owner_row_malformed")
            continue
        actor_id, step, role = item.get("source_id"), item.get("step"), item.get("role")
        kind = "reference_ego" if role == "reference_ego" else "task_actor"
        actual.append((actor_id, step, kind))
        if (item.get("present") is not True or item.get("native_present") is not True
                or item.get("source_valid") is not True
                or item.get("mode_readback_matches") is not True):
            reasons.append(f"task_view_actor_lifecycle_invalid:{actor_id}:{step}")
        generation = item.get("lifetime_generation")
        if type(generation) is int:
            generations.setdefault(actor_id, set()).add(generation)
        else:
            reasons.append(f"task_view_lifetime_generation_missing:{actor_id}:{step}")
        mode = item.get("planned_native_mode")
        if kind == "reference_ego":
            valid_owner = actor_id == source.get("ego_track_id") and mode == 2 and role == "reference_ego"
        else:
            valid_owner = (actor_id in task_ids and role in ("traffic", "context")
                           and mode == (1 if role == "traffic" else 2)
                           and (role != "traffic" or item.get("native_route_valid") is True))
            owner_roles.setdefault(actor_id, set()).add(role)
        if not valid_owner:
            reasons.append(f"task_view_native_owner_invalid:{actor_id}:{step}")
    if len(actual) != len(set(actual)) or set(actual) != expected:
        reasons.append("task_view_owner_coverage_incomplete_or_extra")
    if any(len(values) != 1 for values in generations.values()):
        reasons.append("task_view_actor_lifetime_changed_during_reviewed_steps")
    if any(len(values) != 1 for values in owner_roles.values()):
        reasons.append("task_view_actor_role_changed_during_reviewed_steps")
    return sorted(set(reasons))


def _traffic_protocol_mismatches(record: dict[str, Any]) -> list[str]:
    """Check payload-level native mechanics; a producer's status label is insufficient."""
    fidelity = _object(record.get("protocol_fidelity"))
    reasons = []
    if fidelity.get("protocol_compatibility") != {"status": "current", "reasons": []}:
        reasons.append("traffic_fidelity_protocol_compatibility_not_current")

    startup = _object(fidelity.get("startup"))
    if (startup.get("mode") != "immediate"
            or startup.get("protocol_version") != "matrix_immediate_startup_v1"
            or startup.get("release_schedule_producer_protocol") is not None
            or startup.get("release_count") != 0
            or startup.get("release_checks") != []
            or startup.get("status") != "not_applicable"
            or startup.get("passed") is not True):
        reasons.append("traffic_fidelity_startup_payload_invalid")

    for field in ("native_idm_traffic_intent_samples", "effective_native_idm_mode_samples"):
        count = fidelity.get(field)
        if type(count) is not int or count <= 0:
            reasons.append(f"traffic_fidelity_{field}_missing")
    if fidelity.get("native_route_failures") != []:
        reasons.append("traffic_fidelity_native_route_failures_present")
    routes = fidelity.get("actor_routes")
    if not isinstance(routes, list) or not routes:
        reasons.append("traffic_fidelity_actor_route_evidence_missing")
    else:
        allowed_sources = {"background_source_prior", "native_lane_route_fallback", "not_established"}
        for row in routes:
            if not isinstance(row, dict):
                reasons.append("traffic_fidelity_actor_route_row_malformed")
                continue
            sources = row.get("route_source_classification_from_coverage")
            if (type(row.get("source_id")) is not int
                    or type(row.get("idm_mode_frames")) is not int
                    or row["idm_mode_frames"] <= 0
                    or not isinstance(sources, list) or not sources
                    or any(source not in allowed_sources for source in sources)):
                reasons.append("traffic_fidelity_actor_route_evidence_invalid")
    parameters = fidelity.get("idm_parameters")
    expected_parameters = {"min_gap", "headway_time", "accel_max", "decel_max"}
    if (not isinstance(parameters, dict) or not expected_parameters <= parameters.keys()
            or any(type(parameters[key]) not in (int, float) or not math.isfinite(parameters[key])
                   for key in expected_parameters)
            or parameters["min_gap"] < 0 or parameters["headway_time"] < 0
            or parameters["accel_max"] <= 0 or parameters["decel_max"] <= 0):
        reasons.append("traffic_fidelity_idm_parameters_invalid")

    lifecycle = _object(fidelity.get("lifecycle"))
    idm_frames = _object(lifecycle.get("idm_actor_frames"))
    if (lifecycle.get("observed_frames") != 91
            or type(idm_frames.get("traffic")) is not int or idm_frames["traffic"] <= 0
            or type(fidelity.get("context_replay_samples")) is not int
            or fidelity["context_replay_samples"] < 0):
        reasons.append("traffic_fidelity_lifecycle_evidence_invalid")
    if _object(record.get("identity")).get("valid") is not True or record.get("identity_valid") is not True:
        reasons.append("traffic_fidelity_identity_not_current")
    source_prior = _object(fidelity.get("source_prior_scope"))
    if (source_prior.get("evidence") != "source trajectory coverage/applicability guard"
            or source_prior.get("native_route_ancestry") != "not separately observed"):
        reasons.append("traffic_fidelity_source_prior_scope_unclear")
    return sorted(set(reasons))


def derive_pair(shared: dict[str, Any], ego: dict[str, Any] | None,
                traffic: dict[str, Any] | None, traffic_fidelity: dict[str, Any] | None,
                *, root: Path, shared_path: Path, source_identity: dict[str, Any],
                tool_hashes: dict[str, str], binary_sha256: str | None,
                runtime_source_sha256: str | None, runtime_binary_sha256: str | None,
                evaluation_ini_sha256: str | None, traffic_producer_sha256: str,
                technical_gate_sha256: str | None,
                input_sha256: dict[str, str | None]) -> dict[str, Any]:
    """Combine current evidence without consulting rollout or performance results."""
    reasons = []
    if shared.get("shared_validity", {}).get("status") != "current":
        reasons.append("shared_technical_not_current")
    if shared.get("manual_evidence", {}).get("status") != "current":
        reasons.append("manual_task_review_not_current")
    if shared.get("task_eligibility", {}).get("status") != "eligible":
        reasons.append("shared_task_or_semantic_eligibility_not_established")
    if shared.get("source_identity") != source_identity:
        reasons.append("shared_source_identity_stale")
    if (not all(isinstance(value, str) and len(value) == 64 for value in
                (binary_sha256, runtime_binary_sha256, evaluation_ini_sha256, traffic_producer_sha256))
            or not isinstance(runtime_source_sha256, str)
            or not 16 <= len(runtime_source_sha256) <= 64
            or any(character not in "0123456789abcdef" for character in runtime_source_sha256.lower())):
        reasons.append("current_runtime_or_scene_fingerprint_missing")
    if set(input_sha256) != {"shared", "ego", "traffic", "traffic_fidelity"} or not all(
        isinstance(value, str) and len(value) == 64 for value in input_sha256.values()
    ):
        reasons.append("pair_input_evidence_hash_missing")

    shared_summary = idm_eligibility._shared_summary(shared)
    role_reasons = {
        "ego": _idm_role_check(
            ego, "ego", root=root, shared_path=shared_path, source_identity=source_identity,
            tool_hashes=tool_hashes, binary_sha256=binary_sha256,
            runtime_source_sha256=runtime_source_sha256,
            runtime_binary_sha256=runtime_binary_sha256,
            evaluation_ini_sha256=evaluation_ini_sha256,
            technical_gate_sha256=technical_gate_sha256,
            shared_summary=shared_summary,
        ),
        "traffic": _idm_role_check(
            traffic, "traffic", root=root, shared_path=shared_path, source_identity=source_identity,
            tool_hashes=tool_hashes, binary_sha256=binary_sha256,
            runtime_source_sha256=runtime_source_sha256,
            runtime_binary_sha256=runtime_binary_sha256,
            evaluation_ini_sha256=evaluation_ini_sha256,
            technical_gate_sha256=technical_gate_sha256,
            shared_summary=shared_summary,
        ),
    }
    for role, failures in role_reasons.items():
        reasons.extend(failures)

    fidelity_reasons = []
    if traffic_fidelity is None:
        fidelity_reasons.append("traffic_fidelity_record_missing_or_malformed")
    else:
        binding = _object(traffic_fidelity.get("binding"))
        if (traffic_fidelity.get("schema_version") != 1
                or traffic_fidelity.get("protocol_version") != "idm_reference_traffic_fidelity_v1"):
            fidelity_reasons.append("traffic_fidelity_schema_or_protocol_version_mismatch")
        fidelity_root = traffic_fidelity.get("scene_root")
        if not isinstance(fidelity_root, str) or Path(fidelity_root).resolve() != root:
            fidelity_reasons.append("traffic_fidelity_scene_root_stale")
        if traffic_fidelity.get("traffic_controller") != "idm":
            fidelity_reasons.append("traffic_fidelity_controller_mismatch")
        if traffic_fidelity.get("record_type") != "traffic_protocol_idm_immediate_v1":
            if traffic_fidelity.get("record_type") == "traffic_protocol_idm_source_hold_v1":
                fidelity_reasons.append("source_hold_traffic_record_not_immediate")
            else:
                fidelity_reasons.append("traffic_fidelity_protocol_mismatch")
        if traffic_fidelity.get("traffic_protocol") != "idm" or traffic_fidelity.get("startup_policy") != "immediate":
            fidelity_reasons.append("traffic_fidelity_startup_or_controller_mismatch")
        if traffic_fidelity.get("legacy_shared_protocol") != "idm":
            fidelity_reasons.append("traffic_fidelity_legacy_protocol_not_idm")
        if traffic_fidelity.get("source_identity") != source_identity:
            fidelity_reasons.append("traffic_fidelity_source_identity_stale")
        if traffic_fidelity.get("producer_sha256") != traffic_producer_sha256:
            fidelity_reasons.append("traffic_fidelity_producer_stale")
        if binding.get("tool_sha256") != tool_hashes:
            fidelity_reasons.append("traffic_fidelity_tool_fingerprint_stale")
        if binding.get("binary_sha256") != binary_sha256:
            fidelity_reasons.append("traffic_fidelity_binary_stale")
        if binding.get("runtime_source_sha256") != runtime_source_sha256:
            fidelity_reasons.append("traffic_fidelity_runtime_stale")
        if binding.get("runtime_binary_sha256") != runtime_binary_sha256:
            fidelity_reasons.append("traffic_fidelity_runtime_binary_stale")
        if binding.get("evaluation_ini_sha256") != evaluation_ini_sha256:
            fidelity_reasons.append("traffic_fidelity_evaluation_ini_stale")
        if binding.get("technical_gate_sha256") != technical_gate_sha256:
            fidelity_reasons.append("traffic_fidelity_technical_gate_stale")
        if binding.get("shared_summary") != shared_summary:
            fidelity_reasons.append("traffic_fidelity_shared_summary_stale")
        try:
            bound_shared_path = Path(binding.get("shared_record_path", "")).resolve()
        except (TypeError, ValueError):
            bound_shared_path = None
        if bound_shared_path != shared_path:
            fidelity_reasons.append("traffic_fidelity_shared_record_binding_stale")
        if binding.get("shared_record_sha256") != input_sha256.get("shared"):
            fidelity_reasons.append("traffic_fidelity_shared_record_hash_stale")
        if traffic_fidelity.get("status") != "current":
            fidelity_reasons.append("traffic_fidelity_gate_not_current")
            record_reasons = traffic_fidelity.get("reasons")
            if isinstance(record_reasons, list):
                fidelity_reasons.extend(reason for reason in record_reasons if isinstance(reason, str))
        fidelity_reasons.extend(_traffic_protocol_mismatches(traffic_fidelity))
        task_view = _object(traffic_fidelity.get("task_view"))
        task_reasons = _task_view_mismatches(shared, task_view)
        if task_reasons:
            fidelity_reasons.extend(task_reasons)
    reasons.extend(fidelity_reasons)

    status = "eligible" if not reasons else "not_established"
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "record_type": PROTOCOL_VERSION,
        "scene_root": str(root),
        "pair": {"ego_controller": "idm", "traffic_controller": "idm", "startup": "immediate"},
        "source_identity": source_identity,
        "evidence": {
            "shared_record_path": str(shared_path),
            "input_sha256": input_sha256,
            "role_status": {role: "current" if not failures else "not_established"
                             for role, failures in role_reasons.items()},
            "traffic_fidelity_status": (traffic_fidelity or {}).get("status", "not_established"),
            "task_view_status": (traffic_fidelity or {}).get("task_view", {}).get("status", "not_established"),
        },
        "gate_status": {
            "shared_technical": shared.get("shared_validity", {}).get("status", "not_established"),
            "task_and_semantic": shared.get("task_eligibility", {}).get("status", "not_established"),
            "ego_input": "current" if not role_reasons["ego"] else "not_established",
            "traffic_input": "current" if not role_reasons["traffic"] else "not_established",
            "traffic_fidelity": "current" if not fidelity_reasons else "not_established",
        },
        "research_admission": status,
        "reasons": sorted(set(reasons)),
        "outcome_used": False,
        "producer_sha256": sha256(Path(__file__)),
    }


def build_record(root: str | Path, shared_record_path: str | Path,
                 ego_record_path: str | Path, traffic_record_path: str | Path,
                 traffic_fidelity_path: str | Path) -> dict[str, Any]:
    root = Path(root).resolve()
    shared_path = Path(shared_record_path).resolve()
    paths = {"shared": shared_path, "ego": Path(ego_record_path).resolve(),
             "traffic": Path(traffic_record_path).resolve(),
             "traffic_fidelity": Path(traffic_fidelity_path).resolve()}
    shared = read_shared_admission(root, "idm", shared_path)
    role_records = {name: _read(path) for name, path in paths.items() if name in ("ego", "traffic")}
    traffic_fidelity = _read(paths["traffic_fidelity"])
    try:
        contract = scene_contract.build(root, "expert")
        source_identity = shared.get("source_identity", {})
        runtime = late_spawn_runtime.load()
        runtime_binary_sha256 = sha256(runtime["runtime_binary"])
        tool_hashes = idm_eligibility._tool_hashes()
        traffic_producer_sha256 = sha256(Path(idm_traffic_fidelity_path()))
        return derive_pair(
            shared, role_records["ego"], role_records["traffic"], traffic_fidelity,
            root=root, shared_path=shared_path, source_identity=source_identity,
            tool_hashes=tool_hashes,
            binary_sha256=contract.get("files", {}).get("scene_binary", {}).get("sha256"),
            runtime_source_sha256=runtime.get("runtime_source_sha256"),
            runtime_binary_sha256=runtime_binary_sha256,
            evaluation_ini_sha256=contract.get("files", {}).get("evaluation_ini", {}).get("sha256"),
            traffic_producer_sha256=traffic_producer_sha256,
            technical_gate_sha256=shared.get("shared_validity", {}).get("technical_gate_sha256"),
            input_sha256={name: sha256(path) if path.is_file() else None for name, path in paths.items()},
        )
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
            "record_type": PROTOCOL_VERSION, "scene_root": str(root),
            "pair": {"ego_controller": "idm", "traffic_controller": "idm", "startup": "immediate"},
            "source_identity": shared.get("source_identity"),
            "gate_status": {}, "research_admission": "not_established",
            "reasons": [f"current_pair_inputs_unavailable:{type(exc).__name__}:{exc}"],
            "outcome_used": False, "producer_sha256": sha256(Path(__file__)),
        }


def idm_traffic_fidelity_path() -> Path:
    from geotransfer_gap.validation import idm_traffic_fidelity

    return Path(idm_traffic_fidelity.__file__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shared-record", type=Path, required=True)
    parser.add_argument("--ego-record", type=Path, required=True)
    parser.add_argument("--traffic-record", type=Path, required=True)
    parser.add_argument("--traffic-fidelity-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    artifacts = settings().artifacts.resolve()
    root = args.root.resolve()
    if output.exists():
        raise FileExistsError(f"fresh IDM pair output already exists: {output}")
    if output == root or root in output.parents or output == artifacts or artifacts in output.parents:
        raise ValueError("IDM pair output must be outside the scene and configured artifacts tree")
    record = build_record(root, args.shared_record, args.ego_record, args.traffic_record,
                          args.traffic_fidelity_record)
    write_json(output, record)
    print(json.dumps({"output": str(output), "research_admission": record["research_admission"],
                      "reasons": record["reasons"]}, indent=2))


if __name__ == "__main__":
    main()
