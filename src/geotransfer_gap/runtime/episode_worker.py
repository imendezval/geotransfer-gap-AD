"""Fresh-process entry point for one supported immediate controller pair."""

import argparse
from pathlib import Path

from geotransfer_gap.artifacts import reference, sha256, write_json
from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.scheduler import EpisodeScheduler


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
):
    """Capture each pre-step frame and advance at most ``steps - 1`` times."""
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 91:
        raise ValueError("steps must request 1 through 91 observation frames")
    if frame_fn is None:
        from .session import frame as frame_fn

    index = ActorIndex(binary)
    scheduler = EpisodeScheduler(binding, ego_controller, traffic_controller)
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
        frames.append(
            {
                "step": step,
                "state": state_frame,
                "actors": [
                    assignment.trace_record(applied=advances)
                    for assignment in plan.assignments
                ],
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
        "traffic_startup": "immediate",
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
    parser.add_argument("--ego", choices=("expert", "idm", "ppo"), required=True)
    parser.add_argument("--traffic", choices=("expert", "idm"), required=True)
    parser.add_argument("--steps", type=int, default=91)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not 1 <= args.steps <= 91:
        raise SystemExit("--steps must request 1 through 91 observation frames")

    ensure_bench()
    from geotransfer_gap.runtime import late_spawn_runtime
    from geotransfer_gap.runtime.session import evaluation_env
    from pufferlib.prediction.binary_reader import read_binary_scenario

    root = args.root.resolve()
    binary_path = root / "testing/map_000000.bin"
    binary = read_binary_scenario(str(binary_path))
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
        if args.ego == "ppo":
            from geotransfer_gap.planners.ppo_controller import PPOController
            from geotransfer_gap.planners.ppo_policy import load_pinned_ego_policy

            policy, provenance = load_pinned_ego_policy(env)
            ego_controller = PPOController(policy)
        else:
            ego_controller = (ExpertController("ego") if args.ego == "expert"
                              else IDMController("ego"))
        # Drive initializes the native vector during construction but exposes
        # ``tick`` only after reset(); keep this in lockstep with the legacy
        # replay runner's reset boundary.
        env.reset()
        report = run_episode(
            env,
            binary,
            binding,
            ego_controller,
            ExpertController("traffic")
            if args.traffic == "expert"
            else IDMController("traffic"),
            steps=args.steps,
            runtime=runtime,
            scene_reference=reference(root),
            binary_sha256=sha256(binary_path),
        )
    finally:
        env.close()
    write_json(args.output, report)
    if provenance is not None:
        write_json(args.output.with_name("ppo_provenance.json"), provenance)
    print(args.output.resolve(), flush=True)
    return args.output


if __name__ == "__main__":
    main()
