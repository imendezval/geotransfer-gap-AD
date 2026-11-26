import json
from pathlib import Path

import numpy as np
import pytest

from geotransfer_gap.artifacts import sha256
from geotransfer_gap.runtime.actor_index import ActorKey, SourceActorID
from geotransfer_gap.validation.ppo_scene_proof import (
    validate_map_feature_block,
    validate_observation_row,
)
from geotransfer_gap.validation import shared_admission
from geotransfer_gap.validation.audit_interaction_fidelity import source_evidence_digest


def test_ppo_native_row_requires_current_actor_lifetime_and_slot():
    key = ActorKey(SourceActorID(190), 2)
    row = np.zeros(1151, dtype=np.float32)
    assert validate_observation_row(
        row, actor_key=key, expected_key=key, slot=4,
        source_valid=True, native_present=True,
    ).shape == (1151,)

    with pytest.raises(ValueError, match="missing"):
        validate_observation_row(
            None, actor_key=key, expected_key=key, slot=4,
            source_valid=True, native_present=True,
        )
    with pytest.raises(ValueError, match="identity/lifetime"):
        validate_observation_row(
            row, actor_key=key, expected_key=ActorKey(SourceActorID(190), 1), slot=4,
            source_valid=True, native_present=True,
        )
    with pytest.raises(ValueError, match="current source-valid"):
        validate_observation_row(
            row, actor_key=key, expected_key=key, slot=None,
            source_valid=True, native_present=True,
        )


def test_ppo_native_row_rejects_wrong_width_or_dtype():
    key = ActorKey(SourceActorID(200), 0)
    with pytest.raises(ValueError, match=r"float32\[1151\]"):
        validate_observation_row(
            np.zeros(1150, dtype=np.float32), actor_key=key, expected_key=key,
            slot=0, source_valid=True, native_present=True,
        )
    with pytest.raises(ValueError, match=r"float32\[1151\]"):
        validate_observation_row(
            np.zeros(1151, dtype=np.float64), actor_key=key, expected_key=key,
            slot=0, source_valid=True, native_present=True,
        )


def test_ppo_road_features_match_native_map_geometry_and_normalization():
    road_rows = np.zeros((128, 7), dtype=np.float32)
    road_rows[0] = [0.1, 0.0, 0.05, 0.001, 1.0, 0.0, 0.0]
    state = {"entities": [{
        "type": 4,
        "array_size": 2,
        "traj_x": [0.0, 10.0],
        "traj_y": [0.0, 0.0],
    }]}
    proof = validate_map_feature_block(road_rows, state, 0.0, 0.0, 1.0, 0.0)
    assert proof["status"] == "verified"
    assert proof["matched_segment_rows"] == 1
    assert proof["normalization"]["width_value"] == 0.001

    road_rows[0, 0] = 0.2
    with pytest.raises(ValueError, match="does not match normalized native map geometry"):
        validate_map_feature_block(road_rows, state, 0.0, 0.0, 1.0, 0.0)


def test_shared_reader_rejects_stale_source_identity(tmp_path, monkeypatch):
    current = {
        "schema_version": 1,
        "record_type": "scene_admission_shared_v1",
        "traffic_protocol": "hybrid_startup",
        "producer_sha256": sha256(Path(shared_admission.__file__)),
        "source_identity": {"contract_sha256": "current"},
        "shared_validity": {"status": "current", "reasons": []},
        "manual_evidence": {"status": "current", "reasons": []},
        "task_eligibility": {"status": "eligible", "reasons": []},
        "controller_input": {"status": "not_established"},
        "protocol": {"status": "not_established"},
    }
    old = {**current, "source_identity": {"contract_sha256": "stale"}}
    path = tmp_path / "scene_admission_shared_v1.json"
    path.write_text(json.dumps(old))
    monkeypatch.setattr(shared_admission, "build_shared_admission", lambda *_: current)

    result = shared_admission.read_shared_admission(
        tmp_path, "hybrid_startup", record_path=path
    )
    assert result["shared_validity"]["status"] == "not_established"
    assert "shared_record_source_identity_stale" in result["shared_validity"]["reasons"]
    assert result["task_eligibility"]["status"] == "not_established"


def test_shared_reader_rejects_stale_producer_and_record_type(tmp_path, monkeypatch):
    current = {
        "schema_version": 1,
        "record_type": "scene_admission_shared_v1",
        "traffic_protocol": "hybrid_startup",
        "producer_sha256": sha256(Path(shared_admission.__file__)),
        "source_identity": {"contract_sha256": "current"},
        "shared_validity": {"status": "current", "reasons": []},
        "manual_evidence": {"status": "current", "reasons": []},
        "task_eligibility": {"status": "eligible", "reasons": []},
        "controller_input": {"status": "not_established"},
        "protocol": {"status": "not_established"},
    }
    monkeypatch.setattr(shared_admission, "build_shared_admission", lambda *_: current)
    path = tmp_path / "shared.json"
    for stale, expected in (
        ({**current, "producer_sha256": "old"}, "shared_record_producer_stale"),
        ({**current, "record_type": "other"}, "shared_record_type_mismatch"),
    ):
        path.write_text(json.dumps(stale))
        result = shared_admission.read_shared_admission(
            tmp_path, "hybrid_startup", record_path=path
        )
        assert expected in result["shared_validity"]["reasons"]
        assert result["task_eligibility"]["status"] == "not_established"


