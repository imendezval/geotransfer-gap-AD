"""Single-writer controller scheduler for one native Drive episode."""

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

import numpy as np

from geotransfer_gap.planners.controller_api import (
    ActionIntent,
    Controller,
    IDMIntent,
    IDMParameters,
    ReplayIntent,
    DynamicsIntent,
)
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.runtime.actor_index import ActorKey, SourceActorID
from geotransfer_gap.runtime.native_modes import NativeMovementMode
from geotransfer_gap.runtime.step_snapshot import RemovalReason, StepSnapshot


_INTENT_MODE = MappingProxyType(
    {
        ReplayIntent: NativeMovementMode.EXPERT_REPLAY,
        IDMIntent: NativeMovementMode.IDM,
        DynamicsIntent: NativeMovementMode.DYNAMICS,
    }
)
_CONTROLLER_INTENT = MappingProxyType(
    {
        "expert": ReplayIntent,
        "idm": IDMIntent,
        "ppo": DynamicsIntent,
        "smart": DynamicsIntent,
    }
)


def _normalized_controller_name(controller: Controller) -> str:
    name = getattr(controller, "name", None)
    if not isinstance(name, str):
        raise TypeError("controller name must be a string")
    normalized = name.strip().lower()
    if normalized not in _CONTROLLER_INTENT:
        raise ValueError(f"unsupported controller name: {name!r}")
    return normalized


@dataclass(frozen=True)
class ActorAssignment:
    """One actor's declared role, effective owner and pre-step mode intent."""

    source_id: SourceActorID
    key: ActorKey | None
    binary_index: int
    slot: int | None
    role: Literal["ego", "traffic", "context"]
    declared_controller: str | None
    effective_owner: str
    pre_step_native_mode: int
    intent: ActionIntent | None
    native_mode: NativeMovementMode | None

    def trace_record(self, *, applied: bool):
        if isinstance(self.intent, DynamicsIntent):
            action = list(self.intent.action)
        elif self.slot is not None:
            action = [0.0, 0.0]
        else:
            action = None
        if isinstance(self.intent, IDMIntent):
            target_velocity = self.intent.target_velocity
            idm_route_policy = (
                "native_lane_route_only"
                if self.role == "ego"
                else "background_source_prior_permitted"
            )
        else:
            target_velocity = None
            idm_route_policy = None
        return {
            "source_id": int(self.source_id),
            "lifetime_generation": (
                self.key.lifetime_generation if self.key is not None else None
            ),
            "binary_index": self.binary_index,
            "slot": self.slot,
            "role": self.role,
            "declared_controller": self.declared_controller,
            "effective_owner": self.effective_owner,
            "pre_step_native_movement_mode": self.pre_step_native_mode,
            "intent": self.intent.kind if self.intent is not None else None,
            "planned_movement_mode": (
                int(self.native_mode) if self.native_mode is not None else None
            ),
            "applied_movement_mode": (
                int(self.native_mode)
                if applied and self.slot is not None and self.native_mode is not None
                else None
            ),
            "action": action if applied else None,
            "idm_target_velocity": target_velocity,
            "idm_route_policy": idm_route_policy,
        }


@dataclass(frozen=True)
class TickPlan:
    snapshot: StepSnapshot
    assignments: tuple[ActorAssignment, ...]
    idm_parameters: IDMParameters | None
    advances_simulation: bool

    @property
    def by_source_id(self):
        return MappingProxyType(
            {assignment.source_id: assignment for assignment in self.assignments}
        )


