import numpy as np
import pytest

from geotransfer_gap.planners.controller_api import (
    DynamicsIntent,
    IDMIntent,
    IDMParameters,
    ReplayIntent,
)
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.runtime.actor_index import ActorIndex, ActorKey, SourceActorID
from geotransfer_gap.runtime.episode_worker import run_episode
from geotransfer_gap.runtime.native_modes import NativeMovementMode
from geotransfer_gap.runtime.scheduler import EpisodeScheduler


def scene_and_state():
    valid = np.ones(91, dtype=np.int32)
    binary = {
        "sdc_track_index": 0,
        "objects": [
            {"id": 100, "type": 1, "traj_valid": valid, "mark_as_expert": 0},
            {"id": 200, "type": 1, "traj_valid": valid, "mark_as_expert": 0},
            {"id": 300, "type": 2, "traj_valid": valid, "mark_as_expert": 0},
        ],
    }
    entities = []
    for index in range(3):
        entities.append(
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
                "movement_mode": int(NativeMovementMode.EXPERT_REPLAY),
            }
        )
    state = {
        "active_agent_count": 3,
        "active_agent_indices": [0, 1, 2],
        "entities": entities,
    }
    return binary, state


class FakeEnv:
    def __init__(self, state, events=None):
        self.state = state
        self.c_envs = self
        self.num_agents = 8
        self.observations = np.zeros((state["active_agent_count"], 4), dtype=np.float32)
        self.events = events if events is not None else []
        self.actions = []
        self.step_calls = 0

    def get_state(self):
        return [self.state]

    def step(self, actions):
        self.events.append(("step", actions.copy()))
        self.actions.append(actions.copy())
        self.step_calls += 1


class FakeBinding:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.idm_parameters = []
        self.target_velocity_calls = []
        self.mode_calls = []

    def vec_set_idm_params(self, env, min_gap, headway_time, accel_max, decel_max):
        self.events.append(("idm_params",))
        self.idm_parameters.append((min_gap, headway_time, accel_max, decel_max))

    def vec_set_idm_target_velocity(self, env, slots, velocity):
        self.events.append(("idm_target_velocity", tuple(slots), velocity))
        self.target_velocity_calls.append((tuple(slots), velocity))
        for slot in slots:
            entity_index = env.state["active_agent_indices"][slot]
            env.state["entities"][entity_index]["idm_target_velocity"] = velocity

    def vec_set_movement_mode(self, env, slots, mode):
        self.events.append(("movement_mode", tuple(slots), mode))
        self.mode_calls.append((tuple(slots), mode))
        for slot in slots:
            entity_index = env.state["active_agent_indices"][slot]
            env.state["entities"][entity_index]["movement_mode"] = mode


def controllers(ego, traffic):
    def make(role, name):
        return ExpertController(role) if name == "expert" else IDMController(role)

    return make("ego", ego), make("traffic", traffic)


def snapshot_at(index, env, step):
    snapshot = None
    for current in range(step + 1):
        snapshot = index.capture_pre_step(
            current, env.get_state()[0], env.observations
        )
    return snapshot


