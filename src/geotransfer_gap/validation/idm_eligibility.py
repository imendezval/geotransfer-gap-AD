"""Produce additive, role-specific native IDM eligibility evidence.

This probe is diagnostic evidence about controller inputs, native modes,
routes, and lifecycle. It does not read driving success metrics or make manual
task/rule decisions. Existing scene files are read only; output is explicit.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from numbers import Integral
from typing import Any

import numpy as np

from geotransfer_gap.artifacts import sha256, write_json
from geotransfer_gap.config import ensure_bench, settings
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.planners.controller_api import IDMIntent
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.matrix_inputs import binary_path, load_binary, load_source_hold
from geotransfer_gap.runtime.native_modes import NativeMovementMode as Mode
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from geotransfer_gap.runtime.startup_policy import StartupPolicy
from geotransfer_gap.validation.shared_admission import read_shared_admission


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "idm_native_role_eligibility_v1"
_FOLLOWING_TASK_MARKERS = ("following", "lead_vehicle", "queue_restart")
_NATIVE_FIELDS = ("x", "y", "vx", "vy", "heading")


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def summarize_route(entity: dict[str, Any]) -> dict[str, Any]:
    """Validate the route actually exposed by Drive for a current native actor."""
    try:
        raw_x = entity.get("route_x")
        raw_y = entity.get("route_y")
        xs = np.asarray(() if raw_x is None else raw_x, dtype=np.float64)
        ys = np.asarray(() if raw_y is None else raw_y, dtype=np.float64)
    except (TypeError, ValueError):
        xs = ys = np.asarray((), dtype=np.float64)
    paired = xs.ndim == ys.ndim == 1 and xs.shape == ys.shape
    finite = bool(paired and np.isfinite(xs).all() and np.isfinite(ys).all())
    count = int(xs.size) if paired else 0
    distinct = bool(count >= 2 and np.any(np.hypot(np.diff(xs), np.diff(ys)) > 1e-4)) if finite else False
    return {
        "point_count": count,
        "finite": finite,
        "has_distinct_segment": distinct,
        "valid": bool(finite and distinct),
    }


def validate_identity(binary: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Check binary-index identity and the ego association in a native frame."""
    objects = binary.get("objects")
    entities = state.get("entities")
    ego_index = binary.get("sdc_track_index")
    reasons = []
    if (not isinstance(objects, (list, tuple)) or not isinstance(entities, (list, tuple))
            or isinstance(ego_index, bool) or not isinstance(ego_index, Integral)
            or not 0 <= int(ego_index) < len(objects)
            or len(entities) < len(objects)):
        return {"valid": False, "reasons": ["native_actor_identity_layout_invalid"],
                "ego_binary_index": ego_index, "ego_source_id": None}
    ids = [obj.get("id") for obj in objects]
    if any(isinstance(actor_id, bool) or not isinstance(actor_id, Integral) for actor_id in ids) or len(set(ids)) != len(ids):
        reasons.append("source_actor_ids_missing_or_duplicate")
    active = state.get("active_agent_indices")
    if not isinstance(active, (list, tuple, np.ndarray)):
        reasons.append("native_active_actor_indices_missing")
        active = ()
    elif any(isinstance(index, bool) or not isinstance(index, Integral) for index in active) or len(set(active)) != len(active):
        reasons.append("native_active_actor_indices_invalid")
    ego_index = int(ego_index)
    ego_id = int(ids[ego_index]) if isinstance(ids[ego_index], Integral) else None
    try:
        active_indices = [int(value) for value in active]
    except (TypeError, ValueError, OverflowError):
        active_indices = []
    if ego_index not in active_indices:
        reasons.append("ego_not_associated_with_native_active_slot")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "ego_binary_index": ego_index,
        "ego_source_id": ego_id,
        "actor_count": len(objects),
        "active_binary_indices": active_indices,
        "ego_active": ego_index in active_indices,
    }


