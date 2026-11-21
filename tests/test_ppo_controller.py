import numpy as np
import pytest

from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.episode_worker import run_episode
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from geotransfer_gap.runtime.step_snapshot import RemovalReason
from test_controller_scheduler import FakeBinding, FakeEnv, scene_and_state


class CountingPolicy:
    def __init__(self):
        self.calls = []

    def infer(self, row, state):
        self.calls.append((float(row[0]), state))
        return (0.25, -0.5), (state or 0) + 1, None, None


def test_warmup_takes_observations_once_and_act_uses_cache():
    binary, native = scene_and_state()
    binary["sdc_track_index"] = 1
    index = ActorIndex(binary)
    policy = CountingPolicy()
    ego = PPOController(policy)
    scheduler = EpisodeScheduler(FakeBinding(), ego, ExpertController("traffic"))
    for step in range(12):
        indices = [0, 1, 2] if step % 2 == 0 else [1, 2, 0]
        native["active_agent_indices"] = indices
        obs = np.zeros((3, 1151), dtype=np.float32)
        obs[indices.index(1), 0] = step + 100
        snapshot = index.capture_pre_step(step, native, obs)
        plan = scheduler.decide(snapshot, advances_simulation=True)
        actor = plan.by_source_id[snapshot.ego_id]
        assert actor.slot == indices.index(1)
        assert ego._states == {actor.key: step + 1}
        assert actor.intent.kind == ("replay" if step < 10 else "dynamics")
        if step >= 10:
            assert actor.intent.action == (0.25, -0.5)
            assert ego.act(snapshot, {actor.key})[actor.key] == actor.intent
    assert policy.calls == [(step + 100, step or None) for step in range(12)]
    key = actor.key
    native["entities"][1].update(removed=True, collision_state=1)
    terminal = index.capture_pre_step(12, native, obs)
    scheduler.decide(terminal, advances_simulation=False)
    assert not ego._states and not ego._actions and len(policy.calls) == 12
    with pytest.raises(ValueError, match="cached action"):
        ego.act(terminal, {key})
    scheduler.reset({})
    index.reset_episode()
    _, fresh = scene_and_state()
    scheduler.decide(index.capture_pre_step(0, fresh, obs), advances_simulation=True)
    assert policy.calls[-1][1] is None


def test_live_ego_without_slot_fails_closed():
    binary, native = scene_and_state()
    index = ActorIndex(binary)
    policy = CountingPolicy()
    ego = PPOController(policy)
    scheduler = EpisodeScheduler(FakeBinding(), ego, ExpertController("traffic"))
    scheduler.decide(index.capture_pre_step(0, native, np.zeros((3, 1151))),
                     advances_simulation=True)
    native.update(active_agent_indices=[1, 2], active_agent_count=2)
    snapshot = index.capture_pre_step(1, native, np.zeros((2, 1151)))
    assert snapshot.actor_for(snapshot.ego_id).native_present
    with pytest.raises(ValueError, match="discontinuity at step 1"):
        scheduler.decide(snapshot, advances_simulation=True)
    assert len(policy.calls) == 1


@pytest.mark.parametrize(
    "collision_state,history,reason",
    [
        (1, True, RemovalReason.COLLISION),
        (2, True, RemovalReason.OFFROAD),
        (0, True, RemovalReason.COLLISION),
    ],
)
@pytest.mark.parametrize("terminal_step", [1, 11])
def test_native_present_ego_retires_and_ends_episode(
    collision_state, history, reason, terminal_step
):
    binary, state = scene_and_state()
    binary["sdc_track_index"] = 1
    native_ego = state["entities"][1]
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    policy = CountingPolicy()
    retirements = []
    terminal_keys = []

    class SpyPPO(PPOController):
        def retire(self, actor, reason):
            retirements.append((actor, reason))
            super().retire(actor, reason)

        def observe(self, snapshot, live_keys):
            if snapshot.step == terminal_step:
                actor = snapshot.actor_for(snapshot.ego_id)
                # STOP_AGENT leaves a source-valid actor in the active slot.
                assert actor.source_valid and actor.native_present and not actor.removed
                assert actor.permanently_removed and actor.removal_reason is reason
                assert actor.current_active_slot == 1
                assert not actor.controller_eligible and snapshot.slot_for(actor.key) is None
                assert actor.key not in live_keys
                assert retirements == [(actor.key, reason.value)]
                assert not self._states and not self._actions
                terminal_keys.append(actor.key)
            super().observe(snapshot, live_keys)

    native_step = env.step

    def step(actions):
        native_step(actions)
        if env.step_calls == terminal_step:
            native_ego.update(
                collision_state=collision_state,
                collided_before_goal=history,
                stopped=True,
            )

    env.step = step
    ego = SpyPPO(policy)
    report = run_episode(
        env, binary, binding, ego, ExpertController("traffic"),
        steps=terminal_step + 2,
        frame_fn=lambda state, _, tick: {
            "step": tick,
            "removed": state["entities"][1]["removed"],
            "collision_state": state["entities"][1]["collision_state"],
        },
    )
    assert report["terminal_reason"] == f"ego_{reason.value}"
    assert report["observation_frames"] == terminal_step + 1
    assert report["transitions"] == env.step_calls == len(policy.calls) == terminal_step
    assert env.events[-1][0] == "step"
    assert len(terminal_keys) == 1 and not ego._states and not ego._actions
    terminal = report["frames"][-1]
    assert not terminal["transition_applied"]
    assert not terminal["state"]["removed"]
    assert terminal["state"]["collision_state"] == collision_state
    assert all(actor["action"] is None for actor in terminal["actors"])
