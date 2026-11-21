import numpy as np
import pytest

from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.runtime.actor_index import ActorIndex
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from test_controller_scheduler import FakeBinding, scene_and_state


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
        assert ego._state == step + 1
        assert actor.intent.kind == ("replay" if step < 10 else "dynamics")
        if step >= 10:
            assert actor.intent.action == (0.25, -0.5)
            assert ego.act(snapshot, {actor.key})[actor.key] == actor.intent
    assert policy.calls == [(step + 100, step or None) for step in range(12)]
    key = actor.key
    native["entities"][1].update(removed=True, collision_state=1)
    terminal = index.capture_pre_step(12, native, obs)
    scheduler.decide(terminal, advances_simulation=False)
    assert ego._state is None and ego._action is None and len(policy.calls) == 12
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