@pytest.mark.parametrize(
    "ego_name,traffic_name",
    [("expert", "expert"), ("expert", "idm"), ("idm", "expert"), ("idm", "idm")],
)
def test_four_expert_idm_pairs_take_over_only_at_step_ten(ego_name, traffic_name):
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    ego_controller, traffic_controller = controllers(ego_name, traffic_name)
    scheduler = EpisodeScheduler(binding, ego_controller, traffic_controller)
    index = ActorIndex(binary)
    plans = {}

    for step in range(11):
        snapshot = index.capture_pre_step(
            step, env.get_state()[0], env.observations
        )
        plan = scheduler.decide(snapshot, advances_simulation=True)
        plans[step] = {record.source_id: record for record in plan.assignments}
        scheduler.advance(env, plan)

    for source_id in (SourceActorID(100), SourceActorID(200), SourceActorID(300)):
        assert plans[9][source_id].native_mode is NativeMovementMode.EXPERT_REPLAY
    assert plans[10][SourceActorID(100)].native_mode == (
        NativeMovementMode.IDM if ego_name == "idm" else NativeMovementMode.EXPERT_REPLAY
    )
    assert plans[10][SourceActorID(200)].native_mode == (
        NativeMovementMode.IDM
        if traffic_name == "idm"
        else NativeMovementMode.EXPERT_REPLAY
    )
    assert plans[10][SourceActorID(300)].role == "context"
    assert plans[10][SourceActorID(300)].native_mode is NativeMovementMode.EXPERT_REPLAY
    assert plans[10][SourceActorID(100)].effective_owner != "traffic:idm"
    assert env.step_calls == 11
    assert len(env.actions) == 11
    assert all(action.shape == (env.num_agents, 2) for action in env.actions)
    assert all(np.count_nonzero(action) == 0 for action in env.actions)

    uses_idm = "idm" in (ego_name, traffic_name)
    assert len(binding.idm_parameters) == (1 if uses_idm else 0)
    assert binding.idm_parameters == ([(1.0, 1.5, 1.0, 2.0)] if uses_idm else [])
    expected_idm_slots = tuple(
        slot
        for slot, source_id in enumerate((100, 200, 300))
        if (source_id == 100 and ego_name == "idm")
        or (source_id == 200 and traffic_name == "idm")
    )
    if expected_idm_slots:
        assert binding.target_velocity_calls[-1] == (expected_idm_slots, 15.0)
    else:
        assert not binding.target_velocity_calls

    # Every active slot has exactly one applied mode on every transition.
    for slot in range(len(state["active_agent_indices"])):
        writes = [
            written_slot
            for slots, _mode in binding.mode_calls
            for written_slot in slots
            if written_slot == slot
        ]
        assert len(writes) == env.step_calls


def test_controller_decisions_share_snapshot_and_finish_before_native_writes():
    events = []
    seen_snapshots = []

    class Recorder:
        def __init__(self, role, name):
            self.role = role
            self.name = name
            self.parameters = IDMParameters()

        def reset(self, episode_info):
            return None

        def observe(self, snapshot, visible_targets):
            events.append((self.role, "observe"))
            seen_snapshots.append(snapshot)

        def act(self, snapshot, eligible_targets):
            events.append((self.role, "act"))
            seen_snapshots.append(snapshot)
            if self.name == "idm":
                return {key: IDMIntent(parameters=self.parameters) for key in eligible_targets}
            return {key: ReplayIntent() for key in eligible_targets}

        def retire(self, actor, reason):
            return None

    binary, state = scene_and_state()
    env = FakeEnv(state, events)
    binding = FakeBinding(events)
    scheduler = EpisodeScheduler(binding, Recorder("ego", "idm"), Recorder("traffic", "idm"))
    snapshot = snapshot_at(ActorIndex(binary), env, 10)
    plan = scheduler.decide(snapshot, advances_simulation=True)
    decision_events = list(events)
    scheduler.advance(env, plan)

    assert decision_events == [
        ("ego", "observe"),
        ("traffic", "observe"),
        ("ego", "act"),
        ("traffic", "act"),
    ]
    assert all(item is snapshot for item in seen_snapshots)
    first_native_write = next(i for i, event in enumerate(events) if event[0] == "idm_params")
    assert first_native_write == len(decision_events)
    assert events[-1][0] == "step"


def test_foreign_actor_intent_is_rejected_before_any_slot_is_written():
    class ForeignTrafficController:
        role = "traffic"
        name = "expert"

        def reset(self, episode_info):
            return None

        def observe(self, snapshot, visible_targets):
            return None

        def act(self, snapshot, eligible_targets):
            ego = next(actor.key for actor in snapshot.actors if actor.is_ego)
            return {**{key: ReplayIntent() for key in eligible_targets}, ego: ReplayIntent()}

        def retire(self, actor, reason):
            return None

    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(
        binding,
        IDMController("ego"),
        ForeignTrafficController(),
    )
    snapshot = snapshot_at(ActorIndex(binary), env, 10)

    with pytest.raises(ValueError, match="target mismatch"):
        scheduler.decide(snapshot, advances_simulation=True)
    assert not binding.mode_calls
    assert not binding.idm_parameters
    assert env.step_calls == 0


def test_mismatched_global_idm_parameters_are_rejected_before_execution():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    with pytest.raises(ValueError, match="globally per episode"):
        EpisodeScheduler(
            binding,
            IDMController("ego", parameters=IDMParameters(headway_time=1.0)),
            IDMController("traffic", parameters=IDMParameters(headway_time=2.0)),
        )
    assert not binding.idm_parameters
    assert env.step_calls == 0


