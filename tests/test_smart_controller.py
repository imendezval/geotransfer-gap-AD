import numpy as np
import pytest

from geotransfer_gap.planners.smart_controller import SMARTController
from geotransfer_gap.runtime.actor_index import ActorIndex
from test_ppo_traffic import capture, scenario


class Planner:
    """Record calls across the three existing planner entry points."""

    def __init__(self):
        from types import SimpleNamespace

        self.config = SimpleNamespace(repredict_interval=5, num_historical_steps=11)
        self.history = SimpleNamespace(
            position=np.zeros((5, 120, 2), dtype=np.float32),
            heading=np.zeros((5, 120), dtype=np.float32),
            velocity=np.zeros((5, 120, 2), dtype=np.float32),
            valid=np.zeros((5, 120), dtype=bool),
            num_steps=0,
            num_agents=5,
        )
        self.reset()

    def reset(self):
        self.history.num_steps = 0
        self.history.valid[:] = False
        self._prediction_step = -1
        self._predicted_positions = None
        self.prepared = []
        self.predictions = []
        self.calls = []

    def prepare_step(self, step):
        self.prepared.append(step)
        self.history.num_steps = step + 11
        self.history.valid[:, step + 10] = True

    def _bootstrap_speeds_from_state(self, speed, size):
        speed[:] = 2

    def _run_inference(self):
        self._valid_agent_map = np.flatnonzero(self.history.valid[:, self.history.num_steps - 1])
        self.predictions.append(self._valid_agent_map.tolist())
        self._predicted_positions = np.zeros((5, 5, 2), dtype=np.float32)

    def _positions_to_actions(self, indices, step, positions, headings, speeds):
        self.calls.append((indices.tolist(), step, self._prediction_step))
        return np.array([(i / 5, 0) for i in indices])


def test_smart_temporal_alignment_explicit_subset_and_roles():
    binary, native = scenario()
    binary["sdc_track_index"] = 1
    index = ActorIndex(binary)
    planners = [Planner(), Planner()]
    ego, traffic = (SMARTController(p, role)
                    for p, role in zip(planners, ("ego", "traffic"), strict=True))
    for step in range(17):
        order = [3, 1, 4, 2, 0] if step % 2 else [0, 2, 1, 3, 4]
        snapshot = capture(index, native, binary, step, order)
        live = frozenset(a.key for a in snapshot.actors)
        for controller in (ego, traffic):
            controller.observe(snapshot, live)
        if step >= 10:
            ek = snapshot.actor_for(200).key
            car, other = (snapshot.actor_for(s).key for s in (100, 301))
            with pytest.raises(ValueError, match="target"):
                traffic.act(snapshot, {ek})
            with pytest.raises(ValueError, match="target"):
                traffic.act(snapshot, {snapshot.actor_for(302).key})
            targets = {other} if step == 10 else {other, car}
            actions = traffic.act(snapshot, targets)
            assert set(actions) == targets
            assert actions[other].action == (0.6, 0)
            assert ego.act(snapshot, {ek})[ek].action == (0.2, 0)
    for planner in planners:
        assert planner.prepared == list(range(17))
        assert all(row == list(range(5)) for row in planner.predictions)
    assert [r["step"] for r in ego.refreshes] == [10, 15]
    assert [r["step"] for r in traffic.refreshes] == [10, 11, 15]
    assert planners[1].calls[:2] == [([3], 10, 10), ([0, 3], 11, 11)]


def test_smart_retirement_clears_row_and_refreshes_off_cadence():
    from geotransfer_gap.planners.expert_controller import ExpertController
    from geotransfer_gap.runtime.scheduler import EpisodeScheduler
    from test_controller_scheduler import FakeBinding

    binary, native = scenario()
    binary["objects"][1]["traj_valid"] = np.ones(91, dtype=np.int32)
    binary["objects"][1]["traj_valid"][12:14] = 0
    binary["objects"][3]["traj_valid"] = np.ones(91, dtype=np.int32)
    binary["objects"][3]["traj_valid"][:11] = 0
    index = ActorIndex(binary)
    planner = Planner()
    traffic = SMARTController(planner, "traffic")
    scheduler = EpisodeScheduler(FakeBinding(), ExpertController("ego"), traffic)
    for step in range(17):
        if step == 16:
            native["entities"][3].update(collision_state=2, collided_before_goal=True)
        snapshot = capture(index, native, binary, step, [0, 1, 2, 3, 4])
        plan = scheduler.decide(snapshot, advances_simulation=True)
        if step == 12:
            assert not planner.history.valid[1].any()
        if step == 14:
            assert planner.history.valid[1].sum() == 1
            assert snapshot.actor_for(200).key.lifetime_generation == 1
        if step == 16:
            assert not planner.history.valid[3].any()
            assert plan.by_source_id[snapshot.actor_for(301).source_id].intent.kind == "replay"
    assert [r["step"] for r in traffic.refreshes] == [10, 11, 14, 15]


def test_missing_forecast_fails_before_action_conversion():
    binary, native = scenario()
    index = ActorIndex(binary)
    planner = Planner()
    controller = SMARTController(planner, "traffic")
    planner._run_inference = lambda: None
    for step in range(11):
        snapshot = capture(index, native, binary, step, [0, 1, 2, 3, 4])
        controller.observe(snapshot, frozenset(a.key for a in snapshot.actors))
    with pytest.raises(RuntimeError, match="forecast"):
        controller.act(snapshot, {snapshot.actor_for(200).key})
    assert not planner.calls
