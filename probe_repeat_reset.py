"""Replay the same late scene through repeated resets of one C environment."""

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
ap.add_argument("--cycles", type=int, default=3)
ap.add_argument("--eval-config", action="store_true")
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
late = [i for i, obj in enumerate(scene["objects"]) if not obj["valid"][0]]
assert late
env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
            episode_length=91, map_id=0, action_type="continuous",
            control_mode="control_evaluation", goal_behavior=3 if args.eval_config else 4,
            resample_frequency=0,
            **({"ini_file": str(HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini")}
               if args.eval_config else {}))
cycles = []
try:
    for cycle in range(args.cycles):
        env.reset()
        initial = env.get_state()[0]
        active = initial["active_agent_indices"]
        binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
        offsets = [(obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                    obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0])
                   for i, obj in enumerate(scene["objects"])]
        errors = []
        missing = []
        premature = []
        ego_goal_step = None
        invalid_ego_loss = None
        for t in range(91):
            entities = env.get_state()[0]["entities"]
            for i, obj in enumerate(scene["objects"]):
                e = entities[i]
                if obj["valid"][t]:
                    if e["x"] == -10000.0:
                        if i == 0:
                            if ego_goal_step is None:
                                current = obj["position"][t]
                                goal = obj["goalPosition"]
                                distance = math.dist((current["x"], current["y"]),
                                                     (goal["x"], goal["y"]))
                                if t and distance <= 2.1 and not e["collision_state"]:
                                    ego_goal_step = t
                                else:
                                    invalid_ego_loss = {"step": t, "source_distance_to_goal_at_removal_m": distance,
                                                        "collision_state": e["collision_state"]}
                            continue
                        missing.append([obj["id"], t])
                    else:
                        src = obj["position"][t]
                        errors.append(math.dist((e["x"] + offsets[i][0], e["y"] + offsets[i][1]),
                                                (src["x"], src["y"])))
                elif i in late and not any(obj["valid"][:t]) and e["x"] != -10000.0:
                    premature.append([obj["id"], t])
            if ego_goal_step is not None:
                break
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
        cycles.append({"cycle": cycle, "active_entity_indices": active,
                       "ego_goal_step": ego_goal_step, "invalid_ego_loss": invalid_ego_loss,
                       "observed_steps": t + 1,
                       "post_goal_untested_birth_track_ids": [scene["objects"][i]["id"]
                                                              for i in late if not any(scene["objects"][i]["valid"][:t + 1])],
                       "missing_count": len(missing), "premature_count": len(premature),
                       "max_position_error_m": max(errors), "matched_samples": len(errors),
                       "passed": not missing and not premature and invalid_ego_loss is None
                                 and max(errors) < 0.01})
finally:
    env.close()
report = {"binary_sha256": hashlib.sha256((root / "testing/map_000000.bin").read_bytes()).hexdigest(),
          "evaluation_config": args.eval_config,
          "runtime": runtime, "cycles": cycles,
          "source_replay_passed": all(c["passed"] for c in cycles)}
report["reset_deterministic"] = (len({tuple(c["active_entity_indices"]) for c in cycles}) == 1
    and len({(c["missing_count"], c["premature_count"], c["matched_samples"],
              round(c["max_position_error_m"], 6)) for c in cycles}) == 1)
report["passed"] = report["reset_deterministic"] and report["source_replay_passed"]
(root / ("testing/reset_evaluation_probe.json" if args.eval_config else "testing/reset_probe.json")).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if not report["passed"]:
    raise SystemExit(1)
