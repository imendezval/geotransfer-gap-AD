"""Diagnostic source-speed-guided IDM, without research admission claims."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "behavior-bench"))
import late_spawn_runtime


import hybrid_traffic


def run(root, gain, lateral_offset, guide_lateral=False, reference_routes=False):
    runtime = __import__("source_reference_runtime").load() if reference_routes else late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    root = root.resolve()
    scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
    alias = Path("/tmp") / ("geo_guided_" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    ini = HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini"
    env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
                episode_length=91, map_id=0, action_type="continuous",
                control_mode="control_evaluation", goal_behavior=3,
                ini_file=str(ini), resample_frequency=0)
    ego_index = scene.get("metadata", {}).get("sdc_track_index", 0)
    schedule = hybrid_traffic.release_schedule(scene)
    snapshots = {}
    first_losses = {}
    try:
        env.reset()
        initial = env.get_state()[0]
        offsets = [(obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                    obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0])
                   for i, obj in enumerate(scene["objects"])]
        for t in range(91):
            state = env.get_state()[0]
            slots = {index: slot for slot, index in enumerate(state["active_agent_indices"])}
            if ego_index in slots:
                binding.vec_set_movement_mode(env.c_envs, [slots[ego_index]],
                                              0 if lateral_offset else 2)
            hybrid_traffic.apply(env, scene, schedule, t, binding)
            if lateral_offset and t == 0 and ego_index in slots:
                binding.vec_set_movement_mode(env.c_envs, [slots[ego_index]], 0)
                e = env.get_state()[0]["entities"][ego_index]
                binding.vec_set_positions(env.c_envs, [slots[ego_index]],
                    [e["x"] - math.sin(e["heading"]) * lateral_offset],
                    [e["y"] + math.cos(e["heading"]) * lateral_offset], [e["heading"]])
            state = env.get_state()[0]
            for index, obj in enumerate(scene["objects"]):
                if index == ego_index or obj["type"] != "vehicle" or obj["mark_as_expert"]:
                    continue
                if index in schedule and t < schedule[index]:
                    continue
                slot = slots.get(index)
                if slot is None or not obj["valid"][t]:
                    continue
                entity = state["entities"][index]
                if entity["x"] == -10000.0:
                    continue
                source = obj["position"][t]
                heading = obj["heading"][t]
                dx = source["x"] - (entity["x"] + offsets[index][0])
                dy = source["y"] - (entity["y"] + offsets[index][1])
                along_error = dx * math.cos(heading) + dy * math.sin(heading)
                source_speed = math.hypot(obj["velocity"][t]["x"], obj["velocity"][t]["y"])
                target = min(30.0, max(0.0, source_speed + gain * along_error))
                if guide_lateral and entity.get('route_x') and entity.get('route_y'):
                    route = np.column_stack((entity['route_x'], entity['route_y']))
                    starts, delta = route[:-1], np.diff(route, axis=0)
                    size2 = (delta * delta).sum(axis=1)
                    source_local = np.array([source['x'], source['y']]) - offsets[index]
                    fraction = np.clip(((source_local - starts) * delta).sum(axis=1) / np.maximum(size2, 1e-12), 0, 1)
                    projected = starts + fraction[:, None] * delta
                    distances = np.linalg.norm(source_local - projected, axis=1)
                    distances[size2 < 1e-8] = np.inf
                    segment = int(distances.argmin())
                    tangent = delta[segment] / max(np.sqrt(size2[segment]), 1e-6)
                    difference = source_local - projected[segment]
                    offset = float(tangent[0] * difference[1] - tangent[1] * difference[0])
                    binding.vec_set_idm_proposals(env.c_envs, slot,
                        np.array([target], dtype=np.float32), np.array([offset], dtype=np.float32))
                else:
                    binding.vec_set_idm_target_velocity(env.c_envs, [slot], float(target))
            state = env.get_state()[0]
            for index, obj in enumerate(scene["objects"]):
                if index == ego_index or not obj["valid"][t]:
                    continue
                entity = state["entities"][index]
                if entity["x"] == -10000.0:
                    first_losses.setdefault(str(obj["id"]), t)
            if t in (10, 30, 50, 70, 80, 90):
                snapshots[str(t)] = {}
                for index, obj in enumerate(scene["objects"]):
                    if index == ego_index or not obj["valid"][t]:
                        continue
                    entity = state["entities"][index]
                    if entity["x"] == -10000.0:
                        continue
                    source = obj["position"][t]
                    error = math.dist((entity["x"] + offsets[index][0],
                                       entity["y"] + offsets[index][1]),
                                      (source["x"], source["y"]))
                    snapshots[str(t)][str(obj["id"])] = round(error, 2)
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    result = {"root": str(root), "gain": gain, "lateral_offset_m": lateral_offset,
              "guide_lateral": guide_lateral, "reference_routes": reference_routes, "runtime": runtime, "diagnostic_only": True,
              "first_source_valid_losses": first_losses, "position_errors_m": snapshots,
              "startup_release_steps": {str(scene["objects"][i]["id"]): step
                                        for i, step in schedule.items()}}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--lateral-offset-m", type=float, default=0.0)
    ap.add_argument("--guide-lateral", action="store_true")
    ap.add_argument("--reference-routes", action="store_true")
    args = ap.parse_args()
    run(args.root, args.gain, args.lateral_offset_m, args.guide_lateral, args.reference_routes)
