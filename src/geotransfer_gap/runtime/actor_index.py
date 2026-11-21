"""Stable source identity and per-tick identity-to-native-slot resolution."""

from dataclasses import dataclass
from numbers import Integral
from types import MappingProxyType
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .step_snapshot import StepSnapshot


_REQUIRED_NATIVE_STATE_FIELDS = (
    "x",
    "y",
    "z",
    "vx",
    "vy",
    "heading",
    "valid",
    "removed",
    "stopped",
    "collision_state",
    "collided_before_goal",
    "reached_goal_this_episode",
    "movement_mode",
)


@dataclass(frozen=True, order=True)
class SourceActorID:
    """Stable source track ID; never a native batch position."""

    value: int

    def __post_init__(self):
        if isinstance(self.value, bool) or not isinstance(self.value, Integral):
            raise ValueError("source actor ID must be an integer")
        object.__setattr__(self, "value", int(self.value))

    def __int__(self):
        return self.value


@dataclass(frozen=True, order=True)
class ActorKey:
    """One contiguous source-valid lifetime of a source actor."""

    source_id: SourceActorID
    lifetime_generation: int

    def __post_init__(self):
        if not isinstance(self.source_id, SourceActorID):
            raise TypeError("ActorKey.source_id must be a SourceActorID")
        if (
            isinstance(self.lifetime_generation, bool)
            or not isinstance(self.lifetime_generation, Integral)
            or self.lifetime_generation < 0
        ):
            raise ValueError("lifetime generation must be a nonnegative integer")
        object.__setattr__(self, "lifetime_generation", int(self.lifetime_generation))


