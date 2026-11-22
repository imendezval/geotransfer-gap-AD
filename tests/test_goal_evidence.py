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


def test_campaign_outcome_keeps_raw_flag_separate_from_native_award():
    from geotransfer_gap.matrix_campaign import _driving_outcome

    trace = {"terminal_reason": "ego_removed", "transitions": 1, "ego_binary_index": 0,
             "requested_observation_frames": 91, "observation_frames": 2, "frames": [
        {"state": {"actors": [{"binary_index": 0, "collision_state": 0, "present": False,
                               "removed": True, "reached_goal": False}]}}
    ]}
    assert _driving_outcome(trace)["native_goal_award_observed"] is None
    outcome = _driving_outcome(trace, {"native_goal_awards": [{}], "terminal_cause": "goal_award"})
    assert outcome["native_goal_award_observed"] is True
    assert outcome["reached_goal"] is False
    assert outcome["terminal_cause"] == "goal_award"
