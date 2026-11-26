from __future__ import annotations

from pathlib import Path

import pytest

from geotransfer_gap.runtime.native_modes import NativeMovementMode as Mode
from geotransfer_gap.validation import idm_eligibility, idm_pair_admission as pair, idm_traffic_fidelity
from geotransfer_gap.validation.idm_traffic_fidelity import _task_view


H = "a" * 64


def evidence():
    root = Path("/tmp/idm-pair-scene").resolve()
    shared_path = Path("/tmp/idm-pair-shared.json").resolve()
    identity = {"reference": "scene:1", "recording": 1, "ego_track_id": 10,
                "binary_sha256": "b" * 64, "contract_sha256": "c" * 64}
    tools = {"producer": "d" * 64, "scheduler": "e" * 64}
    shared = {
        "traffic_protocol": "idm",
        "source_identity": identity,
        "shared_validity": {"status": "current", "technical_gate_sha256": "f" * 64},
        "manual_evidence": {
            "status": "current", "review_sha256": "1" * 64,
            "interaction_audit_sha256": "2" * 64,
            "task_types": ["lead_vehicle_braking_response"],
            "task_actor_ids": [20], "interaction_decision_steps": [2, 3],
            "task_actor_source_steps": {"20": 1},
        },
        "task_eligibility": {"status": "eligible", "reasons": []},
    }

    def role_record(role):
        return {
            "schema_version": 1,
            "protocol_version": idm_eligibility.PROTOCOL_VERSION,
            "record_type": f"controller_input_idm_{role}_v1",
            "scene_root": str(root), "role": role, "traffic_protocol": "idm",
            "startup_policy": "immediate", "source_identity": identity,
            "binding": {
                "shared_record_path": str(shared_path),
                "shared_source_identity": identity,
                "shared_validity_status": "current",
                "technical_gate_sha256": "f" * 64,
                "binary_sha256": identity["binary_sha256"],
                "runtime_source_sha256": "3" * 64,
                "runtime_binary_sha256": "4" * 64,
                "evaluation_ini_sha256": "5" * 64,
                "tool_sha256": tools,
            },
            "shared_admission": idm_eligibility._shared_summary(shared),
            "protocol_fidelity": {"status": "current"},
            "native_proof": {"status": "current"},
            "eligibility": {"controller_input_status": "current"},
            "run_outcome": {"collision": True, "goal": False},
        }

    coverage = []
    for step in (1, 2, 3):
        coverage.append({
            "source_id": 10, "step": step, "role": "reference_ego",
            "planned_native_mode": int(Mode.EXPERT_REPLAY), "lifetime_generation": 0,
            "native_present": True, "present": True, "source_valid": True,
            "mode_readback_matches": True, "native_route_valid": None,
        })
        coverage.append({
            "source_id": 20, "step": step, "role": "traffic",
            "planned_native_mode": int(Mode.IDM), "lifetime_generation": 0,
            "native_present": True, "present": True, "source_valid": True,
            "mode_readback_matches": True, "native_route_valid": True,
        })
    fidelity = {
        "schema_version": 1, "protocol_version": "idm_reference_traffic_fidelity_v1",
        "record_type": "traffic_protocol_idm_immediate_v1", "scene_root": str(root),
        "traffic_controller": "idm", "traffic_protocol": "idm", "startup_policy": "immediate",
        "legacy_shared_protocol": "idm", "source_identity": identity,
        "binding": {
            "shared_record_path": str(shared_path), "shared_record_sha256": "1" * 64,
            "shared_summary": idm_eligibility._shared_summary(shared),
            "technical_gate_sha256": "f" * 64,
            "binary_sha256": identity["binary_sha256"],
            "runtime_source_sha256": "3" * 64,
            "runtime_binary_sha256": "4" * 64,
            "evaluation_ini_sha256": "5" * 64,
            "tool_sha256": tools,
        },
        "status": "current", "reasons": [],
        "identity": {"valid": True}, "identity_valid": True,
        "protocol_fidelity": {
            "protocol_compatibility": {"status": "current", "reasons": []},
            "startup": {
                "mode": "immediate", "protocol_version": "matrix_immediate_startup_v1",
                "release_schedule_producer_protocol": None, "release_count": 0,
                "release_checks": [], "status": "not_applicable", "passed": True,
            },
            "native_idm_traffic_intent_samples": 3,
            "effective_native_idm_mode_samples": 3,
            "native_route_failures": [],
            "actor_routes": [{
                "source_id": 20, "route_source_classification_from_coverage": ["background_source_prior"],
                "source_prior_coverage_guard_passes": True, "idm_mode_frames": 3,
            }],
            "idm_parameters": {"min_gap": 1.0, "headway_time": 1.5,
                                "accel_max": 1.0, "decel_max": 2.0},
            "context_replay_samples": 3,
            "lifecycle": {"observed_frames": 91, "idm_actor_frames": {"traffic": 3}},
            "source_prior_scope": {
                "evidence": "source trajectory coverage/applicability guard",
                "native_route_ancestry": "not separately observed",
            },
        },
        "task_view": {
            "status": "current", "reasons": [], "task_actor_ids": [20],
            "required_steps": [1, 2, 3], "decision_steps": [2, 3],
            "source_actor_context_steps": {"20": 1},
            "source_identity": identity, "manual_review_sha256": "1" * 64,
            "interaction_audit_sha256": "2" * 64,
            "reference_ego": {"source_id": 10, "controller": "expert", "role": "ego", "steps": [1, 2, 3]},
            "observed_owner_coverage": coverage, "outcome_used": False,
        },
        "producer_sha256": "7" * 64,
        "run_outcome": {"collision": False, "goal": True},
    }
    current = {
        "shared": shared, "ego": role_record("ego"), "traffic": role_record("traffic"),
        "fidelity": fidelity, "root": root, "shared_path": shared_path,
        "identity": identity, "tools": tools,
    }
    current["derive"] = lambda: pair.derive_pair(
        current["shared"], current["ego"], current["traffic"], current["fidelity"],
        root=root, shared_path=shared_path, source_identity=identity, tool_hashes=tools,
        binary_sha256=identity["binary_sha256"], runtime_source_sha256="3" * 64,
        runtime_binary_sha256="4" * 64, evaluation_ini_sha256="5" * 64,
        traffic_producer_sha256="7" * 64, technical_gate_sha256="f" * 64,
        input_sha256={name: str(index) * 64 for index, name in enumerate(
            ("shared", "ego", "traffic", "traffic_fidelity"), 1)},
    )
    return current