class ActorIndex:
    """Maps stable source IDs to fixed binary indices and tracks lifetimes.

    Active slots are sampled anew for each pre-step snapshot. Consumers resolve
    a current slot through ``StepSnapshot.slot_for``; this class never retains a
    batch slot as actor identity.
    """

    VEHICLE_TYPE = 1

    def __init__(self, binary_scene):
        if not isinstance(binary_scene, dict):
            raise ValueError("binary scene must be a mapping")
        objects = binary_scene.get("objects")
        if not isinstance(objects, (list, tuple)) or not objects:
            raise ValueError("binary scene must contain source objects")

        source_ids = []
        binary_index_by_source_id = {}
        valid_by_source_id = {}
        type_by_source_id = {}
        expert_by_source_id = {}
        for binary_index, obj in enumerate(objects):
            if not isinstance(obj, dict) or "id" not in obj or obj["id"] is None:
                raise ValueError(f"source actor ID missing at binary index {binary_index}")
            source_id = SourceActorID(obj["id"])
            if source_id in binary_index_by_source_id:
                raise ValueError(f"duplicate source actor ID: {int(source_id)}")

            validity = np.asarray(obj.get("traj_valid"))
            if validity.ndim != 1 or validity.size == 0:
                raise ValueError(
                    f"source-valid mask missing or invalid for source actor ID {int(source_id)}"
                )
            if validity.dtype.kind not in "biu":
                raise ValueError(
                    f"source-valid mask must be boolean or integer for source actor ID {int(source_id)}"
                )
            if np.any((validity != 0) & (validity != 1)):
                raise ValueError(
                    f"source-valid mask values must be 0 or 1 for source actor ID {int(source_id)}"
                )

            try:
                raw_type = obj["type"]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"source actor type missing or invalid for source actor ID {int(source_id)}"
                ) from exc
            if isinstance(raw_type, bool) or not isinstance(raw_type, Integral):
                raise ValueError(
                    f"source actor type must be an integer for source actor ID {int(source_id)}"
                )
            actor_type = int(raw_type)

            source_ids.append(source_id)
            binary_index_by_source_id[source_id] = binary_index
            valid_by_source_id[source_id] = tuple(bool(value) for value in validity)
            type_by_source_id[source_id] = actor_type
            expert_by_source_id[source_id] = bool(obj.get("mark_as_expert", False))

        ego_index = binary_scene.get("sdc_track_index")
        if (
            isinstance(ego_index, bool)
            or not isinstance(ego_index, Integral)
            or not 0 <= int(ego_index) < len(source_ids)
        ):
            raise ValueError("ego binary index is missing or out of range")

        self._source_ids = tuple(source_ids)
        self._binary_index_by_source_id = MappingProxyType(binary_index_by_source_id)
        self._valid_by_source_id = valid_by_source_id
        self._type_by_source_id = type_by_source_id
        self._expert_by_source_id = expert_by_source_id
        self._ego_id = self._source_ids[int(ego_index)]
        self.reset_episode()

    @property
    def ego_id(self) -> SourceActorID:
        return self._ego_id

    @property
    def source_id_to_binary_index(self):
        """Read-only static source-ID to binary-index mapping."""
        return self._binary_index_by_source_id

    def binary_index_for(self, source_id: SourceActorID | int) -> int:
        source_id = self._coerce_source_id(source_id)
        try:
            return self._binary_index_by_source_id[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source actor ID: {int(source_id)}") from exc

    def reset_episode(self):
        """Reset lifetime generations and removal state for a fresh episode."""
        self._generation = {source_id: -1 for source_id in self._source_ids}
        self._lifetime_open = {source_id: False for source_id in self._source_ids}
        self._permanent_removal = {source_id: None for source_id in self._source_ids}
        self._source_gap_pending = {source_id: False for source_id in self._source_ids}
        self._last_step = -1

    def capture_pre_step(self, step: int, state, observations) -> "StepSnapshot":
        """Capture identity, lifecycle and copied observations before ``env.step``."""
        from .step_snapshot import ActorSnapshot, RemovalReason, StepSnapshot

        if isinstance(step, bool) or not isinstance(step, Integral) or step < 0:
            raise ValueError("snapshot step must be a nonnegative integer")
        step = int(step)
        if step != self._last_step + 1:
            raise ValueError(
                f"pre-step snapshots must be contiguous from zero; expected {self._last_step + 1}, got {step}"
            )
        if not isinstance(state, dict):
            raise ValueError("native state must be a mapping")

        entities = state.get("entities")
        if not isinstance(entities, (list, tuple)) or len(entities) < len(self._source_ids):
            raise ValueError("native state has fewer entities than source binary objects")

        if "active_agent_indices" not in state:
            raise ValueError("native state is missing active_agent_indices")
        if "active_agent_count" not in state:
            raise ValueError("native state is missing active_agent_count")
        raw_active = state["active_agent_indices"]
        if raw_active is None:
            raw_active = ()
        active_values = tuple(raw_active)
        if any(
            isinstance(index, bool) or not isinstance(index, Integral)
            for index in active_values
        ):
            raise ValueError("active entity indices must be integers")
        active_indices = tuple(int(index) for index in active_values)
        active_count = state["active_agent_count"]
        if (
            isinstance(active_count, bool)
            or not isinstance(active_count, Integral)
            or int(active_count) != len(active_indices)
        ):
            raise ValueError("active_agent_count does not match active_agent_indices")
        if len(set(active_indices)) != len(active_indices):
            raise ValueError("duplicate active entity indices")
        if any(index < 0 or index >= len(self._source_ids) for index in active_indices):
            raise ValueError("active entity index is outside the source object range")

        observation = np.asarray(observations)
        if observation.ndim != 2 or observation.dtype.kind not in "biuf":
            raise ValueError("BB observations must be a two-dimensional numeric buffer")
        if observation.shape[0] != len(active_indices):
            raise ValueError("BB observation rows must match current active agent slots")

        # This is the only per-snapshot active-index-to-slot construction. The
        # public ID-to-slot lookup lives on StepSnapshot and is shared by every role.
        active_slot_by_binary_index = {
            binary_index: slot for slot, binary_index in enumerate(active_indices)
        }
        generation = self._generation.copy()
        lifetime_open = self._lifetime_open.copy()
        permanent_removal = self._permanent_removal.copy()
        source_gap_pending = self._source_gap_pending.copy()

        actors = []
        for binary_index, source_id in enumerate(self._source_ids):
            entity = entities[binary_index]
            if not isinstance(entity, dict):
                raise ValueError(f"native entity {binary_index} is not a mapping")
            validity = self._valid_by_source_id[source_id]
            if step >= len(validity):
                raise ValueError(
                    f"snapshot step {step} exceeds source-valid mask for source actor ID {int(source_id)}"
                )

            source_valid = validity[step]
            missing_fields = tuple(
                key for key in _REQUIRED_NATIVE_STATE_FIELDS if key not in entity
            )
            if missing_fields:
                raise ValueError(
                    f"native entity {binary_index} is missing required state fields: "
                    f"{', '.join(missing_fields)}"
                )
            try:
                x = float(entity["x"])
                y = float(entity["y"])
                z = float(entity["z"])
                vx = float(entity["vx"])
                vy = float(entity["vy"])
                heading = float(entity["heading"])
                native_valid = bool(entity["valid"])
                removed = bool(entity["removed"])
                stopped = bool(entity["stopped"])
                collision_state = int(entity["collision_state"])
                collided_before_goal = bool(entity["collided_before_goal"])
                reached_goal = bool(entity["reached_goal_this_episode"])
                movement_mode = int(entity["movement_mode"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"native entity {binary_index} lacks valid state fields") from exc

            native_present = (
                native_valid
                and not removed
                and x != -10000.0
                and y != -10000.0
            )
            collision_reason = None
            # Native Drive sets the history flag for off-road events too.
            if collision_state == 2:
                collision_reason = RemovalReason.OFFROAD
            elif collision_state == 1 or collided_before_goal:
                collision_reason = RemovalReason.COLLISION

            if collision_reason is not None:
                permanent_removal[source_id] = collision_reason
                source_gap_pending[source_id] = False
            elif not source_valid:
                source_gap_pending[source_id] = True
            elif source_gap_pending[source_id]:
                # A source-gap retirement can leave removed=True after source
                # validity resumes. That is not a physics removal. The native
                # C step may already have spawned it before this pre-step.
                if native_present:
                    source_gap_pending[source_id] = False
            elif removed:
                permanent_removal[source_id] = RemovalReason.NATIVE_REMOVED

            if source_valid and permanent_removal[source_id] is None:
                if generation[source_id] < 0:
                    generation[source_id] = 0
                    lifetime_open[source_id] = True
                elif not lifetime_open[source_id]:
                    generation[source_id] += 1
                    lifetime_open[source_id] = True
            elif source_valid and generation[source_id] < 0:
                generation[source_id] = 0
                lifetime_open[source_id] = False
            if not source_valid or permanent_removal[source_id] is not None:
                lifetime_open[source_id] = False

            if permanent_removal[source_id] is not None:
                removal_reason = permanent_removal[source_id]
            elif not source_valid or source_gap_pending[source_id]:
                removal_reason = RemovalReason.SOURCE_GAP
            else:
                removal_reason = RemovalReason.NONE

            lifetime_generation = (
                generation[source_id] if generation[source_id] >= 0 else None
            )
            actor_key = (
                ActorKey(source_id, lifetime_generation)
                if lifetime_generation is not None
                else None
            )
            current_slot = active_slot_by_binary_index.get(binary_index)
            is_ego = source_id == self._ego_id
            controller_eligible = (
                self._type_by_source_id[source_id] == self.VEHICLE_TYPE
                and not self._expert_by_source_id[source_id]
                and source_valid
                and native_present
                and current_slot is not None
                and permanent_removal[source_id] is None
                and not source_gap_pending[source_id]
            )
            actors.append(
                ActorSnapshot(
                    source_id=source_id,
                    fixed_binary_index=binary_index,
                    actor_type=self._type_by_source_id[source_id],
                    marked_expert=self._expert_by_source_id[source_id],
                    is_ego=is_ego,
                    source_valid=source_valid,
                    native_present=native_present,
                    current_active_slot=current_slot,
                    controller_eligible=controller_eligible,
                    lifetime_generation=lifetime_generation,
                    key=actor_key,
                    permanently_removed=permanent_removal[source_id] is not None,
                    source_gap_pending=source_gap_pending[source_id],
                    removal_reason=removal_reason,
                    removed=removed,
                    stopped=stopped,
                    collision_state=collision_state,
                    collided_before_goal=collided_before_goal,
                    reached_goal=reached_goal,
                    movement_mode=movement_mode,
                    x=x,
                    y=y,
                    z=z,
                    vx=vx,
                    vy=vy,
                    heading=heading,
                )
            )

        snapshot = StepSnapshot(
            step=step,
            observation=observation,
            active_agent_indices=active_indices,
            actors=tuple(actors),
            ego_id=self._ego_id,
        )
        self._generation = generation
        self._lifetime_open = lifetime_open
        self._permanent_removal = permanent_removal
        self._source_gap_pending = source_gap_pending
        self._last_step = step
        return snapshot

    @staticmethod
    def _coerce_source_id(source_id) -> SourceActorID:
        return source_id if isinstance(source_id, SourceActorID) else SourceActorID(source_id)
