"""Synthetic bundles exercise archive integrity without simulation or source data."""

import json
import subprocess
import sys

import pytest

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.evaluation.contracts import AssessmentStatus, CriterionOutcome, MetricResult
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.runtime.trace_io import (
    EvidenceLevel, SavedEvidenceError, UnsupportedTraceSchema, load_saved_trace,
)


SCENE = {"root": "artifacts", "path": "synthetic"}
OLD_REVISION = "504218cb9ecd7fd64d2952630b9f10f56d80f923"


def states(step):
    rows = [
        dict(id=7, binary_index=0, present=step != 1, x=None if step == 1 else 9,
             collision_state=0),
        dict(id=41, binary_index=1, present=True, x=step, collision_state=0),
    ]
    return dict(step=step, time_s=step / 10, actors=rows if step % 2 == 0 else rows[::-1])


@pytest.fixture
def bundle(tmp_path):
    binary = tmp_path / "example.bin"
    binary.write_bytes(b"synthetic binary identity")
    frames, lifecycle = [], []
    for step, generation in enumerate((0, None, 1)):
        rows = [
            dict(source_id=41, binary_index=1, lifetime_generation=0,
                 slot=0, effective_owner="warmup_replay"),
            dict(source_id=7, binary_index=0, slot=1),
        ]
        frames.append(dict(step=step, state=states(step), actors=rows,
                           transition_applied=step < 2))
        lifecycle.append(dict(step=step, active_agent_indices=[1, 0], actors=[
            dict(source_id=7, binary_index=0, lifetime_generation=generation, source_valid=step != 1),
            dict(source_id=41, binary_index=1, lifetime_generation=0, source_valid=True),
        ]))
    trace = dict(schema_version=3, planner="controller_matrix", scene=SCENE,
                 binary_sha256=sha256(binary), ego_binary_index=1,
                 ego_controller="expert", traffic_controller="idm", traffic_startup="immediate",
                 terminal_reason="horizon", requested_observation_frames=3, observation_frames=3,
                 steps_semantics="observation_frames", warmup_replay_frames=10, transitions=2,
                 frames=frames)
    verification = dict(schema_version=2, scene=SCENE, ego="expert", traffic="idm",
                        startup="immediate", driving_outcome="horizon", lifecycle=lifecycle,
                        inputs={"binary": {"sha256": sha256(binary)}},
                        native={"episode_length": 91}, software={"code_sha256": {"old.py": "b" * 64}})
    path = tmp_path / "trace.json"
    write_json(path, trace)
    write_json(path.with_name("verification.json"), verification)
    return path, trace, verification, binary


def attest(path, trace, verification):
    files = {
        key: {"path": name, "sha256": sha256(path.with_name(name))}
        for key, name in (("trace", "trace.json"), ("provenance", "verification.json"))
    }
    config = {key: trace[key] for key in ("scene", "ego_controller", "traffic_controller", "traffic_startup")}
    config.update(inputs=verification["inputs"], steps=trace["requested_observation_frames"])
    attempt = dict(schema_version=1, status="passed", exit_code=0, scene_config=config,
                   evidence=dict(files=files, integration_validity="validated_trace_and_provenance"))
    write_json(path.with_name("attempt.json"), attempt)
    return attempt


def synthetic_capture(trace, trace_digest):
    observations = []
    for frame in trace["frames"]:
        assignments = {row["source_id"]: row for row in frame["actors"]}
        actors = []
        for state in frame["state"]["actors"]:
            assignment = assignments[state["id"]]
            actors.append({
                "source_id": state["id"], "binary_index": state["binary_index"],
                "lifetime_generation": assignment.get("lifetime_generation"),
                "collision_state": state["collision_state"],
                "collision_partner_status": "not_applicable",
                "native_collision_partner_index": None,
                "collision_partner_binary_index": None,
                "collision_partner_source_id": None, "collision_center_world_xy": None,
                "partner_center_world_xy": None, "navigation_goal_world_xy": None,
            })
        observations.append({"step": frame["step"], "coordinate_anchor_binary_index": 0,
                             "coordinate_offset_world_minus_native_m": [0., 0.],
                             "actors": actors})
    return {
        "schema_version": 1, "trace_sha256": trace_digest, "scene": trace["scene"],
        "binary_sha256": trace["binary_sha256"], "ego_binary_index": trace["ego_binary_index"],
        "ego_source_id": 41, "ego_controller": trace["ego_controller"],
        "traffic_controller": trace["traffic_controller"], "traffic_startup": trace["traffic_startup"],
        "steps_semantics": trace["steps_semantics"],
        "requested_observation_frames": trace["requested_observation_frames"],
        "observation_frames": trace["observation_frames"], "terminal_reason": trace["terminal_reason"],
        "native_settings": {"dynamics_model": "classic", "action_type_flag": 1,
                            "episode_length": 91, "observation_width": 1151,
                            "goal_behavior": 3},
        "coordinate_frame": {
            "transform": "world_xy = native_xy + coordinate_offset_world_minus_native_m",
        },
        "observations": observations, "limitations": [],
    }


