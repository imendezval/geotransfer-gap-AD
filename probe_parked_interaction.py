"""Synthetic near/overlap probe for a source parked car in the C runtime."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--root", type=Path, required=True)
ap.add_argument("--track-id", type=int, required=True)
args = ap.parse_args()
root = args.root.resolve()
alias = Path("/tmp") / ("geo_scene_" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
if not alias.exists():
    alias.symlink_to(root, target_is_directory=True)
sys.path.insert(0, str(HERE.parent / "behavior-bench"))
import late_spawn_runtime
runtime = late_spawn_runtime.load()
from pufferlib.ocean.drive.drive import Drive
from pufferlib.ocean.drive import binding

scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
park_idx = next(i for i, obj in enumerate(scene["objects"]) if obj["id"] == args.track_id)
assert scene["objects"][park_idx]["mark_as_expert"]

def create():
    env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
                episode_length=91, map_id=0, action_type="continuous",
                control_mode="control_evaluation", goal_behavior=4, resample_frequency=0)
    env.reset()
    return env

env = create()
try:
    park = env.get_state()[0]["entities"][park_idx]
    h = park["heading"]
    px, py = park["x"], park["y"]
    near_parked = False
    visible_probe_offset = None
    for radius in (5, 7, 9):
        for angle in np.linspace(0, 2 * math.pi, 16, endpoint=False):
            env.reset()
            ox, oy = radius * math.cos(angle), radius * math.sin(angle)
            binding.vec_set_positions(env.c_envs, [0], [px + ox], [py + oy], [h])
            env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
            ego = env.get_state()[0]["entities"][0]
            if ego["x"] == -10000.0 or ego["removed"]:
                continue
            dx, dy = px - ego["x"], py - ego["y"]
            c, s = math.cos(ego["heading"]), math.sin(ego["heading"])
            ex, ey = dx * c + dy * s, -dx * s + dy * c
            partners = env.observations[0][env.ego_features:env.ego_features + 8 * env.max_obs_partners].reshape(-1, 8)
            if any(row[7] == 1 and math.dist((row[0] / 0.02, row[1] / 0.02), (ex, ey)) < 0.5 for row in partners):
                near_parked = True
                visible_probe_offset = [float(ox), float(oy)]
                break
        if near_parked:
            break
finally:
    env.close()

env = create()
try:
    park = env.get_state()[0]["entities"][park_idx]
    binding.vec_set_positions(env.c_envs, [0], [park["x"]], [park["y"]], [park["heading"]])
    env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    ego = env.get_state()[0]["entities"][0]
    collision_with_parked = ego["collision_state"] == 1 and ego["collided_with_index"] == park_idx
    result = {"runtime": runtime, "parked_track_id": args.track_id,
              "parked_visible_within_10m": bool(near_parked),
              "visible_probe_offset_m": visible_probe_offset,
              "overlap_collision_with_parked": bool(collision_with_parked),
              "ego_collision_state": ego["collision_state"],
              "ego_collided_with_index": ego["collided_with_index"],
              "passed": bool(near_parked and collision_with_parked)}
finally:
    env.close()
(root / "testing/parked_interaction_probe.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if not result["passed"]:
    raise SystemExit(1)
