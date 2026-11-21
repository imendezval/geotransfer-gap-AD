"""Role-scoped PPO inference over immutable pre-step observations."""

from geotransfer_gap.planners.controller_api import ControllerRole, DynamicsIntent


class PPOController:
    name = "ppo"

    def __init__(self, policy, *, role: ControllerRole = "ego"):
        if role not in ("ego", "traffic"):
            raise ValueError(f"unsupported PPO role: {role}")
        self.policy = policy
        self.role = role
        self.reset({})

    def reset(self, episode_info):
        self._ego_key = None
        self._states = {}
        self._actions = {}
        self._last_step = -1

    def _targets(self, snapshot):
        if self.role == "traffic":
            return [snapshot.actor_for(source_id)
                    for source_id in sorted(snapshot.eligible_present_vehicle_ids)]

        ego = snapshot.actor_for(snapshot.ego_id)
        if ego.permanently_removed or ego.removed or not ego.native_present:
            return []
        return [ego]

    def observe(self, snapshot, visible_targets):
        self._actions.clear()
        actors = self._targets(snapshot)
        keys = [actor.key for actor in actors]
        slots = [snapshot.slot_for(key) if key is not None else None for key in keys]
        continuing = set(self._states)
        if (
            snapshot.step != self._last_step + 1
            or any(slot is None for slot in slots)
            or not set(keys) <= visible_targets
            or any(not actor.controller_eligible for actor in actors)
            or (self.role == "traffic" and not continuing <= set(keys))
            or (self.role == "ego" and keys and self._ego_key not in (None, keys[0]))
        ):
            raise ValueError(f"PPO {self.role} observation discontinuity at step {snapshot.step}")

        if keys:
            if self.role == "ego":
                key, = keys
                action, state, _, _ = self.policy.infer(
                    snapshot.observation[slots[0]], self._states.get(key)
                )
                self._ego_key = key
                actions, states = [action], [state]
            else:
                actions, states, _, _ = self.policy.infer_batch(
                    snapshot.observation[slots], [self._states.get(key) for key in keys]
                )
            self._actions = {key: DynamicsIntent(action)
                             for key, action in zip(keys, actions, strict=True)}
            self._states = dict(zip(keys, states, strict=True))
        self._last_step = snapshot.step

    def act(self, snapshot, eligible_targets):
        if (
            snapshot.step != self._last_step
            or not eligible_targets <= self._actions.keys()
            or (self.role == "ego" and eligible_targets != self._actions.keys())
        ):
            raise ValueError(f"PPO {self.role} has no matching cached action at step {snapshot.step}")
        return {key: action for key, action in self._actions.items() if key in eligible_targets}

    def retire(self, actor, reason):
        self._states.pop(actor, None)
        self._actions.pop(actor, None)