def test_worker_records_91_observations_and_only_90_transitions():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    report = run_episode(
        env,
        binary,
        binding,
        ExpertController("ego"),
        IDMController("traffic"),
        steps=91,
        frame_fn=lambda native, _binary, step: {"step": step},
    )

    assert report["observation_frames"] == 91
    assert report["transitions"] == 90
    assert env.step_calls == 90
    assert report["frames"][9]["transition_applied"] is True
    assert report["frames"][10]["actors"][0]["planned_movement_mode"] == 2
    assert report["frames"][10]["actors"][1]["planned_movement_mode"] == 1
    assert report["frames"][90]["transition_applied"] is False
    assert report["frames"][90]["actors"][1]["applied_movement_mode"] is None


def test_worker_captures_trace_state_before_native_step():
    binary, state = scene_and_state()
    events = []
    env = FakeEnv(state, events)
    binding = FakeBinding(events)
    report = run_episode(
        env,
        binary,
        binding,
        ExpertController("ego"),
        ExpertController("traffic"),
        steps=2,
        frame_fn=lambda _native, _binary, step: events.append(("frame", step)) or step,
    )

    assert report["frames"][0]["state"] == 0
    assert report["frames"][1]["state"] == 1
    assert events.index(("frame", 0)) < next(
        index for index, event in enumerate(events) if event[0] == "step"
    )
    assert events.index(("frame", 1)) > events.index(("frame", 0))


def test_late_birth_receives_its_role_mode_on_first_present_tick():
    ego_valid = np.ones(91, dtype=np.int32)
    traffic_valid = np.zeros(91, dtype=np.int32)
    traffic_valid[10:] = 1
    binary = {
        "sdc_track_index": 0,
        "objects": [
            {"id": 100, "type": 1, "traj_valid": ego_valid, "mark_as_expert": 0},
            {"id": 200, "type": 1, "traj_valid": traffic_valid, "mark_as_expert": 0},
        ],
    }
    _, base_state = scene_and_state()
    state = {
        "active_agent_count": 1,
        "active_agent_indices": [0],
        "entities": [base_state["entities"][0], dict(base_state["entities"][1])],
    }
    state["entities"][1].update(
        valid=0,
        x=-10000.0,
        y=-10000.0,
        removed=True,
        collision_state=0,
    )
    env = FakeEnv(state)
    env.observations = np.zeros((1, 4), dtype=np.float32)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(binding, ExpertController("ego"), IDMController("traffic"))
    index = ActorIndex(binary)

    for step in range(10):
        snapshot = index.capture_pre_step(step, state, env.observations)
        scheduler.advance(
            env,
            scheduler.decide(snapshot, advances_simulation=True),
        )

    state["entities"][1].update(valid=1, x=20.0, y=3.0, removed=False)
    state["active_agent_indices"] = [1, 0]
    state["active_agent_count"] = 2
    env.observations = np.zeros((2, 4), dtype=np.float32)
    snapshot = index.capture_pre_step(10, state, env.observations)
    born = snapshot.actor_for(SourceActorID(200))
    plan = scheduler.decide(snapshot, advances_simulation=True)
    assignment = plan.by_source_id[SourceActorID(200)]

    assert born.lifetime_generation == 0
    assert born.current_active_slot == 0
    assert assignment.slot == 0
    assert assignment.role == "traffic"
    assert assignment.native_mode is NativeMovementMode.IDM
    assert assignment.effective_owner == "traffic:idm"
    scheduler.advance(env, plan)
    assert binding.target_velocity_calls[-1] == ((0,), 15.0)
    assert binding.mode_calls[-2:] == [((0,), 1), ((1,), 2)]
    assert state["entities"][1]["movement_mode"] == 1
    assert state["entities"][0]["movement_mode"] == 2
    assert env.step_calls == 11


class FakeNamedController:
    def __init__(self, role, name, intent_factory):
        self.role = role
        self.name = name
        self.parameters = IDMParameters()
        self.intent_factory = intent_factory
        self.calls = 0

    def reset(self, episode_info):
        return None

    def observe(self, snapshot, visible_targets):
        return None

    def act(self, snapshot, eligible_targets):
        self.calls += 1
        return {
            key: self.intent_factory(self.calls)
            for key in eligible_targets
        }

    def retire(self, actor, reason):
        return None


