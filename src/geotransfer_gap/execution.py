"""Admission-enforcing execution into separate, immutable-input run directories."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid
from .config import settings, tool_path, ensure_bench
from .artifacts import (
    scene_root,
    read_json,
    write_json,
    sha256,
    reference,
    read_manifest,
)


def new_run(label):
    root = settings().runs / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "_"
        + label
        + "_"
        + uuid.uuid4().hex[:6]
    )
    root.mkdir(parents=True, exist_ok=False)
    return root


def replay(root, output):
    import numpy as np

    ensure_bench()
    from .runtime.session import evaluation_env, frame
    from .runtime import late_spawn_runtime
    from pufferlib.prediction.binary_reader import read_binary_scenario

    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding

    binary = read_binary_scenario(str(root / "testing/map_000000.bin"))
    env = evaluation_env(root)
    frames = []
    try:
        env.reset()
        for step in range(91):
            state = env.get_state()[0]
            frames.append(frame(state, binary, step))
            ego = state["entities"][binary["sdc_track_index"]]
            if ego["removed"]:
                break
            binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
            if step < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    result = dict(
        schema_version=2,
        planner="expert",
        scene=reference(root),
        binary_sha256=sha256(root / "testing/map_000000.bin"),
        runtime=runtime,
        ego_binary_index=int(binary["sdc_track_index"]),
        frames=frames,
        diagnostic_only=True,
    )
    write_json(output, result)


def main(argv=None):
    ap = argparse.ArgumentParser(__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--scene")
    group.add_argument("--manifest", type=Path)
    ap.add_argument("--planner", choices=["smart", "expert", "bb"], default="smart")
    ap.add_argument(
        "--traffic", choices=["hybrid_startup", "idm"], default="hybrid_startup"
    )
    ap.add_argument(
        "--diagnostic",
        action="store_true",
        help="Explicitly run without planner admission; never grants it",
    )
    ap.add_argument("--steps", type=int, default=91)
    ap.add_argument("--bb-args", nargs=argparse.REMAINDER, default=[])
    args = ap.parse_args(argv)
    rows = (
        [{"name": Path(args.scene).name, "root": str(scene_root(args.scene))}]
        if args.scene
        else read_manifest(args.manifest)
    )
    destination = new_run(args.planner)
    results = []
    for row in rows:
        root = scene_root(row["root"])
        folder = destination / row["name"]
        folder.mkdir()
        if args.manifest and args.planner == "smart" and (not args.diagnostic):
            gate = root / "testing" / f"admission_smart_{args.traffic}.json"
            if (
                sha256(gate) != row["admission_sha256"]
                or sha256(root / "testing/map_000000.bin") != row["binary_sha256"]
            ):
                raise ValueError("Stale manifest: " + row["name"])
        if args.planner == "expert":
            replay(root, folder / "trace.json")
        elif args.planner == "smart":
            cmd = [
                sys.executable,
                str(tool_path("probe_faithful_smart_closed_loop.py")),
                "--root",
                str(root),
                "--traffic",
                args.traffic,
                "--steps",
                str(args.steps),
                "--output",
                str(folder / "diagnostic.json"),
                "--trace-output",
                str(folder / "trace.json"),
            ]
            if not args.diagnostic:
                cmd += ["--require-admission"]
            with (folder / "execution.log").open("w") as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        else:
            if not args.diagnostic:
                raise ValueError(
                    "BB planner bridge requires --diagnostic; SMART admission does not validate other planners"
                )
            import os

            env = dict(
                os.environ,
                GEOTRANSFER_SCENE_ROOT=str(root),
                GEOTRANSFER_ALLOW_UNVALIDATED="1",
                GEOTRANSFER_LATE_RUNTIME="1",
                PUFFER_EXP_ROOT=str(folder),
            )
            with (folder / "execution.log").open("w") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(tool_path("run_pilot_eval.py")),
                        *args.bb_args,
                    ],
                    env=env,
                    cwd=settings().bench,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
        results.append(
            dict(
                scene=reference(root),
                name=row["name"],
                output=str(folder),
                planner=args.planner,
                diagnostic_only=args.diagnostic or args.planner != "smart",
            )
        )
        write_json(destination / "run.json", dict(schema_version=2, results=results))
        print(folder, flush=True)
    return destination
