from types import SimpleNamespace

import pytest

from geotransfer_gap.runtime.goal_evidence import GoalEvidence


@pytest.mark.parametrize(("award", "collision", "terminal", "cause"), [
    (1, 0, "ego_removed", "goal_award"),
    (0, 1, "ego_removed", "collision"),
    (0, 2, "ego_removed", "offroad"),
    (0, 0, "ego_removed", "unknown"),
    (0, 0, "horizon", "horizon"),
])
def test_goal_evidence_uses_native_pre_step_slot(award, collision, terminal, cause):
    env = SimpleNamespace(REWARD_COMPONENT_NAMES=["goal"], reward_components_raw=[[1], [award]],
                          goal_behavior=3)
    capture = GoalEvidence(env)
    ego = SimpleNamespace(current_active_slot=1)
    capture.transition(8, ego)
    trace = {"terminal_reason": terminal, "transitions": 9, "ego_binary_index": 4, "frames": [
        {"state": {"actors": [{"binary_index": 4, "collision_state": collision,
                               "removed": terminal == "ego_removed", "reached_goal": False}]}}
    ]}
    result = capture.finish(trace)
    assert result["terminal_cause"] == cause
    assert result["raw_reached_goal"] is False
    assert result["native_goal_awards"] == ([{"transition_from_tick": 8, "observed_at_tick": 9,
                                            "active_slot": 1, "raw_count": 1.0}] if award else [])
