"""Versioned matrix evidence and exact, identity-ordered trace comparison."""

import argparse
from copy import deepcopy
from importlib.metadata import version
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from geotransfer_gap.artifacts import read_json, reference, resolve_reference, sha256, write_json
from geotransfer_gap.config import settings
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.goal_evidence import validate_goal_evidence
from geotransfer_gap.runtime.matrix_inputs import fingerprint, load_binary, load_source_hold
from geotransfer_gap.runtime.native_modes import NativeMovementMode as Mode

BB_COMMIT = "805fe04c6977b60c41c92c31f1a5211fbd704f44"
RUNTIME_DIGEST = "beedf8f1b0e9c490"
PPO_SHA256 = "50a9a580cca905fc3dae47b5847b4edf408de3b7fe7517bd4f3a781fa140e3b3"
SMART_SHA256 = "b2cdeb31b0336588df1fc872e2f64dc6b24ec88472936068ec7e9501e9252616"
EVAL_INI_SHA256 = "afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e"
SMART_CODEBOOK_SHA256 = {
    "map_codebook": "efc4aa79d57cd60aba257bbb2cc2262e13043d545f5e02d9b483a5c1d1926d8a",
    "motion_codebook": "90f727d4753e576bd0f1f13dd64336cd0d16419e98fd06b8900df50611ccf800",
}
MODEL_PROVENANCE = {"ppo": "ppo_provenance.json", "smart": "smart_provenance.json"}
MODES = set(Mode)
VERIFICATION_SCHEMA_VERSION = 2


def lifecycle_frame(snapshot, native):
    """Capture lifecycle facts absent from the historical trace."""
    actors = []
    for actor in snapshot.actors:
        entity = native["entities"][actor.fixed_binary_index]
        goal = ([float(entity[f"goal_position_{axis}"]) for axis in "xy"]
                if actor.native_present and actor.controller_eligible else None)
        actors.append({
            "source_id": int(actor.source_id), "binary_index": actor.fixed_binary_index,
            "lifetime_generation": actor.lifetime_generation,
            "source_valid": actor.source_valid, "native_present": actor.native_present,
            "controller_eligible": actor.controller_eligible,
            "permanently_removed": actor.permanently_removed,
            "removal_reason": actor.removal_reason.value,
            "collided_before_goal": actor.collided_before_goal,
            "navigation_goal_native_xy": goal,
        })
    return {
        "step": snapshot.step,
        "active_agent_indices": list(snapshot.active_agent_indices),
        "actors": actors,
    }


