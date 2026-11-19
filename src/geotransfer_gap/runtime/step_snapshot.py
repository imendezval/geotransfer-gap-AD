"""Immutable pre-step observation, identity and native lifecycle state."""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

import numpy as np

from .actor_index import ActorKey, SourceActorID
from .native_modes import NativeMovementMode


class RemovalReason(str, Enum):
    NONE = "none"
    SOURCE_GAP = "source_gap"
    COLLISION = "collision"
    OFFROAD = "offroad"
    NATIVE_REMOVED = "native_removed"


@dataclass(frozen=True)
class ActorSnapshot:
    """Copied source identity and native state for one binary actor.

    ``lifetime_generation`` identifies a contiguous source-valid lifetime.
    ``current_active_slot`` is only this tick's PPO observation-batch slot;
    its absence does not close a lifetime or advance the generation.
    """

    source_id: SourceActorID
    fixed_binary_index: int
    actor_type: int
    marked_expert: bool
    is_ego: bool
    source_valid: bool
    native_present: bool
    current_active_slot: int | None
    controller_eligible: bool
    lifetime_generation: int | None
    key: ActorKey | None
    permanently_removed: bool
    source_gap_pending: bool
    removal_reason: RemovalReason
    removed: bool
    stopped: bool
    collision_state: int
    collided_before_goal: bool
    reached_goal: bool
    movement_mode: int
    x: float
    y: float
    z: float
    vx: float
    vy: float
    heading: float

    @property
    def source_valid_presence(self) -> bool:
        return self.source_valid

    @property
    def replay_owned(self) -> bool:
        """Whether native state currently assigns this actor to expert replay."""
        return self.movement_mode == NativeMovementMode.EXPERT_REPLAY


@dataclass(frozen=True)
class StepSnapshot:
    """One immutable pre-action frame with its current native slot mapping.

    The observation buffer is backed by immutable ``bytes`` after copying, so
    neither later C writes nor callers can mutate this captured frame.
    """

    step: int
    observation: np.ndarray
    active_agent_indices: tuple[int, ...]
    actors: tuple[ActorSnapshot, ...]
    ego_id: SourceActorID
    _actors_by_source_id: Mapping[SourceActorID, ActorSnapshot] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self):
        if self.step < 0:
            raise ValueError("snapshot step must be nonnegative")
        observation = np.asarray(self.observation)
        if observation.ndim != 2 or observation.dtype.kind not in "biuf":
            raise ValueError("snapshot observation must be a two-dimensional numeric array")
        if observation.shape[0] != len(self.active_agent_indices):
            raise ValueError("snapshot observation rows must match active agent slots")
        if len(set(self.active_agent_indices)) != len(self.active_agent_indices):
            raise ValueError("snapshot active agent indices must be unique")

        copied_bytes = np.ascontiguousarray(observation).tobytes(order="C")
        frozen_observation = np.frombuffer(copied_bytes, dtype=observation.dtype).reshape(
            observation.shape
        )
        object.__setattr__(self, "observation", frozen_observation)
        object.__setattr__(self, "active_agent_indices", tuple(self.active_agent_indices))
        object.__setattr__(self, "actors", tuple(self.actors))

        actors_by_source_id = {}
        fixed_indices = set()
        for actor in self.actors:
            if actor.source_id in actors_by_source_id:
                raise ValueError(f"duplicate source actor ID in snapshot: {int(actor.source_id)}")
            if actor.fixed_binary_index in fixed_indices:
                raise ValueError("duplicate fixed binary index in snapshot")
            actors_by_source_id[actor.source_id] = actor
            fixed_indices.add(actor.fixed_binary_index)
        if self.ego_id not in actors_by_source_id:
            raise ValueError("snapshot ego ID is absent from actor records")
        object.__setattr__(
            self, "_actors_by_source_id", MappingProxyType(actors_by_source_id)
        )

    @property
    def eligible_present_vehicle_ids(self) -> frozenset[SourceActorID]:
        """Current eligible traffic vehicles, excluding the ego by construction."""
        return frozenset(
            actor.source_id
            for actor in self.actors
            if actor.controller_eligible and not actor.is_ego
        )

    @property
    def visible_context_ids(self) -> frozenset[SourceActorID]:
        """Source-valid, native-present non-ego context, independent of batch slots."""
        return frozenset(
            actor.source_id
            for actor in self.actors
            if actor.source_valid
            and actor.native_present
            and not actor.is_ego
        )

    @property
    def replayed_context_ids(self) -> frozenset[SourceActorID]:
        """Visible context actors currently owned by expert replay."""
        visible = self.visible_context_ids
        return frozenset(
            actor.source_id
            for actor in self.actors
            if actor.source_id in visible and actor.replay_owned
        )

    def actor_for(self, source_id: SourceActorID | ActorKey | int) -> ActorSnapshot:
        requested_key = source_id if isinstance(source_id, ActorKey) else None
        if requested_key is not None:
            source_id = requested_key.source_id
        elif not isinstance(source_id, SourceActorID):
            source_id = SourceActorID(source_id)
        try:
            actor = self._actors_by_source_id[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source actor ID: {int(source_id)}") from exc
        if requested_key is not None and actor.key != requested_key:
            raise KeyError(
                f"stale ActorKey for source actor ID {int(source_id)}: "
                f"requested generation {requested_key.lifetime_generation}, "
                f"current generation {actor.lifetime_generation}"
            )
        return actor

    def slot_for(self, actor: SourceActorID | ActorKey | int) -> int | None:
        """Resolve the current slot for one present lifetime, never a past slot."""
        requested_key = actor if isinstance(actor, ActorKey) else None
        if requested_key is not None:
            actor_state = self._actors_by_source_id.get(requested_key.source_id)
            if actor_state is None:
                raise KeyError(
                    f"unknown source actor ID: {int(requested_key.source_id)}"
                )
            if requested_key != actor_state.key:
                return None
        else:
            actor_state = self.actor_for(actor)
        if (
            not actor_state.source_valid
            or not actor_state.native_present
            or actor_state.current_active_slot is None
            or actor_state.permanently_removed
            or actor_state.source_gap_pending
        ):
            return None
        return actor_state.current_active_slot
