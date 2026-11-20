import numpy as np
import pytest

from geotransfer_gap.planners.controller_api import IDMIntent, ReplayIntent
from geotransfer_gap.runtime.actor_index import ActorIndex, ActorKey, SourceActorID
from geotransfer_gap.runtime.scheduler import EpisodeScheduler


def fixture():
    valid = np.ones(91, dtype=np.int32)
    binary = {
        "sdc_track_index": 1,
        "objects": [
            {"id": 100, "type": 1, "traj_valid": valid.copy(), "mark_as_expert": 0},
            {"id": 200, "type": 1, "traj_valid": valid.copy(), "mark_as_expert": 0},
            {"id": 300, "type": 2, "traj_valid": valid.copy(), "mark_as_expert": 0},
        ],
    }
    entities = [
        {
            "valid": 1,
            "x": float(index + 1),
            "y": float(index + 2),
            "z": 0.0,
            "vx": 1.0,
            "vy": 0.0,
            "vz": 0.0,
            "heading": 0.0,
            "removed": False,
            "stopped": False,
            "collision_state": 0,
            "collided_before_goal": False,
            "reached_goal_this_episode": False,
            "movement_mode": 2,
        }
        for index in range(3)
    ]
    state = {
        "active_agent_count": 3,
        "active_agent_indices": [0, 1, 2],
        "entities": entities,
    }
    return binary, state


class Env:
    def __init__(self, state):
        self.state = state
        self.c_envs = self
        self.num_agents = 4
        self.observations = np.zeros((3, 4), dtype=np.float32)
        self.step_calls = 0

    def step(self, actions):
        self.step_calls += 1


class Binding:
    def __init__(self):
        self.mode_calls = []

    def vec_set_movement_mode(self, env, slots, mode):
        self.mode_calls.append((tuple(slots), mode))

    def vec_set_idm_params(self, *args):
        pass

    def vec_set_idm_target_velocity(self, *args):
        pass


class SpyController:
    def __init__(self, role, name, events):
        self.role = role
        self.name = name
        self.events = events

    def reset(self, episode_info):
        self.events.append(("reset", self.role))

    def observe(self, snapshot, visible_targets):
        self.events.append(("observe", self.role, snapshot.step, frozenset(visible_targets)))

    def act(self, snapshot, eligible_targets):
        self.events.append(("act", self.role, snapshot.step))
        intent = IDMIntent() if self.name == "idm" else ReplayIntent()
        return {key: intent for key in eligible_targets}

    def retire(self, actor, reason):
        self.events.append(("retire", self.role, actor, reason))


def set_active(env, indices):
    env.state["active_agent_indices"] = list(indices)
    env.state["active_agent_count"] = len(indices)
    env.observations = np.zeros((len(indices), 4), dtype=np.float32)


def capture(index, env, step):
    return index.capture_pre_step(step, env.state, env.observations)


def scheduler_for(state):
    events = []
    ego = SpyController("ego", "expert", events)
    traffic = SpyController("traffic", "expert", events)
    scheduler = EpisodeScheduler(Binding(), ego, traffic)
    env = Env(state)
    index = ActorIndex(fixture()[0])
    return scheduler, index, env, events, (ego, traffic)


@pytest.mark.parametrize(
    "return_kind", ["native_retired_then_active", "immediately_active"]
)
def test_source_gap_retires_old_key_once_before_new_generation_observation(return_kind):
    binary, state = fixture()
    events = []
    ego = SpyController("ego", "expert", events)
    traffic = SpyController("traffic", "expert", events)
    scheduler = EpisodeScheduler(Binding(), ego, traffic)
    env = Env(state)
    index = ActorIndex(binary)
    old_key = ActorKey(SourceActorID(100), 0)

    scheduler.decide(capture(index, env, 0), advances_simulation=True)
    events.clear()

    binary["objects"][0]["traj_valid"][1] = 0
    state["entities"][0].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    set_active(env, [1, 2])
    gap = capture(index, env, 1)
    scheduler.decide(gap, advances_simulation=True)

    binary["objects"][0]["traj_valid"][2] = 1
    if return_kind == "immediately_active":
        state["entities"][0].update(valid=1, x=10.0, y=2.0, removed=False)
        set_active(env, [1, 0, 2])
    else:
        state["entities"][0].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
        set_active(env, [1, 2])
    returned = capture(index, env, 2)
    scheduler.decide(returned, advances_simulation=True)

    if return_kind == "native_retired_then_active":
        state["entities"][0].update(valid=1, x=10.0, y=2.0, removed=False)
        set_active(env, [1, 0, 2])
        active_return = capture(index, env, 3)
        scheduler.decide(active_return, advances_simulation=True)
    else:
        active_return = returned

    retires = [event for event in events if event[0] == "retire"]
    assert retires == [
        ("retire", "ego", old_key, "source_gap"),
        ("retire", "traffic", old_key, "source_gap"),
    ]
    assert active_return.actor_for(SourceActorID(200)).is_ego
    assert active_return.actor_for(SourceActorID(100)).lifetime_generation == 1
    first_new_observe = next(
        position
        for position, event in enumerate(events)
        if event[0] == "observe" and event[2] >= 2
    )
    assert all(events.index(event) < first_new_observe for event in retires)
    assert env.step_calls == 0
    assert not scheduler.writer._binding.mode_calls


