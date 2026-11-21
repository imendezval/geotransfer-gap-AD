"""Check native PPO observations and classic actuation on an unchanged fixture."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from geotransfer_gap.config import ensure_bench
from geotransfer_gap.planners.controller_api import DynamicsIntent
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_policy import observation_tensor, validate_native_env
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.episode_worker import run_episode
from geotransfer_gap.runtime.native_modes import NativeMovementMode
from geotransfer_gap.runtime.session import evaluation_env


class FixedAction(ExpertController):
    def __init__(self, action):
        super().__init__("ego", "ppo")
        self.action = action

    def act(self, snapshot, eligible_targets):
        assert len(eligible_targets) == 1
        return {key: DynamicsIntent(self.action) for key in eligible_targets}


def sample(state, index):
    entity = state["entities"][index]
    return {key: entity[key] for key in (
        "x", "y", "vx", "vy", "heading", "length", "steering_angle", "movement_mode",
    )}


def classic_reference(pre, action):
    h = pre["heading"]
    speed = math.copysign(math.hypot(pre["vx"], pre["vy"]),
                          pre["vx"] * math.cos(h) + pre["vy"] * math.sin(h))
    accelerator, steer = action
    next_speed = min(100, max(-100, speed + 4 * accelerator * .1))
    beta = math.tanh(.5 * math.tan(steer))
    vx = next_speed * math.cos(h + beta)
    vy = next_speed * math.sin(h + beta)
    return dict(x=pre["x"] + vx * .1, y=pre["y"] + vy * .1, vx=vx, vy=vy,
                heading=h + next_speed * math.cos(beta) * math.tan(steer) / pre["length"] * .1,
                steering_angle=steer)


def observation_probe(env, reference, binary, binding):
    env.reset()
    reference.reset()
    index = ActorIndex(binary)
    rows = []
    for step in range(2):
        state = env.get_state()[0]
        ref_state = reference.get_state()[0]
        snapshot = index.capture_pre_step(step, state, env.observations)
        actor = snapshot.actor_for(snapshot.ego_id)
        slot = snapshot.slot_for(actor.key)
        ref_slot = ref_state["active_agent_indices"].index(binary["sdc_track_index"])
        expected = reference.observations[ref_slot]
        np.testing.assert_array_equal(observation_tensor(snapshot.observation[slot])[0], expected)
        entity = state["entities"][actor.fixed_binary_index]
        dx = entity["goal_position_x"] - entity["x"]
        dy = entity["goal_position_y"] - entity["y"]
        c, s = math.cos(entity["heading"]), math.sin(entity["heading"])
        signed_speed = math.copysign(math.hypot(entity["vx"], entity["vy"]),
                                     entity["vx"] * c + entity["vy"] * s)
        np.testing.assert_allclose(expected[:7], [
            (dx*c + dy*s)*.005, (-dx*s + dy*c)*.005, signed_speed/100,
            entity["width"]/15, entity["length"]/30, bool(entity["collision_state"]),
            0,  # Fresh evaluation reset, followed by one replay tick.
        ], rtol=0, atol=2e-7)
        partners = expected[7:255].reshape(31, 8)
        roads = expected[255:].reshape(128, 7)
        assert np.any(partners[:, 7] == 0) and np.any(partners[:, 7] > 0)
        np.testing.assert_array_equal(partners[partners[:, 7] == 0], 0)
        assert np.any(roads[:, :6])
        rows.append(dict(step=step, slot=slot, reference_slot=ref_slot,
                         max_abs_difference=0, ego_features=expected[:7].tolist()))
        if step == 0:
            for native in (env, reference):
                binding.vec_set_movement_mode(native.c_envs,
                    list(range(native.num_agents)), int(NativeMovementMode.EXPERT_REPLAY))
                native.step(np.zeros_like(native.actions))
    return rows


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    ensure_bench()
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive import binding
    from pufferlib.prediction.binary_reader import read_binary_scenario

    assert Path(binding.__file__).resolve() == Path(runtime["runtime_binary"]).resolve()
    binary = read_binary_scenario(str(args.root / "testing/map_000000.bin"))
    ego_index = binary["sdc_track_index"]
    env = evaluation_env(args.root)
    reference = evaluation_env(args.root, action_type="discrete")
    try:
        validate_native_env(env)
        assert reference.single_action_space.nvec.tolist() == [91]
        rows = observation_probe(env, reference, binary, binding)
        cases = {}
        for name, action in {
            "straight": (0., 0.), "accelerate": (1., 0.), "brake": (-1., 0.),
            "left": (0., .5), "right": (0., -.5), "max_steer": (0., 1.),
        }.items():
            env.reset()
            frames = []
            report = run_episode(
                env, binary, binding, FixedAction(action), ExpertController("traffic"),
                steps=12, frame_fn=lambda state, _binary, _step: frames.append(
                    sample(state, ego_index)
                ),
            )
            assert report["transitions"] == env.tick == 11
            pre, post = frames[10:12]
            assert post["movement_mode"] == NativeMovementMode.DYNAMICS
            expected = classic_reference(pre, action)
            errors = {key: abs(expected[key] - post[key]) for key in expected}
            assert max(errors.values()) < 1e-5, (name, errors)
            actor = next(a for a in report["frames"][10]["actors"] if a["role"] == "ego")
            assert actor["applied_movement_mode"] == NativeMovementMode.DYNAMICS
            np.testing.assert_array_equal(env.actions[actor["slot"]], action)
            cases[name] = dict(action=action, written=env.actions[actor["slot"]].tolist(),
                               slot=actor["slot"], mode=post["movement_mode"], before=pre,
                               expected=expected, observed=post, absolute_error=errors)
    finally:
        reference.close()
        env.close()
    print(json.dumps(dict(runtime=runtime, observation_parity=rows, physics=cases), indent=2))


if __name__ == "__main__":
    main()