def _source_prior_coverage(obj: dict[str, Any], target_velocity: float = 15.0) -> dict[str, Any]:
    """Mirror the native background route producer's birth-time coverage guard."""
    valid = np.asarray(obj.get("traj_valid", ()))
    if valid.ndim != 1 or valid.dtype.kind not in "biu":
        return {"status": "not_established", "reason": "source_validity_missing"}
    starts = np.flatnonzero(valid == 1)
    if not starts.size:
        return {"status": "not_applicable", "reason": "actor_has_no_valid_source_samples"}
    birth = int(starts[0])
    end = birth
    while end < len(valid) and valid[end] == 1:
        end += 1
    x = np.asarray(obj.get("traj_x", ()), dtype=np.float64)
    y = np.asarray(obj.get("traj_y", ()), dtype=np.float64)
    vx = np.asarray(obj.get("traj_vx", ()), dtype=np.float64)
    vy = np.asarray(obj.get("traj_vy", ()), dtype=np.float64)
    if any(a.shape != valid.shape or not np.isfinite(a).all() for a in (x, y, vx, vy)):
        return {"status": "not_established", "reason": "source_dynamics_invalid"}
    speeds = np.hypot(vx[birth:end], vy[birth:end])
    distance = float(np.hypot(np.diff(x[birth:end]), np.diff(y[birth:end])).sum())
    duration = max(0.0, (end - birth - 1) * 0.1)
    speed_bound = max(float(speeds[0]) if speeds.size else 0.0, float(target_velocity))
    startup_samples = speeds[: min(11, speeds.size)]
    startup_moving = bool(startup_samples.size and np.all(startup_samples >= 1.0))
    covered = bool(startup_moving and duration > 0 and distance + 0.0001 >= speed_bound * duration)
    return {
        "status": "covered" if covered else "fallback_lane_route",
        "birth_step": birth,
        "contiguous_source_end_step_exclusive": end,
        "source_route_length_m": distance,
        "coverage_duration_s": duration,
        "required_distance_m": speed_bound * duration,
        "startup_moving": startup_moving,
        "target_velocity_mps": float(target_velocity),
    }