class NativeActionWriter:
    """The sole matrix-scheduler writer of native modes, targets and actions."""

    def __init__(self, binding):
        self._binding = binding
        self._initialized_idm_parameters: IDMParameters | None = None

    def reset(self):
        """Clear episode-local native parameter initialization state."""
        self._initialized_idm_parameters = None

    def apply_and_step(self, env, plan: TickPlan):
        if not plan.advances_simulation:
            raise ValueError("a final observation plan cannot advance the simulator")
        if int(env.num_agents) < len(plan.snapshot.active_agent_indices):
            raise ValueError("native action matrix is smaller than the active slot list")

        active_slots = set(range(len(plan.snapshot.active_agent_indices)))
        assignments_by_slot = {}
        for assignment in plan.assignments:
            if assignment.slot is None:
                continue
            if assignment.slot in assignments_by_slot:
                raise ValueError(f"multiple owners assigned to slot {assignment.slot}")
            assignments_by_slot[assignment.slot] = assignment
        if set(assignments_by_slot) != active_slots:
            raise ValueError("every active native slot must receive exactly one mode")

        actions = np.zeros((int(env.num_agents), 2), dtype=np.float32)
        mode_slots = defaultdict(list)
        idm_slots_by_velocity = defaultdict(list)
        for slot in sorted(active_slots):
            assignment = assignments_by_slot[slot]
            if assignment.native_mode is None or assignment.intent is None:
                raise ValueError(f"active slot {slot} lacks a complete intent and mode")
            expected_mode = _INTENT_MODE.get(type(assignment.intent))
            if expected_mode is None or expected_mode != assignment.native_mode:
                raise ValueError(f"intent and native mode disagree for slot {slot}")
            mode_slots[assignment.native_mode].append(slot)
            if isinstance(assignment.intent, IDMIntent):
                idm_slots_by_velocity[assignment.intent.target_velocity].append(slot)
            elif isinstance(assignment.intent, DynamicsIntent):
                actions[slot, :] = assignment.intent.action

        if plan.idm_parameters is not None:
            if self._initialized_idm_parameters is None:
                parameters = plan.idm_parameters
                self._binding.vec_set_idm_params(
                    env.c_envs,
                    parameters.min_gap,
                    parameters.headway_time,
                    parameters.accel_max,
                    parameters.decel_max,
                )
                self._initialized_idm_parameters = parameters
            elif self._initialized_idm_parameters != plan.idm_parameters:
                raise ValueError("episode IDM global parameters changed after initialization")

        # The native binding treats target speed as an active-slot property.
        # Slots are resolved anew from this plan on every observed frame.
        for target_velocity in sorted(idm_slots_by_velocity):
            self._binding.vec_set_idm_target_velocity(
                env.c_envs,
                idm_slots_by_velocity[target_velocity],
                float(target_velocity),
            )
        for mode in NativeMovementMode:
            slots = mode_slots.get(mode, ())
            if slots:
                self._binding.vec_set_movement_mode(
                    env.c_envs, list(slots), int(mode)
                )

        env.step(actions)
        return actions