@pytest.mark.parametrize(
    "role,name,intent_factory",
    [
        ("ego", "ppo", lambda _: IDMIntent()),
        ("traffic", "ppo", lambda _: IDMIntent()),
        ("ego", "idm", lambda _: DynamicsIntent((0.2, -0.1))),
        ("traffic", "idm", lambda _: DynamicsIntent((0.2, -0.1))),
        ("ego", "expert", lambda _: DynamicsIntent((0.2, -0.1))),
        ("traffic", "expert", lambda _: DynamicsIntent((0.2, -0.1))),
    ],
)
def test_declared_controller_rejects_mismatched_intent_before_native_write(
    role, name, intent_factory
):
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    invalid = FakeNamedController(role, name, intent_factory)
    valid_role = "traffic" if role == "ego" else "ego"
    valid = ExpertController(valid_role)
    scheduler = EpisodeScheduler(
        binding,
        invalid if role == "ego" else valid,
        invalid if role == "traffic" else valid,
    )
    snapshot = snapshot_at(ActorIndex(binary), env, 10)

    with pytest.raises(TypeError, match="declared controller"):
        scheduler.decide(snapshot, advances_simulation=True)

    assert not binding.mode_calls
    assert not binding.idm_parameters
    assert env.step_calls == 0


@pytest.mark.parametrize("name", ["ppo", " Smart "])
def test_dynamics_intent_matches_normalized_declared_controller(name):
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(
        binding,
        FakeNamedController("ego", name, lambda _: DynamicsIntent((0.2, -0.1))),
        ExpertController("traffic"),
    )
    snapshot = snapshot_at(ActorIndex(binary), env, 10)

    plan = scheduler.decide(snapshot, advances_simulation=True)
    assert plan.by_source_id[SourceActorID(100)].intent == DynamicsIntent((0.2, -0.1))
    assert not binding.mode_calls
    assert env.step_calls == 0


def test_unsupported_declared_controller_name_fails_closed():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    with pytest.raises(ValueError, match="unsupported controller name"):
        EpisodeScheduler(
            FakeBinding(env.events),
            FakeNamedController("ego", "not-a-controller", lambda _: ReplayIntent()),
            ExpertController("traffic"),
        )


def test_declared_controller_cannot_change_intent_type_mid_episode():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(
        binding,
        FakeNamedController(
            "ego",
            "ppo",
            lambda call: DynamicsIntent((0.2, -0.1))
            if call == 1
            else IDMIntent(),
        ),
        ExpertController("traffic"),
    )
    index = ActorIndex(binary)
    first = snapshot_at(index, env, 10)
    second = index.capture_pre_step(11, env.get_state()[0], env.observations)

    scheduler.decide(first, advances_simulation=True)
    with pytest.raises(TypeError, match="declared controller"):
        scheduler.decide(second, advances_simulation=True)
    assert not binding.mode_calls
    assert env.step_calls == 0


def test_warmup_override_allows_future_nonexpert_controller_to_replay():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(
        binding,
        FakeNamedController("ego", "ppo", lambda _: IDMIntent()),
        FakeNamedController("traffic", "smart", lambda _: IDMIntent()),
    )
    snapshot = snapshot_at(ActorIndex(binary), env, 9)

    plan = scheduler.decide(snapshot, advances_simulation=True)
    assert all(
        assignment.intent is None
        or isinstance(assignment.intent, ReplayIntent)
        for assignment in plan.assignments
    )


def test_scheduler_reset_reinitializes_global_idm_parameters_per_episode():
    binary, state = scene_and_state()
    env = FakeEnv(state)
    binding = FakeBinding(env.events)
    scheduler = EpisodeScheduler(binding, ExpertController("ego"), IDMController("traffic"))
    index = ActorIndex(binary)

    def execute_episode():
        for step in range(11):
            snapshot = index.capture_pre_step(step, env.get_state()[0], env.observations)
            scheduler.advance(
                env,
                scheduler.decide(snapshot, advances_simulation=True),
            )

    execute_episode()
    assert len(binding.idm_parameters) == 1

    # Model env.reset() and ActorIndex.reset_episode() at the fresh episode boundary.
    index.reset_episode()
    _, env.state = scene_and_state()
    env.observations = np.zeros((env.state["active_agent_count"], 4), dtype=np.float32)
    env.step_calls = 0
    scheduler.reset({"episode": 2})
    execute_episode()

    assert len(binding.idm_parameters) == 2
    assert binding.idm_parameters == [(1.0, 1.5, 1.0, 2.0)] * 2
