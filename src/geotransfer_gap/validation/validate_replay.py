"""Check BehaviorBench's C expert replay against a converted inD window.

Run with the bb_pufferdrive Python 3.11 interpreter; pass --root for another scene.
"""

from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path
import numpy as np


def main():
    here = PROJECT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=project_path("pilot"))
    parser.add_argument(
        "--late-runtime",
        action="store_true",
        help="Use isolated experimental late-spawn C runtime",
    )
    parser.add_argument(
        "--no-early-reset",
        action="store_true",
        help="Technical probe: run full 91 steps despite all agents finishing",
    )
    args = parser.parse_args()
    actual_root = args.root.resolve()
    digest = hashlib.sha256(str(actual_root).encode()).hexdigest()[:12]
    scene_root = Path("/tmp") / f"geo_scene_{digest}"
    if not scene_root.exists():
        scene_root.symlink_to(actual_root, target_is_directory=True)
    elif scene_root.resolve() != actual_root:
        raise RuntimeError(f"Scene alias points elsewhere: {scene_root}")
    sys.path.insert(0, str(settings().bench))
    runtime = None
    if args.late_runtime:
        from geotransfer_gap.runtime import late_spawn_runtime

        runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding

    json_files = list((scene_root / "testing").glob("ind_*.json"))
    assert (
        len(json_files) == 1
    ), f"Expected one scene JSON in {scene_root}/testing, found {len(json_files)}"
    scenario = json.loads(json_files[0].read_text())
    ini_path = None
    if args.no_early_reset:
        source_ini = settings().bench / "pufferlib/config/ocean/drive.ini"
        ini_text = source_ini.read_text()
        assert "termination_mode = 1 #" in ini_text
        ini_path = Path("/tmp") / (
            "geo_replay_ini_"
            + hashlib.sha256(ini_text.encode()).hexdigest()[:12]
            + ".ini"
        )
        ini_path.write_text(
            ini_text.replace("termination_mode = 1 #", "termination_mode = 0 #")
        )
    env = Drive(
        data_root=str(scene_root),
        split="testing",
        num_maps=1,
        num_agents=128,
        episode_length=91,
        map_id=0,
        action_type="continuous",
        control_mode="control_evaluation",
        goal_behavior=4,
        collision_behavior=0,
        offroad_behavior=0,
        resample_frequency=0,
        **{"ini_file": str(ini_path)} if ini_path else {},
    )
    try:
        env.reset()
        initial = env.get_state()[0]
        active = initial["active_agent_indices"]
        binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
        local_origins = [
            (
                source["position"][0]["x"] - initial["entities"][i]["traj_x"][0],
                source["position"][0]["y"] - initial["entities"][i]["traj_y"][0],
            )
            for i, source in enumerate(scenario["objects"])
        ]
        errors = []
        heading_errors = []
        missing = []
        premature = []
        compared = 0
        ego_raw = np.zeros(len(env.REWARD_COMPONENT_NAMES), dtype=float)
        for t in range(91):
            entities = env.get_state()[0]["entities"]
            for entity_idx, source in enumerate(scenario["objects"]):
                if not source["valid"][t]:
                    if (
                        not any(source["valid"][:t])
                        and entities[entity_idx]["x"] > -1000
                    ):
                        premature.append({"track_id": source["id"], "step": t})
                    continue
                expected = source["position"][t]
                entity = entities[entity_idx]
                actual_x, actual_y = (float(entity["x"]), float(entity["y"]))
                if actual_x < -1000 or actual_y < -1000:
                    missing.append({"track_id": source["id"], "step": t})
                    continue
                ox, oy = local_origins[entity_idx]
                errors.append(
                    float(
                        np.hypot(
                            actual_x + ox - expected["x"], actual_y + oy - expected["y"]
                        )
                    )
                )
                delta_heading = float(entity["heading"]) - source["heading"][t]
                heading_errors.append(
                    abs((delta_heading + np.pi) % (2 * np.pi) - np.pi)
                )
                compared += 1
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
                ego_raw += env.reward_components_raw[0]
        result = {
            "binary_sha256": hashlib.sha256(
                (actual_root / "testing/map_000000.bin").read_bytes()
            ).hexdigest(),
            "active_entity_indices": active,
            "expert_background_entity_indices": [
                i for i in range(len(scenario["objects"])) if i not in active
            ],
            "expected_objects": len(scenario["objects"]),
            "position_samples_compared": compared,
            "max_expert_replay_position_error_m": max(errors) if errors else None,
            "max_expert_replay_heading_error_rad": (
                max(heading_errors) if heading_errors else None
            ),
            "expert_ego_raw_collision_count": float(ego_raw[0]),
            "expert_ego_raw_offroad_count": float(ego_raw[1]),
            "expert_ego_raw_goal_count": float(ego_raw[2]),
            "missing_valid_samples_count": len(missing),
            "premature_samples_count": len(premature),
            "first_premature_samples": premature[:10],
            "runtime": runtime,
            "test_termination_mode": 0 if args.no_early_reset else 1,
            "missing_valid_samples_by_track": dict(
                Counter((item["track_id"] for item in missing))
            ),
            "first_missing_valid_samples": missing[:10],
            "replay_passed": bool(
                not missing
                and (not premature)
                and (max(errors) < 0.0001)
                and (max(heading_errors) < 0.0001)
                and (ego_raw[0] == 0)
                and (ego_raw[1] == 0)
            ),
        }
        path = scene_root / "testing/replay_validation.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        env.close()
    if not result["replay_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
