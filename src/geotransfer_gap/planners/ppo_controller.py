"""Single-ego PPO adapter using the scheduler's immutable pre-step frames."""

from geotransfer_gap.planners.controller_api import DynamicsIntent


class PPOController:
    name = "ppo"
    role = "ego"

    def __init__(self, policy):
        self.policy = policy
        self.reset({})

    def reset(self, episode_info):
        self._ego_key = None
        self._state = None
        self._action = None
        self._last_step = -1

    def observe(self, snapshot, visible_targets):
        ego = snapshot.actor_for(snapshot.ego_id)
        self._action = None
        if ego.permanently_removed or ego.removed or not ego.native_present:
            # The worker records this terminal frame without advancing.
            return
        key = ego.key
        slot = snapshot.slot_for(key) if key is not None else None
        if (
            key not in visible_targets
            or slot is None
            or not ego.controller_eligible
            or (self._ego_key is not None and self._ego_key != key)
            or snapshot.step != self._last_step + 1
        ):
            raise ValueError(f"PPO ego observation discontinuity at step {snapshot.step}")
        action, state, _, _ = self.policy.infer(snapshot.observation[slot], self._state)
        self._action = DynamicsIntent(action)
        self._ego_key = key
        self._state = state
        self._last_step = snapshot.step

    def act(self, snapshot, eligible_targets):
        if (
            self._action is None
            or snapshot.step != self._last_step
            or eligible_targets != {self._ego_key}
        ):
            raise ValueError(f"PPO ego has no matching cached action at step {snapshot.step}")
        return {self._ego_key: self._action}

    def retire(self, actor, reason):
        if actor == self._ego_key:
            self._state = None
            self._action = None