def test_archived_bundle_binds_bytes_and_joins_identity(bundle):
    path, trace, verification, binary = bundle
    attempt = attest(path, trace, verification)
    before = {p: p.read_bytes() for p in path.parent.iterdir()}
    result = load_saved_trace(path, expected_files=attempt["evidence"]["files"],
                              input_paths={"binary": binary}, expected_ego_source_id=41,
                              expected_scene=SCENE, producer_revision=OLD_REVISION)
    assert result.evidence_level is EvidenceLevel.ARCHIVED_ATTESTED
    assert result.producer_revision == OLD_REVISION
    assert result.ego_source_id == 41
    assert result.playback.hashes["trace"] == sha256(path)
    frames = list(result.frames())
    assert [row["id"] for row in frames[1]["actors"]] == [41, 7]
    assert [next(row for row in frame["actors"] if row["id"] == 7)["lifetime_generation"]
            for frame in frames] == [0, None, 1]
    assert frames[0]["actors"][1]["effective_owner"] == "warmup_replay"
    assert {p: p.read_bytes() for p in path.parent.iterdir()} == before


def test_campaign_can_attest_detached_single(bundle):
    path, trace, verification, binary = bundle
    attempt = attest(path, trace, verification)
    path.with_name("attempt.json").unlink()
    slot = dict(scene="synthetic", ego="expert", traffic="idm", startup="immediate",
                status="PASS", exact_parity=True, integration_validity="validated_exact",
                single=dict(status="passed", files=attempt["evidence"]["files"]))
    kwargs = dict(expected_scene=SCENE, expected_binary_sha256=sha256(binary),
                  producer_revision=OLD_REVISION)
    assert load_saved_trace(path, campaign_slot=slot, **kwargs).evidence_level == "archived_attested"
    with pytest.raises(SavedEvidenceError, match="differs"):
        load_saved_trace(path, campaign_slot=dict(slot, ego="ppo"), **kwargs)


def test_bound_evaluation_capture_is_returned_and_tampering_is_rejected(bundle):
    path, trace, verification, _ = bundle
    attempt = attest(path, trace, verification)
    capture = synthetic_capture(trace, sha256(path))
    capture_path = path.with_name("evaluation_capture.json")
    write_json(capture_path, capture)
    attempt["scene_config"]["capture_evaluation"] = True
    attempt["evidence"]["files"]["evaluation_capture"] = {
        "path": capture_path.name, "sha256": sha256(capture_path),
    }
    write_json(path.with_name("attempt.json"), attempt)

    result = load_saved_trace(path)
    assert result.evidence_level is EvidenceLevel.ARCHIVED_ATTESTED
    assert result.playback.evaluation_capture["ego_source_id"] == 41
    assert result.playback.evaluation_capture_bound

    capture_path.write_bytes(capture_path.read_bytes() + b" ")
    with pytest.raises(SavedEvidenceError, match="Playback hash"):
        load_saved_trace(path)


def test_saved_capture_settings_must_match_verification_native_facts(bundle):
    path, trace, verification, _ = bundle
    attempt = attest(path, trace, verification)
    capture_path = path.with_name("evaluation_capture.json")
    capture = synthetic_capture(trace, sha256(path))
    write_json(capture_path, capture)
    attempt["scene_config"]["capture_evaluation"] = True
    attempt["evidence"]["files"]["evaluation_capture"] = {
        "path": capture_path.name, "sha256": sha256(capture_path),
    }
    write_json(path.with_name("attempt.json"), attempt)

    capture["native_settings"]["episode_length"] = 92
    write_json(capture_path, capture)
    attempt["evidence"]["files"]["evaluation_capture"]["sha256"] = sha256(capture_path)
    write_json(path.with_name("attempt.json"), attempt)
    with pytest.raises(SavedEvidenceError, match="native settings differ"):
        load_saved_trace(path)


