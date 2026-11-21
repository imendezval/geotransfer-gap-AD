"""CPU inference for the pinned BehaviorBench classic discrete Drive policy."""

from collections.abc import Mapping
from types import SimpleNamespace

import numpy as np
import torch

from geotransfer_gap.config import ensure_bench

OBS_WIDTH = 1151
HIDDEN_SIZE = 256
ACTION_COUNT = 91
_LAYOUT = dict(ego_features=7, max_partner_objects=31, partner_features=8,
               max_road_objects=128, road_features=7)
_FLAGS = dict(dynamics_model="classic", reward_conditioning=False,
              include_global_state=False, emit_jerk_ego_obs=False)


def policy_space(*, continuous=False):
    from gymnasium.spaces import Box, MultiDiscrete

    return SimpleNamespace(
        single_observation_space=Box(-np.inf, np.inf, (OBS_WIDTH,), np.float32),
        single_action_space=(Box(-1, 1, (2,), np.float32) if continuous
                             else MultiDiscrete([ACTION_COUNT])),
        **_LAYOUT, **_FLAGS,
    )


def validate_native_env(env):
    expected = policy_space(continuous=True)
    for name, value in (_LAYOUT | _FLAGS).items():
        if getattr(env, name, None) != value:
            raise ValueError(f"PPO native {name} must be {value!r}")
    obs = env.single_observation_space
    if obs.shape != (OBS_WIDTH,) or obs.dtype != np.float32:
        raise ValueError("PPO native observation space must be float32[1151]")
    if env.single_action_space != expected.single_action_space:
        raise ValueError("PPO native action space must be normalized continuous [2]")


def load_model_state(policy, checkpoint):
    if not isinstance(checkpoint, Mapping):
        raise ValueError("PPO checkpoint must contain a state mapping")
    containers = {"model_state_dict", "state_dict"} & checkpoint.keys()
    if len(containers) > 1:
        raise ValueError("PPO checkpoint has ambiguous state containers")
    # A documented wrapper separates model state from training metadata.
    state = checkpoint[next(iter(containers))] if containers else checkpoint
    if not isinstance(state, Mapping):
        raise ValueError("PPO model state must be a mapping")
    normalized = {}
    for key, value in state.items():
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ValueError("PPO model state must map names to tensors")
        name = key.removeprefix("module.")
        if name in normalized:
            raise ValueError(f"duplicate PPO model key {name}")
        if value.dtype != torch.float32 or not torch.isfinite(value).all():
            raise ValueError(f"PPO model tensor {name} must be finite float32")
        normalized[name] = value
    for suffix in ("weight_ih", "weight_hh", "bias_ih", "bias_hh"):
        cell, lstm = f"cell.{suffix}", f"lstm.{suffix}_l0"
        if cell in normalized and lstm in normalized:
            if not torch.equal(normalized[cell], normalized[lstm]):
                raise ValueError(f"inconsistent PPO recurrent alias {cell}")
    policy.load_state_dict(normalized, strict=True)


def build_policy(checkpoint):
    ensure_bench()
    from pufferlib.models import LSTMWrapper
    from pufferlib.ocean.torch import Drive

    space = policy_space()
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(0)
        policy = LSTMWrapper(
            space, Drive(space, input_size=64, hidden_size=HIDDEN_SIZE),
            input_size=HIDDEN_SIZE, hidden_size=HIDDEN_SIZE,
        )
    load_model_state(policy, checkpoint)
    return policy.eval()


def observation_tensor(row):
    if row.shape != (OBS_WIDTH,):
        raise ValueError("PPO observation must have width 1151")
    tensor = torch.tensor(row, dtype=torch.float32).unsqueeze(0)
    if not torch.isfinite(tensor).all():
        raise ValueError("PPO observation must be finite")
    categories = tensor[:, 7 + 31 * 8 + 6 :: 7]
    if not ((categories == categories.trunc()) & (categories >= 0) & (categories <= 6)).all():
        raise ValueError("PPO road category must be an integer from 0 through 6")
    return tensor


class PPOPolicy:
    def __init__(self, path):
        self.model = build_policy(torch.load(path, weights_only=True, map_location="cpu"))
        from pufferlib.planning.policy import PPOConfig

        config = PPOConfig(device="cpu", stochastic=False)
        accel = config.accel_values
        steer = config.steer_values
        if (len(accel), len(steer)) != (7, 13):
            raise ValueError("PPO checkpoint requires a 7 by 13 action grid")
        self.accel = accel / np.abs(accel).max()
        self.steer = steer / np.abs(steer).max()

    def decode(self, index):
        if not 0 <= index < ACTION_COUNT:
            raise ValueError("PPO action index out of range")
        longitudinal, lateral = divmod(index, len(self.steer))
        return float(self.accel[longitudinal]), float(self.steer[lateral])

    @torch.inference_mode()
    def infer(self, row, state):
        inputs = observation_tensor(row)
        if state is None:
            state = {name: torch.zeros((1, HIDDEN_SIZE)) for name in ("lstm_h", "lstm_c")}
        (logits,), value = self.model.forward_eval(inputs, state)
        if logits.shape != (1, ACTION_COUNT) or not torch.isfinite(logits).all():
            raise ValueError("PPO inference must produce 91 finite joint logits")
        index = int(logits.argmax(dim=-1).item())
        return self.decode(index), state, logits, value
