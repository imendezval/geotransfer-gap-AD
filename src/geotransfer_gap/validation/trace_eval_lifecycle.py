"""Record every source actor's evaluator-state timeline and first loss cause."""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np


def main():
    HERE = PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument(
        "--traffic-mode",
        choices=("expert", "idm", "zero_action_dynamics", "hybrid_startup"),
        default="expert",
    )
    ap.add_argument("--lateral-offset-m", type=float, default=0.0)
    ap.add_argument("--perturb-step", type=int, default=0)
    args = ap.parse_args()
    root = args.root.resolve()
    alias = Path("/tmp") / (
        "geo_scene_" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    )
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime

    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    from geotransfer_gap.runtime import hybrid_traffic

    scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
    ini = settings().bench / "pufferlib/config/evaluation.ini"
    env = Drive(
        data_root=str(alias),
        split="testing",
        num_maps=1,
        num_agents=128,
        episode_length=91,
        map_id=0,
        action_type="continuous",
        control_mode="control_evaluation",
        goal_behavior=3,
        ini_file=str(ini),
        resample_frequency=0,
    )
    timeline = {str(obj["id"]): [] for obj in scene["objects"]}
    reset_steps = []
    justified_goal_terminal_step = None
    try:
        env.reset()
        initial = env.get_state()[0]
        binding.vec_set_movement_mode(
            env.c_envs,
            [0],
            2 if args.perturb_step else 0 if args.lateral_offset_m else 2,
        )
        binding.vec_set_movement_mode(
            env.c_envs,
            list(range(1, env.num_agents)),
            {"expert": 2, "idm": 1, "zero_action_dynamics": 0, "hybrid_startup": 1}[
                args.traffic_mode
            ],
        )
        hybrid_releases = (
            hybrid_traffic.release_schedule(scene)
            if args.traffic_mode == "hybrid_startup"
            else {}
        )
        offsets = [
            (
                obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0],
            )
            for i, obj in enumerate(scene["objects"])
        ]
        for t in range(91):
            if args.traffic_mode == "hybrid_startup":
                hybrid_traffic.apply(env, scene, hybrid_releases, t, binding)
            if args.lateral_offset_m and t == args.perturb_step:
                binding.vec_set_movement_mode(env.c_envs, [0], 0)
                current = env.get_state()[0]["entities"][0]
                binding.vec_set_positions(
                    env.c_envs,
                    [0],
                    [
                        current["x"]
                        - math.sin(current["heading"]) * args.lateral_offset_m
                    ],
                    [
                        current["y"]
                        + math.cos(current["heading"]) * args.lateral_offset_m
                    ],
                    [current["heading"]],
                )
            entities = env.get_state()[0]["entities"]
            ego = entities[0]
            ego_source = scene["objects"][0]
            if t > 1 and ego["x"] != -10000.0:
                now = (ego["x"] + offsets[0][0], ego["y"] + offsets[0][1])
                start = ego_source["position"][0]
                expected = ego_source["position"][t]
                if (
                    math.dist(now, (start["x"], start["y"])) < 0.05
                    and math.dist(
                        (expected["x"], expected["y"]), (start["x"], start["y"])
                    )
                    > 5
                ):
                    reset_steps.append(t)
            for i, obj in enumerate(scene["objects"]):
                e = entities[i]
                present = e["x"] != -10000.0 and e["y"] != -10000.0
                error = heading_error = None
                if present and obj["valid"][t]:
                    src = obj["position"][t]
                    error = math.dist(
                        (e["x"] + offsets[i][0], e["y"] + offsets[i][1]),
                        (src["x"], src["y"]),
                    )
                    heading_error = abs(
                        (e["heading"] - obj["heading"][t] + math.pi) % (2 * math.pi)
                        - math.pi
                    )
                timeline[str(obj["id"])].append(
                    {
                        "step": t,
                        "source_valid": bool(obj["valid"][t]),
                        "present": present,
                        "source_local_position": (
                            [e["x"] + offsets[i][0], e["y"] + offsets[i][1]]
                            if present
                            else None
                        ),
                        "sim_heading_rad": e["heading"],
                        "sim_speed_mps": math.hypot(e["vx"], e["vy"]),
                        "sim_length_m": e["length"],
                        "sim_width_m": e["width"],
                        "position_error_m": error,
                        "heading_error_rad": heading_error,
                        "removed": bool(e["removed"]),
                        "stopped": bool(e["stopped"]),
                        "collision_state": int(e["collision_state"]),
                        "collided_with_index": int(e["collided_with_index"]),
                        "collision_position_local": (
                            [
                                e["collision_x"] + offsets[i][0],
                                e["collision_y"] + offsets[i][1],
                            ]
                            if e["collision_state"] == 1
                            else None
                        ),
                        "reached_goal": bool(e["reached_goal_this_episode"]),
                        "movement_mode": int(e["movement_mode"]),
                    }
                )
            ego_source_position = ego_source["position"][t]
            ego_goal = ego_source["goalPosition"]
            if (
                ego["x"] == -10000.0
                and ego_source["valid"][t]
                and ego["removed"]
                and (ego["collision_state"] == 0)
                and (
                    math.dist(
                        (ego_source_position["x"], ego_source_position["y"]),
                        (ego_goal["x"], ego_goal["y"]),
                    )
                    <= 2.1
                )
            ):
                justified_goal_terminal_step = t
                break
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    first_losses = {}
    for obj in scene["objects"]:
        tid = str(obj["id"])
        rows = timeline[tid]
        for t, row in enumerate(rows):
            if not row["source_valid"] or row["present"] or t in reset_steps:
                continue
            prior = rows[t - 1] if t else None
            goal = obj["goalPosition"]
            prior_position = obj["position"][t - 1] if t else obj["position"][0]
            source_goal_distance = math.dist(
                (prior_position["x"], prior_position["y"]), (goal["x"], goal["y"])
            )
            current_position = obj["position"][t]
            current_goal_distance = math.dist(
                (current_position["x"], current_position["y"]), (goal["x"], goal["y"])
            )
            if row["collision_state"] == 1 or (prior and prior["collision_state"] == 1):
                cause = "collision"
            elif row["collision_state"] == 2 or (
                prior and prior["collision_state"] == 2
            ):
                cause = "offroad"
            elif row["removed"] and current_goal_distance < 2.1:
                cause = "goal"
            elif prior and prior["removed"]:
                cause = "removed_unknown"
            else:
                cause = "absent_unknown"
            first_losses[tid] = {
                "step": t,
                "cause": cause,
                "prior": prior,
                "current": row,
                "source_goal_distance_prior_m": source_goal_distance,
                "source_goal_distance_current_m": current_goal_distance,
                "last_source_valid_step": max(
                    (j for j, valid in enumerate(obj["valid"]) if valid)
                ),
            }
            break
    report = {
        "binary_sha256": hashlib.sha256(
            (root / "testing/map_000000.bin").read_bytes()
        ).hexdigest(),
        "evaluation_ini_sha256": hashlib.sha256(ini.read_bytes()).hexdigest(),
        "runtime_source_sha256": runtime["runtime_source_sha256"],
        "traffic_mode": args.traffic_mode,
        "lateral_offset_m": args.lateral_offset_m,
        "hybrid_release_steps_by_track_id": {
            str(scene["objects"][i]["id"]): t for i, t in hybrid_releases.items()
        },
        "perturb_step": args.perturb_step,
        "episode_steps": 91,
        "observed_steps": len(next(iter(timeline.values()))),
        "justified_goal_terminal_step": justified_goal_terminal_step,
        "post_goal_source_steps_not_evaluated": (
            90 - justified_goal_terminal_step
            if justified_goal_terminal_step is not None
            else 0
        ),
        "reset_steps": reset_steps,
        "first_source_valid_losses": first_losses,
        "timeline": timeline,
    }
    suffix = (
        f"_shift{args.lateral_offset_m:g}_at{args.perturb_step}"
        if args.lateral_offset_m
        else ""
    )
    (root / "testing" / f"lifecycle_trace_{args.traffic_mode}{suffix}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "timeline"}, indent=2))


if __name__ == "__main__":
    main()
