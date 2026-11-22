"""Compare role SMART and faithful single-ego execution on one native timeline."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench, settings
from geotransfer_gap.planners.smart_controller import load_smart_controller
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.matrix_inputs import load_binary
from geotransfer_gap.runtime.native_modes import NativeMovementMode
from geotransfer_gap.runtime.session import evaluation_env


def audit(env, binary, binding, steps):
    import torch
    from pufferlib.planning.smart import SMARTConfig
    from geotransfer_gap.planners.faithful_smart import FaithfulSMARTPlanner

    ego_index = binary["sdc_track_index"]
    adapter = load_smart_controller(env, ego_index, "ego")
    reference = FaithfulSMARTPlanner(
        env, ego_index, np.array([-4, -1], np.float32), np.array([4, 1], np.float32),
        SMARTConfig(weights_path=str(settings().weights), device="cpu", greedy=True),
    )
    for key, weight in reference.model.state_dict().items():
        assert torch.equal(weight, adapter.planner.model.state_dict()[key])
    graphs = [{}, {}]
    for planner, record in zip((reference, adapter.planner), graphs, strict=True):
        build = planner._build_hetero_data

        def capture(build=build, record=record):
            data = build()
            record[env.tick] = {
                (store, key): value.clone() if torch.is_tensor(value) else value
                for store, fields in data.to_dict().items() for key, value in fields.items()
            }
            return data

        planner._build_hetero_data = capture
    index = ActorIndex(binary)
    actions = []
    differences = []
    births = []
    for step in range(steps):
        state = env.get_state()[0]
        snapshot = index.capture_pre_step(step, state, env.observations)
        actor = snapshot.actor_for(snapshot.ego_id)
        live = frozenset(a.key for a in snapshot.actors if a.native_present
                         and a.source_valid and not a.permanently_removed)
        adapter.observe(snapshot, live)
        if step < 10:
            reference.prepare_step(step)
        else:
            expected = reference.plan(step, snapshot.observation[snapshot.slot_for(actor.key)])
            actual = adapter.act(snapshot, {actor.key})[actor.key].action
            difference = float(np.max(np.abs(expected - np.asarray(actual))))
            actions.append({"step": step, "reference": expected.tolist(), "adapter": list(actual),
                            "prediction_step": reference._prediction_step, "max_abs_difference": difference})
        a, b = reference.history, adapter.planner.history
        assert a.num_steps == b.num_steps == step + 11
        tick = a.num_steps - 1
        assert reference._prediction_step == adapter.planner._prediction_step
        np.testing.assert_array_equal(a.valid[:, tick], b.valid[:, tick])
        visible = a.valid[:, tick]
        for field in ("position", "heading"):
            np.testing.assert_array_equal(getattr(a, field)[visible, tick],
                                          getattr(b, field)[visible, tick])
        continuous = visible & a.valid[:, tick - 1]
        np.testing.assert_array_equal(a.velocity[continuous, tick], b.velocity[continuous, tick])
        born = np.flatnonzero(visible & ~continuous)
        if len(born):
            speeds = np.zeros(a.num_agents, dtype=np.float32)
            reference._bootstrap_speeds_from_state(speeds, a.num_agents)
            np.testing.assert_allclose(np.linalg.norm(b.velocity[born, tick], axis=1),
                                       speeds[born], rtol=0, atol=1e-6)
            np.testing.assert_array_equal(a.velocity[born, tick], 0)
            for i in born:
                births.append({
                    "step": step, "index": int(i), "source_id": int(binary["objects"][i]["id"]),
                    "reference_bootstrap_speed_m_s": float(speeds[i]),
                    "reference_history_velocity": a.velocity[i, tick].tolist(),
                    "adapter_history_velocity": b.velocity[i, tick].tolist(),
                    "native_velocity": [state["entities"][i][axis] for axis in ("vx", "vy")],
                })
        if step in graphs[0]:
            assert graphs[0][step].keys() == graphs[1][step].keys()
            for key, value in graphs[0][step].items():
                other = graphs[1][step][key]
                if not (torch.equal(value, other) if torch.is_tensor(value) else value == other):
                    differences.append({"step": step, "field": "/".join(map(str, key)),
                                        "max_abs_difference": float((value - other).abs().max())})
            for field in ("_predicted_positions", "_predicted_headings"):
                expected, actual = getattr(reference, field), getattr(adapter.planner, field)
                if not np.array_equal(expected, actual):
                    differences.append({"step": step, "field": field,
                                        "max_abs_difference": float(np.max(np.abs(expected - actual)))})
        binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)),
                                      int(NativeMovementMode.EXPERT_REPLAY))
        env.step(np.zeros_like(env.actions))
    graph_hashes = {}
    for tick, graph in graphs[0].items():
        graph_hashes[tick] = {
            "/".join(map(str, key)): hashlib.sha256(value.detach().cpu().numpy().tobytes()).hexdigest()
            for key, value in graph.items() if torch.is_tensor(value)
        }
    report = {"actions": actions, "graph_and_prediction_differences": differences,
              "causal_births": births, "prediction_steps": sorted(graphs[0]),
              "clock": "identical native pre-step observations, shared expert replay transitions",
              "reference_graph_tensor_hashes": graph_hashes}
    print(json.dumps(report, indent=2), flush=True)
    assert sorted(graphs[0]) == sorted(graphs[1]) == list(range(10, steps, 5))
    assert not differences
    assert all(row["max_abs_difference"] == 0 for row in actions)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--require-birth", action="store_true")
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    binary = load_binary(args.root)
    env = evaluation_env(args.root)
    try:
        env.reset()
        report = audit(env, binary, binding, args.steps)
        if args.require_birth:
            assert any(birth["reference_bootstrap_speed_m_s"] > 0 for birth in report["causal_births"])
    finally:
        env.close()


if __name__ == "__main__":
    main()
