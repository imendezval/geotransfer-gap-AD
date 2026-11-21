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
            assert ppo.batches[-1][0][1] is not None if gap != slice(16,19) else ppo.batches[-1][0][1] is None
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
