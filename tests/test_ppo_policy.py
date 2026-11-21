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


@pytest.mark.parametrize("nonzero", [False, True])
def test_upstream_sequence_parity(monkeypatch, policy, nonzero):
    from unittest.mock import patch

    from geotransfer_gap.planners.ppo_policy import PPOPolicy, policy_space
    from pufferlib.planning.policy import PPOConfig, PPOPlanner

    path = settings().bench / "weights/simple_ppo.pt"
    adapter = PPOPolicy(path)

    # Upstream builds a scratch Drive solely to obtain its model space.
    # Keep the actual PPOPlanner constructor and plan path, with safe weights.
    from types import SimpleNamespace
    space = policy_space()
    space.close = lambda: None
    with patch("pufferlib.ocean.drive.drive.Drive", return_value=space) as scratch:
        reference = PPOPlanner(SimpleNamespace(episode_length=91, split="testing"),
                               0, np.full(2, -1.), np.ones(2), PPOConfig(device="cpu"))
    assert scratch.call_args.kwargs["action_type"] == "discrete"
    reference.policy.load_state_dict(
        torch.load(path, weights_only=True, map_location="cpu"), strict=True
    )
    rng = np.random.default_rng(0)
    rows = rng.normal(size=(12, 1151)).astype(np.float32)
    rows[:, 261::7] = rng.integers(0, 7, size=(12, 128))
    if nonzero:
        h, c = (torch.tensor(rng.normal(size=(1, 256)), dtype=torch.float32)
                for _ in range(2))
    else:
        h = c = torch.zeros((1, 256))
    captured = []
    encode = adapter.model.policy.encode_observations

    def capture(inputs, state=None):
        captured.append(inputs.clone())
        return encode(inputs, state)

    monkeypatch.setattr(adapter.model.policy, "encode_observations", capture)
    outputs = []
    for _ in range(2):
        reference.reset()
        reference.lstm_h, reference.lstm_c = h.clone(), c.clone()
        state = {"lstm_h": h.clone(), "lstm_c": c.clone()}
        actions = []
        for step, row in enumerate(rows):
            expected = reference.plan(step, row)
            action, state, logits, value = adapter.infer(row, state)
            assert torch.equal(captured[-1], reference._obs_buffer), step
            assert torch.equal(logits, reference.last_logits[0]), step
            assert torch.equal(value, reference._last_value_tensor), step
            assert torch.equal(state["lstm_h"], reference.lstm_h), step
            assert torch.equal(state["lstm_c"], reference.lstm_c), step
            np.testing.assert_array_equal(action, expected)
            actions.append(action)
        outputs.append(actions)
    assert outputs[0] == outputs[1]


def test_all_joint_action_indices_against_independent_grid(policy):
    from geotransfer_gap.planners.ppo_policy import PPOPolicy

    adapter = PPOPolicy(settings().bench / "weights/simple_ppo.pt")
    expected = [(a / 4, (s - 6) / 6)
                for a in (-4, -2.67, -1.33, 0, 1.33, 2.67, 4)
                for s in range(13)]
    np.testing.assert_array_equal(
        np.asarray([adapter.decode(i) for i in range(91)], dtype=np.float32),
        np.asarray(expected, dtype=np.float32),
    )
    for invalid in (-1, 91):
        with pytest.raises(ValueError, match="out of range"):
            adapter.decode(invalid)


def test_batch_matches_independent_single_actor_histories(policy, checkpoint):
    from geotransfer_gap.planners.ppo_policy import PPOPolicy

    adapter = PPOPolicy(settings().bench / "weights/simple_ppo.pt")
    rng = np.random.default_rng(0)
    rows = rng.normal(size=(3, 1151)).astype(np.float32)
    rows[:, 261::7] = rng.integers(0, 7, size=(3, 128))
    initial = [
        {name: torch.full((1, 256), float(i) / 10)
         for name in ("lstm_h", "lstm_c")} if i else None
        for i in range(3)
    ]
    expected = [adapter.infer(row, state) for row, state in zip(rows, initial)]
    actions, states, logits, values = adapter.infer_batch(rows, initial)
    for i, (action, state, single_logits, value) in enumerate(expected):
        assert actions[i] == action
        torch.testing.assert_close(logits[i:i+1], single_logits, rtol=0, atol=2e-6)
        torch.testing.assert_close(values[i:i+1], value, rtol=0, atol=2e-6)
        for name in ("lstm_h", "lstm_c"):
            torch.testing.assert_close(states[i][name], state[name], rtol=0, atol=2e-6)
