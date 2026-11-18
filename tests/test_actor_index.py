from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from geotransfer_gap.runtime.actor_index import ActorIndex, ActorKey, SourceActorID
from geotransfer_gap.runtime.step_snapshot import RemovalReason


def object_record(
    source_id,
    *,
    valid=(1, 1, 1, 1, 1),
    actor_type=1,
    mark_as_expert=False,
):
    item = {
        "type": actor_type,
        "traj_valid": np.asarray(valid, dtype=np.int32),
        "mark_as_expert": int(mark_as_expert),
    }
    if source_id is not ...:
        item["id"] = source_id
    return item


def native_entity(index, **overrides):
    entity = {
        "valid": 1,
        "x": float(index + 10),
        "y": float(index + 20),
        "z": 0.0,
        "vx": 1.0,
        "vy": 0.0,
        "vz": 0.0,
        "heading": 0.0,
        "removed": False,
        "stopped": False,
        "collision_state": 0,
        "collided_before_goal": False,
        "reached_goal_this_episode": False,
        "movement_mode": 2,
    }
    entity.update(overrides)
    return entity


def scene_index(objects, ego_index=0):
    binary = {"objects": objects, "sdc_track_index": ego_index}
    return binary, ActorIndex(binary)


def capture(index, step, active, entities, observations=None):
    state = {
        "active_agent_indices": list(active),
        "active_agent_count": len(active),
        "entities": entities,
    }
    if observations is None:
        observations = np.arange(max(len(active), 1) * 3, dtype=np.float32).reshape(
            max(len(active), 1), 3
        )
    return index.capture_pre_step(step, state, observations)


def entities_for(count):
    return [native_entity(i) for i in range(count)]


def test_nonzero_ego_uses_source_id_binary_index_and_current_slot():
    objects = [object_record(100 + i) for i in range(6)]
    binary, index = scene_index(objects, ego_index=4)
    snapshot = capture(index, 0, [4, 0, 3, 5], entities_for(len(objects) + 3))

    assert snapshot.ego_id == SourceActorID(104)
    assert snapshot.actor_for(SourceActorID(104)).fixed_binary_index == 4
    assert snapshot.slot_for(ActorKey(SourceActorID(104), 0)) == 0
    assert snapshot.slot_for(SourceActorID(100)) == 1
    assert snapshot.slot_for(SourceActorID(101)) is None
    assert snapshot.eligible_present_vehicle_ids == frozenset(
        {SourceActorID(100), SourceActorID(103), SourceActorID(105)}
    )


@pytest.mark.parametrize(
    "objects",
    [
        [object_record(...), object_record(2)],
        [object_record(1), object_record(1)],
    ],
    ids=["missing-id", "duplicate-id"],
)
def test_missing_or_duplicate_source_ids_fail_closed(objects):
    with pytest.raises(ValueError, match="source actor ID"):
        ActorIndex({"objects": objects, "sdc_track_index": 0})


def test_late_birth_starts_first_lifetime_only_when_source_becomes_valid():
    objects = [object_record(10), object_record(20, valid=(0, 0, 1, 1, 1))]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1], entities_for(2))
    assert first.actor_for(SourceActorID(20)).source_valid is False
    assert first.actor_for(SourceActorID(20)).key is None
    assert first.slot_for(SourceActorID(20)) is None

    entities = entities_for(2)
    second = capture(index, 1, [0, 1], entities)
    assert second.actor_for(SourceActorID(20)).key is None
    birth_entities = entities_for(2)
    birth_entities[1].update(valid=0, x=-10000.0, y=-10000.0)
    third = capture(index, 2, [0, 1], birth_entities)
    actor = third.actor_for(SourceActorID(20))
    assert actor.key == ActorKey(SourceActorID(20), 0)
    assert not actor.controller_eligible
    assert third.slot_for(actor.key) is None

    fourth = capture(index, 3, [0, 1], entities_for(2))
    actor = fourth.actor_for(SourceActorID(20))
    assert actor.controller_eligible
    assert fourth.slot_for(actor.key) == 1