def test_current_idm_pair_uses_reference_task_view_and_ignores_outcomes():
    case = evidence()

    record = case["derive"]()

    assert record["research_admission"] == "eligible"
    assert record["outcome_used"] is False
    assert record["reasons"] == []


@pytest.mark.parametrize("mutation, expected", [
    ("missing_role", "ego_record_missing_or_malformed"),
    ("wrong_role", "idm_record_role_stale"),
    ("wrong_startup", "ego_source_hold_is_not_immediate_startup"),
    ("stale_runtime", "idm_record_runtime_stale"),
    ("stale_producer", "traffic_fidelity_producer_stale"),
    ("unsupported_semantics", "shared_task_or_semantic_eligibility_not_established"),
    ("legacy_hybrid", "source_hold_traffic_record_not_immediate"),
    ("missing_shared_binding", "traffic_fidelity_shared_record_hash_stale"),
])
def test_pair_gate_fails_closed_on_stale_or_unsupported_inputs(mutation, expected):
    case = evidence()
    if mutation == "missing_role":
        case["ego"] = None
    elif mutation == "wrong_role":
        case["ego"]["role"] = "traffic"
    elif mutation == "wrong_startup":
        case["ego"]["startup_policy"] = "source_hold"
    elif mutation == "stale_runtime":
        case["ego"]["binding"]["runtime_source_sha256"] = "8" * 64
    elif mutation == "stale_producer":
        case["fidelity"]["producer_sha256"] = "9" * 64
    elif mutation == "unsupported_semantics":
        case["shared"]["task_eligibility"] = {"status": "blocked", "reasons": ["unsupported_rule"]}
    elif mutation == "legacy_hybrid":
        case["fidelity"]["record_type"] = "traffic_protocol_idm_source_hold_v1"
        case["fidelity"]["startup_policy"] = "source_hold"
        case["fidelity"]["legacy_shared_protocol"] = "hybrid_startup"
    elif mutation == "missing_shared_binding":
        case["fidelity"]["binding"]["shared_record_sha256"] = None
    record = case["derive"]()

    assert record["research_admission"] == "not_established"
    assert expected in record["reasons"]


def test_pair_rejects_missing_task_actor_or_context_coverage_even_if_status_says_current():
    case = evidence()
    case["fidelity"]["task_view"]["observed_owner_coverage"].pop()

    record = case["derive"]()

    assert record["research_admission"] == "not_established"
    assert "task_view_owner_coverage_incomplete_or_extra" in record["reasons"]


