"""Exercise one non-ego PPO target through the real matrix writer."""

import argparse
import json
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.planners.ppo_policy import load_pinned_ego_policy
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.matrix_inputs import load_binary
from geotransfer_gap.runtime.native_modes import NativeMovementMode
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from geotransfer_gap.runtime.session import evaluation_env
from probe_ppo_native import classic_reference, sample


def audit(env, binary, binding, target_index):
    policy, provenance = load_pinned_ego_policy(env)
    cases = {}
    real_infer = policy.infer_batch
    for label, index, intended in (
        ("accel", 84, (1., 0.)), ("brake", 6, (-1., 0.)),
        ("left", 48, (0., .5)), ("right", 42, (0., -.5)),
    ):
        def directed(rows, states):
            actions, memory, logits, value = real_infer(rows, states)
            # Select a known grid index so each physical response is observable.
            return [policy.decode(index)] * len(actions), memory, logits, value

        policy.infer_batch = directed
        env.reset()
        scheduler = EpisodeScheduler(binding, ExpertController("ego"), PPOController(policy, role="traffic"))
        actor_index = ActorIndex(binary)
        target_id = int(binary["objects"][target_index]["id"])
        for step in range(11):
            native, = env.get_state()
            snapshot = actor_index.capture_pre_step(step, native, env.observations)
            plan = scheduler.decide(snapshot, advances_simulation=True)
            before = sample(native, target_index)
            actions = scheduler.advance(env, plan)
        actor = snapshot.actor_for(target_id)
        slot = snapshot.slot_for(actor.key)
        assert not actor.is_ego and int(actor.key.source_id) == target_id
        assert actor.fixed_binary_index == target_index == native["active_agent_indices"][slot]
        assert slot > 0 and env.tick == 11
        assignment = plan.by_source_id[actor.source_id]
        assert assignment.effective_owner == "traffic:ppo"
        action = policy.decode(index)
        assert action == intended
        np.testing.assert_array_equal(actions[slot], action)
        np.testing.assert_array_equal(env.actions[slot], action)
        after = sample(env.get_state()[0], target_index)
        assert after["movement_mode"] == assignment.native_mode == NativeMovementMode.DYNAMICS
        speed_delta = np.hypot(after["vx"], after["vy"]) - np.hypot(before["vx"], before["vy"])
        np.testing.assert_allclose(speed_delta, .4 * action[0], rtol=0, atol=1e-5)
        assert np.sign(after["heading"] - before["heading"]) == np.sign(action[1])
        assert after["steering_angle"] == action[1]
        expected = classic_reference(before, action)
        errors = {k: abs(expected[k] - after[k]) for k in expected}
        assert max(errors.values()) < 1e-5, (label, errors)
        cases[label] = {"source_id": target_id, "generation": actor.key.lifetime_generation,
                        "binary_index": target_index, "slot": slot, "action_index": index,
                        "action": action, "written": env.actions[slot].tolist(), "before": before,
                        "observed": after, "expected": expected, "absolute_errors": errors}
    return {"checkpoint_sha256": provenance["checkpoint_sha256"], "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--target-index", type=int, required=True)
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    binary = load_binary(args.root)
    env = evaluation_env(args.root)
    try:
        print(json.dumps(audit(env, binary, binding, args.target_index), indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