@pytest.mark.parametrize(
    "collision_state,collided_before_goal,removed,reason",
    [
        (1, False, True, "collision"),
        (2, False, True, "offroad"),
        (0, False, True, "native_removed"),
        (0, True, True, "collision"),
    ],
)
def test_permanent_removal_notifies_exactly_once(
    collision_state, collided_before_goal, removed, reason
):
    binary, state = fixture()
    events = []
    scheduler = EpisodeScheduler(
        Binding(),
        SpyController("ego", "expert", events),
        SpyController("traffic", "expert", events),
    )
    env = Env(state)
    index = ActorIndex(binary)
    key = ActorKey(SourceActorID(100), 0)
    scheduler.decide(capture(index, env, 0), advances_simulation=True)
    events.clear()

    state["entities"][0].update(
        valid=0 if removed else 1,
        x=-10000.0 if removed else 1.0,
        y=-10000.0 if removed else 2.0,
        removed=removed,
        collision_state=collision_state,
        collided_before_goal=collided_before_goal,
    )
    set_active(env, [1, 2])
    scheduler.decide(capture(index, env, 1), advances_simulation=True)
    scheduler.decide(capture(index, env, 2), advances_simulation=True)

    assert [event for event in events if event[0] == "retire"] == [
        ("retire", "ego", key, reason),
        ("retire", "traffic", key, reason),
    ]


def test_birth_reordering_and_active_slot_loss_do_not_retire_lifetime():
    binary, state = fixture()
    binary["objects"][0]["traj_valid"][:2] = 0
    state["entities"][0].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    state["active_agent_indices"] = [1, 2]
    state["active_agent_count"] = 2
    events = []
    scheduler = EpisodeScheduler(
        Binding(),
        SpyController("ego", "expert", events),
        SpyController("traffic", "expert", events),
    )
    env = Env(state)
    env.observations = np.zeros((2, 4), dtype=np.float32)
    index = ActorIndex(binary)
    scheduler.decide(capture(index, env, 0), advances_simulation=True)

    binary["objects"][0]["traj_valid"][1] = 1
    state["entities"][0].update(valid=1, x=10.0, y=2.0, removed=False)
    set_active(env, [1, 0, 2])
    born = capture(index, env, 1)
    assert born.actor_for(SourceActorID(200)).is_ego
    scheduler.decide(born, advances_simulation=True)
    events.clear()

    # Same lifetime, native-present and source-valid, but absent from the batch.
    set_active(env, [2, 1])
    missing_slot = capture(index, env, 2)
    scheduler.decide(missing_slot, advances_simulation=True)
    set_active(env, [0, 1, 2])
    returned_slot = capture(index, env, 3)
    scheduler.decide(returned_slot, advances_simulation=True)

    assert returned_slot.actor_for(SourceActorID(100)).lifetime_generation == 0
    assert not [event for event in events if event[0] == "retire"]


def test_context_only_vru_is_retired_for_each_distinct_observer():
    binary, state = fixture()
    events = []
    ego = SpyController("ego", "expert", events)
    traffic = SpyController("traffic", "expert", events)
    scheduler = EpisodeScheduler(Binding(), ego, traffic)
    env = Env(state)
    index = ActorIndex(binary)
    vru_key = ActorKey(SourceActorID(300), 0)

    first = capture(index, env, 0)
    scheduler.decide(first, advances_simulation=True)
    assert all(vru_key in event[3] for event in events if event[0] == "observe")
    events.clear()
    binary["objects"][2]["traj_valid"][1] = 0
    state["entities"][2].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    set_active(env, [0, 1])

    scheduler.decide(capture(index, env, 1), advances_simulation=True)
    assert [event for event in events if event[0] == "retire"] == [
        ("retire", "ego", vru_key, "source_gap"),
        ("retire", "traffic", vru_key, "source_gap"),
    ]
    first_observe = next(i for i, event in enumerate(events) if event[0] == "observe")
    assert all(i < first_observe for i, event in enumerate(events) if event[0] == "retire")


def test_terminal_removal_retires_before_final_observe_without_advancing():
    binary, state = fixture()
    events = []
    scheduler = EpisodeScheduler(
        Binding(),
        SpyController("ego", "expert", events),
        SpyController("traffic", "expert", events),
    )
    env = Env(state)
    index = ActorIndex(binary)
    key = ActorKey(SourceActorID(200), 0)
    scheduler.decide(capture(index, env, 0), advances_simulation=True)
    events.clear()

    state["entities"][1].update(
        valid=0,
        x=-10000.0,
        y=-10000.0,
        removed=True,
        collision_state=1,
    )
    set_active(env, [0, 2])
    scheduler.decide(capture(index, env, 1), advances_simulation=False)

    assert [event for event in events if event[0] == "retire"] == [
        ("retire", "ego", key, "collision"),
        ("retire", "traffic", key, "collision"),
    ]
    assert env.step_calls == 0


def test_reset_does_not_carry_retirement_notifications_between_episodes():
    binary, state = fixture()
    events = []
    ego = SpyController("ego", "expert", events)
    traffic = SpyController("traffic", "expert", events)
    scheduler = EpisodeScheduler(Binding(), ego, traffic)
    env = Env(state)
    index = ActorIndex(binary)

    def retire_traffic_actor():
        scheduler.decide(capture(index, env, 0), advances_simulation=True)
        binary["objects"][0]["traj_valid"][1] = 0
        state["entities"][0].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
        set_active(env, [1, 2])
        scheduler.decide(capture(index, env, 1), advances_simulation=True)

    retire_traffic_actor()
    scheduler.reset({"episode": 2})
    index.reset_episode()
    binary["objects"][0]["traj_valid"][:] = 1
    _, state = fixture()
    env.state = state
    env.observations = np.zeros((3, 4), dtype=np.float32)
    retire_traffic_actor()

    retire_events = [event for event in events if event[0] == "retire"]
    key = ActorKey(SourceActorID(100), 0)
    assert retire_events.count(("retire", "ego", key, "source_gap")) == 2
    assert retire_events.count(("retire", "traffic", key, "source_gap")) == 2
