"""Fresh-process entry point for a supported controller pair."""

import argparse
from pathlib import Path

from geotransfer_gap.artifacts import read_json, reference, sha256, write_json
from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from geotransfer_gap.runtime.startup_policy import StartupPolicy, source_hold_policy


def run_episode(
    env,
    binary,
    binding,
    ego_controller,
    traffic_controller,
    *,
    steps=91,
    runtime=None,
    scene_reference=None,
    binary_sha256=None,
    frame_fn=None,
    startup=None,
):
    """Capture each pre-step frame and advance at most ``steps - 1`` times."""
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 91:
        raise ValueError("steps must request 1 through 91 observation frames")
    if frame_fn is None:
        from .session import frame as frame_fn

    index = ActorIndex(binary)
    scheduler = EpisodeScheduler(binding, ego_controller, traffic_controller, startup=startup)
    scheduler.reset(
        {
            "ego_binary_index": int(binary["sdc_track_index"]),
            "scene": scene_reference,
        }
    )
    frames = []
    transitions = 0
    terminal_reason = None

    for step in range(steps):
        native = env.get_state()
        state = native[0] if isinstance(native, list) else native
        snapshot = index.capture_pre_step(step, state, env.observations)
        ego = snapshot.actor_for(snapshot.ego_id)
        if ego.removed:
            terminal_reason = "ego_removed"
        elif not ego.native_present:
            terminal_reason = "ego_absent"
        elif ego.permanently_removed:
            terminal_reason = f"ego_{ego.removal_reason.value}"
        advances = terminal_reason is None and step < steps - 1
        plan = scheduler.decide(snapshot, advances_simulation=advances)
        # Drive's state serializer can expose fields backed by buffers that the
        # next native step mutates. Capture the trace frame before the single
        # write/step so state and controller decisions refer to the same tick.
        state_frame = frame_fn(state, binary, step)
        if advances:
            scheduler.advance(env, plan)
            transitions += 1
        actors = []
        for assignment in plan.assignments:
            record = assignment.trace_record(applied=advances)
            if scheduler.startup.mode == "source_hold":
                record.update(scheduler.startup_record(
                    snapshot.actor_for(assignment.source_id), step, advances,
                ))
            actors.append(record)
        frames.append(
            {
                "step": step,
                "state": state_frame,
                "actors": actors,
                "transition_applied": advances,
            }
        )
        if terminal_reason is not None:
            break

    return {
        "schema_version": 3,
        "planner": "controller_matrix",
        "ego_controller": ego_controller.name,
        "traffic_controller": traffic_controller.name,
        "traffic_startup": scheduler.startup.mode,
        "warmup_replay_frames": 10,
        "steps_semantics": "observation_frames",
        "requested_observation_frames": steps,
        "observation_frames": len(frames),
        "transitions": transitions,
        "terminal_reason": terminal_reason or "horizon",
        "scene": scene_reference,
        "binary_sha256": binary_sha256,
        "runtime": runtime,
        "ego_binary_index": int(binary["sdc_track_index"]),
        "idm_global_parameters": (
            vars(scheduler.idm_parameters)
            if scheduler.idm_parameters is not None
            else None
        ),
        "frames": frames,
    }


