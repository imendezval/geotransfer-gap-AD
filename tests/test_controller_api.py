from dataclasses import FrozenInstanceError

import pytest

from geotransfer_gap.planners.controller_api import (
    DynamicsIntent,
    IDMIntent,
    IDMParameters,
    ReplayIntent,
)
from geotransfer_gap.runtime.native_modes import NativeMovementMode


def test_controller_intents_are_typed_and_immutable():
    replay = ReplayIntent()
    idm = IDMIntent(target_velocity=8.0, parameters=IDMParameters())
    dynamics = DynamicsIntent((0.25, -0.5))

    assert replay.kind == "replay"
    assert idm.kind == "idm" and idm.target_velocity == 8.0
    assert dynamics.kind == "dynamics" and dynamics.action == (0.25, -0.5)
    with pytest.raises(FrozenInstanceError):
        idm.target_velocity = 10.0
    with pytest.raises(FrozenInstanceError):
        dynamics.action = (0.0, 0.0)


@pytest.mark.parametrize(
    "values",
    [
        {"min_gap": -1.0},
        {"headway_time": float("nan")},
        {"accel_max": 0.0},
        {"decel_max": float("inf")},
    ],
)
def test_invalid_global_idm_parameters_fail_closed(values):
    with pytest.raises(ValueError):
        IDMParameters(**values)


@pytest.mark.parametrize("target_velocity", [-0.1, float("nan"), float("inf")])
def test_invalid_idm_target_velocity_fails_closed(target_velocity):
    with pytest.raises(ValueError, match="target_velocity"):
        IDMIntent(target_velocity=target_velocity)


@pytest.mark.parametrize("action", [(0.0,), (0.0, 0.0, 0.0), (1.1, 0.0), (float("nan"), 0.0)])
def test_invalid_normalized_action_fails_closed(action):
    with pytest.raises(ValueError):
        DynamicsIntent(action)


def test_native_mode_enum_matches_pinned_drive_values():
    assert int(NativeMovementMode.DYNAMICS) == 0
    assert int(NativeMovementMode.IDM) == 1
    assert int(NativeMovementMode.EXPERT_REPLAY) == 2