def test_capture_alone_does_not_attest_execution(bundle):
    path, trace, _, _ = bundle
    capture = synthetic_capture(trace, sha256(path))
    write_json(path.with_name("evaluation_capture.json"), capture)
    result = load_saved_trace(path)
    assert result.evidence_level is EvidenceLevel.TRACE_ONLY_DIAGNOSTIC
    assert result.playback.evaluation_capture is not None
    assert not result.playback.evaluation_capture_bound


def test_hashes_and_sidecar_alone_do_not_attest(bundle):
    path, trace, verification, _ = bundle
    files = attest(path, trace, verification)["evidence"]["files"]
    path.with_name("attempt.json").unlink()
    result = load_saved_trace(path, expected_files=files)
    assert result.evidence_level is EvidenceLevel.TRACE_ONLY_DIAGNOSTIC
    assert result.playback.bound
    unbound = load_saved_trace(path)
    assert not unbound.playback.bound
    assert list(unbound.frames())[-1]["actors"][0]["lifetime_generation"] is None
    path.with_name("verification.json").unlink()
    assert load_saved_trace(path).playback.verification is None


@pytest.mark.parametrize("planner", ["expert", "smart"])
def test_flat_schema2_keeps_unknown_lifetime_and_transition(tmp_path, planner):
    path = tmp_path / "trace.json"
    write_json(path, dict(schema_version=2, planner=planner, ego_binary_index=1,
                          binary_sha256="1" * 64, frames=[states(0)]))
    result = load_saved_trace(path)
    frame, = result.frames()
    assert result.ego_source_id == 41
    assert frame["transition_applied"] is None
    assert frame["actors"][1]["lifetime_generation"] is None
    assert frame["actors"][1]["x"] == 0


@pytest.mark.parametrize("filename", ["trace.json", "verification.json"])
def test_tampering_rejected(bundle, filename):
    path, trace, verification, _ = bundle
    attest(path, trace, verification)
    file = path.with_name(filename)
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(SavedEvidenceError, match="Playback hash"):
        load_saved_trace(path)


@pytest.mark.parametrize("key,value,match", [
    ("ego", "ppo", "Verification sidecar"),
    ("startup", "source_hold", "Verification sidecar"),
    ("trace_sha256", "c" * 64, "trace hash mismatch"),
    ("requested_observation_frames", 4, "horizon"),
    ("native", {"episode_length": 2}, "episode length"),
])
def test_contradictory_same_scene_sidecar(bundle, key, value, match):
    path, _, verification, _ = bundle
    verification[key] = value
    write_json(path.with_name("verification.json"), verification)
    with pytest.raises(SavedEvidenceError, match=match):
        load_saved_trace(path)


def test_lifecycle_mismatch_rejected(bundle):
    path, _, verification, _ = bundle
    verification["lifecycle"][2]["actors"][1]["lifetime_generation"] = 8
    write_json(path.with_name("verification.json"), verification)
    with pytest.raises(SavedEvidenceError, match="generation"):
        load_saved_trace(path)


def test_malformed_or_unsupported_trace(bundle):
    path, trace, _, _ = bundle
    write_json(path, dict(trace, schema_version=99))
    with pytest.raises(UnsupportedTraceSchema):
        load_saved_trace(path)
    trace["frames"][0]["state"]["actors"][1]["binary_index"] = 0
    write_json(path, trace)
    with pytest.raises(SavedEvidenceError, match="Inconsistent actors"):
        load_saved_trace(path)
    trace["infinite"] = "overflow"
    path.write_text(json.dumps(trace).replace('"overflow"', "1e999"))
    with pytest.raises(SavedEvidenceError, match="nonfinite"):
        load_saved_trace(path)


def test_profile_hash_uses_effective_content(tmp_path):
    from geotransfer_gap.config import settings

    default = settings().project / "configs/evaluation/default.toml"
    original = load_profile()
    path = tmp_path / "other.toml"
    source = default.read_text()
    path.write_text("# equivalent\n" + source.replace("primary_horizon_s = 5.0", "primary_horizon_s = 5"))
    equivalent = load_profile(path)
    assert original.effective_sha256 == equivalent.effective_sha256
    assert original.raw_sha256 != equivalent.raw_sha256
    path.write_text(source.replace("primary_horizon_s = 5.0", "primary_horizon_s = 8.0"))
    assert original.effective_sha256 != load_profile(path).effective_sha256