@pytest.mark.parametrize("mutation, expected", [
    ("stripped", "traffic_fidelity_startup_payload_invalid"),
    ("wrong_startup_protocol", "traffic_fidelity_startup_payload_invalid"),
    ("missing_intent", "traffic_fidelity_native_idm_traffic_intent_samples_missing"),
    ("route_failure", "traffic_fidelity_native_route_failures_present"),
    ("missing_lifecycle", "traffic_fidelity_lifecycle_evidence_invalid"),
    ("unproven_source_hold", "traffic_fidelity_protocol_compatibility_not_current"),
    ("invalid_identity", "traffic_fidelity_identity_not_current"),
])
def test_pair_checks_concrete_traffic_protocol_payload(mutation, expected):
    case = evidence()
    protocol = case["fidelity"]["protocol_fidelity"]
    if mutation == "stripped":
        case["fidelity"].pop("protocol_fidelity")
    elif mutation == "wrong_startup_protocol":
        protocol["startup"].pop("protocol_version")
    elif mutation == "missing_intent":
        protocol["native_idm_traffic_intent_samples"] = 0
    elif mutation == "route_failure":
        protocol["native_route_failures"] = [{"step": 4, "valid": False}]
    elif mutation == "missing_lifecycle":
        protocol["lifecycle"].pop("observed_frames")
    elif mutation == "unproven_source_hold":
        protocol["protocol_compatibility"] = {
            "status": "not_established",
            "reasons": ["legacy_hybrid_startup_is_not_matrix_source_hold_protocol"],
        }
    elif mutation == "invalid_identity":
        case["fidelity"]["identity_valid"] = False
    record = case["derive"]()

    assert record["research_admission"] == "not_established"
    assert expected in record["reasons"]


def test_reference_task_view_uses_exact_pre_step_frames_and_owner_readback():
    shared = evidence()["shared"]
    shared["source_identity"]["ego_track_id"] = 10
    frames = {}
    for actor_id, role, mode, route in (
        (10, "ego", Mode.EXPERT_REPLAY, None),
        (20, "traffic", Mode.IDM, True),
    ):
        frames[actor_id] = [{
            "step": step, "role": role, "planned_native_mode": int(mode),
            "mode_readback_matches": True, "present": True, "native_present": True,
            "source_valid": True, "lifetime_generation": 0,
            "native_route_valid": route,
        } for step in (1, 2, 3)]
    probe = {
        "identity": {"ego_source_id": 10},
        "task_view_frames": frames,
        "run_outcome": {"ego_collision_state_at_horizon": 9},
    }

    view = _task_view(shared, probe)

    assert view["status"] == "current"
    assert view["required_steps"] == [1, 2, 3]
    assert all(row["role"] in ("reference_ego", "traffic")
               for row in view["observed_owner_coverage"])
    probe["task_view_frames"][20] = [row for row in frames[20] if row["step"] != 2]
    missing = _task_view(shared, probe)
    assert missing["status"] == "not_established"
    assert "task_actor_or_context_missing:20:2" in missing["reasons"]


def test_traffic_fidelity_producer_fails_status_on_invalid_identity(monkeypatch):
    case = evidence()
    monkeypatch.setattr(idm_traffic_fidelity, "read_shared_admission",
                        lambda *_args, **_kwargs: case["shared"])
    monkeypatch.setattr(idm_eligibility, "_tool_hashes", lambda: {})
    monkeypatch.setattr(idm_eligibility, "_native_probe", lambda *_args, **_kwargs: {
        "available": True, "runtime_reasons": [], "identity_valid": False,
        "startup": {"mode": "immediate", "status": "not_applicable"},
        "intent_samples": {"traffic": 1}, "effective_mode_samples": {"traffic": 1},
        "route_failures": {"traffic": []}, "dynamics_failures": [],
        "lifecycle": {"observed_frames": 91, "idm_actor_frames": {"traffic": 1}},
        "idm_parameters": {"min_gap": 1.0}, "runtime": {},
        "root_binary_sha256": "b" * 64, "evaluation_ini_sha256": "c" * 64,
        "role_actor_rows": {"traffic": {}},
    })

    record = idm_traffic_fidelity.build_record(case["root"], "idm")

    assert record["status"] == "not_established"
    assert "native_ego_identity_not_current" in record["reasons"]


def test_legacy_hybrid_source_hold_is_diagnostic_not_matrix_compatibility(monkeypatch):
    case = evidence()
    monkeypatch.setattr(idm_traffic_fidelity, "read_shared_admission",
                        lambda *_args, **_kwargs: case["shared"])
    monkeypatch.setattr(idm_eligibility, "_tool_hashes", lambda: {})
    monkeypatch.setattr(idm_eligibility, "_native_probe", lambda *_args, **_kwargs: {
        "available": True, "runtime_reasons": [], "identity_valid": True,
        "startup": {"mode": "source_hold", "status": "current"},
        "intent_samples": {"traffic": 1}, "effective_mode_samples": {"traffic": 1},
        "route_failures": {"traffic": []}, "dynamics_failures": [],
        "lifecycle": {"observed_frames": 91, "idm_actor_frames": {"traffic": 1}},
        "idm_parameters": {"min_gap": 1.0}, "runtime": {},
        "root_binary_sha256": "b" * 64, "evaluation_ini_sha256": "c" * 64,
        "role_actor_rows": {"traffic": {}},
    })

    record = idm_traffic_fidelity.build_record(case["root"], "hybrid_startup")

    assert record["protocol_fidelity"]["protocol_compatibility"] == {
        "status": "not_established",
        "reasons": ["legacy_hybrid_startup_is_not_matrix_source_hold_protocol"],
    }
