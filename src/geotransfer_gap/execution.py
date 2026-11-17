"""Admission-enforcing execution into separate, immutable-input run directories."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Literal
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


Controller = Literal["expert", "idm", "ppo", "smart"]
TrafficStartup = Literal["immediate", "source_hold"]
LegacyPlanner = Literal["smart", "expert", "bb"]
LegacyTraffic = Literal["hybrid_startup", "idm", "expert"]


class _StoreConsistentSelector(argparse.Action):
    """Allow harmless repeats, but never let later selector values win silently."""

    def __call__(self, parser, namespace, values, option_string=None):
        previous = getattr(namespace, self.dest, None)
        if previous is not None and previous != values:
            raise argparse.ArgumentError(
                self, f"conflicting values for {option_string or self.dest}"
            )
        setattr(namespace, self.dest, values)


@dataclass(frozen=True)
class RunProtocol:
    """Immutable, normalized run request shared with future episode workers."""

    selection: Literal["legacy", "matrix", "bb"]
    scene: str | None
    manifest: Path | None
    diagnostic: bool
    steps: int
    ego: Controller | None
    traffic: Controller | None
    traffic_startup: TrafficStartup
    legacy_planner: LegacyPlanner | None
    legacy_traffic: LegacyTraffic | None
    preset: Literal["smart_hybrid_baseline"] | None
    bb_args: tuple[str, ...]


def build_parser():
    """Build the public run parser, preserving omission for normalization."""
    parser = argparse.ArgumentParser(__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scene")
    group.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--planner",
        choices=["smart", "expert", "bb"],
        default=None,
        action=_StoreConsistentSelector,
        help="Legacy runner selection (omitted means smart)",
    )
    parser.add_argument(
        "--ego",
        choices=["expert", "idm", "ppo", "smart"],
        default=None,
        action=_StoreConsistentSelector,
        help="Ego controller for a new controller-matrix pair",
    )
    parser.add_argument(
        "--traffic",
        choices=["expert", "idm", "ppo", "smart", "hybrid_startup"],
        default=None,
        action=_StoreConsistentSelector,
        help="Traffic controller; hybrid_startup is a legacy SMART alias",
    )
    parser.add_argument(
        "--traffic-startup",
        choices=["immediate", "source_hold"],
        default=None,
        action=_StoreConsistentSelector,
        help="New-pair traffic startup policy (default: immediate)",
    )
    parser.add_argument(
        "--preset",
        choices=["smart_hybrid_baseline"],
        default=None,
        action=_StoreConsistentSelector,
        help="Named exact alias for the legacy SMART + hybrid-startup baseline",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Explicitly run without planner admission; never grants it",
    )
    parser.add_argument("--steps", type=int, default=91)
    parser.add_argument(
        "--bb-args",
        nargs=argparse.REMAINDER,
        default=None,
        help="Pass remaining arguments unchanged to the diagnostic BB bridge",
    )
    return parser


def normalize_protocol(args) -> RunProtocol:
    """Resolve old and new selectors without relying on argparse option order."""
    raw_traffic = args.traffic
    bb_args = tuple(args.bb_args or ())

    if args.ego is not None:
        if args.planner is not None or args.preset is not None:
            raise ValueError("--ego cannot be combined with legacy --planner or --preset")
        if raw_traffic is None:
            raise ValueError("--ego requires an explicit --traffic controller")
        if raw_traffic == "hybrid_startup":
            raise ValueError("--traffic hybrid_startup is only valid with legacy selection")
        if args.bb_args is not None:
            raise ValueError("--bb-args requires --planner bb and cannot accompany --ego")
        startup = args.traffic_startup or "immediate"
        if raw_traffic == "expert" and startup == "source_hold":
            raise ValueError("traffic=expert does not support --traffic-startup source_hold")
        return RunProtocol(
            selection="matrix",
            scene=args.scene,
            manifest=args.manifest,
            diagnostic=args.diagnostic,
            steps=args.steps,
            ego=args.ego,
            traffic=raw_traffic,
            traffic_startup=startup,
            legacy_planner=None,
            legacy_traffic=None,
            preset=None,
            bb_args=(),
        )

    if args.preset is not None:
        if args.planner not in (None, "smart"):
            raise ValueError("preset smart_hybrid_baseline conflicts with --planner")
        if raw_traffic not in (None, "hybrid_startup"):
            raise ValueError("preset smart_hybrid_baseline conflicts with --traffic")
        if args.traffic_startup not in (None, "source_hold"):
            raise ValueError("preset smart_hybrid_baseline requires source_hold startup")
        if args.bb_args is not None:
            raise ValueError("--bb-args cannot be combined with --preset")
        return RunProtocol(
            selection="legacy",
            scene=args.scene,
            manifest=args.manifest,
            diagnostic=args.diagnostic,
            steps=args.steps,
            ego="smart",
            traffic="idm",
            traffic_startup="source_hold",
            legacy_planner="smart",
            legacy_traffic="hybrid_startup",
            preset="smart_hybrid_baseline",
            bb_args=(),
        )

    if args.planner == "bb":
        if raw_traffic is not None or args.traffic_startup is not None:
            raise ValueError("BB bridge selection cannot be combined with traffic selectors")
        if not args.diagnostic:
            raise ValueError("BB planner bridge requires --diagnostic")
        return RunProtocol(
            selection="bb",
            scene=args.scene,
            manifest=args.manifest,
            diagnostic=args.diagnostic,
            steps=args.steps,
            ego=None,
            traffic=None,
            traffic_startup="immediate",
            legacy_planner="bb",
            legacy_traffic=None,
            preset=None,
            bb_args=bb_args,
        )

    if args.bb_args is not None:
        raise ValueError("--bb-args requires --planner bb")
    if args.traffic_startup is not None:
        raise ValueError("--traffic-startup requires the new --ego/--traffic pair")

    planner = args.planner or "smart"
    if planner == "expert":
        if raw_traffic not in (None, "expert"):
            raise ValueError("--planner expert replays every actor; conflicting --traffic selection")
        return RunProtocol(
            selection="legacy",
            scene=args.scene,
            manifest=args.manifest,
            diagnostic=args.diagnostic,
            steps=args.steps,
            ego="expert",
            traffic="expert",
            traffic_startup="immediate",
            legacy_planner="expert",
            legacy_traffic="expert" if raw_traffic == "expert" else None,
            preset=None,
            bb_args=(),
        )

    legacy_traffic = raw_traffic or "hybrid_startup"
    if legacy_traffic not in ("hybrid_startup", "idm"):
        raise ValueError(
            "legacy --planner smart supports traffic idm or hybrid_startup; "
            "use --ego with --traffic for other controllers"
        )
    return RunProtocol(
        selection="legacy",
        scene=args.scene,
        manifest=args.manifest,
        diagnostic=args.diagnostic,
        steps=args.steps,
        ego="smart",
        traffic="idm",
        traffic_startup=("source_hold" if legacy_traffic == "hybrid_startup" else "immediate"),
        legacy_planner="smart",
        legacy_traffic=legacy_traffic,
        preset=None,
        bb_args=(),
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
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        protocol = normalize_protocol(args)
    except ValueError as exc:
        ap.error(str(exc))
    if protocol.selection == "matrix":
        ap.error(
            "controller-matrix execution is not yet integrated; no run directory was created"
        )
    rows = (
        [{"name": Path(protocol.scene).name, "root": str(scene_root(protocol.scene))}]
        if protocol.scene
        else read_manifest(protocol.manifest)
    )
    destination = new_run(protocol.legacy_planner)
    results = []
    for row in rows:
        root = scene_root(row["root"])
        folder = destination / row["name"]
        folder.mkdir()
        if protocol.manifest and protocol.legacy_planner == "smart" and (not protocol.diagnostic):
            gate = root / "testing" / f"admission_smart_{protocol.legacy_traffic}.json"
            if (
                sha256(gate) != row["admission_sha256"]
                or sha256(root / "testing/map_000000.bin") != row["binary_sha256"]
            ):
                raise ValueError("Stale manifest: " + row["name"])
        if protocol.legacy_planner == "expert":
            replay(root, folder / "trace.json")
        elif protocol.legacy_planner == "smart":
            cmd = [
                sys.executable,
                str(tool_path("probe_faithful_smart_closed_loop.py")),
                "--root",
                str(root),
                "--traffic",
                protocol.legacy_traffic,
                "--steps",
                str(protocol.steps),
                "--output",
                str(folder / "diagnostic.json"),
                "--trace-output",
                str(folder / "trace.json"),
            ]
            if not protocol.diagnostic:
                cmd += ["--require-admission"]
            with (folder / "execution.log").open("w") as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        else:
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
                        *protocol.bb_args,
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
                planner=protocol.legacy_planner,
                diagnostic_only=protocol.diagnostic or protocol.legacy_planner != "smart",
            )
        )
        write_json(destination / "run.json", dict(schema_version=2, results=results))
        print(folder, flush=True)
    return destination
