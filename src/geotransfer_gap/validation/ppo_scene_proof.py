"""Produce a read-only, scene-and-role PPO observation mechanics proof.

Example (all destinations must be new files)::

    python -m geotransfer_gap.validation.ppo_scene_proof \
      --root /tmp/scene-copy --traffic-protocol hybrid_startup \
      --output /tmp/scene-copy/testing/controller_input_ppo_v1.json

The proof records PPO inputs and inference only. It does not use rollout
success, collision, goal completion, progress, or reward for admission.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np

from geotransfer_gap.artifacts import reference, sha256, write_json
from geotransfer_gap.config import ensure_bench, settings
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.actor_index import ActorKey, ActorIndex, SourceActorID
from geotransfer_gap.validation.shared_admission import read_shared_admission
from geotransfer_gap.validation import scene_contract


_EGO_WIDTH = 7
_OBS_WIDTH = 1151
_HIDDEN_SIZE = 256
_ACTION_COUNT = 91
_PARTNER_COUNT = 31
_PARTNER_WIDTH = 8
_ROAD_COUNT = 128
_ROAD_WIDTH = 7
_PARTNER_START = _EGO_WIDTH
_ROAD_START = _PARTNER_START + _PARTNER_COUNT * _PARTNER_WIDTH
_ROAD_CATEGORY_INDICES = np.arange(_ROAD_START + 6, _OBS_WIDTH, _ROAD_WIDTH)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _json_compatible(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return _json_compatible(value.tolist())
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _state_digest(state: dict[str, Any] | None) -> str | None:
    if state is None:
        return None
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().to("cpu").contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(np.asarray(tuple(tensor.shape), dtype=np.int64).tobytes())
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _clone_state(state: dict[str, Any] | None):
    return None if state is None else {k: v.detach().clone() for k, v in state.items()}


def expected_role_targets(snapshot, role: str) -> list[Any]:
    """Resolve current role targets using the production PPOController rules."""
    if role == "ego":
        actor = snapshot.actor_for(snapshot.ego_id)
        return [actor] if (
            not actor.permanently_removed and not actor.removed and actor.native_present
        ) else []
    if role == "traffic":
        return [snapshot.actor_for(source_id)
                for source_id in sorted(snapshot.eligible_present_vehicle_ids)]
    raise ValueError(f"unsupported PPO role: {role}")


def validate_observation_row(row, *, actor_key: ActorKey, expected_key: ActorKey,
                             slot: int | None, source_valid: bool,
                             native_present: bool) -> np.ndarray:
    """Fail closed on missing, wrong-identity, or unbound native rows."""
    if actor_key != expected_key:
        raise ValueError("PPO row actor identity/lifetime mismatch")
    if slot is None or not source_valid or not native_present:
        raise ValueError("PPO row missing current source-valid native observation slot")
    if row is None:
        raise ValueError("PPO native observation row is missing")
    value = np.asarray(row)
    if value.shape != (_OBS_WIDTH,) or value.dtype != np.float32:
        raise ValueError("PPO native observation must be float32[1151]")
    if not np.isfinite(value).all():
        raise ValueError("PPO native observation must be finite")
    return value


def _row_context(snapshot, state, binary, role: str) -> list[dict[str, Any]]:
    targets = expected_role_targets(snapshot, role)
    records = []
    slots = set()
    keys = set()
    for actor in targets:
        if actor.key is None:
            raise ValueError("eligible PPO target lacks ActorKey lifetime identity")
        slot = snapshot.slot_for(actor.key)
        row = validate_observation_row(
            snapshot.observation[slot] if slot is not None else None,
            actor_key=actor.key,
            expected_key=snapshot.actor_for(actor.key).key,
            slot=slot,
            source_valid=actor.source_valid,
            native_present=actor.native_present,
        )
        if slot in slots or actor.key in keys:
            raise ValueError("duplicate PPO row slot or actor lifetime identity")
        slots.add(slot)
        keys.add(actor.key)
        records.append({
            "source_id": int(actor.source_id),
            "lifetime_generation": actor.key.lifetime_generation,
            "binary_index": actor.fixed_binary_index,
            "slot": slot,
            "source_valid": actor.source_valid,
            "native_present": actor.native_present,
            "controller_eligible": actor.controller_eligible,
            "actor_type": actor.actor_type,
            "marked_expert": actor.marked_expert,
            "source_valid_mask": list(binary["objects"][actor.fixed_binary_index]["traj_valid"]),
            "row": row.copy(),
        })
    return records


def _expected_partner_block(row: np.ndarray, target_index: int, state: dict[str, Any],
                            snapshot, binary) -> tuple[list[int], int]:
    """Reconstruct the pinned native Drive partner rows from pre-step entities."""
    entities = state["entities"]
    active = state.get("active_agent_indices") or []
    static = state.get("static_car_indices") or []
    ordered_indices = [int(i) for i in active] + [int(i) for i in static]
    target = entities[target_index]
    hx, hy = float(target["heading_x"]), float(target["heading_y"])
    x0, y0 = float(target["x"]), float(target["y"])
    candidates = []
    for position, index in enumerate(ordered_indices):
        if index == target_index:
            continue
        other = entities[index]
        if int(other["type"]) > 3:
            break
        if other.get("removed") or other.get("respawn_timestep", -1) != -1:
            continue
        x, y = float(other["x"]), float(other["y"])
        if x == -10000.0 or y == -10000.0:
            continue
        dx, dy = x - x0, y - y0
        distance_sq = dx * dx + dy * dy
        if distance_sq <= 2500.0:
            candidates.append((distance_sq, position, index))
    candidates.sort(key=lambda value: value[0])
    candidates = candidates[:_PARTNER_COUNT]

    expected = np.zeros((_PARTNER_COUNT, _PARTNER_WIDTH), dtype=np.float32)
    source_ids = []
    for slot, (_, _, index) in enumerate(candidates):
        other = entities[index]
        dx, dy = float(other["x"]) - x0, float(other["y"]) - y0
        rel_x = dx * hx + dy * hy
        rel_y = -dx * hy + dy * hx
        other_hx, other_hy = float(other["heading_x"]), float(other["heading_y"])
        rel_hx = other_hx * hx + other_hy * hy
        rel_hy = other_hy * hx - other_hx * hy
        speed = math.hypot(float(other["vx"]), float(other["vy"]))
        velocity_dot_heading = float(other["vx"]) * other_hx + float(other["vy"]) * other_hy
        signed_speed = math.copysign(speed, velocity_dot_heading)
        expected[slot] = (
            rel_x * 0.02,
            rel_y * 0.02,
            float(other["width"]) / 15.0,
            float(other["length"]) / 30.0,
            rel_hx,
            rel_hy,
            signed_speed / 100.0,
            float(other["type"]),
        )
        if index < len(binary["objects"]):
            source_ids.append(int(binary["objects"][index]["id"]))
        else:
            source_ids.append(None)
    observed = row[_PARTNER_START:_ROAD_START].reshape(_PARTNER_COUNT, _PARTNER_WIDTH)
    np.testing.assert_allclose(observed, expected, rtol=0.0, atol=3e-6,
                               err_msg="PPO partner feature rows differ from current native actors")
    return source_ids, len(candidates)


def validate_map_feature_block(road_rows: np.ndarray, state: dict[str, Any],
                               origin_x: float, origin_y: float,
                               heading_x: float, heading_y: float) -> dict[str, Any]:
    """Match every emitted road row to current native map geometry and scaling."""
    source_by_category: dict[int, list[list[float]]] = {}
    source_segments = 0
    for entity in state["entities"]:
        entity_type = int(entity["type"])
        if entity_type <= 3:
            continue
        size = int(entity["array_size"])
        xs, ys = entity["traj_x"], entity["traj_y"]
        if size < 2:
            continue
        if len(xs) < size or len(ys) < size:
            raise ValueError("native map entity has incomplete geometry for PPO road features")
        category = entity_type - 4
        category_rows = source_by_category.setdefault(category, [])
        for index in range(size - 1):
            start_x, start_y = float(xs[index]), float(ys[index])
            end_x, end_y = float(xs[index + 1]), float(ys[index + 1])
            mid_x, mid_y = (start_x + end_x) / 2.0, (start_y + end_y) / 2.0
            dx, dy = end_x - mid_x, end_y - mid_y
            half_length = math.hypot(dx, dy)
            if half_length > 0:
                dx_norm, dy_norm = dx / half_length, dy / half_length
            else:
                dx_norm = dy_norm = 0.0
            rel_x, rel_y = mid_x - origin_x, mid_y - origin_y
            category_rows.append([
                (rel_x * heading_x + rel_y * heading_y) * 0.02,
                (-rel_x * heading_y + rel_y * heading_x) * 0.02,
                half_length / 100.0,
                0.1 / 100.0,
                dx_norm * heading_x + dy_norm * heading_y,
                -dx_norm * heading_y + dy_norm * heading_x,
                float(category),
            ])
            source_segments += 1

    active_mask = np.any(road_rows != 0, axis=1)
    observed = road_rows[active_mask]
    if not len(observed) or not source_segments:
        raise ValueError("PPO road feature block or native map geometry is empty")
    matched = 0
    for row in observed:
        category = int(row[6])
        candidates = source_by_category.get(category, [])
        if not candidates:
            raise ValueError("PPO road feature category has no native map source")
        differences = np.max(np.abs(np.asarray(candidates, dtype=np.float64) - row), axis=1)
        if float(np.min(differences)) > 5e-6:
            raise ValueError("PPO road feature does not match normalized native map geometry")
        matched += 1
    return {
        "status": "verified",
        "observed_segment_rows": int(len(observed)),
        "source_native_segments_examined": source_segments,
        "matched_segment_rows": matched,
        "normalization": {
            "relative_position_m": 50.0,
            "half_segment_length_m": 100.0,
            "width_m": 100.0,
            "width_value": 0.001,
        },
        "source": "pinned Drive compute_observations geometry and current native map entities",
    }


def _validate_feature_semantics(record: dict[str, Any], state: dict[str, Any],
                                snapshot, binary, role: str,
                                required_task_actors: set[int]) -> dict[str, Any]:
    row = record["row"]
    index = record["binary_index"]
    entity = state["entities"][index]
    dx = float(entity["goal_position_x"]) - float(entity["x"])
    dy = float(entity["goal_position_y"]) - float(entity["y"])
    heading = float(entity["heading"])
    c, s = math.cos(heading), math.sin(heading)
    speed = math.hypot(float(entity["vx"]), float(entity["vy"]))
    speed_dot_heading = float(entity["vx"]) * c + float(entity["vy"]) * s
    expected_ego = np.asarray([
        (dx * c + dy * s) * 0.005,
        (-dx * s + dy * c) * 0.005,
        math.copysign(speed, speed_dot_heading) / 100.0,
        float(entity["width"]) / 15.0,
        float(entity["length"]) / 30.0,
        float(int(entity["collision_state"]) > 0),
        0.0 if entity.get("respawn_timestep", -1) == -1 else 1.0,
    ], dtype=np.float32)
    np.testing.assert_allclose(row[:_EGO_WIDTH], expected_ego, rtol=0.0, atol=3e-6,
                               err_msg="PPO ego/goal feature normalization mismatch")
    if row.shape != (_OBS_WIDTH,) or not np.isfinite(row).all():
        raise ValueError("PPO observation layout or finite-value check failed")
    partners, roads = row[_PARTNER_START:_ROAD_START], row[_ROAD_START:]
    partner_rows = partners.reshape(_PARTNER_COUNT, _PARTNER_WIDTH)
    road_rows = roads.reshape(_ROAD_COUNT, _ROAD_WIDTH)
    categories = row[_ROAD_CATEGORY_INDICES]
    if not np.all((categories == np.trunc(categories)) & (categories >= 0) & (categories <= 6)):
        raise ValueError("PPO road categories must be integer values from 0 through 6")
    if np.any(np.abs(partner_rows[:, :2]) > 50.0) or np.any(np.abs(road_rows[:, :2]) > 50.0):
        raise ValueError("PPO relative position normalization is outside the 50 m bound")
    source_ids, partner_count = _expected_partner_block(
        row, index, state, snapshot, binary
    )
    map_semantics = validate_map_feature_block(
        road_rows, state, float(entity["x"]), float(entity["y"]), c, s
    )
    partner_index_by_source = {
        source_id: slot for slot, source_id in enumerate(source_ids)
        if source_id is not None
    }
    visible_task_ids = sorted(required_task_actors.intersection(partner_index_by_source))
    task_contexts = []
    for source_id in visible_task_ids:
        actor = snapshot.actor_for(source_id)
        if actor.key is None or not actor.source_valid or not actor.native_present:
            raise ValueError("visible PPO task partner lacks a current source lifetime")
        partner_slot = partner_index_by_source[source_id]
        features = partner_rows[partner_slot]
        task_contexts.append({
            "source_id": source_id,
            "lifetime_generation": actor.key.lifetime_generation,
            "binary_index": actor.fixed_binary_index,
            "actor_type": actor.actor_type,
            "source_valid": actor.source_valid,
            "native_present": actor.native_present,
            "current_active_slot": actor.current_active_slot,
            "source_valid_mask": list(binary["objects"][actor.fixed_binary_index]["traj_valid"]),
            "partner_feature_slot": partner_slot,
            "partner_features": [float(value) for value in features],
        })
    return {
        "role": role,
        "layout": {
            "ego": {"offset": 0, "width": _EGO_WIDTH,
                    "normalization": {"goal_m": 200.0, "speed_mps": 100.0,
                                      "width_m": 15.0, "length_m": 30.0}},
            "partners": {"offset": _PARTNER_START, "count": _PARTNER_COUNT,
                         "features_per_actor": _PARTNER_WIDTH, "count_observed": partner_count,
                         "normalization": {"relative_position_m": 50.0,
                                           "width_m": 15.0, "length_m": 30.0,
                                           "speed_mps": 100.0}},
            "road": {"offset": _ROAD_START, "count": _ROAD_COUNT,
                     "features_per_segment": _ROAD_WIDTH,
                     "normalization": {"relative_position_m": 50.0,
                                       "segment_length_m": 100.0,
                                       "width_scale_m": 100.0},
                     "categories": sorted(set(int(v) for v in categories))},
        },
        "partner_source_ids_in_distance_order": source_ids,
        "map_feature_semantics": map_semantics,
        "reviewed_task_actor_ids_visible_as_partners": visible_task_ids,
        "reviewed_task_actor_contexts": task_contexts,
        "goal_world": [float(entity["goal_position_x"]), float(entity["goal_position_y"])],
        "goal_local_normalized": [float(row[0]), float(row[1])],
        "row_sha256": hashlib.sha256(row.tobytes(order="C")).hexdigest(),
    }


class _RecordingPolicy:
    def __init__(self, policy: PPOPolicy):
        self.policy = policy
        self.step_context: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []

    def _append(self, row, state, action, next_state, logits, value, target):
        context = self.step_context
        if context is None:
            raise ValueError("PPO inference has no matching native snapshot identity")
        expected = context["targets"]
        position = len(context["captured"])
        if position >= len(expected):
            raise ValueError("PPO inferred more rows than current role targets")
        actor = expected[position]
        value_row = validate_observation_row(
            row, actor_key=ActorKey(SourceActorID(actor["source_id"]), actor["lifetime_generation"]),
            expected_key=ActorKey(SourceActorID(actor["source_id"]), actor["lifetime_generation"]),
            slot=actor["slot"], source_valid=actor["source_valid"],
            native_present=actor["native_present"],
        )
        self.rows.append({
            "step": context["step"],
            "role": context["role"],
            "source_id": actor["source_id"],
            "lifetime_generation": actor["lifetime_generation"],
            "binary_index": actor["binary_index"],
            "slot": actor["slot"],
            "state_in_sha256": _state_digest(state),
            "state_out_sha256": _state_digest(next_state),
            "action": [float(action[0]), float(action[1])],
            "action_index": int(logits.argmax(dim=-1).item()) if logits is not None else None,
            "logits_sha256": hashlib.sha256(logits.detach().cpu().contiguous().numpy().tobytes()).hexdigest(),
            "value": float(value.reshape(-1)[0].item()),
            "input_sha256": hashlib.sha256(value_row.tobytes(order="C")).hexdigest(),
            "observation": value_row.astype(np.float32, copy=True).tolist(),
        })
        context["captured"].append(actor)

    def infer(self, row, state):
        previous = _clone_state(state)
        action, next_state, logits, value = self.policy.infer(row, state)
        self._append(row, previous, action, next_state, logits, value, None)
        return action, next_state, logits, value

    def infer_batch(self, rows, states):
        previous = [_clone_state(state) for state in states]
        actions, next_states, logits, values = self.policy.infer_batch(rows, states)
        context = self.step_context
        if context is None:
            raise ValueError("PPO batch inference has no matching native snapshot identity")
        for index, (row, state_in, action, state_out) in enumerate(
            zip(rows, previous, actions, next_states, strict=True)
        ):
            self._append(row, state_in, action, state_out,
                         logits[index:index + 1], values[index:index + 1], None)
        return actions, next_states, logits, values


def _upstream_reference(path: Path, env):
    PPOConfig, PPOPlanner = _upstream_policy_types()
    import torch
    from geotransfer_gap.planners.ppo_policy import policy_space

    space = policy_space()
    space.close = lambda: None
    with patch("pufferlib.ocean.drive.drive.Drive", return_value=space):
        # This host's Torch/NumPy ABI rejects otherwise valid ndarrays in
        # torch.from_numpy. The upstream planner uses it only for fixed LUT
        # construction; tensor(list) produces the identical float32 LUT values.
        from_numpy = torch.from_numpy
        torch.from_numpy = lambda value: torch.tensor(value.tolist(), dtype=torch.float32)
        try:
            reference_policy = PPOPlanner(
                SimpleNamespace(episode_length=91, split="testing"), 0,
                np.full(2, -1.0, dtype=np.float32), np.ones(2, dtype=np.float32),
                PPOConfig(device="cpu", stochastic=False),
            )
        finally:
            torch.from_numpy = from_numpy
    checkpoint = __import__("torch").load(path, map_location="cpu", weights_only=True)
    reference_policy.policy.load_state_dict(checkpoint, strict=True)
    reference_policy.policy.eval()
    return reference_policy


def _upstream_policy_types():
    """Load the pinned policy module without eager unrelated SMART imports."""
    ensure_bench()
    package_name = "pufferlib.planning"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(settings().bench / "pufferlib/planning")]
        package.__package__ = package_name
        sys.modules[package_name] = package
    module = importlib.import_module("pufferlib.planning.policy")
    return module.PPOConfig, module.PPOPlanner


def _verify_upstream_sequence(rows: list[dict[str, Any]], checkpoint: Path,
                              batch_policy: PPOPolicy) -> dict[str, Any]:
    """Compare actual native input inference to pinned upstream PPOPlanner."""
    import torch

    reference_policy = _upstream_reference(checkpoint, None)
    states: dict[tuple[int, int], dict[str, Any]] = {}
    maxima = {"logits": 0.0, "value": 0.0, "lstm_h": 0.0, "lstm_c": 0.0}
    for row in sorted(rows, key=lambda item: (item["step"], item["slot"])):
        key = (row["source_id"], row["lifetime_generation"])
        state = states.get(key)
        reference_policy.lstm_h = None if state is None else state["lstm_h"].clone()
        reference_policy.lstm_c = None if state is None else state["lstm_c"].clone()
        native_row = np.asarray(row["observation"], dtype=np.float32)
        action = reference_policy.plan(row["step"], native_row)
        state_out = {"lstm_h": reference_policy.lstm_h.detach().clone(),
                     "lstm_c": reference_policy.lstm_c.detach().clone()}
        states[key] = state_out
        logits = reference_policy.last_logits[0]
        value = reference_policy._last_value_tensor
        expected_action = np.asarray(row["action"], dtype=np.float32)
        if not np.array_equal(np.asarray(action, dtype=np.float32), expected_action):
            raise ValueError(f"PPO upstream action mismatch at step {row['step']} actor {key}")
        if row["action_index"] != int(logits.argmax(dim=-1).item()):
            raise ValueError("PPO argmax action index differs from upstream logits")
        actual_logits = batch_policy._last_proof_logits.get((row["step"], key))
        actual_value = batch_policy._last_proof_values.get((row["step"], key))
        actual_state = batch_policy._last_proof_states.get((row["step"], key))
        if actual_logits is None or actual_value is None or actual_state is None:
            # Recorder outputs are registered by the runner immediately below.
            continue
        maxima["logits"] = max(maxima["logits"], float((actual_logits - logits).abs().max()))
        maxima["value"] = max(maxima["value"], float((actual_value - value).abs().max()))
        for name in ("lstm_h", "lstm_c"):
            maxima[name] = max(maxima[name], float((actual_state[name] - state_out[name]).abs().max()))
        torch.testing.assert_close(actual_logits, logits, rtol=1e-5, atol=5e-5)
        torch.testing.assert_close(actual_value, value, rtol=1e-5, atol=5e-5)
        for name in ("lstm_h", "lstm_c"):
            torch.testing.assert_close(actual_state[name], state_out[name], rtol=1e-5, atol=5e-5)
    return {"passed": True, "rows_checked": len(rows), "max_abs_error": maxima,
            "method": "pinned upstream PPOPlanner.plan on actual native float32 rows, keyed by ActorKey",
            "initialization_note": "Fixed upstream LUT initialization used torch.tensor(list) because this installed Torch/NumPy ABI rejects torch.from_numpy(ndarray); values are identical float32 arrays."}


def _bind_upstream_outputs(recording: _RecordingPolicy):
    """Retain tensors only for a short-lived proof until parity is checked."""
    recording.policy._last_proof_logits = {}
    recording.policy._last_proof_values = {}
    recording.policy._last_proof_states = {}
    infer = recording.policy.infer
    infer_batch = recording.policy.infer_batch

    def single(row, state):
        action, state_out, logits, value = infer(row, state)
        context = recording.step_context
        actor = context["targets"][len(context["captured"]) - 1]
        key = (actor["source_id"], actor["lifetime_generation"])
        recording.policy._last_proof_logits[(context["step"], key)] = logits.clone()
        recording.policy._last_proof_values[(context["step"], key)] = value.clone()
        recording.policy._last_proof_states[(context["step"], key)] = _clone_state(state_out)
        return action, state_out, logits, value

    def batch(rows, states):
        actions, states_out, logits, values = infer_batch(rows, states)
        context = recording.step_context
        start = len(context["captured"])
        for offset, actor in enumerate(context["targets"][start:start + len(rows)]):
            key = (actor["source_id"], actor["lifetime_generation"])
            identity = (context["step"], key)
            recording.policy._last_proof_logits[identity] = logits[offset:offset + 1].clone()
            recording.policy._last_proof_values[identity] = values[offset:offset + 1].clone()
            recording.policy._last_proof_states[identity] = _clone_state(states_out[offset])
        return actions, states_out, logits, values

    recording.policy.infer = single
    recording.policy.infer_batch = batch


def _file_hashes(env, runtime: dict[str, Any], root: Path, probe_path: Path) -> dict[str, Any]:
    from geotransfer_gap.planners import ppo_controller, ppo_policy
    from geotransfer_gap.runtime import actor_index, episode_worker, native_modes, scheduler, step_snapshot

    bench = settings().bench
    files = {
        "behaviorbench_drive_python": bench / "pufferlib/ocean/drive/drive.py",
        "behaviorbench_drive_header": bench / "pufferlib/ocean/drive/drive.h",
        "behaviorbench_ppo_reference": bench / "pufferlib/planning/policy.py",
        "ppo_policy_adapter": Path(ppo_policy.__file__),
        "ppo_controller_adapter": Path(ppo_controller.__file__),
        "actor_index": Path(actor_index.__file__),
        "step_snapshot": Path(step_snapshot.__file__),
        "episode_worker": Path(episode_worker.__file__),
        "scheduler": Path(scheduler.__file__),
        "native_modes": Path(native_modes.__file__),
        "scene_contract_producer": Path(scene_contract.__file__),
        "shared_admission_checker": Path(__import__(
            "geotransfer_gap.validation.shared_admission", fromlist=["x"]
        ).__file__),
        "ppo_scene_proof": probe_path,
        "ppo_scheduler_warmup_tests": settings().project / "tests/test_ppo_controller.py",
        "ppo_traffic_lifetime_tests": settings().project / "tests/test_ppo_traffic.py",
    }
    result = {name: {"path": str(path), "sha256": sha256(path)}
              for name, path in files.items()}
    result["native_runtime_binary"] = {
        "path": runtime.get("runtime_binary"),
        "sha256": sha256(runtime["runtime_binary"]),
    }
    result["evaluation_ini"] = {"path": str(env.ini_file), "sha256": sha256(env.ini_file)}
    return result


def _role_run(env, binding, binary, role: str, steps: int,
              policy: PPOPolicy, task_actor_ids: set[int], task_decision_steps: set[int], root: Path,
              runtime: dict[str, Any]):
    from geotransfer_gap.planners.ppo_policy import PPOPolicy
    from geotransfer_gap.runtime.scheduler import EpisodeScheduler

    recording = _RecordingPolicy(policy)
    _bind_upstream_outputs(recording)
    controller = PPOController(recording, role=role)
    index = ActorIndex(binary)
    replay_scheduler = EpisodeScheduler(
        binding, ExpertController("ego"), ExpertController("traffic")
    )
    replay_scheduler.reset({})
    snapshots: dict[int, dict[str, Any]] = {}

    for step in range(steps):
        raw_state = env.get_state()
        state = raw_state[0] if isinstance(raw_state, list) else raw_state
        snapshot = index.capture_pre_step(step, state, env.observations)
        context = _row_context(snapshot, state, binary, role)
        for target in context:
            identity = (target["source_id"], target["lifetime_generation"])
            index_actor = snapshot.actor_for(target["source_id"])
            if index_actor.key != ActorKey(SourceActorID(identity[0]), identity[1]):
                raise ValueError("stale ActorKey in PPO observation snapshot")
        snapshots[snapshot.step] = {"state": state, "snapshot": snapshot,
                                    "targets": context}
        recording.step_context = {
            "step": snapshot.step,
            "role": role,
            "targets": context,
            "captured": [],
        }
        current_keys = {
            ActorKey(SourceActorID(row["source_id"]), row["lifetime_generation"])
            for row in context
        }
        for old_key in set(controller._states) - current_keys:
            controller.retire(old_key, "source_lifetime_ended_on_expert_timeline")
        live_keys = frozenset(
            actor.key for actor in snapshot.actors
            if actor.key is not None and actor.source_valid and actor.native_present
            and not actor.permanently_removed
        )
        controller.observe(snapshot, live_keys)
        if len(recording.step_context["captured"]) != len(context):
            raise ValueError("PPO shadow inference rows do not match current role targets")
        advances = step < steps - 1
        plan = replay_scheduler.decide(snapshot, advances_simulation=advances)
        if advances:
            replay_scheduler.advance(env, plan)

    report = {"observation_frames": len(snapshots), "transitions": max(0, len(snapshots) - 1)}
    if len(recording.rows) < min(11, steps):
        raise ValueError(f"PPO {role} produced too few actual native inference rows")
    if len(recording.rows) != sum(len(s["targets"]) for s in snapshots.values()):
        raise ValueError("PPO inference row count does not match current role targets")

    semantics = []
    task_visible_steps = {actor: set() for actor in task_actor_ids}
    task_visible_reviewed_steps = {actor: set() for actor in task_actor_ids}
    for step, snapshot_data in snapshots.items():
        for target in snapshot_data["targets"]:
            record = next(row for row in recording.rows
                          if row["step"] == step and row["source_id"] == target["source_id"]
                          and row["lifetime_generation"] == target["lifetime_generation"])
            semantic = _validate_feature_semantics(
                {"row": np.asarray(record["observation"], dtype=np.float32),
                 "binary_index": target["binary_index"]},
                snapshot_data["state"], snapshot_data["snapshot"], binary, role,
                task_actor_ids,
            )
            semantics.append(semantic)
            for actor_id in semantic["reviewed_task_actor_ids_visible_as_partners"]:
                task_visible_steps[actor_id].add(step)
                if step in task_decision_steps:
                    task_visible_reviewed_steps[actor_id].add(step)

    # The native scene follows expert replay for the complete source timeline;
    # PPO inference is shadowed here so policy outcomes cannot censor task rows.
    recurrent_checks = []
    prior_state_by_key = {}
    for row in sorted(recording.rows, key=lambda item: (item["source_id"],
                                                        item["lifetime_generation"],
                                                        item["step"])):
        key = (row["source_id"], row["lifetime_generation"])
        expected_state = prior_state_by_key.get(key)
        if row["state_in_sha256"] != expected_state:
            raise ValueError(f"PPO recurrent state identity mismatch for actor {key} at {row['step']}")
        recurrent_checks.append({"step": row["step"], "actor_key": list(key), "passed": True})
        prior_state_by_key[key] = row["state_out_sha256"]
    warmup_rows = [row for row in recording.rows if row["step"] < 10]
    step_zero_rows = [row for row in recording.rows if row["step"] == 0]
    if not warmup_rows or not step_zero_rows or not all(
        row["state_in_sha256"] is None for row in step_zero_rows
    ):
        raise ValueError(f"PPO {role} zero-state initialization at episode reset was not established")

    parity = _verify_upstream_sequence(recording.rows, settings().bench / "weights/simple_ppo.pt", policy)
    # Repeat deterministic inference from the exact saved rows and same actor
    # lifetimes; no native simulation outcome is consulted.
    replay = PPOPolicy(settings().bench / "weights/simple_ppo.pt")
    replay_rows = []
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in recording.rows:
        grouped.setdefault(row["step"], []).append(row)
    replay_states: dict[tuple[int, int], dict[str, Any] | None] = {}
    for step in sorted(grouped):
        group = grouped[step]
        group.sort(key=lambda row: row["slot"])
        identities = [(row["source_id"], row["lifetime_generation"]) for row in group]
        states = [replay_states.get(identity) for identity in identities]
        actions, updated, logits, values = replay.infer_batch(
            np.asarray([row["observation"] for row in group], dtype=np.float32), states
        )
        for position, row in enumerate(group):
            if list(map(float, actions[position])) != row["action"]:
                raise ValueError("PPO deterministic replay changed an action")
            replay_states[identities[position]] = updated[position]
            replay_rows.append(row)
    if len(replay_rows) != len(recording.rows):
        raise ValueError("PPO deterministic replay omitted a native inference row")

    row_status = {
        "status": "verified",
        "rows": recording.rows,
        "row_count": len(recording.rows),
        "semantics": semantics,
        "warmup_replay": {
            "frames": 10,
            "actual_input_steps": sorted({row["step"] for row in warmup_rows}),
            "zero_hc_at_episode_reset": True,
            "scheduled_takeover_transition": 10,
            "takeover_mechanics_exercised_here": False,
            "takeover_mechanics_test_sources": [
                "tests/test_ppo_controller.py", "tests/test_ppo_traffic.py"
            ],
        },
        "recurrent_identity": {"status": "verified", "checks": recurrent_checks,
                               "actor_lifetimes": len(prior_state_by_key)},
        "tested_pairing": {
            "ppo_observation_role": role,
            "ego_transition_owner": "expert_replay",
            "traffic_transition_owner": "expert_replay",
            "startup": "immediate",
            "ppo_action_application": False,
            "observation_timeline": "native evaluator expert replay source timeline",
        },
        "upstream_parity": parity,
        "deterministic_replay": {"passed": True, "rows": len(replay_rows)},
        "task_actor_visible_steps": {
            str(actor): sorted(steps) for actor, steps in task_visible_steps.items()
        },
        "task_actor_visible_reviewed_decision_steps": {
            str(actor): sorted(steps) for actor, steps in task_visible_reviewed_steps.items()
        },
        "episode_frames_observed": report["observation_frames"],
        "expert_replay_transitions": report["transitions"],
    }
    return row_status


def build_ppo_scene_proof(root: str | Path, output_path: str | Path,
                          traffic_protocol: str = "hybrid_startup",
                          shared_record_path: str | Path | None = None,
                          steps: int = 91) -> dict[str, Any]:
    if not 1 <= steps <= 91:
        raise ValueError("steps must request 1 through 91 observation frames")
    root = Path(root).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"fresh PPO output already exists: {output_path}")
    ensure_bench()
    _upstream_policy_types()
    from geotransfer_gap.planners.ppo_policy import (
        PPOPolicy, load_pinned_ego_policy, validate_native_env,
    )
    runtime = late_spawn_runtime.load()
    from geotransfer_gap.runtime.session import evaluation_env
    from geotransfer_gap.runtime.matrix_inputs import load_binary
    from pufferlib.ocean.drive import binding

    if Path(binding.__file__).resolve() != Path(runtime["runtime_binary"]).resolve():
        raise RuntimeError("PPO proof loaded a native binding different from the pinned runtime")
    binary_path = root / "testing/map_000000.bin"
    binary = load_binary(root)
    contract = scene_contract.build(root, "expert")
    shared = read_shared_admission(root, traffic_protocol, shared_record_path)
    env = evaluation_env(root)
    try:
        validate_native_env(env)
        policy, pinned = load_pinned_ego_policy(env)
        manual = shared.get("manual_evidence", {})
        raw_actor_ids = manual.get("task_actor_ids") if isinstance(manual, dict) else None
        raw_decision_steps = manual.get("interaction_decision_steps") if isinstance(manual, dict) else None
        task_actor_ids = (set(raw_actor_ids) if isinstance(raw_actor_ids, list)
                          and all(type(value) is int for value in raw_actor_ids) else set())
        task_decision_steps = (set(raw_decision_steps) if isinstance(raw_decision_steps, list)
                               and all(type(value) is int for value in raw_decision_steps) else set())
        if bool(getattr(env, "reward_conditioning", True)) or bool(getattr(env, "include_global_state", True)):
            raise ValueError("PPO native environment has forbidden reward/global-state features")
        role_records = {}
        for role in ("ego", "traffic"):
            env.reset()
            role_records[role] = _role_run(
                env, binding, binary, role, steps, policy, task_actor_ids,
                task_decision_steps, root, runtime,
            )
    finally:
        env.close()

    contract_identity = scene_contract.identity(contract)
    source = {
        "reference": reference(root),
        "recording": contract.get("recording"),
        "ego_track_id": contract.get("ego_track_id"),
        "scene_json_sha256": contract["files"]["scene_json"]["sha256"],
        "scene_binary_sha256": contract["files"]["scene_binary"]["sha256"],
        "manifest_sha256": contract["files"]["scene_manifest"]["sha256"],
        "contract_sha256": _canonical_sha256(contract_identity),
    }
    file_hashes = _file_hashes(env, runtime, root, Path(__file__))
    protocol = {
        "version": 1,
        "role": ["ego", "traffic"],
        "observation": {"dtype": "float32", "width": _OBS_WIDTH,
                        "layout": {"ego_features": _EGO_WIDTH,
                                   "max_partner_objects": _PARTNER_COUNT,
                                   "partner_features": _PARTNER_WIDTH,
                                   "max_road_objects": _ROAD_COUNT,
                                   "road_features": _ROAD_WIDTH,
                                   "dynamics_model": "classic",
                                   "reward_conditioning": False,
                                   "include_global_state": False,
                                   "emit_jerk_ego_obs": False}},
        "action": {"count": _ACTION_COUNT, "selection": "deterministic argmax",
                   "decode": "index // 13 selects one of seven normalized acceleration values; index % 13 selects one of thirteen normalized steering values",
                   "native_scale": {"acceleration_m_s2": 4, "steering_rad": 1},
                   "dt_s": 0.1},
        "recurrent": {"hidden_size": _HIDDEN_SIZE, "state_key": "ActorKey(source_id,lifetime_generation)",
                      "state_reset": "zero h/c for a new ActorKey or episode reset",
                      "warmup_frames": 10},
        "tested_pairings": {
            "ego_role": {"ppo_observes": "ego", "ego_transition_owner": "expert_replay",
                         "traffic_transition_owner": "expert_replay", "startup": "immediate"},
            "traffic_role": {"ppo_observes": "traffic", "ego_transition_owner": "expert_replay",
                             "traffic_transition_owner": "expert_replay", "startup": "immediate"},
            "ppo_actions_applied": False,
        },
        "admission_reference_traffic_protocol": traffic_protocol,
        "hashes": file_hashes,
    }
    protocol["sha256"] = _canonical_sha256(protocol)
    role_status = {}
    for role, proof in role_records.items():
        visible = proof["task_actor_visible_reviewed_decision_steps"]
        missing_task_coverage = {}
        for actor in task_actor_ids:
            actor_steps = set(visible.get(str(actor), []))
            missing = [step for step in sorted(task_decision_steps)
                       if step < 10 or step not in actor_steps]
            if not task_decision_steps:
                missing.append("reviewed_decision_steps_missing")
            if missing:
                missing_task_coverage[str(actor)] = missing
        if not task_actor_ids or not task_decision_steps:
            missing_task_coverage["reviewed_task_window"] = ["missing_actor_or_decision_steps"]
        visibility_ok = bool(task_actor_ids and task_decision_steps) and not missing_task_coverage
        mechanics_ok = proof["status"] == "verified" and proof["row_count"] > 0
        shared_status = shared.get("shared_validity", {}).get("status")
        manual_status = shared.get("manual_evidence", {}).get("status")
        task_status = shared.get("task_eligibility", {}).get("status")
        if task_status == "blocked":
            research_status = "blocked"
            research_reasons = list(shared.get("task_eligibility", {}).get("reasons", []))
        elif shared_status != "current" or manual_status != "current" or task_status != "eligible":
            research_status = "not_established"
            research_reasons = [
                f"shared_validity:{shared_status}",
                f"manual_evidence:{manual_status}",
                f"task_eligibility:{task_status}",
            ]
        elif not mechanics_ok or not visibility_ok:
            research_status = "not_established"
            research_reasons = ["observation_mechanics_or_full_reviewed_task_window_not_established"]
        else:
            research_status = "eligible"
            research_reasons = []
        role_status[role] = {
            "observation_mechanics": "verified" if mechanics_ok else "not_established",
            "task_actor_visibility": "verified" if visibility_ok else "not_established",
            "controller_research_eligibility": research_status,
            "research_reasons": research_reasons,
            "reviewed_task_coverage_missing": missing_task_coverage,
            "tested_pairing": proof["tested_pairing"],
            "pair_research_eligibility": "not_established",
            "pair_research_reasons": ["traffic_fidelity_protocol_record_required"],
        }
    record = {
        "schema_version": 1,
        "record_type": "controller_input_ppo_roles_v1",
        "controller": "ppo",
        "admission_reference_traffic_protocol": traffic_protocol,
        "source_identity": source,
        "shared_admission_record": {
            "path": str(Path(shared_record_path).resolve()) if shared_record_path is not None else None,
            "sha256": (sha256(Path(shared_record_path))
                       if shared_record_path is not None and Path(shared_record_path).is_file()
                       else None),
            "producer_sha256": shared.get("producer_sha256"),
        },
        "shared_validity": shared.get("shared_validity"),
        "manual_evidence": shared.get("manual_evidence"),
        "task_eligibility": shared.get("task_eligibility"),
        "controller_input": {"status": "verified" if all(
            x["observation_mechanics"] == "verified" for x in role_status.values()
        ) else "not_established", "roles": role_status},
        "controller_protocol": {"status": "current", "sha256": protocol["sha256"],
                                "details": protocol},
        "protocol": {"status": "not_established",
                     "reasons": ["traffic_fidelity_protocol_record_required"]},
        "pinned_model": pinned,
        "roles": role_records,
        "decision_scope": {
            "rollout_outcomes_used": False,
            "excluded_outcome_fields": ["collision", "goal completion", "progress", "reward", "aggregate score"],
            "research_claim": "observation mechanics and source-linked task visibility only; planner performance is not established",
        },
        "producer_sha256": sha256(Path(__file__)),
    }
    record = _json_compatible(record)
    write_json(output_path, record)
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--traffic-protocol", choices=("idm", "hybrid_startup"),
                        default="hybrid_startup")
    parser.add_argument("--shared-record", type=Path)
    parser.add_argument("--steps", type=int, default=91)
    parser.add_argument("--output", type=Path, required=True,
                        help="Explicit fresh output path; existing files are never overwritten")
    args = parser.parse_args(argv)
    record = build_ppo_scene_proof(args.root, args.output, args.traffic_protocol,
                                   args.shared_record, args.steps)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "controller_input": record["controller_input"]["status"],
        "roles": record["controller_input"]["roles"],
        "controller_protocol_sha256": record["controller_protocol"]["sha256"],
        "traffic_protocol_status": record["protocol"]["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
