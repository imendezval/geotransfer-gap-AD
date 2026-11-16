"""Verify parked vehicles follow recorded samples while nearby traffic uses IDM."""

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
ap.add_argument("--no-early-reset", action="store_true", help="Technical full-duration probe only")
ap.add_argument("--eval-config", action="store_true", help="Use BehaviorBench evaluation.ini and its box scaling")
args = ap.parse_args()
if args.no_early_reset and args.eval_config:
    ap.error("Choose one config mode")
root = args.root.resolve()
alias = Path("/tmp") / ("geo_scene_" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
if not alias.exists():
    alias.symlink_to(root, target_is_directory=True)
sys.path.insert(0, str(HERE.parent / "behavior-bench"))
import late_spawn_runtime
runtime = late_spawn_runtime.load()
from pufferlib.ocean.drive.drive import Drive
from pufferlib.ocean.drive import binding

ini_path = HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini" if args.eval_config else None
if args.no_early_reset:
    source_ini = HERE.parent / "behavior-bench/pufferlib/config/ocean/drive.ini"
    ini_text = source_ini.read_text()
    assert "termination_mode = 1 #" in ini_text
    ini_path = Path("/tmp") / ("geo_parked_ini_" + hashlib.sha256(ini_text.encode()).hexdigest()[:12] + ".ini")
    ini_path.write_text(ini_text.replace("termination_mode = 1 #", "termination_mode = 0 #"))

scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
parked = {i: obj for i, obj in enumerate(scene["objects"]) if obj["mark_as_expert"]}
env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
            episode_length=91, map_id=0, action_type="continuous",
            control_mode="control_evaluation", goal_behavior=3 if args.eval_config else 4,
            idm_others=True, resample_frequency=0,
            **({"ini_file": str(ini_path)} if ini_path else {}))
try:
    env.reset()
    # Keep the episode on the recorded ego path while testing the parked
    # background lifecycle under evaluator termination settings.
    binding.vec_set_movement_mode(env.c_envs, [0], 2)
    initial = env.get_state()[0]
    origins = {i: (obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                   obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0])
               for i, obj in parked.items()}
    active = set(initial["active_agent_indices"])
    scale = 1.0 if args.eval_config else 0.7
    dimension_errors = [abs(initial["entities"][i][field] - obj[field] * scale)
                        for i, obj in parked.items() for field in ("width", "length")]
    errors = []
    error_details = []
    missing = []
    ego_goal_step = None
    invalid_ego_terminal = False
    for t in range(91):
        entities = env.get_state()[0]["entities"]
        if t and entities[0]["x"] == -10000.0:
            current = scene["objects"][0]["position"][t]
            goal = scene["objects"][0]["goalPosition"]
            ego_goal_step = t
            invalid_ego_terminal = (math.dist((current["x"], current["y"]),
                                               (goal["x"], goal["y"])) > 2.1
                                    or entities[0]["collision_state"] != 0)
            break
        for i, obj in parked.items():
            if not obj["valid"][t]:
                continue
            e = entities[i]
            if e["x"] == -10000.0:
                missing.append([obj["id"], t])
                continue
            expected = obj["position"][t]
            error = math.dist((e["x"] + origins[i][0], e["y"] + origins[i][1]),
                              (expected["x"], expected["y"]))
            errors.append(error)
            if error > 0.001:
                error_details.append({"track_id": obj["id"], "step": t, "error_m": error})
        if t < 90:
            env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    result = {"binary_sha256": hashlib.sha256((root / "testing/map_000000.bin").read_bytes()).hexdigest(),
              "test_termination_mode": 0 if args.no_early_reset else 1,
              "ini_sha256": hashlib.sha256(ini_path.read_bytes()).hexdigest() if ini_path else None,
              "collision_shrink": scale,
              "runtime": runtime, "parked_track_ids": [o["id"] for o in parked.values()],
              "parked_active_slots": [scene["objects"][i]["id"] for i in parked if i in active],
              "ego_goal_step": ego_goal_step,
              "invalid_ego_terminal": invalid_ego_terminal,
              "missing_valid_samples": missing[:20], "missing_valid_count": len(missing),
              "max_position_error_m": max(errors, default=0.0),
              "first_position_errors_over_1mm": error_details[:20],
              "max_dimension_scale_error_m": max(dimension_errors, default=0.0),
              "passed": not missing and not invalid_ego_terminal
                        and not any(i in active for i in parked)
                        and max(errors, default=0.0) < 0.01
                        and max(dimension_errors, default=0.0) < 0.01}
finally:
    env.close()
(root / ("testing/parked_evaluation_validation.json" if args.eval_config else "testing/parked_validation.json")).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if not result["passed"]:
    raise SystemExit(1)
