from dataclasses import FrozenInstanceError

import pytest

from geotransfer_gap.planners.controller_api import IDMIntent, ReplayIntent
from geotransfer_gap.planners.expert_controller import ExpertController
from geotransfer_gap.planners.idm_controller import IDMController
from geotransfer_gap.runtime.actor_index import ActorKey, SourceActorID


@pytest.mark.parametrize("role", ["ego", "traffic"])
def test_expert_adapter_returns_replay_intents_without_environment_side_effects(role):
    controller = ExpertController(role)
    keys = frozenset(
        {ActorKey(SourceActorID(101), 0), ActorKey(SourceActorID(202), 3)}
    )

    controller.reset({"episode": 1})
    controller.observe(object(), keys)
    intents = controller.act(object(), keys)
    controller.retire(next(iter(keys)), "source_gap")

    assert controller.name == "expert"
    assert set(intents) == keys
    assert all(isinstance(intent, ReplayIntent) for intent in intents.values())
    assert not hasattr(controller, "env")


@pytest.mark.parametrize("role", ["ego", "traffic"])
def test_idm_adapter_returns_native_intents_without_environment_side_effects(role):
    controller = IDMController(role, target_velocity=8.5)
    keys = frozenset(
        {ActorKey(SourceActorID(7), 0), ActorKey(SourceActorID(8), 1)}
    )
    controller.reset({"episode": 1})
    controller.observe(object(), keys)
    intents = controller.act(object(), keys)
    controller.retire(next(iter(keys)), "collision")

    assert controller.name == "idm"
    assert set(intents) == keys
    assert all(isinstance(intent, IDMIntent) for intent in intents.values())
    assert {intent.target_velocity for intent in intents.values()} == {8.5}
    assert not hasattr(controller, "env")


def test_controller_configuration_is_immutable_and_non_mutating():
    controller = IDMController("traffic")
    with pytest.raises(FrozenInstanceError):
        controller.target_velocity = 20.0
    with pytest.raises(FrozenInstanceError):
        controller.parameters = object()
    assert controller.act(object(), frozenset()) == {}