class EpisodeScheduler:
    """Resolve roles from one immutable pre-action frame and advance once."""

    def __init__(self, binding, ego_controller: Controller, traffic_controller: Controller):
        if ego_controller.role != "ego":
            raise ValueError("ego controller must declare role='ego'")
        if traffic_controller.role != "traffic":
            raise ValueError("traffic controller must declare role='traffic'")
        self.controllers = {
            "ego": ego_controller,
            "traffic": traffic_controller,
        }
        for controller in self.controllers.values():
            _normalized_controller_name(controller)
        self.warmup_experts = {
            role: (
                controller
                if _normalized_controller_name(controller) == "expert"
                else ExpertController(role)
            )
            for role, controller in self.controllers.items()
        }
        idm_parameters = {
            controller.parameters
            for controller in self.controllers.values()
            if _normalized_controller_name(controller) == "idm"
        }
        if len(idm_parameters) > 1:
            raise ValueError(
                "ego and traffic IDM parameters must match because the native "
                "binding configures them globally per episode"
            )
        self.idm_parameters = next(iter(idm_parameters), None)
        self.writer = NativeActionWriter(binding)
        self._observed_lifetimes: set[ActorKey] = set()
        self._retired_lifetimes: set[ActorKey] = set()
        self._reset = False

    def reset(self, episode_info: Mapping[str, object]):
        for controller in self._controller_instances():
            controller.reset(episode_info)
        self.writer.reset()
        self._observed_lifetimes.clear()
        self._retired_lifetimes.clear()
        self._reset = True

    def _controller_instances(self):
        instances = []
        seen = set()
        for role in ("ego", "traffic"):
            for controller in (self.controllers[role], self.warmup_experts[role]):
                if id(controller) in seen:
                    continue
                seen.add(id(controller))
                instances.append(controller)
        return tuple(instances)

    @staticmethod
    def _retirement_reason(actor, previous_key: ActorKey) -> str | None:
        if actor.permanently_removed:
            if actor.removal_reason is RemovalReason.NONE:
                raise ValueError(
                    f"permanently removed actor {int(actor.source_id)} has no removal reason"
                )
            return actor.removal_reason.value
        if not actor.source_valid or actor.source_gap_pending:
            return RemovalReason.SOURCE_GAP.value
        if actor.key != previous_key:
            # ActorIndex increments this generation only after a source-valid gap.
            return RemovalReason.SOURCE_GAP.value
        return None

    def _retire_ended_lifetimes(self, snapshot: StepSnapshot):
        notifications = []
        for key in sorted(self._observed_lifetimes):
            if key in self._retired_lifetimes:
                continue
            actor = snapshot.actor_for(key.source_id)
            reason = self._retirement_reason(actor, key)
            if reason is not None:
                notifications.append((key, reason))

        controllers = self._controller_instances()
        for key, reason in notifications:
            self._retired_lifetimes.add(key)
            self._observed_lifetimes.discard(key)
            for controller in controllers:
                controller.retire(key, reason)

    def decide(self, snapshot: StepSnapshot, *, advances_simulation: bool) -> TickPlan:
        if not self._reset:
            self.reset({})

        # Retirement is delivered before observers can see a later generation.
        self._retire_ended_lifetimes(snapshot)
        live_keys = frozenset(
            actor.key
            for actor in snapshot.actors
            if actor.key is not None
            and actor.source_valid
            and actor.native_present
            and not actor.permanently_removed
            and actor.key not in self._retired_lifetimes
        )
        for controller in self._controller_instances():
            controller.observe(snapshot, live_keys)
        self._observed_lifetimes.update(live_keys)

        role_targets = {
            "ego": self._eligible_targets(snapshot, "ego"),
            "traffic": self._eligible_targets(snapshot, "traffic"),
        }
        decisions = {}
        if advances_simulation:
            for role in ("ego", "traffic"):
                controller = (
                    self.warmup_experts[role]
                    if snapshot.step < 10
                    else self.controllers[role]
                )
                effective_name = _normalized_controller_name(controller)
                expected_intent_type = _CONTROLLER_INTENT[effective_name]
                returned = controller.act(snapshot, role_targets[role])
                if not isinstance(returned, Mapping):
                    raise TypeError(f"{role} controller must return a mapping of intents")
                expected = role_targets[role]
                returned_keys = set(returned)
                if returned_keys != set(expected):
                    extra = returned_keys - set(expected)
                    missing = set(expected) - returned_keys
                    raise ValueError(
                        f"{role} controller target mismatch; extra={extra}, missing={missing}"
                    )
                for key, intent in returned.items():
                    actor = snapshot.actor_for(key)
                    self._authorize(snapshot, actor, role)
                    if type(intent) is not expected_intent_type:
                        raise TypeError(
                            f"{role} declared controller {effective_name!r} must return "
                            f"{expected_intent_type.__name__}, got {type(intent).__name__}"
                        )
                    if key in decisions:
                        raise ValueError(f"multiple controllers own actor key {key}")
                    decisions[key] = intent

        assignments = []
        used_slots = set()
        for actor in snapshot.actors:
            if actor.controller_eligible:
                role = "ego" if actor.is_ego else "traffic"
                if actor.key is None:
                    raise ValueError("eligible actor has no lifetime key")
                # Eligibility and explicit role authorization grant permission;
                # slot lookup only resolves this tick's native batch position.
                self._authorize(snapshot, actor, role)
                slot = snapshot.slot_for(actor.key)
                if slot is None:
                    raise ValueError(
                        f"eligible actor {int(actor.source_id)} has no current active slot"
                    )
                if advances_simulation and actor.key not in decisions:
                    raise ValueError(
                        f"eligible actor {int(actor.source_id)} has no controller intent"
                    )
                controller = self.controllers[role]
                intent = decisions.get(actor.key)
                mode = _INTENT_MODE[type(intent)] if intent is not None else None
                effective_owner = (
                    "warmup_replay"
                    if snapshot.step < 10
                    else f"{role}:{_normalized_controller_name(controller)}"
                )
                declared_controller = _normalized_controller_name(controller)
            else:
                role = "context"
                slot = actor.current_active_slot
                intent = ReplayIntent() if advances_simulation and slot is not None else None
                mode = (
                    NativeMovementMode.EXPERT_REPLAY
                    if advances_simulation and slot is not None
                    else None
                )
                declared_controller = None
                if actor.native_present and actor.source_valid:
                    effective_owner = "context_replay"
                elif slot is not None:
                    effective_owner = "inactive_replay_mode"
                else:
                    effective_owner = "not_present"

            if slot is not None:
                if slot in used_slots:
                    raise ValueError(f"multiple owners assigned to active slot {slot}")
                used_slots.add(slot)
            assignments.append(
                ActorAssignment(
                    source_id=actor.source_id,
                    key=actor.key,
                    binary_index=actor.fixed_binary_index,
                    slot=slot,
                    role=role,
                    declared_controller=declared_controller,
                    effective_owner=effective_owner,
                    pre_step_native_mode=actor.movement_mode,
                    intent=intent,
                    native_mode=mode,
                )
            )

        self._validate_idm_parameter_compatibility(decisions.values())
        plan_parameters = self.idm_parameters
        if plan_parameters is None:
            observed = {
                intent.parameters
                for intent in decisions.values()
                if isinstance(intent, IDMIntent)
            }
            if len(observed) > 1:
                raise ValueError("one episode cannot mix global IDM parameter values")
            plan_parameters = next(iter(observed), None)
        return TickPlan(
            snapshot=snapshot,
            assignments=tuple(assignments),
            idm_parameters=plan_parameters,
            advances_simulation=advances_simulation,
        )

    def advance(self, env, plan: TickPlan):
        """Apply the completed plan through one writer and one native step."""
        return self.writer.apply_and_step(env, plan)

    @staticmethod
    def _eligible_targets(snapshot: StepSnapshot, role: str) -> frozenset[ActorKey]:
        targets = set()
        for actor in snapshot.actors:
            if not actor.controller_eligible:
                continue
            if role == "ego" and actor.is_ego:
                if actor.key is None:
                    raise ValueError("eligible ego has no lifetime key")
                targets.add(actor.key)
            elif role == "traffic" and not actor.is_ego:
                if actor.key is None:
                    raise ValueError("eligible traffic has no lifetime key")
                targets.add(actor.key)
        return frozenset(targets)

    @staticmethod
    def _authorize(snapshot: StepSnapshot, actor, role: str):
        if not actor.controller_eligible:
            raise ValueError(
                f"actor {int(actor.source_id)} is not controller_eligible"
            )
        if role == "ego" and not actor.is_ego:
            raise ValueError("ego controller cannot own a traffic actor")
        if role == "traffic" and actor.is_ego:
            raise ValueError("traffic controller cannot own the ego")
        if role not in ("ego", "traffic"):
            raise ValueError(f"unknown controller role: {role}")

    def _validate_idm_parameter_compatibility(self, intents):
        parameters = {
            intent.parameters for intent in intents if isinstance(intent, IDMIntent)
        }
        if self.idm_parameters is not None and any(
            item != self.idm_parameters for item in parameters
        ):
            raise ValueError("IDM intent conflicts with episode-global IDM parameters")
        if len(parameters) > 1:
            raise ValueError("one episode cannot mix global IDM parameter values")