def _native_probe(root: Path, traffic_protocol: str,
                  ego_controller: str = "idm") -> dict[str, Any]:
    """Run the native scheduler for one fixed window with IDM traffic.

    The IDM/IDM mode proves the evaluated role pair. Expert/IDM is a separate
    reference protocol for task-actor preservation, independent of IDM-ego
    collisions or removals.
    """
    ensure_bench()
    from geotransfer_gap.runtime import late_spawn_runtime
    from geotransfer_gap.runtime.session import evaluation_env

    binary_file = binary_path(root)
    binary = load_binary(root)
    startup = StartupPolicy()
    startup_source = None
    if traffic_protocol == "hybrid_startup":
        startup_source, startup = load_source_hold(root, binary, 91)
    elif traffic_protocol != "idm":
        raise ValueError(f"unsupported traffic protocol: {traffic_protocol}")

    runtime = late_spawn_runtime.load()
    from geotransfer_gap.runtime import hybrid_traffic
    from pufferlib.ocean.drive import binding

    if Path(binding.__file__).resolve() != Path(runtime["runtime_binary"]).resolve():
        raise RuntimeError("native IDM proof loaded a binding outside the pinned runtime")

    env = evaluation_env(root)
    if ego_controller == "idm":
        ego = IDMController("ego")
    elif ego_controller == "expert":
        from geotransfer_gap.planners.expert_controller import ExpertController

        ego = ExpertController("ego")
    else:
        raise ValueError(f"unsupported native IDM probe ego: {ego_controller}")
    idm_traffic = IDMController("traffic")
    scheduler = EpisodeScheduler(binding, ego, idm_traffic, startup=startup)
    identity_ok = True
    reasons: set[str] = set()
    role_rows = {role: {} for role in ("ego", "traffic")}
    mode_samples = {role: 0 for role in ("ego", "traffic")}
    intent_samples = {role: 0 for role in ("ego", "traffic")}
    route_failures = {role: [] for role in ("ego", "traffic")}
    dynamics_failures = []
    lifecycle = {"observed_frames": 0, "births": [], "source_gap_frames": 0,
                 "context_replay_samples": 0, "idm_actor_frames": {"ego": 0, "traffic": 0}}
    release_steps: dict[tuple[int, int], int] = {}
    permanently_removed: set[int] = set()
    actor_generations: dict[int, int] = {}
    following_frames: dict[int, list[dict[str, Any]]] = {}
    task_view_frames: dict[int, list[dict[str, Any]]] = {}
    identity = None
    try:
        env.reset()
        index = ActorIndex(binary)
        scheduler.reset({"ego_binary_index": int(binary["sdc_track_index"])})
        for step in range(91):
            raw_state = env.get_state()
            state = raw_state[0] if isinstance(raw_state, list) else raw_state
            if identity is None:
                identity = validate_identity(binary, state)
            current = index.capture_pre_step(step, state, env.observations)
            if current.ego_id != index.ego_id:
                identity_ok = False
                reasons.add("actor_index_ego_association_changed")
            lifecycle["observed_frames"] += 1
            for actor in current.actors:
                source_id = int(actor.source_id)
                if actor.permanently_removed:
                    permanently_removed.add(source_id)
                if actor.source_gap_pending or not actor.source_valid:
                    lifecycle["source_gap_frames"] += 1
                previous = actor_generations.get(source_id)
                if actor.lifetime_generation is not None and actor.lifetime_generation != previous:
                    lifecycle["births"].append({"source_id": source_id,
                                                "binary_index": actor.fixed_binary_index,
                                                "step": step,
                                                "generation": actor.lifetime_generation})
                actor_generations[source_id] = actor.lifetime_generation
                if actor.native_present and not actor.removed:
                    native_entity = state["entities"][actor.fixed_binary_index]
                    if not all(_finite(native_entity.get(field)) for field in _NATIVE_FIELDS):
                        dynamics_failures.append({"step": step, "source_id": source_id,
                                                  "reason": "nonfinite_native_dynamics"})

            advances = step < 90
            plan = scheduler.decide(current, advances_simulation=advances)
            pre_step_task_frames = []
            for assignment in plan.assignments:
                if assignment.role == "context" and assignment.slot is not None and advances:
                    lifecycle["context_replay_samples"] += 1
                if assignment.role not in ("ego", "traffic"):
                    if assignment.role != "context":
                        continue
                if assignment.slot is not None and assignment.native_mode is not None:
                    actor = current.actor_for(assignment.source_id)
                    entity = state["entities"][assignment.binary_index]
                    pre_step_task_frames.append({
                        "source_id": int(assignment.source_id),
                        "binary_index": int(assignment.binary_index),
                        "lifetime_generation": actor.lifetime_generation,
                        "step": step,
                        "role": assignment.role,
                        "source_valid": bool(actor.source_valid),
                        "native_present": bool(actor.native_present),
                        "present": entity.get("x") != -10000.0 and not bool(entity.get("removed")),
                        "planned_native_mode": int(assignment.native_mode),
                        "native_route_valid": (
                            summarize_route(entity)["valid"]
                            if assignment.role == "traffic" and assignment.native_mode == Mode.IDM
                            else None
                        ),
                    })
                if assignment.role not in ("ego", "traffic"):
                    continue
                actor = current.actor_for(assignment.source_id)
                if ((assignment.role == "ego") != actor.is_ego
                        or (assignment.role == "ego") != (assignment.binary_index == int(binary["sdc_track_index"]))):
                    identity_ok = False
                    reasons.add(f"role_to_source_identity_mismatch:{step}:{int(assignment.source_id)}")
                row = role_rows[assignment.role].setdefault(int(assignment.source_id), {
                    "source_id": int(assignment.source_id),
                    "binary_index": assignment.binary_index,
                    "lifetime_generations": [],
                    "eligible_frames": 0,
                    "idm_intent_frames": 0,
                    "idm_mode_frames": 0,
                    "route_samples": [],
                })
                if actor.lifetime_generation is not None and actor.lifetime_generation not in row["lifetime_generations"]:
                    row["lifetime_generations"].append(actor.lifetime_generation)
                if assignment.slot is not None and actor.controller_eligible:
                    row["eligible_frames"] += 1
                if isinstance(assignment.intent, IDMIntent):
                    intent_samples[assignment.role] += 1
                    row["idm_intent_frames"] += 1
                    if not _finite(assignment.intent.target_velocity) or assignment.intent.target_velocity < 0:
                        reasons.add(f"{assignment.role}_idm_intent_invalid")
            if advances:
                scheduler.advance(env, plan)

            # Read back the actual post-step C state. This verifies the native
            # mode writer and route generated by Drive, not the planned intent.
            if advances:
                raw_after = env.get_state()
                after = raw_after[0] if isinstance(raw_after, list) else raw_after
            else:
                after = state
            after_entities = after["entities"]
            for frame in pre_step_task_frames:
                after_entity = after_entities[frame["binary_index"]]
                readback = int(after_entity.get("movement_mode", -1))
                frame["mode_readback"] = readback
                frame["mode_readback_matches"] = readback == frame["planned_native_mode"]
                frame["post_step_present"] = (
                    after_entity.get("x") != -10000.0 and not bool(after_entity.get("removed"))
                )
                task_view_frames.setdefault(frame["source_id"], []).append(frame)
            for assignment in plan.assignments:
                if assignment.slot is None or assignment.native_mode is None:
                    continue
                entity = after_entities[assignment.binary_index]
                actual_mode = int(entity.get("movement_mode", -1))
                if actual_mode != int(assignment.native_mode):
                    reasons.add(f"native_mode_readback_mismatch:{assignment.role}:{step}")
                actor = current.actor_for(assignment.source_id)
                source_id = int(assignment.source_id)
                following_frames.setdefault(source_id, []).append({
                    "step": step, "x": float(entity["x"]), "y": float(entity["y"]),
                    "vx": float(entity["vx"]), "vy": float(entity["vy"]),
                    "heading": float(entity["heading"]),
                    "mode": actual_mode, "role": assignment.role,
                    "present": entity["x"] != -10000.0 and not bool(entity.get("removed")),
                })
                if assignment.role == "context":
                    if actual_mode != int(Mode.EXPERT_REPLAY):
                        reasons.add(f"context_replay_mode_mismatch:{step}")
                    else:
                        lifecycle["context_replay_samples"] += 1
                    continue
                if assignment.role not in ("ego", "traffic") or not actor.controller_eligible:
                    continue
                row = role_rows[assignment.role][source_id]
                if actual_mode == int(Mode.IDM) and not actor.marked_expert:
                    mode_samples[assignment.role] += 1
                    row["idm_mode_frames"] += 1
                    lifecycle["idm_actor_frames"][assignment.role] += 1
                    route = summarize_route(entity)
                    route_row = {"step": step, **route}
                    row["route_samples"].append(route_row)
                    if not route["valid"]:
                        route_failures[assignment.role].append({"step": step,
                                                                "source_id": source_id,
                                                                **route})
                    if assignment.role == "ego" and route["valid"]:
                        route_row["route_source"] = "native_lane_route"
                        route_row["source_prior_used"] = False
                    elif assignment.role == "traffic" and route["valid"]:
                        source_obj = binary["objects"][assignment.binary_index]
                        prior = _source_prior_coverage(source_obj)
                        route_row["route_source"] = (
                            "background_source_prior" if prior.get("status") == "covered"
                            else "native_lane_route_fallback" if prior.get("status") == "fallback_lane_route"
                            else "not_established"
                        )
                        route_row["source_prior"] = prior
                        route_row["source_prior_used"] = prior.get("status") == "covered"
                if assignment.role == "traffic" and scheduler.startup.mode == "source_hold":
                    scheduled = startup.releases.get(assignment.binary_index)
                    if scheduled is not None and assignment.native_mode == Mode.IDM:
                        release_steps.setdefault((source_id, actor.lifetime_generation), step)
        if not identity or identity.get("valid") is not True or not identity.get("ego_active"):
            identity_ok = False
            reasons.update((identity or {}).get("reasons", ["ego_identity_not_observed"]))
        if dynamics_failures:
            reasons.add("native_dynamics_nonfinite")

        # Verify every source-hold scheduled actor transitioned on its frozen
        # step after the ten-frame warmup; outcome events do not alter this gate.
        release_checks = []
        if scheduler.startup.mode == "source_hold":
            for binary_index, scheduled in sorted(startup.releases.items()):
                actor_obj = binary["objects"][binary_index]
                source_id = int(actor_obj["id"])
                generations = role_rows["traffic"].get(source_id, {}).get("lifetime_generations", [])
                actuals = [release_steps.get((source_id, generation)) for generation in generations]
                actual = next((value for value in actuals if value is not None), None)
                expected = max(10, int(scheduled))
                passed = actual == expected
                held_through_window = int(scheduled) >= 91 and actual is None
                unavailable_after_removal = actual is None and source_id in permanently_removed
                release_status = (
                    "current" if passed or held_through_window
                    else "not_established" if unavailable_after_removal
                    else "blocked"
                )
                release_checks.append({"source_id": source_id, "binary_index": binary_index,
                                       "scheduled_source_step": int(scheduled),
                                       "expected_native_idm_step": expected,
                                       "actual_native_idm_step": actual,
                                       "status": release_status,
                                       "passed": passed or held_through_window})
        return {
            "available": True,
            "root_binary_sha256": sha256(binary_file),
            "runtime": runtime,
            "evaluation_ini_sha256": sha256(Path(env.ini_file).resolve()),
            "startup": {
                "mode": scheduler.startup.mode,
                "protocol_version": (
                    "matrix_source_hold_release_v1" if scheduler.startup.mode == "source_hold"
                    else "matrix_immediate_startup_v1"
                ),
                "release_schedule_producer_protocol": (
                    hybrid_traffic.PROTOCOL_VERSION if startup_source else None
                ),
                "source_sha256": sha256(startup_source) if startup_source else None,
                "release_count": len(startup.releases),
                "release_checks": release_checks,
                "status": (
                    "blocked" if any(row["status"] == "blocked" for row in release_checks)
                    else "not_established" if any(row["status"] == "not_established" for row in release_checks)
                    else "current"
                ) if startup_source else "not_applicable",
                "passed": all(row["passed"] for row in release_checks),
            },
            "identity": identity,
            "identity_valid": identity_ok,
            "role_actor_rows": role_rows,
            "intent_samples": intent_samples,
            "effective_mode_samples": mode_samples,
            "route_failures": route_failures,
            "dynamics_failures": dynamics_failures,
            "lifecycle": lifecycle,
            "task_view_frames": task_view_frames,
            "idm_parameters": vars(scheduler.idm_parameters) if scheduler.idm_parameters else None,
            "runtime_reasons": sorted(reasons),
            "leader_observations": following_frames,
        "run_outcome": {
            "ego_removed_at_horizon": bool(after_entities[binary["sdc_track_index"]].get("removed")),
            "ego_collision_state_at_horizon": int(after_entities[binary["sdc_track_index"]].get("collision_state", 0)),
            "ego_reached_goal_at_horizon": bool(after_entities[binary["sdc_track_index"]].get("reached_goal_this_episode")),
        },
        }
    finally:
        env.close()


