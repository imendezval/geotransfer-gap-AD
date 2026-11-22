"""Additive evidence from the native per-transition RC_GOAL reward counter."""

import math


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
        states = [actor for frame in trace["frames"] for actor in frame["state"]["actors"]
                  if actor["binary_index"] == trace["ego_binary_index"]]
        final = states[-1]
        reason = trace["terminal_reason"]
        final_award = bool(self.awards and self.awards[-1]["observed_at_tick"] == trace["transitions"])
        raw = any(actor["reached_goal"] for actor in states)
        collision = final["collision_state"]
        cause = "unknown"
        if reason != "horizon" and final_award and self.env.goal_behavior == 3 and final["removed"] and not collision:
            cause = "goal_award"
        elif collision == 1:
            cause = "collision"
        elif collision == 2:
            cause = "offroad"
        elif reason == "horizon":
            cause = "horizon"
        return {"schema_version": 1,
                "source": "Drive.reward_components_raw[pre_transition_ego_active_slot, RC_GOAL]",
                "native_goal_behavior": self.env.goal_behavior,
                "raw_reached_goal": raw,
                "native_goal_awards": self.awards,
                "observed_transitions": self.observed,
                "native_removed": final["removed"], "native_terminal_reason": reason,
                "collision_state": collision, "terminal_cause": cause,
                "terminal_cause_evidence": "confirmed" if cause != "unknown" else "unknown"}
