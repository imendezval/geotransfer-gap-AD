"""Audit the actual evaluator traffic route against observed source intent."""

from geotransfer_gap.maps import lanelet as map_geometry
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime import hybrid_traffic

HERE = PROJECT_ROOT
sys.path.insert(0, str(settings().bench))


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--actor", type=int, required=True)
    ap.add_argument("--step", type=int, default=0)
    args = ap.parse_args()
    root = args.root.resolve()
    scene = json.loads(next((root / "testing").glob("ind_*.json")).read_text())
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding

    alias = Path("/tmp") / (
        "geo_route_" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    )
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
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
        ini_file=str(settings().bench / "pufferlib/config/evaluation.ini"),
        resample_frequency=0,
    )
    try:
        env.reset()
        schedule = hybrid_traffic.release_schedule(scene)
        ego = scene.get("metadata", {}).get("sdc_track_index", 0)
        index = next(
            (i for i, o in enumerate(scene["objects"]) if o["id"] == args.actor)
        )
        obj = scene["objects"][index]
        initial = env.get_state()[0]["entities"][ego]
        offset = np.array(
            [
                scene["objects"][ego]["position"][0]["x"] - initial["traj_x"][0],
                scene["objects"][ego]["position"][0]["y"] - initial["traj_y"][0],
            ]
        )
        for t in range(args.step + 1):
            state = env.get_state()[0]
            slots = {i: s for s, i in enumerate(state["active_agent_indices"])}
            if ego in slots:
                binding.vec_set_movement_mode(env.c_envs, [slots[ego]], 2)
            hybrid_traffic.apply(env, scene, schedule, t, binding)
            if t < args.step:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
        entity = env.get_state()[0]["entities"][index]
        route = (
            np.array(list(zip(entity["route_x"] or [], entity["route_y"] or [])))
            + offset
        )
        samples = []
        for t in range(args.step, 91):
            if not obj["valid"][t]:
                continue
            pt = (obj["position"][t]["x"], obj["position"][t]["y"])
            dist = (
                map_geometry.point_polyline_distance(pt, route.tolist())
                if len(route) > 1
                else None
            )
            samples.append({"step": t, "source_to_evaluator_route_distance_m": dist})
        out = {
            "binary_sha256": hashlib.sha256(
                (root / "testing/map_000000.bin").read_bytes()
            ).hexdigest(),
            "runtime": runtime,
            "actor": args.actor,
            "snapshot_step": args.step,
            "source_future_only_used_by_audit": True,
            "route_world_xy": route.tolist(),
            "source_route_distance": samples,
            "maximum_source_route_distance_m": max(
                (
                    r["source_to_evaluator_route_distance_m"]
                    for r in samples
                    if r["source_to_evaluator_route_distance_m"] is not None
                ),
                default=None,
            ),
        }
        (
            root / "testing" / f"traffic_route_actor{args.actor}_step{args.step}.json"
        ).write_text(json.dumps(out, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in out.items()
                    if k not in ("route_world_xy", "source_route_distance")
                }
            )
        )
    finally:
        env.close()


if __name__ == "__main__":
    main()