def test_shared_writer_refuses_to_overwrite(tmp_path, monkeypatch):
    output = tmp_path / "scene_admission_shared_v1.json"
    output.write_text("preserve me")
    monkeypatch.setattr(shared_admission, "build_shared_admission",
                        lambda *_: pytest.fail("existing output must be rejected before build"))
    with pytest.raises(FileExistsError, match="fresh shared admission output"):
        shared_admission.write_shared_admission(tmp_path, "hybrid_startup", output)
    assert output.read_text() == "preserve me"


def test_source_bound_manual_review_does_not_clear_unsupported_rules():
    eligible = shared_admission._task_eligibility({
        "status": "current", "reasons": [], "unsupported_rule_reasons": [],
    }, {"checks": {"source_supported_irrelevance_plausible": True}},
        source_rule_evidence_current=True)
    representation_blocked = shared_admission._task_eligibility({
        "status": "current", "reasons": [],
        "unsupported_rule_reasons": ["controller_specific_rule_representation:crosswalk:77"],
    }, {"checks": {"source_supported_irrelevance_plausible": True}},
        source_rule_evidence_current=True)
    raw_rule_blocked = shared_admission._task_eligibility({
        "status": "current", "reasons": [], "unsupported_rule_reasons": [],
    }, {
        "checks": {"source_supported_irrelevance_plausible": False},
        "details": {"source_supported_irrelevance_plausible": [
            "ego_stop_sign_requires_stop_even_without_conflicting_traffic",
            "yield_lane_fast_crosspath_cyclist_190",
        ]},
    }, source_rule_evidence_current=True)
    missing_rule_gate = shared_admission._task_eligibility({
        "status": "current", "reasons": [], "unsupported_rule_reasons": [],
    })
    missing = shared_admission._task_eligibility({
        "status": "not_established", "reasons": ["manual_review_missing"],
    }, {"checks": {"source_supported_irrelevance_plausible": True}})
    assert eligible["status"] == "eligible"
    assert representation_blocked["status"] == "blocked"
    assert representation_blocked["reasons"] == ["controller_specific_rule_representation:crosswalk:77"]
    assert raw_rule_blocked["status"] == "blocked"
    assert raw_rule_blocked["reasons"] == [
        "unresolved_applicable_rule:ego_stop_sign_requires_stop_even_without_conflicting_traffic",
        "unresolved_applicable_rule:yield_lane_fast_crosspath_cyclist_190",
    ]
    assert missing_rule_gate["status"] == "blocked"
    assert missing_rule_gate["reasons"] == ["source_supported_irrelevance_plausible:stale_or_unknown"]
    assert missing["status"] == "not_established"


def test_shared_manual_audit_malformed_collections_fail_closed_without_crashing():
    expected = shared_admission._expected_rule_ids({
        "governing_regulatory_elements": None,
        "ego_box_crosswalk_contacts": "invalid",
        "nearby_source_signs": {},
        "nearby_omitted_markings": [None],
    })
    assert expected == {
        "regulatory_element": set(),
        "crosswalk": set(),
        "sign": set(),
        "omitted_marking": {"<invalid-id:id:0>"},
    }


def test_shared_interaction_evidence_binds_rule_audit_and_lifecycle_trace(tmp_path):
    audit_path = tmp_path / "rule_applicability_audit.json"
    trace_path = tmp_path / "lifecycle_trace_hybrid_startup.json"
    audit_path.write_text("audit-v1")
    trace_path.write_text("trace-v1")
    interaction = {
        "schema_version": 3,
        "traffic_mode": "hybrid_startup",
        "binary_sha256": "binary",
        "ego_track_id": 10,
        "evaluation_ini_sha256": "ini",
        "runtime_source_sha256": "runtime",
        "rule_audit_sha256": sha256(audit_path),
        "idm_trace_sha256": sha256(trace_path),
        "actor_opportunities": [],
    }
    interaction["source_evidence_digest"] = source_evidence_digest(interaction)
    review = {"interaction_source_digest": interaction["source_evidence_digest"]}
    contract = {
        "ego_track_id": 10,
        "runtime_source_sha256": "runtime",
        "files": {
            "scene_binary": {"sha256": "binary"},
            "evaluation_ini": {"sha256": "ini"},
        },
    }
    assert shared_admission._interaction_bound(
        interaction, review, "hybrid_startup", contract, audit_path, trace_path
    )

    audit_path.write_text("audit-v2")
    assert not shared_admission._interaction_bound(
        interaction, review, "hybrid_startup", contract, audit_path, trace_path
    )
