"""Additive evidence from the native per-transition RC_GOAL reward counter."""

import math


SOURCE = "Drive.reward_components_raw[pre_transition_ego_active_slot, RC_GOAL]"


class GoalEvidence:
    def __init__(self, env):
        self.env = env
        self.goal_index = env.REWARD_COMPONENT_NAMES.index("goal")
        self.observed = []
        self.awards = []

    def transition(self, tick, ego):
        slot = ego.current_active_slot
        if slot is None:
            return
        count = float(self.env.reward_components_raw[slot][self.goal_index])
        if not math.isfinite(count) or count < 0:
            raise ValueError("invalid native goal reward counter")
        self.observed.append(tick)
        if count:
            self.awards.append({"transition_from_tick": tick, "observed_at_tick": tick + 1,
                                "active_slot": slot, "raw_count": count})

    def finish(self, trace):
        return _record(trace, self.env.goal_behavior, self.observed, self.awards)


def _record(trace, goal_behavior, observed, awards):
    states = [actor for frame in trace["frames"] for actor in frame["state"]["actors"]
              if actor["binary_index"] == trace["ego_binary_index"]]
    final = states[-1]
    reason = trace["terminal_reason"]
    final_award = bool(awards and awards[-1]["observed_at_tick"] == trace["transitions"])
    raw = any(actor["reached_goal"] for actor in states)
    collision = final["collision_state"]
    cause = "unknown"
    if reason != "horizon" and final_award and goal_behavior == 3 and final["removed"] and not collision:
        cause = "goal_award"
    elif collision == 1:
        cause = "collision"
    elif collision == 2:
        cause = "offroad"
    elif reason == "horizon":
        cause = "horizon"
    return {"schema_version": 1,
            "source": SOURCE,
            "native_goal_behavior": goal_behavior,
            "raw_reached_goal": raw,
            "native_goal_awards": awards,
            "observed_transitions": observed,
            "native_removed": final["removed"], "native_terminal_reason": reason,
            "collision_state": collision, "terminal_cause": cause,
            "terminal_cause_evidence": "confirmed" if cause != "unknown" else "unknown"}



def validate_goal_evidence(trace, record, goal_behavior):
    ego = trace["ego_binary_index"]
    slots = [next(actor["slot"] for actor in frame["actors"] if actor["binary_index"] == ego)
             for frame in trace["frames"][:-1]]
    observed = [tick for tick, slot in enumerate(slots) if slot is not None]
    awards = record["native_goal_awards"]
    previous = -1
    for award in awards:
        tick = award["transition_from_tick"]
        if (type(tick) is not int or not previous < tick < len(slots)
                or slots[tick] is None or award["active_slot"] != slots[tick]
                or award["observed_at_tick"] != tick + 1
                or type(award["raw_count"]) not in (int, float)
                or not math.isfinite(award["raw_count"]) or award["raw_count"] <= 0):
            raise ValueError("invalid native goal award evidence")
        previous = tick
    actual = {key: value for key, value in record.items() if key != "trace_sha256"}
    if actual != _record(trace, goal_behavior, observed, awards):
        raise ValueError("inconsistent native goal evidence")