def test_source_gap_retirement_is_temporary_and_reentry_increments_generation():
    objects = [object_record(10), object_record(20, valid=(1, 1, 0, 1, 1))]
    _, index = scene_index(objects)
    active = [0, 1]
    first = capture(index, 0, active, entities_for(2))
    prior_key = first.actor_for(SourceActorID(20)).key
    assert prior_key == ActorKey(SourceActorID(20), 0)
    capture(index, 1, active, entities_for(2))

    gap_entities = entities_for(2)
    gap_entities[1].update(
        valid=0,
        x=-10000.0,
        y=-10000.0,
        removed=True,
    )
    gap = capture(index, 2, active, gap_entities)
    gap_actor = gap.actor_for(SourceActorID(20))
    assert gap_actor.key == prior_key
    assert gap_actor.source_valid is False
    assert gap_actor.removal_reason is RemovalReason.SOURCE_GAP
    assert not gap_actor.permanently_removed
    assert gap.slot_for(prior_key) is None

    returned_entities = entities_for(2)
    returned_entities[1].update(
        valid=0,
        x=-10000.0,
        y=-10000.0,
        removed=True,
    )
    returned = capture(index, 3, active, returned_entities)
    actor = returned.actor_for(SourceActorID(20))
    assert actor.key == ActorKey(SourceActorID(20), 1)
    assert returned.slot_for(prior_key) is None
    assert not actor.controller_eligible
    assert returned.slot_for(actor.key) is None

    resumed = capture(index, 4, active, entities_for(2))
    actor = resumed.actor_for(SourceActorID(20))
    assert actor.key == ActorKey(SourceActorID(20), 1)
    assert actor.controller_eligible
    assert resumed.slot_for(actor.key) == 1


def test_source_gap_return_already_present_on_first_valid_pre_step_is_eligible():
    objects = [object_record(10), object_record(20, valid=(1, 0, 1, 1))]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1], entities_for(2))
    old_key = first.actor_for(SourceActorID(20)).key

    gap_entities = entities_for(2)
    gap_entities[1].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    capture(index, 1, [0, 1], gap_entities)

    # The corrected C runtime may spawn during the step immediately before
    # this first source-valid pre-step, so the native actor can already exist.
    returned = capture(index, 2, [0, 1], entities_for(2))
    actor = returned.actor_for(SourceActorID(20))
    assert actor.key == ActorKey(SourceActorID(20), 1)
    assert actor.source_valid and actor.native_present
    assert actor.controller_eligible
    assert returned.slot_for(actor.key) == 1
    assert returned.slot_for(old_key) is None


def test_stale_actor_key_is_rejected_by_actor_and_slot_lookup():
    objects = [object_record(10), object_record(20, valid=(1, 0, 1, 1))]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1], entities_for(2))
    stale_key = first.actor_for(SourceActorID(20)).key

    gap_entities = entities_for(2)
    gap_entities[1].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    capture(index, 1, [0, 1], gap_entities)
    returned = capture(index, 2, [0, 1], entities_for(2))

    assert returned.actor_for(SourceActorID(20)).key == ActorKey(
        SourceActorID(20), 1
    )
    with pytest.raises(KeyError, match="stale ActorKey"):
        returned.actor_for(stale_key)
    assert returned.slot_for(stale_key) is None


def test_active_batch_slot_absence_is_not_a_physical_lifetime_boundary():
    objects = [object_record(10), object_record(20), object_record(30)]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1, 2], entities_for(3))
    key = first.actor_for(SourceActorID(20)).key

    absent = capture(index, 1, [0, 2], entities_for(3))
    actor = absent.actor_for(SourceActorID(20))
    assert actor.current_active_slot is None
    assert actor.source_valid and actor.native_present
    assert actor.key == key
    assert not actor.controller_eligible
    assert absent.slot_for(key) is None

    restored = capture(index, 2, [2, 1, 0], entities_for(3))
    actor = restored.actor_for(SourceActorID(20))
    assert actor.current_active_slot == 1
    assert actor.key == key
    assert actor.controller_eligible