def _applicable_leader_evidence(shared: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    manual = shared.get("manual_evidence", {})
    task_types = manual.get("task_types") if isinstance(manual.get("task_types"), list) else []
    applicable = any(any(marker in task_type.lower() for marker in _FOLLOWING_TASK_MARKERS)
                     for task_type in task_types if isinstance(task_type, str))
    if not applicable:
        return {"status": "not_applicable", "reason": "reviewed_task_does_not_require_leader_following",
                "task_types": task_types}
    actor_ids = manual.get("task_actor_ids")
    actor_ids = actor_ids if isinstance(actor_ids, list) else []
    observations = probe.get("leader_observations", {})
    ego_id = (probe.get("identity") or {}).get("ego_source_id")
    ego_by_step = {row["step"]: row for row in observations.get(ego_id, [])}
    if not actor_ids:
        return {"status": "blocked", "reason": "reviewed_leader_actor_missing_from_native_probe",
                "task_types": task_types, "actor_ids": actor_ids, "missing_actor_ids": []}
    missing = [actor_id for actor_id in actor_ids if actor_id not in observations]
    if missing:
        return {"status": "blocked", "reason": "reviewed_leader_actor_missing_from_native_probe",
                "task_types": task_types, "actor_ids": actor_ids, "missing_actor_ids": missing}
    rows = []
    for actor_id in actor_ids:
        leader_by_step = {row["step"]: row for row in observations.get(actor_id, [])}
        follower_samples = []
        for step in sorted(ego_by_step.keys() & leader_by_step.keys()):
            ego = ego_by_step[step]
            leader = leader_by_step[step]
            if not (ego["present"] and leader["present"] and ego["mode"] == int(Mode.IDM)):
                continue
            dx, dy = leader["x"] - ego["x"], leader["y"] - ego["y"]
            forward = dx * math.cos(ego["heading"]) + dy * math.sin(ego["heading"])
            lateral = -dx * math.sin(ego["heading"]) + dy * math.cos(ego["heading"])
            ego_routes = probe.get("role_actor_rows", {}).get("ego", {}).get(ego_id, {}).get("route_samples", [])
            route_ok = any(row["step"] == step and row["valid"] for row in ego_routes)
            if forward > 0 and abs(lateral) <= 5.0 and route_ok:
                follower_samples.append({"step": step, "forward_gap_m": forward,
                                         "lateral_offset_m": lateral,
                                         "leader_role": leader["role"],
                                         "leader_native_mode": leader["mode"]})
        rows.append({"source_id": actor_id, "same_heading_leader_samples": follower_samples,
                     "leader_observed_frames": len(leader_by_step)})
    valid = all(row["same_heading_leader_samples"] for row in rows)
    return {"status": "current" if valid else "blocked", "task_types": task_types,
            "actors": rows,
            "reason": None if valid else "leader_following_native_route_or_mode_evidence_missing"}


def _shared_summary(shared: dict[str, Any]) -> dict[str, Any]:
    return {
        "traffic_protocol": shared.get("traffic_protocol"),
        "source_identity": shared.get("source_identity"),
        "shared_validity": shared.get("shared_validity"),
        "manual_evidence": shared.get("manual_evidence"),
        "task_eligibility": shared.get("task_eligibility"),
    }


def _protocol_fidelity(shared: dict[str, Any], probe: dict[str, Any],
                       traffic_protocol: str, tool_hashes: dict[str, str]) -> dict[str, Any]:
    """Compare the legacy shared traffic gate with the exact matrix protocol."""
    from geotransfer_gap.runtime import background_route_intent
    shared_gate = shared.get("shared_validity", {})
    gate_path = Path(shared_gate.get("technical_gate", ""))
    try:
        legacy_gate = json.loads(gate_path.read_text())
    except (OSError, ValueError, TypeError):
        legacy_gate = {}
    legacy_contract = legacy_gate.get("contract", {}) if isinstance(legacy_gate, dict) else {}
    legacy_files = legacy_contract.get("files", {})
    legacy_protocol = legacy_gate.get("traffic_protocol") if isinstance(legacy_gate, dict) else None
    runtime_sha = probe.get("runtime", {}).get("runtime_source_sha256")
    ini_sha = probe.get("evaluation_ini_sha256")
    checks = {
        "shared_technical_gate_current": shared_gate.get("status") == "current",
        "legacy_protocol_matches_matrix_traffic": legacy_protocol == traffic_protocol,
        "matrix_startup_matches_protocol": (
            (traffic_protocol == "idm" and probe.get("startup", {}).get("mode") == "immediate")
            or (traffic_protocol == "hybrid_startup" and probe.get("startup", {}).get("mode") == "source_hold")
        ),
        "native_runtime_matches_shared_contract": bool(runtime_sha and runtime_sha == legacy_contract.get("runtime_source_sha256")),
        "evaluation_ini_matches_shared_contract": bool(ini_sha and ini_sha == legacy_files.get("evaluation_ini", {}).get("sha256")),
        "background_route_producer_matches_shared_contract": bool(
            tool_hashes.get("background_route_intent")
            and tool_hashes["background_route_intent"]
            == legacy_files.get("tool_background_route_intent.py", {}).get("sha256")
        ),
        "startup_lifecycle_evidence_current": (
            probe.get("startup", {}).get("status") in ("current", "not_applicable")
        ),
    }
    # The existing hybrid_startup gate describes the legacy hybrid_traffic
    # release protocol. Matrix source_hold is a separate scheduler protocol,
    # even though both use IDM after a source-derived release decision.
    reasons = []
    if traffic_protocol == "hybrid_startup":
        reasons.append("legacy_hybrid_startup_is_not_matrix_source_hold_protocol")
    elif traffic_protocol != "idm":
        reasons.append("unsupported_shared_traffic_protocol")
    reasons.extend(name for name, passed in checks.items() if not passed)
    status = "current" if not reasons else "not_established"
    return {
        "status": status,
        "reasons": sorted(set(reasons)),
        "legacy_shared_protocol": legacy_protocol,
        "legacy_runtime_source_sha256": legacy_contract.get("runtime_source_sha256"),
        "matrix_pair": {"ego_controller": "idm", "traffic_controller": "idm",
                        "startup": probe.get("startup", {}).get("mode"),
                        "startup_protocol_version": probe.get("startup", {}).get("protocol_version"),
                        "release_schedule_producer_protocol": probe.get("startup", {}).get("release_schedule_producer_protocol")},
        "route_protocol_version": background_route_intent.PROTOCOL_VERSION,
        "checks": checks,
    }


def fingerprint_mismatches(record: dict[str, Any], *, role: str, traffic_protocol: str,
                           source_identity: dict[str, Any], tool_sha256: dict[str, str],
                           binary_sha256: str | None,
                           runtime_source_sha256: str | None) -> list[str]:
    """Fail closed when an IDM record is reused under changed bound inputs."""
    reasons = []
    binding = record.get("binding", {})
    if record.get("schema_version") != SCHEMA_VERSION or record.get("record_type") != f"controller_input_idm_{role}_v1":
        reasons.append("idm_record_schema_or_role_mismatch")
    if record.get("role") != role:
        reasons.append("idm_record_role_stale")
    if record.get("traffic_protocol") != traffic_protocol:
        reasons.append("idm_record_protocol_stale")
    if record.get("source_identity") != source_identity:
        reasons.append("idm_record_source_identity_stale")
    if binding.get("tool_sha256") != tool_sha256:
        reasons.append("idm_record_tool_fingerprint_stale")
    if binding.get("binary_sha256") != binary_sha256:
        reasons.append("idm_record_binary_stale")
    if binding.get("runtime_source_sha256") != runtime_source_sha256:
        reasons.append("idm_record_runtime_stale")
    return reasons


def _eligibility_dimensions(native_status: str, shared_status: str,
                            protocol_status: str, task_status: str) -> dict[str, str]:
    """Keep native route, shared technical, protocol, and task gates distinct."""
    return {
        "model_route_status": "eligible" if native_status == "current" else "blocked",
        "shared_technical_status": shared_status,
        "protocol_compatibility_status": protocol_status,
        "controller_input_status": (
            "current" if native_status == "current" and shared_status == "current"
            and protocol_status == "current" else "blocked"
        ),
        "task_status": task_status,
        "research_admission": "not_established",
    }


def _check_new_output(root: Path, output_dir: Path) -> tuple[Path, Path]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir == root or root in output_dir.parents:
        raise ValueError("IDM evidence output must be outside the scene root")
    artifacts = settings().artifacts.resolve()
    if output_dir == artifacts or artifacts in output_dir.parents:
        raise ValueError("IDM evidence output must be outside the configured artifacts tree")
    outputs = tuple(output_dir / f"controller_input_idm_{role}_v1.json"
                    for role in ("ego", "traffic"))
    if any(path.exists() for path in outputs):
        raise FileExistsError("IDM evidence output exists; choose a new output directory")
    return outputs


def _tool_hashes() -> dict[str, str]:
    from geotransfer_gap.runtime import background_route_intent, hybrid_traffic, late_spawn_runtime, scheduler, startup_policy
    from geotransfer_gap.runtime import matrix_inputs, native_modes, session
    return {
        "producer": sha256(Path(__file__)),
        "idm_adapter": sha256(Path(__file__).resolve().parents[1] / "planners/idm_controller.py"),
        "expert_reference": sha256(Path(__file__).resolve().parents[1] / "planners/expert_controller.py"),
        "controller_api": sha256(Path(__file__).resolve().parents[1] / "planners/controller_api.py"),
        "scheduler": sha256(Path(scheduler.__file__)),
        "actor_index": sha256(Path(__file__).resolve().parents[1] / "runtime/actor_index.py"),
        "startup_policy": sha256(Path(startup_policy.__file__)),
        "hybrid_traffic_release_schedule": sha256(Path(hybrid_traffic.__file__)),
        "matrix_inputs": sha256(Path(matrix_inputs.__file__)),
        "native_modes": sha256(Path(native_modes.__file__)),
        "runtime_session": sha256(Path(session.__file__)),
        "background_route_intent": sha256(Path(background_route_intent.__file__)),
        "late_spawn_runtime": sha256(Path(late_spawn_runtime.__file__)),
    }


def build_records(root: str | Path, traffic_protocol: str,
                  shared_record_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Build role-specific IDM records from fresh shared and native evidence."""
    root = Path(root).resolve()
    shared = read_shared_admission(root, traffic_protocol, record_path=shared_record_path)
    try:
        probe = _native_probe(root, traffic_protocol)
    except Exception as exc:  # Preserve unavailable runtime evidence as a blocked record.
        probe = {"available": False, "runtime_reasons": [f"native_probe_unavailable:{type(exc).__name__}:{exc}"]}
    tool_hashes = _tool_hashes()
    protocol_fidelity = _protocol_fidelity(shared, probe, traffic_protocol, tool_hashes)
    identity = shared.get("source_identity", {})
    records = {}
    for role in ("ego", "traffic"):
        role_rows = probe.get("role_actor_rows", {}).get(role, {})
        route_failures = probe.get("route_failures", {}).get(role, ["native_probe_unavailable"])
        intent_count = probe.get("intent_samples", {}).get(role, 0)
        mode_count = probe.get("effective_mode_samples", {}).get(role, 0)
        role_reason = []
        if not probe.get("available"):
            role_reason.extend(probe.get("runtime_reasons", ["native_probe_unavailable"]))
        if probe.get("identity_valid") is not True:
            role_reason.append("actor_ego_association_not_current")
        if not intent_count:
            role_reason.append("finite_idm_intent_not_observed")
        if not mode_count:
            role_reason.append("effective_native_idm_mode_not_observed")
        if route_failures:
            role_reason.append("native_route_missing_or_invalid")
        if probe.get("dynamics_failures"):
            role_reason.append("nonfinite_native_dynamics_observed")
        if probe.get("runtime_reasons"):
            role_reason.extend(probe["runtime_reasons"])
        runtime_ok = not role_reason
        controller_status = "eligible" if runtime_ok else "blocked"
        task_status = shared.get("task_eligibility", {}).get("status", "not_established")
        leader = _applicable_leader_evidence(shared, probe)
        dimensions = _eligibility_dimensions(
            "current" if runtime_ok else "blocked",
            shared.get("shared_validity", {}).get("status", "not_established"),
            protocol_fidelity["status"],
            task_status,
        )
        source_prior = {
            "ego": {"policy": "native_lane_route_only", "status": "not_applicable"},
            "traffic": {"policy": "background_source_prior_if_coverage_guard_passes",
                        "actors": [
                            {"source_id": source_id,
                             "route_sources": sorted({route.get("route_source", "not_established")
                                                      for route in actor.get("route_samples", [])}),
                             "source_prior_used": any(route.get("source_prior_used") is True
                                                      for route in actor.get("route_samples", [])),
                             "source_prior_status": next((route.get("source_prior", {}).get("status")
                                                           for route in actor.get("route_samples", [])
                                                           if route.get("source_prior")), None)}
                            for source_id, actor in sorted(role_rows.items())
                        ]},
        }[role]
        records[role] = {
            "schema_version": SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "record_type": f"controller_input_idm_{role}_v1",
            "scene_root": str(root),
            "role": role,
            "traffic_protocol": traffic_protocol,
            "startup_policy": probe.get("startup", {}).get("mode"),
            "source_identity": identity,
            "binding": {
                "shared_record_path": str(shared_record_path) if shared_record_path else None,
                "shared_source_identity": identity,
                "shared_validity_status": shared.get("shared_validity", {}).get("status"),
                "technical_gate_sha256": shared.get("shared_validity", {}).get("technical_gate_sha256"),
                "binary_sha256": probe.get("root_binary_sha256"),
                "runtime_source_sha256": probe.get("runtime", {}).get("runtime_source_sha256"),
                "runtime_binary_sha256": (sha256(probe["runtime"]["runtime_binary"])
                                          if probe.get("runtime", {}).get("runtime_binary") else None),
                "evaluation_ini_sha256": probe.get("evaluation_ini_sha256"),
                "tool_sha256": tool_hashes,
            },
            "shared_admission": _shared_summary(shared),
            "protocol_fidelity": protocol_fidelity,
            "native_proof": {
                "status": "current" if runtime_ok else "blocked",
                "reasons": sorted(set(role_reason)),
                "identity": probe.get("identity"),
                "actor_rows": role_rows,
                "finite_intent_samples": intent_count,
                "effective_native_idm_mode_samples": mode_count,
                "route_failures": route_failures,
                "idm_parameters": probe.get("idm_parameters"),
                "startup": probe.get("startup"),
                "lifecycle": probe.get("lifecycle"),
                "source_prior": source_prior,
                "leader_following_evidence": leader,
            },
            "eligibility": {
                **dimensions,
                "model_route_reasons": sorted(set(role_reason)),
                "shared_technical_reasons": shared.get("shared_validity", {}).get("reasons", []),
                "protocol_compatibility_reasons": protocol_fidelity["reasons"],
                "task_reasons": shared.get("task_eligibility", {}).get("reasons", []),
                "task_runtime_evidence_status": leader["status"],
                "manual_decision": "not_made_by_producer",
                "outcome_used": False,
            },
            "run_outcome": {"status": "observed_excluded_from_eligibility",
                            **probe.get("run_outcome", {})},
        }
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--traffic-protocol", choices=("idm", "hybrid_startup"), required=True)
    parser.add_argument("--shared-record", type=Path,
                        help="Optional stored shared record; stale records fail closed")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory outside the scene/artifacts roots for role-specific records")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    outputs = _check_new_output(args.root, args.output_dir)
    records = build_records(args.root, args.traffic_protocol, args.shared_record)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for (role, record), path in zip(records.items(), outputs, strict=True):
        write_json(path, record)
    print(json.dumps({role: {"output": str(args.output_dir / f"controller_input_idm_{role}_v1.json"),
                            "model_route_status": record["eligibility"]["model_route_status"],
                            "shared_technical_status": record["eligibility"]["shared_technical_status"],
                            "protocol_compatibility_status": record["eligibility"]["protocol_compatibility_status"],
                            "task_status": record["eligibility"]["task_status"],
                            "controller_input_status": record["eligibility"]["controller_input_status"]}
                      for role, record in records.items()}, indent=2))


if __name__ == "__main__":
    main()
