import numpy as np
import pytest

from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.planners.ppo_controller import PPOController
from geotransfer_gap.planners.smart_controller import SMARTController
from geotransfer_gap.runtime.actor_index import ActorIndex, SourceActorID
from geotransfer_gap.runtime.scheduler import EpisodeScheduler
from geotransfer_gap.runtime.startup_policy import StartupPolicy
from test_controller_scheduler import FakeBinding, FakeEnv
from test_ppo_traffic import BatchSpy, capture, scenario
from test_smart_controller import Planner


@pytest.mark.parametrize("controller", ["idm", "ppo", "smart"])
@pytest.mark.parametrize("gap,first_control", [(None,17), (slice(13,15),17), (slice(16,19),19)])
def test_source_hold_late_birth_gaps_and_release(controller, gap, first_control):
    binary, native = scenario()
    binary["objects"][1]["traj_valid"] = np.ones(91, dtype=np.int32)
    binary["objects"][1]["traj_valid"][:12] = 0
    if gap is not None:
        binary["objects"][1]["traj_valid"][gap] = 0
    policy = StartupPolicy("source_hold", 91, {1:17})
    index = ActorIndex(binary)
    ppo = BatchSpy()
    planner = Planner()
    traffic = {
        "idm": IDMController("traffic"),
        "ppo": PPOController(ppo, role="traffic"),
        "smart": SMARTController(planner, "traffic"),
    }[controller]
    env = FakeEnv(native)
    scheduler = EpisodeScheduler(FakeBinding(), ExpertController("ego"), traffic, startup=policy)
    for step in range(21):
        order = ([3, 0, 2, 4, 1] if step % 2 else [1, 4, 3, 0, 2]) if step >= 12 else [0, 2, 3, 4]
        snapshot = capture(index, native, binary, step, order)
        plan = scheduler.decide(snapshot, advances_simulation=True)
        target = plan.by_source_id[SourceActorID(200)]
        applied = scheduler.advance(env, plan)
        for source_id in (100, 300, 302):
            assert plan.by_source_id[SourceActorID(source_id)].native_mode == 2
        if not snapshot.actor_for(200).controller_eligible:
            continue
        released = step >= first_control
        assert target.role == "traffic" and target.declared_controller == controller
        assert target.slot == order.index(1)
        assert target.effective_owner == (f"traffic:{controller}" if released else "source_hold_replay")
        expected_mode = (1 if controller == "idm" else 0) if released else 2
        assert native["entities"][1]["movement_mode"] == target.native_mode == expected_mode
        assert scheduler.startup_record(snapshot.actor_for(200), snapshot.step, True) == {
            "scheduled_release_step": 17,
            "actual_release_step": first_control if released else None,
            "startup_status": "released" if released else "scheduled",
        }
        if not released:
            np.testing.assert_array_equal(applied[target.slot], [0, 0])
        if controller == "ppo" and step == first_control:
            prior = ppo.batches[-1][0][1]
            assert (prior is None) == (first_control == 19)
    assert env.step_calls == 21
    if controller == "ppo":
        assert len(ppo.batches) == 21
    if controller == "smart":
        assert planner.prepared == list(range(21))
        assert [r["step"] for r in traffic.refreshes] == [10, 15, first_control, 20]
        assert traffic.refreshes[2]["reason"] == "new_target"


@pytest.mark.parametrize("final,status", [(12,"scheduled_not_released"), (90,"held_through_window")])
def test_no_release_terminal_status(final, status):
    binary, native = scenario()
    index = ActorIndex(binary)
    ppo = BatchSpy()
    scheduler = EpisodeScheduler(FakeBinding(), ExpertController("ego"),
                                 PPOController(ppo, role="traffic"),
                                 startup=StartupPolicy("source_hold", 91, {1:91}))
    for step in range(final+1):
        snapshot = capture(index, native, binary, step, [0, 1, 2, 3, 4])
        plan = scheduler.decide(snapshot, advances_simulation=step != final)
        if 10 <= step < final:
            assert plan.by_source_id[SourceActorID(200)].intent.kind == "replay"
    assert scheduler.startup_record(snapshot.actor_for(200), final, False) == {
        "scheduled_release_step": 91, "actual_release_step": None, "startup_status": status,
    }
    assert scheduler.startup_record(snapshot.actor_for(301), final, False)["startup_status"] == "not_scheduled"
    assert scheduler.startup_record(snapshot.actor_for(302), final, False)["startup_status"] == "exempt"


@pytest.mark.parametrize("kind", ["ppo", "smart"])
def test_permanent_retirement_during_hold_prevents_release(kind):
    binary, native = scenario()
    index = ActorIndex(binary)
    traffic = (PPOController(BatchSpy(), role="traffic") if kind == "ppo"
               else SMARTController(Planner(), "traffic"))
    scheduler = EpisodeScheduler(FakeBinding(), ExpertController("ego"), traffic,
                                 startup=StartupPolicy("source_hold", 91, {1:17}))
    env = FakeEnv(native)
    for step in range(18):
        if step == 15:
            native["entities"][1].update(collision_state=1, collided_before_goal=True)
        snapshot = capture(index, native, binary, step, [0, 1, 2, 3, 4])
        plan = scheduler.decide(snapshot, advances_simulation=step != 17)
        if step != 17:
            scheduler.advance(env, plan)
    actor = snapshot.actor_for(200)
    assert actor.native_present and actor.permanently_removed
    assert plan.by_source_id[actor.source_id].role == "context"
    assert scheduler.startup_record(actor, 17, False) == {
        "scheduled_release_step": 17, "actual_release_step": None,
        "startup_status": "scheduled_not_released",
    }
    if kind == "ppo":
        assert actor.key not in traffic._states
    else:
        assert not traffic.planner.history.valid[1].any()


@pytest.mark.parametrize("collision,terminal", [(False, "horizon"), (True, "ego_collision")])
def test_final_smart_release_observes_without_act_or_transition(collision, terminal):
    from geotransfer_gap.runtime.episode_worker import run_episode

    binary, native = scenario()
    native.update(active_agent_indices=[0, 1, 2, 3, 4], active_agent_count=5)
    planner = Planner()
    traffic = SMARTController(planner, "traffic")
    calls = []
    act = traffic.act

    def record(snapshot, targets):
        calls.append(snapshot.step)
        return act(snapshot, targets)

    traffic.act = record

    class TerminalEnv(FakeEnv):
        def step(self, actions):
            super().step(actions)
            if collision and self.step_calls == 12:
                self.state["entities"][0].update(collision_state=1, collided_before_goal=True)

    env = TerminalEnv(native)
    report = run_episode(env, binary, FakeBinding(), ExpertController("ego"), traffic,
                         steps=13, startup=StartupPolicy("source_hold", 91, {1: 12}),
                         frame_fn=lambda *_: {})
    final = report["frames"][-1]
    target = next(row for row in final["actors"] if row["source_id"] == 200)
    assert report["terminal_reason"] == terminal
    assert planner.prepared == list(range(13))
    assert env.step_calls == report["transitions"] == 12
    assert calls == [10, 11]
    assert 12 not in [row["step"] for row in traffic.refreshes]
    assert not final["transition_applied"]
    assert target["actual_release_step"] is target["applied_movement_mode"] is target["action"] is None
    assert target["startup_status"] == "scheduled_not_released"