def test_physics_removal_is_permanent_even_if_native_state_later_looks_present():
    objects = [object_record(10), object_record(20)]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1], entities_for(2))
    actor_key = first.actor_for(SourceActorID(20)).key

    collided = entities_for(2)
    collided[1].update(
        valid=0,
        x=-10000.0,
        y=-10000.0,
        removed=True,
        collision_state=1,
        collided_before_goal=True,
    )
    after_collision = capture(index, 1, [0], collided)
    actor = after_collision.actor_for(SourceActorID(20))
    assert actor.removal_reason is RemovalReason.COLLISION
    assert actor.permanently_removed
    assert actor.current_active_slot is None
    assert after_collision.slot_for(actor_key) is None

    apparent_return = entities_for(2)
    returned = capture(index, 2, [0, 1], apparent_return)
    actor = returned.actor_for(SourceActorID(20))
    assert actor.key == actor_key
    assert actor.removal_reason is RemovalReason.COLLISION
    assert actor.permanently_removed
    assert not actor.controller_eligible
    assert returned.slot_for(actor_key) is None


def test_removed_without_collision_is_not_permanent_during_source_gap():
    objects = [object_record(10), object_record(20, valid=(1, 0, 1, 1, 1))]
    _, index = scene_index(objects)
    capture(index, 0, [0, 1], entities_for(2))
    retired = entities_for(2)
    retired[1].update(valid=0, x=-10000.0, y=-10000.0, removed=True)

    snapshot = capture(index, 1, [0, 1], retired)
    actor = snapshot.actor_for(SourceActorID(20))
    assert actor.removal_reason is RemovalReason.SOURCE_GAP
    assert not actor.permanently_removed


def test_same_length_slot_swap_recomputes_mapping_without_changing_identity():
    objects = [object_record(10 + i) for i in range(3)]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1, 2], entities_for(3))
    second = capture(index, 1, [1, 0, 2], entities_for(3))

    key = ActorKey(SourceActorID(10), 0)
    assert first.slot_for(key) == 0
    assert second.slot_for(key) == 1
    assert second.actor_for(SourceActorID(10)).fixed_binary_index == 0
    assert second.actor_for(SourceActorID(10)).lifetime_generation == 0


def test_active_count_change_removes_and_restores_current_slot_only():
    objects = [object_record(10 + i) for i in range(3)]
    _, index = scene_index(objects)
    first = capture(index, 0, [0, 1, 2], entities_for(3))
    key = first.actor_for(SourceActorID(11)).key
    fewer = capture(index, 1, [0, 2], entities_for(3))
    assert fewer.actor_for(SourceActorID(11)).current_active_slot is None
    assert not fewer.actor_for(SourceActorID(11)).controller_eligible
    assert fewer.slot_for(key) is None

    restored = capture(index, 2, [2, 1, 0], entities_for(3))
    assert restored.slot_for(key) == 1
    assert restored.actor_for(SourceActorID(11)).lifetime_generation == 0


def test_disappearance_after_collision_closes_control_and_reports_reason():
    objects = [object_record(10), object_record(20)]
    _, index = scene_index(objects)
    capture(index, 0, [0, 1], entities_for(2))
    entities = entities_for(2)
    entities[1].update(
        x=-10000.0,
        y=-10000.0,
        removed=True,
        collision_state=1,
        collided_before_goal=True,
    )
    snapshot = capture(index, 1, [0], entities)
    actor = snapshot.actor_for(SourceActorID(20))
    assert not actor.native_present
    assert actor.removal_reason is RemovalReason.COLLISION
    assert SourceActorID(20) not in snapshot.eligible_present_vehicle_ids
    assert snapshot.slot_for(actor.key) is None


def test_episode_reset_restarts_generation_and_removal_state():
    objects = [object_record(10), object_record(20, valid=(1, 0, 1, 1, 1))]
    _, index = scene_index(objects)
    capture(index, 0, [0, 1], entities_for(2))
    gap_entities = entities_for(2)
    gap_entities[1].update(valid=0, x=-10000.0, y=-10000.0, removed=True)
    capture(index, 1, [0, 1], gap_entities)
    second_lifetime = capture(index, 2, [0, 1], entities_for(2))
    assert second_lifetime.actor_for(SourceActorID(20)).lifetime_generation == 1

    collision = entities_for(2)
    collision[1].update(removed=True, collision_state=1, collided_before_goal=True)
    terminated = capture(index, 3, [0, 1], collision)
    assert terminated.actor_for(SourceActorID(20)).permanently_removed

    for _ in range(3):
        index.reset_episode()
        reset = capture(index, 0, [0, 1], entities_for(2))
        assert reset.actor_for(SourceActorID(20)).key == ActorKey(SourceActorID(20), 0)
        assert not reset.actor_for(SourceActorID(20)).permanently_removed


