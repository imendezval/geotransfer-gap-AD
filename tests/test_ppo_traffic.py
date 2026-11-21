"""Exercise traffic PPO with native-shaped actor lifecycle snapshots."""

import numpy as np
import pytest

from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.runtime.actor_index import ActorIndex, ActorKey, SourceActorID
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from test_controller_scheduler import FakeBinding, scene_and_state
from test_ppo_controller import CountingPolicy


class BatchSpy(CountingPolicy):
    def __init__(self):
        super().__init__()
        self.batches = []

    def infer_batch(self, rows, states):
        self.batches.append([(int(row[0]), state) for row, state in zip(rows, states)])
        return ([((int(row[0]) % 100) / 100, 0) for row in rows],
                [(state or 0) + int(row[0]) for row, state in zip(rows, states)],
                None, None)


def scenario():
    binary, native = scene_and_state()
    for source_id, marked in ((301, False), (302, True)):
        binary["objects"].append(dict(binary["objects"][1], id=source_id,
                                      mark_as_expert=marked))
        native["entities"].append(dict(native["entities"][1]))
    return binary, native


def capture(index, native, binary, step, active):
    native.update(active_agent_indices=active, active_agent_count=len(active))
    rows = np.zeros((len(active), 1151), dtype=np.float32)
    rows[:, 0] = [binary["objects"][i]["id"] + step for i in active]
    return index.capture_pre_step(step, native, rows)


@pytest.mark.parametrize("status", [1, 2])
def test_traffic_lifetimes_warmup_and_reset(status):
    binary, native = scenario()
    gap = binary["objects"][1]["traj_valid"].copy()
    gap[10] = 0
    binary["objects"][1]["traj_valid"] = gap
    birth = binary["objects"][3]["traj_valid"].copy()
    birth[:6] = 0
    binary["objects"][3]["traj_valid"] = birth
    index = ActorIndex(binary)
    policy = BatchSpy()
    traffic = PPOController(policy, role="traffic")
    ego = PPOController(policy)
    scheduler = EpisodeScheduler(FakeBinding(), ego, traffic)
    for step in range(13):
        if step == 12:
            native["entities"][3].update(collision_state=status, collided_before_goal=True)
        slot_order = [1, 0, 3, 2, 4] if step % 2 else [4, 3, 0, 2, 1]
        s = capture(index, native, binary, step, slot_order)
        p = scheduler.decide(s, advances_simulation=True)
        actors = p.by_source_id
        assert actors[SourceActorID(100)].intent.kind == ("replay" if step < 10 else "dynamics")
        for source_id in (300, 302):
            assert actors[SourceActorID(source_id)].intent.kind == "replay"
        if step == 10:
            assert policy.batches[-1] == [(311, sum(range(307, 311)))]
            assert actors[SourceActorID(200)].intent.kind == "replay"
        if step == 11:
            assert policy.batches[-1][0] == (211, None)
            assert s.actor_for(200).key == ActorKey(SourceActorID(200), 1)
            assert traffic.act(s, {s.actor_for(200).key, s.actor_for(301).key}) == {
                a.key: a.intent for a in p.assignments if a.role == "traffic"
            }
            with pytest.raises(ValueError, match="cached"):
                traffic.act(s, {ActorKey(SourceActorID(200), 0), s.actor_for(301).key})
        if step == 12:
            assert len(policy.batches[-1]) == 1
            assert actors[SourceActorID(301)].intent.kind == "replay"
    assert len(policy.batches) == len(policy.calls) == 13
    assert policy.calls[1] == (101, 1)
    assert policy.batches[6][-1] == (307, None)
    for _ in range(2):
        index.reset_episode()
        scheduler.reset({})
        s = capture(index, native, binary, 0, [1, 0, 2, 3, 4])
        scheduler.decide(s, advances_simulation=True)
        assert policy.calls[-1] == (100, None)
        assert policy.batches[-1] == [(200, None)]


def test_live_traffic_slot_loss_fails_closed_without_retirement():
    binary, native = scenario()
    index = ActorIndex(binary)
    policy = BatchSpy()
    traffic = PPOController(policy, role="traffic")
    scheduler = EpisodeScheduler(FakeBinding(), ExpertController("ego"), traffic)
    s = capture(index, native, binary, 0, [0, 1, 2, 3, 4])
    scheduler.decide(s, advances_simulation=True)
    key = s.actor_for(200).key
    with pytest.raises(ValueError, match="discontinuity"):
        scheduler.decide(s, advances_simulation=True)
    next_frame = capture(index, native, binary, 1, [0, 2, 3, 4])
    actor = next_frame.actor_for(key)
    assert actor.native_present and not actor.permanently_removed and actor.key == key
    with pytest.raises(ValueError, match="discontinuity"):
        scheduler.decide(next_frame, advances_simulation=True)
    assert len(policy.batches) == 1
