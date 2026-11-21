"""Compatibility checks using the pinned local upstream model."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from geotransfer_gap.config import settings


@pytest.fixture(scope="module")
def checkpoint():
    path = settings().bench / "weights/simple_ppo.pt"
    if not path.is_file():
        pytest.skip("local BehaviorBench PPO checkpoint unavailable")
    return torch.load(path, map_location="cpu", weights_only=True)


@pytest.fixture(scope="module")
def policy(checkpoint):
    from geotransfer_gap.planners.ppo_policy import build_policy

    old_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        yield build_policy(checkpoint)
    finally:
        torch.set_num_threads(old_threads)


@pytest.mark.parametrize("defect,match", [
    ("missing", "Missing key"),
    ("unexpected", "Unexpected key"),
    ("shape", "size mismatch"),
    ("duplicate", "duplicate"),
    ("alias", "alias"),
])
def test_invalid_checkpoint(checkpoint, policy, defect, match):
    from geotransfer_gap.planners.ppo_policy import load_model_state

    state = dict(checkpoint)
    key = "lstm.weight_ih_l0"
    if defect == "missing":
        del state[key]
    elif defect == "unexpected":
        state["learned.extra"] = torch.ones(1)
    elif defect == "shape":
        state["policy.actor.weight"] = state["policy.actor.weight"][:90]
    elif defect == "duplicate":
        state["module." + key] = state[key]
    else:
        state["cell.weight_ih"] = state[key] + 1
    with pytest.raises((ValueError, RuntimeError), match=match):
        load_model_state(policy, state)


def test_documented_prefix_and_metadata(checkpoint, policy):
    from geotransfer_gap.planners.ppo_policy import load_model_state

    load_model_state(policy, {
        "model_state_dict": {"module." + k: v for k, v in checkpoint.items()},
        "epoch": 2,
        "optimizer_state_dict": {},
    })
    assert all(torch.equal(v, policy.state_dict()[k]) for k, v in checkpoint.items())


@pytest.mark.parametrize("row,match", [
    (np.zeros(1150, dtype=np.float32), "1151"),
    (np.full(1151, np.nan, dtype=np.float32), "finite"),
])
def test_bad_observation(row, match):
    from geotransfer_gap.planners.ppo_policy import observation_tensor

    with pytest.raises(ValueError, match=match):
        observation_tensor(row)


@pytest.mark.parametrize("override", [
    {"dynamics_model": "jerk"},
    {"reward_conditioning": True},
    {"single_action_space": None},
    {"max_partner_objects": 30},
])
def test_incompatible_native_space(override):
    from geotransfer_gap.planners.ppo_policy import policy_space, validate_native_env

    env = policy_space(continuous=True)
    vars(env).update(override)
    with pytest.raises(ValueError, match="PPO native"):
        validate_native_env(env)
