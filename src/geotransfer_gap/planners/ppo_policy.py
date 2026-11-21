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
    return _observation_batch(row[None, :])


def _observation_batch(rows):
    if rows.ndim != 2 or rows.shape[1] != OBS_WIDTH or not len(rows):
        raise ValueError("PPO observation batch must have rows of width 1151")
    tensor = torch.tensor(rows, dtype=torch.float32)
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
            state = self._initial_state()
        actions, logits, value = self._forward(inputs, state)
        return actions[0], state, logits, value

    @staticmethod
    def _initial_state():
        return {name: torch.zeros((1, HIDDEN_SIZE)) for name in ("lstm_h", "lstm_c")}

    @torch.inference_mode()
    def infer_batch(self, rows, states):
        """Run ordered rows together and return independent per-row h/c."""
        inputs = _observation_batch(rows)
        if len(states) != len(inputs):
            raise ValueError("PPO requires one recurrent state per observation row")
        initial = self._initial_state()
        names = tuple(initial)
        state = {name: torch.cat([(previous or initial)[name] for previous in states])
                 for name in names}
        actions, logits, value = self._forward(inputs, state)
        updated = [{name: state[name][i:i + 1].clone() for name in names}
                   for i in range(len(inputs))]
        return actions, updated, logits, value

    def _forward(self, inputs, state):
        (logits,), value = self.model.forward_eval(inputs, state)
        if logits.shape != (len(inputs), ACTION_COUNT) or not torch.isfinite(logits).all():
            raise ValueError("PPO inference must produce 91 finite joint logits")
        actions = [self.decode(index) for index in logits.argmax(dim=-1).tolist()]
        return actions, logits, value


def load_pinned_ego_policy(env):
    """Validate the production inputs and return policy and run provenance."""
    import subprocess

    from geotransfer_gap.artifacts import sha256
    from geotransfer_gap.config import settings

    validate_native_env(env)
    bench = settings().bench
    head = subprocess.check_output(["git", "-C", str(bench), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != "805fe04c6977b60c41c92c31f1a5211fbd704f44":
        raise ValueError(f"PPO requires the pinned BehaviorBench revision, got {head}")
    path = bench / "weights/simple_ppo.pt"
    digest = sha256(path)
    if digest != "50a9a580cca905fc3dae47b5847b4edf408de3b7fe7517bd4f3a781fa140e3b3":
        raise ValueError(f"PPO checkpoint SHA-256 differs from the audited weights: {digest}")
    ini_digest = sha256(env.ini_file)
    if ini_digest != "afdf157a7b809e31700a49f977c46a7a4913c7e73546a5803d8635a9ae1f5e4e":
        raise ValueError("PPO requires the audited native evaluation INI")
    torch.set_num_threads(1)
    torch.manual_seed(0)
    policy = PPOPolicy(path)
    return policy, {
        "behaviorbench_commit": head,
        "checkpoint": str(path),
        "checkpoint_sha256": digest,
        "evaluation_ini_sha256": ini_digest,
        "architecture": "Drive(64,256) + LSTMWrapper(256,256)",
        "checkpoint_keys": len(policy.model.state_dict()),
        "trainable_scalars": sum(p.numel() for p in policy.model.parameters()),
        "observation": {"dtype": "float32", "width": OBS_WIDTH, **_LAYOUT, **_FLAGS},
        "information_access": (
            "Current native actor state, static road geometry and simulator navigation "
            "goal. German navigation goals use the final valid source position. "
            "Actor future arrays and background IDM route points are not model inputs."
        ),
        "action": {
            "selection": "argmax of 91 joint logits, acceleration-major",
            "normalized_acceleration_grid": policy.accel.tolist(),
            "normalized_steering_grid": policy.steer.tolist(),
            "native_scale": {"acceleration_m_s2": 4, "steering_rad": 1},
            "native_dt_s": 0.1,
        },
        "device": "cpu",
        "torch_version": str(torch.__version__),
        "torch_threads": torch.get_num_threads(),
        "seed": 0,
        "recurrent_shape": [1, HIDDEN_SIZE],
        "warmup": "Observe frames 0-9 with zero initial h/c and apply expert replay; PPO takes over at transition 10.",
        "research_admission_status": "not_established",
        "diagnostic_only": True,
    }
