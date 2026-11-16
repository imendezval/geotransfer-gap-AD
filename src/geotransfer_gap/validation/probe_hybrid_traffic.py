"""Diagnostic: hold initially stopped actors on source replay, then use IDM.

This is an exploratory traffic protocol, not a Step 2 admission mode.  It
tests whether preserving the source startup delay recovers an interaction.
"""

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
    ap.add_argument("--focus-track", type=int, required=True)
    ap.add_argument("--focus-step", type=int, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    alias = Path("/tmp") / (
        "geo_scene_" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    )
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime

    late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding

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
    report = {
        "protocol": "initially stationary vehicles expert until source motion; VRUs and static vehicles expert; other vehicles IDM",
        "focus_track": args.focus_track,
        "focus_step": args.focus_step,
        "startup_hold_steps": {},
        "focus_samples": [],
    }
    try:
        env.reset()
        initial = env.get_state()[0]
        slots = {idx: slot for slot, idx in enumerate(initial["active_agent_indices"])}
        offsets = [
            (
                obj["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                obj["position"][0]["y"] - initial["entities"][i]["traj_y"][0],
            )
            for i, obj in enumerate(scene["objects"])
        ]
        binding.vec_set_movement_mode(env.c_envs, list(range(1, env.num_agents)), 1)
        binding.vec_set_movement_mode(env.c_envs, [slots[0]], 2)
        releases = {}
        for i, obj in enumerate(scene["objects"][1:], start=1):
            if i not in slots:
                continue
            if obj["type"] != "vehicle" or obj["mark_as_expert"]:
                binding.vec_set_movement_mode(env.c_envs, [slots[i]], 2)
                continue
            first_speed = math.hypot(obj["velocity"][0]["x"], obj["velocity"][0]["y"])
            if first_speed >= 1.0 or obj["source_window_path_length_m"] < 1.0:
                continue
            start = obj["position"][0]
            moving = next(
                (
                    t
                    for t in range(1, len(obj["valid"]))
                    if obj["valid"][t]
                    and math.dist(
                        (obj["position"][t]["x"], obj["position"][t]["y"]),
                        (start["x"], start["y"]),
                    )
                    >= 1.0
                ),
                None,
            )
            if moving is not None and moving >= 10:
                binding.vec_set_movement_mode(env.c_envs, [slots[i]], 2)
                releases[i] = moving
                report["startup_hold_steps"][str(obj["id"])] = moving
        focus_index = next(
            (
                i
                for i, obj in enumerate(scene["objects"])
                if obj["id"] == args.focus_track
            )
        )
        for t in range(91):
            for i, release in list(releases.items()):
                if t >= release:
                    binding.vec_set_movement_mode(env.c_envs, [slots[i]], 1)
                    del releases[i]
            state = env.get_state()[0]
            e = state["entities"][focus_index]
            if e["x"] != -10000.0 and scene["objects"][focus_index]["valid"][t]:
                source = scene["objects"][focus_index]["position"][t]
                error = math.dist(
                    (
                        e["x"] + offsets[focus_index][0],
                        e["y"] + offsets[focus_index][1],
                    ),
                    (source["x"], source["y"]),
                )
                if t in (
                    0,
                    max(0, args.focus_step - 10),
                    args.focus_step,
                    min(90, args.focus_step + 10),
                    70,
                    80,
                ):
                    report["focus_samples"].append(
                        {
                            "step": t,
                            "position_error_m": error,
                            "sim_speed_mps": math.hypot(e["vx"], e["vy"]),
                        }
                    )
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    path = root / "testing/hybrid_traffic_diagnostic.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
