"""Perturb the ego and audit actor lifecycle under three evaluator traffic modes."""

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
ap.add_argument("--lateral-offset-m", type=float, default=1.0)
ap.add_argument("--perturb-step", type=int, default=0)
ap.add_argument("--report-name", default="counterfactual_probe.json")
ap.add_argument("--include-hybrid", action="store_true")
ap.add_argument("--require-hybrid", action="store_true")
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
import hybrid_traffic

scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
ini = HERE.parent / "behavior-bench/pufferlib/config/evaluation.ini"
results = {}
mode_list = [("expert", 2), ("idm", 1), ("zero_action_dynamics", 0)]
if args.include_hybrid or args.require_hybrid:
    mode_list.append(("hybrid_startup", 1))
for mode, movement in mode_list:
    env = Drive(data_root=str(alias), split="testing", num_maps=1, num_agents=128,
                episode_length=91, map_id=0, action_type="continuous",
                control_mode="control_evaluation", goal_behavior=3,
                ini_file=str(ini), resample_frequency=0)
    try:
        env.reset()
        initial = env.get_state()[0]
        active = initial["active_agent_indices"]
        slots = {idx: slot for slot, idx in enumerate(active)}
        binding.vec_set_movement_mode(env.c_envs, [slots[0]], 2 if args.perturb_step else 0)
        binding.vec_set_movement_mode(env.c_envs, [slots[i] for i in slots if i != 0], movement)
        hybrid_releases = hybrid_traffic.release_schedule(scene) if mode == "hybrid_startup" else {}
        ego = initial["entities"][0]
        start_x, start_y = ego["x"], ego["y"]
        origins = [(obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                    obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0])
                   for i, obj in enumerate(scene["objects"])]
        births = {i: next((t for t, valid in enumerate(obj["valid"]) if valid), None)
                  for i, obj in enumerate(scene["objects"])}
        exits = {i: max(t for t, valid in enumerate(obj["valid"]) if valid)
                 for i, obj in enumerate(scene["objects"])}
        ghost, postexit, missing, removals = [], [], [], []
        reset_steps = []
        first_terminal = None
        terminal_state = None
        observed_steps = 0
        ego_moved_away = False
        max_traffic_source_deviation = 0.0
        traffic_positions = {str(obj["id"]): [] for obj in scene["objects"][1:]}
        for t in range(91):
            # An evaluator episode ends when its controlled ego terminates.  A
            # collision at that terminal transition is an outcome of the
            # counterfactual, not missing source traffic in a continuing task.
            if first_terminal is not None and t >= first_terminal:
                break
            observed_steps += 1
            if mode == "hybrid_startup":
                hybrid_traffic.apply(env, scene, hybrid_releases, t, binding)
            if t == args.perturb_step:
                binding.vec_set_movement_mode(env.c_envs, [slots[0]], 0)
                ego_now = env.get_state()[0]["entities"][0]
                dx = -math.sin(ego_now["heading"]) * args.lateral_offset_m
                dy = math.cos(ego_now["heading"]) * args.lateral_offset_m
                binding.vec_set_positions(env.c_envs, [slots[0]],
                    [ego_now["x"] + dx], [ego_now["y"] + dy], [ego_now["heading"]])
            entities = env.get_state()[0]["entities"]
            for i, obj in enumerate(scene["objects"]):
                e = entities[i]
                present = e["x"] != -10000.0 and e["y"] != -10000.0
                if i:
                    traffic_positions[str(obj["id"])].append(
                        [e["x"] + origins[i][0], e["y"] + origins[i][1]] if present else None)
                if t < births[i] and present:
                    ghost.append([obj["id"], t])
                if t > exits[i] and present:
                    postexit.append([obj["id"], t])
                if i and obj["valid"][t] and not present:
                    missing.append([obj["id"], t, int(e["collision_state"]), bool(e["removed"])])
                    if t == 0 or (t > 0 and env.get_state()[0]["entities"][i]["removed"] and
                                  t == births[i]):
                        removals.append([obj["id"], t, int(e["collision_state"])])
                if i and present and obj["valid"][t] and t < 90:
                    src = obj["position"][t]
                    max_traffic_source_deviation = max(max_traffic_source_deviation,
                        math.dist((e["x"] + origins[i][0], e["y"] + origins[i][1]), (src["x"], src["y"])))
            e = entities[0]
            if e["x"] != -10000.0:
                distance_from_start = math.dist((e["x"], e["y"]), (start_x, start_y))
                if distance_from_start > 5:
                    ego_moved_away = True
                if t > 5 and ego_moved_away and distance_from_start < 0.05:
                    reset_steps.append(t)
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
                if first_terminal is None and (env.terminals[slots[0]] or env.truncations[slots[0]]):
                    first_terminal = t + 1
                    final_ego = env.get_state()[0]["entities"][0]
                    terminal_state = {"collision_state": int(final_ego["collision_state"]),
                                      "removed": bool(final_ego["removed"]),
                                      "truncated": bool(env.truncations[slots[0]])}
        results[mode] = {"active_entity_indices": active, "prebirth_ghosts": ghost,
            "postexit_presence": postexit, "source_valid_missing": missing[:30],
            "source_valid_missing_count": len(missing), "birth_removal_events": removals,
            "reset_steps": reset_steps, "ego_first_terminal_step": first_terminal,
            "ego_terminal_state": terminal_state,
            "observed_steps": observed_steps,
            "post_terminal_source_steps_not_evaluated": 91 - observed_steps,
            "max_traffic_source_deviation_m": max_traffic_source_deviation,
            "traffic_positions": traffic_positions,
            "lifecycle_passed": (observed_steps >= 10 and not ghost and not postexit
                                 and not reset_steps and not missing)}
    finally:
        env.close()
report = {"schema_version": 2,
          "binary_sha256": hashlib.sha256((root / "testing/map_000000.bin").read_bytes()).hexdigest(),
          "evaluation_ini_sha256": hashlib.sha256(ini.read_bytes()).hexdigest(),
          "runtime_source_sha256": runtime["runtime_source_sha256"],
          "lateral_offset_m": args.lateral_offset_m, "perturb_step": args.perturb_step,
          "modes": results,
          "required_evaluator_modes": ["expert", "hybrid_startup"] if args.require_hybrid else ["expert", "idm"],
          "required_evaluator_modes_passed": all(results[m]["lifecycle_passed"] for m in
                                                  (("expert", "hybrid_startup") if args.require_hybrid else ("expert", "idm"))),
          "all_diagnostic_modes_passed": all(r["lifecycle_passed"] for r in results.values()),
          "passed": all(results[m]["lifecycle_passed"] for m in
                        (("expert", "hybrid_startup") if args.require_hybrid else ("expert", "idm")))}
(root / "testing" / args.report_name).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