def build_parser():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ego", choices=("expert", "idm", "ppo", "smart"), required=True)
    parser.add_argument("--traffic", choices=("expert", "idm", "ppo", "smart"), required=True)
    parser.add_argument("--traffic-startup", choices=("immediate", "source_hold"), default="immediate")
    parser.add_argument("--steps", type=int, default=91)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _traffic_ppo_provenance(report, observation):
    lifetimes = {}
    for frame in report["frames"]:
        for actor in frame["actors"]:
            if actor["role"] != "traffic" or actor["declared_controller"] != "ppo":
                continue
            key = (actor["source_id"], actor["lifetime_generation"])
            entry = lifetimes.setdefault(key, {
                "source_id": key[0],
                "lifetime_generation": key[1],
                "binary_index": actor["binary_index"],
                "observation_shape": [observation["width"]],
                "observations": [],
            })
            entry["observations"].append({"step": frame["step"], "slot": actor["slot"]})
    return {
        "input": "Actor-centric row from the shared native pre-step snapshot",
        "state_scope": "Traffic ActorKey, independent of ego PPO",
        "live_slot_discontinuity": "abort episode",
        "lifetimes": list(lifetimes.values()),
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not 1 <= args.steps <= 91:
        raise SystemExit("--steps must request 1 through 91 observation frames")
    if args.traffic_startup == "source_hold" and args.traffic == "expert":
        raise SystemExit("source_hold requires non-expert traffic")

    ensure_bench()
    from geotransfer_gap.runtime import late_spawn_runtime
    from geotransfer_gap.runtime.session import evaluation_env
    from pufferlib.prediction.binary_reader import read_binary_scenario

    root = args.root.resolve()
    binary_path = root / "testing/map_000000.bin"
    binary = read_binary_scenario(str(binary_path))
    startup = StartupPolicy()
    source = None
    if args.traffic_startup == "source_hold":
        sources = sorted((root / "testing").glob("ind_*.json"))
        if len(sources) != 1:
            raise SystemExit(f"source_hold requires exactly one authoritative source JSON in {root / 'testing'}")
        source, = sources
        startup = source_hold_policy(read_json(source), binary)
        if args.steps > startup.window:
            raise SystemExit("source_hold steps exceed the authoritative source window")
    runtime = late_spawn_runtime.load()
    # Load the corrected extension before importing the package's binding
    # attribute; an earlier import would stay attached to the stock module even
    # after late_spawn_runtime replaces sys.modules.
    from pufferlib.ocean.drive import binding

    if Path(binding.__file__).resolve() != Path(runtime["runtime_binary"]).resolve():
        raise RuntimeError("episode worker loaded a different native binding than the runtime")

    env = evaluation_env(root)
    try:
        provenance = None
        factories = {"expert": ExpertController, "idm": IDMController}
        if "ppo" in (args.ego, args.traffic):
            from geotransfer_gap.planners.ppo_controller import PPOController
            from geotransfer_gap.planners.ppo_policy import load_pinned_ego_policy

            policy, provenance = load_pinned_ego_policy(env)
            factories["ppo"] = lambda role: PPOController(policy, role=role)
        if "smart" in (args.ego, args.traffic):
            from geotransfer_gap.planners.smart_controller import load_smart_controller

            factories["smart"] = lambda role: load_smart_controller(
                env, binary["sdc_track_index"], role
            )
        # Drive initializes the native vector during construction but exposes
        # ``tick`` only after reset(); keep this in lockstep with the legacy
        # replay runner's reset boundary.
        env.reset()
        ego_controller = factories[args.ego]("ego")
        traffic_controller = factories[args.traffic]("traffic")
        report = run_episode(
            env,
            binary,
            binding,
            ego_controller,
            traffic_controller,
            steps=args.steps,
            runtime=runtime,
            scene_reference=reference(root),
            binary_sha256=sha256(binary_path),
            startup=startup,
        )
    finally:
        env.close()
    if source is not None:
        report["startup_policy"] = {
            "source": reference(source),
            "source_sha256": sha256(source),
            "window_observations": startup.window,
            "release_schedule": [
                {"binary_index": index, "source_id": int(binary["objects"][index]["id"]),
                 "step": step}
                for index, step in sorted(startup.releases.items())
            ],
            "information_access": "Release timing uses recorded future source motion. The schedule is scheduler input only.",
            "diagnostic_only": True,
            "research_admission_status": "not_established",
        }
    write_json(args.output, report)
    if provenance is not None:
        if args.traffic == "ppo":
            provenance["traffic_ppo"] = _traffic_ppo_provenance(report, provenance["observation"])
        write_json(args.output.with_name("ppo_provenance.json"), provenance)
    smart_roles = {
        controller.role: controller.refreshes
        for controller in (ego_controller, traffic_controller)
        if controller.name == "smart"
    }
    if smart_roles:
        from geotransfer_gap.config import settings
        from geotransfer_gap.planners.protocol import input_paths

        write_json(args.output.with_name("smart_provenance.json"), {
            "checkpoint_sha256": sha256(settings().weights),
            "input_hashes": {name: sha256(path) for name, path in input_paths().items()},
            "binary_sha256": report["binary_sha256"],
            "seed": 0,
            "device": "cpu",
            "greedy": True,
            "diagnostic_only": True,
            "research_admission_status": "not_established",
            "information_access": "Static map, observed joint histories and observed-birth velocity",
            "refreshes": smart_roles,
        })
    print(args.output.resolve(), flush=True)
    return args.output


if __name__ == "__main__":
    main()