@pytest.mark.parametrize("old,new", [
    ("primary_start_observation = 10", "primary_start_observation = 9"),
    ("bootstrap_seed = 0", "bootstrap_seed = true"),
    ("confidence_level = 0.95", "confidence_level = inf"),
    ("schema_version = 1", "schema_version = 2"),
    ("ttc_below_s = 1.5", "ttc_below_s = 4.0"),
    ("smooth_states = false", "smooth_states = true"),
])
def test_inconsistent_or_invalid_profiles(tmp_path, old, new):
    from geotransfer_gap.config import settings

    path = tmp_path / "bad.toml"
    default = settings().project / "configs/evaluation/default.toml"
    path.write_text(default.read_text().replace(old, new, 1))
    with pytest.raises(ValueError):
        load_profile(path)


def test_finite_result_keeps_status_separate_from_outcome(tmp_path):
    path = tmp_path / "result.json"
    unknown = MetricResult("test.quantity", "1.0.0", AssessmentStatus.UNAVAILABLE, "no evidence")
    unknown.write(path)
    data = json.loads(path.read_bytes())
    assert data["value"] is None and data["criterion_outcome"] == "not_assessed"
    assert data["eligible_samples"] is None
    with pytest.raises(ValueError):
        MetricResult("test.quantity", "1.0.0", AssessmentStatus.UNAVAILABLE, "no evidence",
                     criterion_outcome=CriterionOutcome.PASS)
    with pytest.raises(ValueError):
        MetricResult("test.quantity", "1.0.0", AssessmentStatus.VALID, "measured",
                     value={"nested": [float("nan")]})


def test_offline_without_site_packages_or_assets(bundle):
    from geotransfer_gap.config import settings

    trace, *_ = bundle
    src = str(settings().project / "src")
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from geotransfer_gap.evaluation.contracts import MetricResult
from geotransfer_gap.evaluation.profile import load_profile
from geotransfer_gap.runtime.trace_io import load_saved_trace
assert load_profile().definition_version == '1.0.0'
assert load_saved_trace(sys.argv[2]).ego_source_id == 41
assert not {'numpy', 'torch', 'pufferlib', 'lanelet2'} & sys.modules.keys()
"""
    env = {f"GEOTRANSFER_{key}": str(trace.parent / "missing")
           for key in ("BENCH", "WEIGHTS", "SOURCE", "ARTIFACTS", "REFERENCE_DATA", "CACHE")}
    subprocess.run([sys.executable, "-I", "-S", "-c", code, src, str(trace)],
                   cwd=trace.parent, env=env, check=True)


def test_bound_capture_reader_needs_no_native_or_model_imports(bundle):
    from geotransfer_gap.config import settings

    path, trace, verification, _ = bundle
    attempt = attest(path, trace, verification)
    capture_path = path.with_name("evaluation_capture.json")
    write_json(capture_path, synthetic_capture(trace, sha256(path)))
    attempt["scene_config"]["capture_evaluation"] = True
    attempt["evidence"]["files"]["evaluation_capture"] = {
        "path": capture_path.name, "sha256": sha256(capture_path),
    }
    write_json(path.with_name("attempt.json"), attempt)
    src = str(settings().project / "src")
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from geotransfer_gap.runtime.trace_io import load_saved_trace
saved = load_saved_trace(sys.argv[2])
assert saved.playback.evaluation_capture_bound
assert saved.playback.evaluation_capture['ego_source_id'] == 41
assert not {'numpy', 'torch', 'pufferlib', 'lanelet2'} & sys.modules.keys()
"""
    env = {f"GEOTRANSFER_{key}": str(path.parent / "missing")
           for key in ("BENCH", "WEIGHTS", "SOURCE", "ARTIFACTS", "REFERENCE_DATA", "CACHE")}
    subprocess.run([sys.executable, "-I", "-S", "-c", code, src, str(path)],
                   cwd=path.parent, env=env, check=True)


def test_expected_trace_digest_without_optional_sidecars(bundle):
    path, _, _, _ = bundle
    path.with_name("verification.json").unlink()
    files = {"trace": {"path": path.name, "sha256": sha256(path)}}
    assert load_saved_trace(path, expected_files=files).evidence_level == "trace_only_diagnostic"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SavedEvidenceError, match="Playback hash"):
        load_saved_trace(path, expected_files=files)


def test_passed_attempt_cannot_attest_other_horizon(bundle):
    path, trace, verification, _ = bundle
    attempt = attest(path, trace, verification)
    attempt["scene_config"]["steps"] += 1
    write_json(path.with_name("attempt.json"), attempt)
    with pytest.raises(SavedEvidenceError, match="does not attest"):
        load_saved_trace(path)
