"""Native SMART joint-input regression before matrix dispatch integration."""

import argparse
import json
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench, settings
from geotransfer_gap.conversion.binary import load_source_writer
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
    assert row["effective_owner"] == "traffic:smart"
    assert row["lifetime_generation"] == 1 and row["action"] is not None
    return dict(graph_equality_steps=common, num_observations=report["observation_frames"],
                histories=[ego.planner.history.num_steps, traffic.planner.history.num_steps],
                refreshes={c.role: c.refreshes for c in (ego, traffic)}, reentry_action=row)


def build_fixture(root):
    root = root.resolve()
    if root == settings().runs or not root.is_relative_to(settings().runs):
        raise ValueError("Synthetic fixture must be a new directory under configured runs")
    root.mkdir(parents=True, exist_ok=False)
    testing = root / "testing"
    testing.mkdir()
    lane_y = (0, 5, 10)
    objects = [
        dict(id=sid, type="vehicle", width=2, length=4, height=1.5,
             position=[dict(x=step * 0.5, y=y) for step in range(91)],
             velocity=[dict(x=5, y=0)] * 91, heading=[0] * 91,
             valid=[int(sid != 1035 or step not in (12, 13)) for step in range(91)],
             goalPosition=dict(x=45, y=y))
        for sid, y in zip((1000, 1001, 1035), lane_y, strict=True)
    ]
    roads = [
        dict(id=2000 + i, type="lane",
             geometry=[dict(x=x, y=y) for x in range(-20, 71, 10)])
        for i, y in enumerate(lane_y)
    ]
    roads += [dict(id=2010 + i, type="road_edge",
                   geometry=[dict(x=x, y=y) for x in range(-30, 81, 10)])
              for i, y in enumerate((-8, 18))]
    load_source_writer()(dict(metadata=dict(sdc_track_index=0), objects=objects, roads=roads),
                         str(testing / "map_000000.bin"), 0)
    return root


def verify_fixture(binary):
    objects = binary["objects"]
    target = next((o for o in objects if o["id"] == 1035), None)
    if (target is None or target["type"] != 1 or target.get("mark_as_expert")
            or target is objects[binary["sdc_track_index"]]
            or list(target["traj_valid"][:15]) != [1] * 12 + [0, 0, 1]):
        raise ValueError("SMART joint fixture requires traffic vehicle 1035 present at steps "
                         "0–11, absent at 12–13, and returning at 14. Use --fixture-dir.")


def main():
    parser = argparse.ArgumentParser(__doc__)
    fixture = parser.add_mutually_exclusive_group(required=True)
    fixture.add_argument("--root", type=Path)
    fixture.add_argument("--fixture-dir", type=Path, help="Create a synthetic scene under runs")
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding
    from pufferlib.prediction.binary_reader import read_binary_scenario

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    root = build_fixture(args.fixture_dir) if args.fixture_dir else args.root
    binary = read_binary_scenario(str(root / "testing/map_000000.bin"))
    verify_fixture(binary)
    env = evaluation_env(root, num_agents=3) if args.fixture_dir else evaluation_env(root)
    try:
        env.reset()
        target_index = next(i for i, actor in enumerate(binary["objects"])
                            if actor["id"] == 1035)
        active = env.get_state()[0]["active_agent_indices"]
        if len(active) <= 2 or active[2] != target_index:
            raise ValueError("SMART joint fixture requires actor 1035 in native slot 2 at reset")
        result = audit(env, binary, binding)
    finally:
        env.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
