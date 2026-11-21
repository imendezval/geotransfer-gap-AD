"""Native SMART joint-input regression before matrix dispatch integration."""

import argparse
import json
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.smart_controller import load_smart_controller
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.episode_worker import run_episode
from geotransfer_gap.runtime.session import evaluation_env


def changed_future(objects, step):
    result = []
    for entity in objects:
        changed = dict(entity)
        for key in ("traj_x", "traj_y", "traj_vx", "traj_vy", "traj_heading", "traj_valid"):
            if entity.get(key) is None:
                continue
            series = np.asarray(entity[key]).copy()
            if key == "traj_valid":
                series[step + 1:] = 1 - series[step + 1:]
            else:
                series[step + 1:] += 70
            changed[key] = series
        result.append(changed)
    return result


def audit(env, binary, binding):
    import torch

    ego, traffic = (load_smart_controller(env, binary["sdc_track_index"], role)
                    for role in ("ego", "traffic"))
    assert ego.planner.history is not traffic.planner.history
    graphs = {c.role: {} for c in (ego, traffic)}

    for controller in (ego, traffic):
        planner = controller.planner
        build = planner._build_hetero_data

        def record(build=build, role=controller.role):
            data = build()
            assert data is not None
            graph = data.to_dict()
            assert not graph["agent"]["valid_mask"][:, 11:].any()
            assert not graph["agent"]["token_idx"][:, 2:].any()
            graphs[role][int(env.tick)] = {
                store: {name: value.clone() if torch.is_tensor(value) else value
                        for name, value in fields.items()}
                for store, fields in graph.items()
            }
            return data

        planner._build_hetero_data = record

    mutant = traffic.planner
    state = mutant._state
    prepare = mutant.prepare_step

    def mutated_state():
        value = state()
        return dict(value, entities=changed_future(value["entities"], int(env.tick)))

    def mutated_prepare(step):
        mutant._load_map()
        original = mutant._scenario_objects
        mutant._scenario_objects = changed_future(original, step)
        try:
            return prepare(step)
        finally:
            mutant._scenario_objects = original

    mutant._state = mutated_state
    mutant.prepare_step = mutated_prepare
    report = run_episode(env, binary, binding, ego, traffic, steps=20)
    assert env.tick == report["transitions"] == 19
    assert ego.planner.history.num_steps == traffic.planner.history.num_steps == 30
    assert ego.planner._predicted_positions is not traffic.planner._predicted_positions
    common = sorted(graphs["ego"].keys() & graphs["traffic"].keys())
    assert common == [10, 15]
    for step in common:
        reference, altered = (graphs[role][step] for role in ("ego", "traffic"))
        assert reference.keys() == altered.keys()
        for store, fields in reference.items():
            assert fields.keys() == altered[store].keys()
            for name, value in fields.items():
                other = altered[store][name]
                assert (torch.equal(value, other) if torch.is_tensor(value)
                        else value == other), (step, store, name)
    refresh = next(row for row in traffic.refreshes if row["step"] == 14)
    assert refresh["reason"] == "new_target"
    assert any(t["source_id"] == 1035 and t["generation"] == 1
               for t in refresh["targets"])
    row = next(r for r in report["frames"][14]["actors"] if r["source_id"] == 1035)
    assert row["applied_movement_mode"] == 0
    assert row["slot"] == 2
    return dict(graph_equality_steps=common, num_observations=report["observation_frames"],
                histories=[ego.planner.history.num_steps, traffic.planner.history.num_steps],
                refreshes={c.role: c.refreshes for c in (ego, traffic)}, reentry_action=row)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding
    from pufferlib.prediction.binary_reader import read_binary_scenario

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    binary = read_binary_scenario(str(args.root / "testing/map_000000.bin"))
    env = evaluation_env(args.root)
    try:
        env.reset()
        print(json.dumps(audit(env, binary, binding), indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