def _git_at(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def original_admission(scene):
    """Reference the original protocol only when the official manifest pins it."""
    from geotransfer_gap.verification_matrix import MANIFEST_SHA256

    manifest = settings().project / "configs/current_manifest.json"
    if manifest.is_file() and sha256(manifest) == MANIFEST_SHA256:
        for row in read_json(manifest)["scenes"]:
            if row["root"] != scene:
                continue
            gate = resolve_reference(scene) / "testing/admission_smart_hybrid_startup.json"
            if gate.is_file() and sha256(gate) == row["admission_sha256"]:
                original = read_json(gate)
                files = original["contract"]["files"]
                evidence = [files[key] for key in ("scene_binary", "scene_json", "scene_manifest")]
                if original.get("research_admitted") is True and all(
                    resolve_reference(item["reference"]).is_file()
                    and sha256(resolve_reference(item["reference"])) == item["sha256"]
                    for item in evidence
                ):
                    return {"status": "recorded", "protocol": "SMART/hybrid_startup",
                            "evidence": fingerprint(gate)}
    return {"status": "not_recorded"}


def code_fingerprints():
    source = Path(__file__).resolve().parents[1]
    return {str(path.relative_to(source)): sha256(path) for path in sorted(source.rglob("*.py"))}


def run_provenance(report, lifecycle, env_settings, binary_file, source):
    cfg = settings()
    torch = sys.modules.get("torch")
    return {
        "schema_version": VERIFICATION_SCHEMA_VERSION, "scene": report["scene"],
        "ego": report["ego_controller"], "traffic": report["traffic_controller"],
        "startup": report["traffic_startup"], "diagnostic_only": True,
        "integration_validity": "pending_parent_validation",
        "original_source_admission": original_admission(report["scene"]),
        "controller_pair_research_admission": "not_established",
        "task_preservation": "not_assessed", "driving_outcome": report["terminal_reason"],
        "inputs": {
            "binary": fingerprint(binary_file),
            **({"source_hold": fingerprint(source)} if source is not None else {}),
        },
        "software": {
            "behaviorbench_commit": _git_at(cfg.bench, "rev-parse", "HEAD"),
            "behaviorbench_dirty": bool(_git_at(cfg.bench, "status", "--porcelain")),
            "runtime_source_digest": report["runtime"]["runtime_source_sha256"],
            "runtime_binary_sha256": sha256(report["runtime"]["runtime_binary"]),
            "evaluation_ini": fingerprint(Path(env_settings["ini"]).resolve()),
            "python": sys.version.split()[0], "numpy": version("numpy"), "torch": version("torch"),
            "code_sha256": code_fingerprints(),
        },
        "determinism": {
            "device": "cpu", "native_reset_seed": 0, "numpy_seed": 0,
            "learned_model_torch_seed": 0 if set(MODEL_PROVENANCE) &
                {report["ego_controller"], report["traffic_controller"]} else None,
            "thread_environment": {
                key: os.getenv(key) for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                               "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
            },
            "torch_threads": torch.get_num_threads() if torch is not None else None,
            "torch_interop_threads": torch.get_num_interop_threads() if torch is not None else None,
            "python_hash_seed": os.getenv("PYTHONHASHSEED"),
            "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        },
        "native": {key: value for key, value in env_settings.items() if key != "ini"},
        "action": {"layout": ["normalized_acceleration", "normalized_steering"],
                   "maximum_abs_acceleration_m_s2": 4, "maximum_abs_steering_rad": 1},
        "model_provenance": {
            name: path for name, path in MODEL_PROVENANCE.items()
            if name in {report["ego_controller"], report["traffic_controller"]}
        },
        "idm_prior": {
            "ego": "native lane route",
            "traffic": "recorded source-informed background route where available",
            "parameters": report["idm_global_parameters"],
        } if report["idm_global_parameters"] is not None else None,
        "source_hold_prior": report.get("startup_policy"),
        "lifecycle": lifecycle,
    }


def _actors_by_id(rows, field, label):
    result = {row[field]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate actor identity in {label}")
    return result


def validate_trace(trace, lifecycle=None, binary=None):
    frames = trace["frames"]
    requested = trace["requested_observation_frames"]
    reason = trace["terminal_reason"]
    if (trace.get("schema_version") != 3 or trace.get("planner") != "controller_matrix"
            or trace["steps_semantics"] != "observation_frames" or trace["warmup_replay_frames"] != 10
            or not 1 <= len(frames) == trace["observation_frames"] <= requested <= 91
            or trace["transitions"] != len(frames) - 1):
        raise ValueError("invalid observation/transition counts or trace contract")
    if reason not in {"horizon", "ego_absent", "ego_removed", "ego_collision", "ego_offroad"}:
        raise ValueError(f"invalid terminal reason: {reason}")
    if reason == "horizon" and len(frames) != requested:
        raise ValueError("incomplete horizon observation trace")
    if lifecycle is not None and len(lifecycle) != len(frames):
        raise ValueError("incomplete lifecycle observation trace")
    previous = {}
    scene_actors = ({int(obj["id"]): index for index, obj in enumerate(binary["objects"])}
                    if binary is not None else None)
    if binary is not None and trace["ego_binary_index"] != binary["sdc_track_index"]:
        raise ValueError("ego binary index does not match the scene")
    schedule = {row["binary_index"]: row["step"]
                for row in trace.get("startup_policy", {}).get("release_schedule", [])}
    releases = {}
    for tick, frame in enumerate(frames):
        advances = tick < len(frames) - 1
        if (frame["step"] != tick or frame["state"]["step"] != tick
                or frame["transition_applied"] is not advances):
            raise ValueError(f"invalid transition at step {tick}")
        state = _actors_by_id(frame["state"]["actors"], "id", "native state")
        assignments = _actors_by_id(frame["actors"], "source_id", "scheduler assignments")
        life = active_indices = None
        if lifecycle is not None:
            life = _actors_by_id(lifecycle[tick]["actors"], "source_id", "lifecycle")
            if life.keys() != state.keys() or lifecycle[tick]["step"] != tick:
                raise ValueError(f"lifecycle identity mismatch at step {tick}")
            active_indices = lifecycle[tick].get("active_agent_indices")
            if (not isinstance(active_indices, list)
                    or any(type(index) is not int for index in active_indices)
                    or len(set(active_indices)) != len(active_indices)):
                raise ValueError(f"invalid native active index ordering at step {tick}")
        identities = {sid: row["binary_index"] for sid, row in state.items()}
        if scene_actors is None:
            scene_actors = identities
        if (not identities or scene_actors != identities or state.keys() != assignments.keys()
                or len(set(identities.values())) != len(identities)
                or trace["ego_binary_index"] not in identities.values()):
            raise ValueError(f"actor identity mismatch at step {tick}")
        slots = set()
        current = {}
        for sid, assignment in assignments.items():
            actor = state[sid]
            slot = assignment["slot"]
            if slot is not None:
                if type(slot) is not int or slot < 0 or slot in slots:
                    raise ValueError(f"duplicate or invalid slot at step {tick}, actor {sid}")
                slots.add(slot)
            if actor["binary_index"] != assignment["binary_index"]:
                raise ValueError(f"binary index changed at step {tick}, actor {sid}")
            if active_indices is not None and slot is not None:
                if slot >= len(active_indices) or active_indices[slot] != actor["binary_index"]:
                    raise ValueError(f"native slot {slot} does not map to binary index "
                                     f"{actor['binary_index']} at step {tick}, actor {sid}")
            pre = assignment.get("pre_step_native_movement_mode")
            applied = assignment.get("applied_movement_mode")
            planned = assignment.get("planned_movement_mode")
            action = assignment.get("action")
            if (pre not in MODES or pre != actor.get("movement_mode")
                    or "applied_movement_mode" not in assignment
                    or "planned_movement_mode" not in assignment):
                raise ValueError(f"missing or invalid movement mode at step {tick}, actor {sid}")
            if advances and slot is not None:
                if (applied not in MODES or applied != planned or not isinstance(action, list)
                        or len(action) != 2 or not all(type(x) in (float, int) and -1 <= x <= 1 for x in action)
                        or assignment["intent"] != {Mode.DYNAMICS: "dynamics", Mode.IDM: "idm", Mode.EXPERT_REPLAY: "replay"}[applied]
                        or (tick < 10 and applied != Mode.EXPERT_REPLAY)):
                    raise ValueError(f"invalid action or mode at step {tick}, actor {sid}")
            elif applied is not None or planned is not None or action is not None:
                raise ValueError(f"action without a transition/slot at step {tick}, actor {sid}")
            generation = assignment["lifetime_generation"]
            live = actor["present"] and not actor["collision_state"] and not actor["removed"]
            if life is not None:
                info = life[sid]
                if info["binary_index"] != actor["binary_index"] or info["lifetime_generation"] != generation:
                    raise ValueError(f"lifecycle identity mismatch at step {tick}, actor {sid}")
                live = info["source_valid"] and info["native_present"] and not info["permanently_removed"]
                expected_role = ("ego" if actor["binary_index"] == trace["ego_binary_index"] else "traffic"
                                 ) if info["controller_eligible"] else "context"
                if assignment["role"] != expected_role:
                    raise ValueError(f"unexpected controller ownership at step {tick}, actor {sid}")
                _validate_ownership(trace, assignment, info, tick, advances, schedule, releases, binary)
            if live and generation is not None:
                key = (sid, generation)
                if previous.get(key) is not None and previous[key] != pre:
                    raise ValueError(f"applied movement mode did not persist at step {tick}, actor {sid}, generation {generation}")
                current[key] = applied
        active_count = len(slots) if active_indices is None else len(active_indices)
        if slots != set(range(active_count)):
            raise ValueError(f"incomplete active slots at step {tick}")
        previous = current

    if lifecycle is not None:
        ego_id = next(sid for sid, index in scene_actors.items() if index == trace["ego_binary_index"])
        final, = [row for row in lifecycle[-1]["actors"] if row["source_id"] == ego_id]
        terminal = state[ego_id]
        actual_reason = ("ego_removed" if terminal["removed"] else
                         "ego_absent" if not final["native_present"] else
                         f"ego_{final['removal_reason']}" if final["permanently_removed"] else "horizon")
        if reason != actual_reason:
            raise ValueError("terminal reason does not match the last native ego observation")


def _validate_ownership(trace, actor, lifecycle, tick, advances, schedule, releases, binary):
    sid, index, role = actor["source_id"], actor["binary_index"], actor["role"]
    declared = trace[f"{role}_controller"] if role != "context" else None
    if actor["declared_controller"] != declared:
        raise ValueError(f"unexpected declared controller at step {tick}, actor {sid}")
    scheduled = schedule.get(index)
    held = role == "traffic" and scheduled is not None and tick < scheduled
    if role == "context":
        if lifecycle["source_valid"] and lifecycle["native_present"]:
            owner = "context_replay"
        else:
            owner = "inactive_replay_mode" if actor["slot"] is not None else "not_present"
        mode = Mode.EXPERT_REPLAY
    elif tick < 10 or held:
        owner = "warmup_replay" if tick < 10 else "source_hold_replay"
        mode = Mode.EXPERT_REPLAY
    else:
        owner = f"{role}:{declared}"
        mode = {"expert": Mode.EXPERT_REPLAY, "idm": Mode.IDM,
                "ppo": Mode.DYNAMICS, "smart": Mode.DYNAMICS}[declared]
    if (actor["effective_owner"] != owner
            or (advances and actor["slot"] is not None and actor["applied_movement_mode"] != mode)
            or (mode != Mode.DYNAMICS and actor.get("action") not in (None, [0, 0]))):
        raise ValueError(f"invalid effective owner or controller action at step {tick}, actor {sid}")
    if trace["traffic_startup"] == "source_hold":
        key = (sid, actor["lifetime_generation"])
        if role == "traffic" and scheduled is not None and advances and mode != Mode.EXPERT_REPLAY:
            releases.setdefault(key, tick)
        if ("scheduled_release_step" not in actor or "actual_release_step" not in actor
                or actor["scheduled_release_step"] != scheduled
                or actor["actual_release_step"] != releases.get(key)):
            raise ValueError(f"invalid hold/release record at step {tick}, actor {sid}")

        if binary is not None:
            obj = binary["objects"][index]
            window = trace["startup_policy"]["window_observations"]
            if (index == trace["ego_binary_index"] or obj.get("mark_as_expert")
                    or obj["type"] != ActorIndex.VEHICLE_TYPE):
                status = "exempt"
            elif scheduled is None:
                status = "not_scheduled"
            elif key in releases:
                status = "released"
            elif scheduled == window and tick + 1 == window:
                status = "held_through_window"
            elif not advances:
                status = "scheduled_not_released"
            else:
                status = "scheduled"
            if actor.get("startup_status") != status:
                raise ValueError(f"invalid startup status at step {tick}, actor {sid}")


def _digest(value, label):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError(f"missing or invalid {label} hash")
    return value


def validate_models(folder, ego, traffic, *, models=None):
    from geotransfer_gap.planners.protocol import input_paths

    records = {}
    for model in sorted({ego, traffic} & MODEL_PROVENANCE.keys()):
        path = folder / MODEL_PROVENANCE[model]
        if models is None and not path.is_file():
            raise ValueError(f"missing {model} provenance")
        record = read_json(path) if models is None else models[model]
        digest = _digest(record.get("checkpoint_sha256"), model + " checkpoint")
        checkpoint, pinned = ((settings().bench / "weights/simple_ppo.pt", PPO_SHA256)
                              if model == "ppo" else (settings().weights, SMART_SHA256))
        if digest != pinned or sha256(checkpoint) != digest:
            raise ValueError(f"{model} checkpoint hash differs from the pinned input")
        if (record.get("research_admission_status") != "not_established"
                or record.get("diagnostic_only") is not True
                or record.get("device") != "cpu" or record.get("seed") != 0
                or not record.get("information_access")):
            raise ValueError(f"invalid {model} provenance or admission")
        if model == "ppo":
            if (Path(record["checkpoint"]).resolve() != checkpoint
                    or record["evaluation_ini_sha256"] != EVAL_INI_SHA256
                    or record["behaviorbench_commit"] != BB_COMMIT or record["torch_threads"] != 1
                    or record["observation"]["width"] != 1151 or record["checkpoint_keys"] != 32
                    or record["action"]["selection"] != "argmax of 91 joint logits, acceleration-major"
                    or (traffic == "ppo" and "traffic_ppo" not in record)):
                raise ValueError("invalid PPO model, observation or action provenance")
        elif (record["input_hashes"] != {key: sha256(path) for key, path in input_paths().items()}
              or any(record["input_hashes"].get(key) != digest for key, digest in SMART_CODEBOOK_SHA256.items())
              or record["greedy"] is not True
              or set(record["refreshes"]) != {role for role, name in (("ego", ego), ("traffic", traffic)) if name == "smart"}):
            raise ValueError("invalid SMART input hashes or model provenance")
        records[model] = record
    return records


def validate_claims(provenance):
    expected_admission = (original_admission(provenance["scene"]) if "scene" in provenance
                          else {"status": "not_recorded"})
    if (provenance.get("diagnostic_only") is not True
            or provenance.get("controller_pair_research_admission") != "not_established"
            or provenance.get("task_preservation") != "not_assessed"
            or provenance.get("original_source_admission") != expected_admission):
        raise ValueError("unsupported source, task or controller-pair admission claim")


def _validate_startup(trace, inputs, root, binary):
    recorded = trace.get("startup_policy")
    if trace["traffic_startup"] != "source_hold":
        if recorded is not None or "source_hold" in inputs:
            raise ValueError("immediate startup contains source-hold evidence")
        return

    source, policy = load_source_hold(root, binary, trace["requested_observation_frames"])
    actual = fingerprint(source)
    if (inputs.get("source_hold") != actual or not isinstance(recorded, dict)
            or recorded.get("source") != actual["reference"]
            or recorded.get("source_sha256") != actual["sha256"]
            or recorded.get("window_observations") != policy.window):
        raise ValueError("source-hold evidence does not match the authoritative source")

    expected_schedule = [
        {"binary_index": index, "source_id": int(binary["objects"][index]["id"]), "step": step}
        for index, step in sorted(policy.releases.items())
    ]
    if recorded.get("release_schedule") != expected_schedule:
        raise ValueError("release schedule disagrees with the authoritative source")


def validate_run(folder, row):
    bundle = load_bundle(folder)
    trace, provenance = bundle["trace"], bundle["provenance"]
    validate_claims(provenance)
    if provenance.get("integration_validity") != "pending_parent_validation":
        raise ValueError("worker cannot attest to its own integration validation")
    for key in ("scene", "ego_controller", "traffic_controller", "traffic_startup"):
        if trace[key] != row[key]:
            raise ValueError(f"worker trace has the wrong {key}")
    if (provenance.get("schema_version") != VERIFICATION_SCHEMA_VERSION
            or provenance["scene"] != row["scene"]
            or [provenance[key] for key in ("ego", "traffic", "startup")] !=
               [row[key] for key in ("ego_controller", "traffic_controller", "traffic_startup")]
            or row["inputs"] != provenance["inputs"]
            or trace["binary_sha256"] != row["inputs"]["binary"]["sha256"]
            or trace["requested_observation_frames"] != row["steps"]
            or trace["terminal_reason"] != provenance["driving_outcome"]):
        raise ValueError("worker evidence does not match the requested scene, configuration or outcome")
    inputs = dict(provenance["inputs"], evaluation_ini=provenance["software"]["evaluation_ini"])
    for key, artifact in inputs.items():
        if sha256(resolve_reference(artifact["reference"])) != _digest(artifact["sha256"], key):
            raise ValueError(f"input hash mismatch: {key}")
    software = provenance["software"]
    if (software["evaluation_ini"]["sha256"] != EVAL_INI_SHA256
            or software["behaviorbench_commit"] != BB_COMMIT or software["behaviorbench_dirty"]
            or software["runtime_source_digest"] != RUNTIME_DIGEST
            or software["code_sha256"] != code_fingerprints()
            or trace["runtime"]["runtime_source_sha256"] != RUNTIME_DIGEST
            or software["runtime_binary_sha256"] != sha256(trace["runtime"]["runtime_binary"])):
        raise ValueError("worker did not use the pinned corrected native runtime")
    determinism = provenance["determinism"]
    if (determinism["thread_environment"] != {
            key: "1" for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")}
            or determinism["native_reset_seed"] != 0
            or determinism["numpy_seed"] != 0
            or determinism["device"] != "cpu"
            or determinism["python_hash_seed"] != "0" or determinism["cuda_visible_devices"] != ""
            or (provenance["model_provenance"] and (
                determinism["torch_threads"] != 1 or determinism["learned_model_torch_seed"] != 0
            ))
            or provenance["native"]["dynamics_model"] != "classic"
            or provenance["native"]["action_type_flag"] != 1):
        raise ValueError("worker did not use the pinned CPU/classic dynamics configuration")
    if trace.get("startup_policy") != provenance["source_hold_prior"]:
        raise ValueError("startup policy provenance is inconsistent")
    root = resolve_reference(row["scene"])
    binary = load_binary(root)
    _validate_startup(trace, row["inputs"], root, binary)
    validate_trace(trace, provenance["lifecycle"], binary)
    models = validate_models(folder, row["ego_controller"], row["traffic_controller"])
    if ("smart" in models and models["smart"]["binary_sha256"] != trace["binary_sha256"]):
        raise ValueError("SMART evidence names a different scene binary")
    expected = {"trace": "trace.json", "provenance": "verification.json",
                **{model: MODEL_PROVENANCE[model] for model in models}}
    goal = bundle.get("goal_evidence")
    if goal is None or goal["trace_sha256"] != sha256(folder / "trace.json"):
        raise ValueError("missing or inconsistent native goal evidence")
    validate_goal_evidence(trace, goal, provenance["native"]["goal_behavior"])
    expected["goal_evidence"] = "goal_evidence.json"
    return {
        "integration_validity": "validated_trace_and_provenance",
        "files": {key: {"path": name, "sha256": sha256(folder / name)}
                  for key, name in expected.items()},
    }


def load_bundle(folder):
    return {
        "trace": read_json(folder / "trace.json"),
        "provenance": read_json(folder / "verification.json"),
        **{model: read_json(folder / name) for model, name in dict(MODEL_PROVENANCE, goal_evidence="goal_evidence.json").items()
           if (folder / name).is_file()},
    }


def canonical(bundle):
    """Canonical evidence preserves assigned slots as fields, never as actor identity."""
    result = deepcopy(bundle)
    trace = result["trace"]
    if "goal_evidence" in result:
        result["goal_evidence"].pop("trace_sha256", None)
    for frame in trace["frames"]:
        frame["actors"].sort(key=lambda row: (row["source_id"], row["lifetime_generation"] or 0))
        generations = {row["source_id"]: row["lifetime_generation"] for row in frame["actors"]}
        for actor in frame["state"]["actors"]:
            actor["lifetime_generation"] = generations.get(actor["id"])
        frame["state"]["actors"].sort(key=lambda row: row["id"])
    runtime = trace.get("runtime")
    if runtime and "runtime_binary" in runtime:
        runtime["runtime_binary"] = Path(runtime["runtime_binary"]).name
    if "ppo" in result:
        result["ppo"]["checkpoint"] = reference(Path(result["ppo"]["checkpoint"]))
        if "traffic_ppo" in result["ppo"]:
            result["ppo"]["traffic_ppo"]["lifetimes"].sort(
                key=lambda row: (row["source_id"], row["lifetime_generation"]))
    if "provenance" in result:
        for frame in result["provenance"]["lifecycle"]:
            frame["actors"].sort(key=lambda row: (row["source_id"], row["lifetime_generation"] or 0))
    if "smart" in result:
        for refreshes in result["smart"]["refreshes"].values():
            for event in refreshes:
                event["targets"].sort(key=lambda row: (row["source_id"], row["generation"]))
    return result


_MISSING = object()


def _first(expected, actual, where, field=""):
    if type(expected) is type(actual):
        if isinstance(expected, dict):
            actor = expected.get("source_id", expected.get("id"))
            if "step" in expected:
                where = {**where, "tick": expected["step"]}
            if actor is not None:
                where = {**where, "source_id": actor,
                         "lifetime": expected.get("lifetime_generation", expected.get("generation", where["lifetime"]))}
            for key in sorted(expected.keys() | actual.keys()):
                diff = _first(expected.get(key, _MISSING), actual.get(key, _MISSING),
                              where, f"{field}.{key}" if field else key)
                if diff:
                    return diff
            return None
        if isinstance(expected, list):
            actor_or_tick_records = (expected and isinstance(expected[0], dict)
                                     and ("step" in expected[0] or "source_id" in expected[0] or "id" in expected[0]))
            for i in range(max(len(expected), len(actual))):
                diff = _first(expected[i] if i < len(expected) else _MISSING,
                              actual[i] if i < len(actual) else _MISSING, where,
                              field if actor_or_tick_records else f"{field}[{i}]")
                if diff:
                    return diff
            return None
        if expected == actual and (not isinstance(expected, float)
                                   or math.copysign(1, expected) == math.copysign(1, actual)):
            return None
    return {**where, "field": field,
            "expected": {"missing": True} if expected is _MISSING else expected,
            "actual": {"missing": True} if actual is _MISSING else actual}


def compare(expected, actual):
    trace = expected["trace"]
    scope = {"scene": trace["scene"], "ego": trace["ego_controller"],
             "traffic": trace["traffic_controller"], "startup": trace["traffic_startup"],
             "tick": None, "source_id": None, "lifetime": None}
    return _first(canonical(expected), canonical(actual), scope)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    difference = compare(load_bundle(args.expected), load_bundle(args.actual))
    write_json(args.output, {"schema_version": 1, "equal": difference is None, "first_mismatch": difference})
    if difference:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
