"""Audit held model inputs with the declared release schedule frozen."""

import argparse
import json
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.planners.ppo_policy import load_pinned_ego_policy
from geotransfer_gap.planners.smart_controller import load_smart_controller
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.episode_worker import run_episode
from geotransfer_gap.runtime.session import evaluation_env
from geotransfer_gap.runtime.startup_policy import source_hold_policy


def mutate_future(scene, binary, actor_index, cutoff):
    """Change the test copy of future speed so the frozen policy releases later."""
    obj = scene["objects"][actor_index]
    scene = dict(scene, objects=list(scene["objects"]))
    scene["objects"][actor_index] = dict(obj, velocity=[
        v if t <= cutoff else dict(x=0, y=0, z=0)
        for t, v in enumerate(obj["velocity"])
    ])
    binary = dict(binary, objects=list(binary["objects"]))
    binary["objects"][actor_index] = zero_future_velocity(
        binary["objects"][actor_index], cutoff
    )
    return scene, binary


def zero_future_velocity(actor, cutoff):
    actor = dict(actor)
    for field in ("traj_vx", "traj_vy", "traj_vz"):
        value = np.asarray(actor[field]).copy()
        value[cutoff+1:] = 0
        actor[field] = value
    return actor


def audit(env, binding, binary, startup, actor_index, kind, mutate):
    import torch

    inputs = []
    hcs = {}
    ego_idx = binary["sdc_track_index"]
    release = startup.releases[actor_index]
    source_id = binary["objects"][actor_index]["id"]
    if kind == "ppo":
        policy, _ = load_pinned_ego_policy(env)
        controller = PPOController(policy, role="traffic")
        model = policy.model.policy
        encode = model.encode_observations

        def recorded_encode(tensor, state=None):
            inputs.append(tensor.clone())
            return encode(tensor, state)

        model.encode_observations = recorded_encode
    else:
        controller = load_smart_controller(env, ego_idx, "traffic")
        planner = controller.planner
        build = planner._build_hetero_data

        def recorded_build():
            graph = build()
            inputs.append({
                (store, name): value.clone()
                for store, fields in graph.to_dict().items()
                for name, value in fields.items() if torch.is_tensor(value)
            })
            return graph

        planner._build_hetero_data = recorded_build
        if mutate:
            prepare, state = planner.prepare_step, planner._state

            def mutated_state():
                raw = state()
                entities = list(raw["entities"])
                entities[actor_index] = zero_future_velocity(entities[actor_index], int(env.tick))
                return dict(raw, entities=entities)

            def mutated_prepare(step):
                planner._load_map()
                original = planner._scenario_objects
                objects = list(original)
                objects[actor_index] = zero_future_velocity(objects[actor_index], step)
                planner._scenario_objects = objects
                try:
                    return prepare(step)
                finally:
                    planner._scenario_objects = original

            planner._state = mutated_state
            planner.prepare_step = mutated_prepare

    from geotransfer_gap.runtime.session import frame

    def capture(state, binary, step):
        if kind == "ppo":
            key, = (k for k in controller._states if int(k.source_id) == source_id)
            hcs[step] = controller._states[key]["lstm_c"].clone()
        return frame(state, binary, step)

    env.reset()
    report = run_episode(env, binary, binding, ExpertController("ego"), controller,
                         steps=release+3, startup=startup, frame_fn=capture)
    assert report["transitions"] == env.tick == release+2
    for step in range(10, release+1):
        a = report["frames"][step]["actors"][actor_index]
        assert a["role"] == "traffic" and a["declared_controller"] == kind
        if step < release:
            assert a["action"] == [0, 0] and a["applied_movement_mode"] == 2
        else:
            assert a["applied_movement_mode"] == 0 and a["actual_release_step"] == release
            assert report["frames"][step+1]["actors"][actor_index]["pre_step_native_movement_mode"] == 0
    if kind == "ppo":
        assert len(inputs) == len(hcs) == report["observation_frames"]
        assert all(not torch.equal(hcs[i],hcs[i+1]) for i in range(9, release))
        detail = {"continuous_ppo_updates": len(hcs)}
    else:
        assert controller.planner.history.num_steps == report["observation_frames"] + 10
        assert controller.planner.history.valid[actor_index, 10:release+11].all()
        event = next(r for r in controller.refreshes if r["step"] == release)
        assert event["reason"] == "new_target"
        assert any(a["source_id"] == source_id for a in event["targets"])
        detail = {"history_count": controller.planner.history.num_steps, "refresh": event}
    return report, inputs, detail


def main():
    import torch

    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--actor", type=int, required=True)
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding
    from pufferlib.prediction.binary_reader import read_binary_scenario

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    source, = (args.root/"testing").glob("ind_*.json")
    scene = json.loads(source.read_text())
    binary = read_binary_scenario(str(args.root/"testing/map_000000.bin"))
    idx = next(i for i,a in enumerate(binary["objects"]) if a["id"] == args.actor)
    startup = source_hold_policy(scene, binary)
    mutated_scene, mutated_binary = mutate_future(scene, binary, idx, 10)
    alternate = source_hold_policy(mutated_scene, mutated_binary)
    assert alternate.releases[idx] == startup.window != startup.releases[idx]

    details = {}
    for kind in ("ppo", "smart"):
        results = []
        for fixture in (binary, mutated_binary):
            env = evaluation_env(args.root)
            try:
                results.append(audit(env, binding, fixture, startup, idx, kind, fixture is mutated_binary))
            finally:
                env.close()
        (left, a, detail), (right, b, _) = results
        assert left == right
        for x, y in zip(a, b, strict=True):
            if kind == "ppo":
                assert torch.equal(x,y)
            else:
                assert x.keys() == y.keys()
                assert all(torch.equal(x[k],y[k]) for k in x)
        details[kind] = dict(compared_input_batches=len(a), **detail)
    print(json.dumps(dict(runtime=runtime, fixed_release=startup.releases[idx],
                          counterfactual_release=alternate.releases[idx], models=details), indent=2))


if __name__ == "__main__":
    main()