def test_parked_and_vru_actors_remain_context_not_controller_targets():
    objects = [
        object_record(10),
        object_record(20, mark_as_expert=True),
        object_record(30, actor_type=2),
        object_record(40, actor_type=3),
    ]
    _, index = scene_index(objects)
    snapshot = capture(index, 0, [0], entities_for(4))

    assert snapshot.eligible_present_vehicle_ids == frozenset()
    assert snapshot.actor_for(SourceActorID(10)).controller_eligible
    assert snapshot.replayed_context_ids == frozenset(
        {SourceActorID(20), SourceActorID(30), SourceActorID(40)}
    )
    assert snapshot.actor_for(SourceActorID(20)).current_active_slot is None
    assert not snapshot.actor_for(SourceActorID(20)).controller_eligible


def test_context_presence_is_separate_from_current_replay_ownership():
    objects = [
        object_record(10),
        object_record(20),
        object_record(30, mark_as_expert=True),
        object_record(40, actor_type=2),
    ]
    _, index = scene_index(objects)
    entities = entities_for(4)
    entities[1]["movement_mode"] = 1
    entities[2]["movement_mode"] = 2
    entities[3]["movement_mode"] = 2
    snapshot = capture(index, 0, [0, 2, 3], entities)

    assert snapshot.visible_context_ids == frozenset(
        {SourceActorID(20), SourceActorID(30), SourceActorID(40)}
    )
    assert snapshot.replayed_context_ids == frozenset(
        {SourceActorID(30), SourceActorID(40)}
    )
    # Source/native visibility does not imply a row in the PPO batch.
    assert snapshot.actor_for(SourceActorID(20)).current_active_slot is None


@pytest.mark.parametrize(
    "missing_field",
    [
        "active_agent_count",
        "valid",
        "removed",
        "stopped",
        "collision_state",
        "collided_before_goal",
        "reached_goal_this_episode",
        "movement_mode",
    ],
)
def test_missing_native_lifecycle_fields_fail_closed(missing_field):
    objects = [object_record(10), object_record(20)]
    _, index = scene_index(objects)
    entities = entities_for(2)
    state = {
        "active_agent_indices": [0, 1],
        "active_agent_count": 2,
        "entities": entities,
    }
    if missing_field == "active_agent_count":
        state.pop(missing_field)
    else:
        entities[1].pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        index.capture_pre_step(0, state, np.zeros((2, 3), dtype=np.float32))


def test_duplicate_or_out_of_range_active_indices_fail_closed():
    objects = [object_record(10), object_record(20)]
    _, index = scene_index(objects)
    with pytest.raises(ValueError, match="duplicate active"):
        capture(index, 0, [0, 0], entities_for(2))

    _, index = scene_index(objects)
    with pytest.raises(ValueError, match="active entity index"):
        capture(index, 0, [0, 2], entities_for(2))


def test_snapshot_copies_and_freezes_observation_and_native_state():
    objects = [object_record(10), object_record(20)]
    _, index = scene_index(objects)
    active = [0, 1]
    entities = entities_for(2)
    observations = np.arange(6, dtype=np.float32).reshape(2, 3)
    snapshot = capture(index, 0, active, entities, observations)
    expected = observations.copy()

    observations[:] = -1
    active[1] = 0
    entities[1]["x"] = 999.0

    np.testing.assert_array_equal(snapshot.observation, expected)
    assert snapshot.observation.flags.writeable is False
    with pytest.raises(ValueError):
        snapshot.observation[0, 0] = 99
    with pytest.raises(ValueError):
        snapshot.observation.setflags(write=True)
    assert snapshot.active_agent_indices == (0, 1)
    assert snapshot.actor_for(SourceActorID(20)).x == 11.0
    with pytest.raises(FrozenInstanceError):
        snapshot.step = 7
