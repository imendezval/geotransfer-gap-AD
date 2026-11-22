"""Role and lifetime adapter for the existing faithful SMART planner."""

import numpy as np

from geotransfer_gap.planners.controller_api import ControllerRole, DynamicsIntent


class SMARTController:
    name = "smart"

    def __init__(self, planner, role: ControllerRole):
        if role not in ("ego", "traffic"):
            raise ValueError(f"unsupported SMART role: {role}")
        self.planner = planner
        self.role = role
        self.reset({})

    def reset(self, episode_info):
        self.planner.reset()
        self._snapshot = None
        self._live = frozenset()
        self._forecast_steps = {}
        self.refreshes = []

    def retire(self, actor, reason):
        self._forecast_steps.pop(actor, None)
        if self._snapshot is None or actor not in self._live:
            return
        index = self._snapshot.actor_for(actor).fixed_binary_index
        # Clear the old lifetime's entire row, including values behind masks.
        self._clear_history(index, slice(None))

    def _clear_history(self, index, ticks):
        h = self.planner.history
        for field in (h.position, h.heading, h.velocity, h.valid):
            field[index, ticks] = 0

    def observe(self, snapshot, visible_targets):
        expected = 0 if self._snapshot is None else self._snapshot.step + 1
        if snapshot.step != expected:
            raise ValueError(f"SMART expected observation {expected}, got {snapshot.step}")
        p = self.planner
        p.prepare_step(snapshot.step)
        h = p.history
        if h.num_steps != snapshot.step + p.config.num_historical_steps:
            raise RuntimeError("SMART history is not aligned with the pre-step observation")

        tick = h.num_steps - 1
        born = []
        for actor in snapshot.actors:
            index = actor.fixed_binary_index
            if actor.key not in visible_targets:
                self._clear_history(index, slice(None) if snapshot.step == 0 else tick)
            elif not h.valid[index, tick]:
                raise ValueError(f"SMART could not represent live actor {actor.key}")
            elif not h.valid[index, tick - 1]:
                born.append(index)

        if born:
            speeds = np.zeros(h.num_agents, dtype=np.float32)
            p._bootstrap_speeds_from_state(speeds, h.num_agents)
            heading = h.heading[born, tick]
            h.velocity[born, tick, 0] = speeds[born] * np.cos(heading)
            h.velocity[born, tick, 1] = speeds[born] * np.sin(heading)
        self._snapshot = snapshot
        self._live = visible_targets

    def act(self, snapshot, eligible_targets):
        if snapshot is not self._snapshot:
            raise ValueError("SMART requires the current observed snapshot")
        keys = sorted(eligible_targets)
        actors = [snapshot.actor_for(key) for key in keys]
        if any(
            actor.key not in self._live
            or not actor.controller_eligible
            or actor.is_ego != (self.role == "ego")
            for actor in actors
        ):
            raise ValueError(f"unauthorized SMART {self.role} target")
        self._forecast_steps = {
            key: self._forecast_steps[key] for key in keys if key in self._forecast_steps
        }
        if not keys:
            return {}
        indices = np.array([actor.fixed_binary_index for actor in actors], dtype=np.int32)
        self._ensure_forecast(snapshot.step, keys, indices)

        h = self.planner.history
        tick = h.num_steps - 1
        speeds = np.zeros(h.num_agents, dtype=np.float32)
        # Match plan()'s pre-append speed estimate when the prior pair is valid.
        # Fresh births and returns use the causal bootstrap for this observed tick.
        for index in indices:
            has_prior_pair = h.valid[index, tick - 2:tick].all()
            if self.role == "ego" and has_prior_pair:
                # Keep the faithful ego path's float32 operation order.
                dx, dy = h.position[[index], tick - 1].T - h.position[[index], tick - 2].T
                speeds[index] = (np.sqrt(dx**2 + dy**2) / self.planner.config.dt)[0]
            else:
                speed_tick = tick - 1 if has_prior_pair else tick
                speeds[index] = np.linalg.norm(h.velocity[index, speed_tick])
        actions = self.planner._positions_to_actions(
            indices, snapshot.step, h.position[:, tick], h.heading[:, tick], speeds,
        )
        return {key: DynamicsIntent(tuple(action))
                for key, action in zip(keys, actions, strict=True)}

    def _ensure_forecast(self, step, keys, indices):
        p = self.planner
        timestamp = p._prediction_step
        interval = p.config.repredict_interval
        missing = [key for key in keys if self._forecast_steps.get(key) != timestamp]
        if timestamp < 0:
            reason = "first_targets"
        elif step % interval == 0 and timestamp != step:
            reason = "cadence"
        elif missing:
            reason = "new_target"
        elif not self._usable(step, indices):
            reason = "unusable_forecast"
        else:
            return

        p._predicted_positions = None
        p._run_inference()
        p._prediction_step = step
        if not self._usable(step, indices):
            raise RuntimeError(f"SMART failed to produce a usable forecast at step {step}")
        self._forecast_steps = dict.fromkeys(keys, step)
        self.refreshes.append({
            "step": step,
            "reason": reason,
            "previous_prediction_step": None if timestamp < 0 else timestamp,
            "targets": [
                {"source_id": int(key.source_id), "generation": key.lifetime_generation,
                 "binary_index": int(index)}
                for key, index in zip(keys, indices, strict=True)
            ],
        })

    def _usable(self, step, indices):
        p = self.planner
        positions = p._predicted_positions
        offset = step - p._prediction_step
        if positions is None or not 0 <= offset < positions.shape[1]:
            return False
        if not set(indices) <= set(p._valid_agent_map):
            return False
        points = positions[indices, offset]
        return np.isfinite(points).all() and (np.abs(points) < 9000).all()


def load_smart_controller(env, ego_binary_index, role):
    """Construct the faithful CPU planner with an independent mutable history."""
    import torch

    from geotransfer_gap.config import ensure_bench, settings

    ensure_bench()
    from pufferlib.planning.smart import SMARTConfig
    from geotransfer_gap.planners.faithful_smart import FaithfulSMARTPlanner

    np.random.seed(0)
    torch.manual_seed(0)
    torch.set_num_threads(1)
    planner = FaithfulSMARTPlanner(
        env,
        ego_binary_index,
        np.array([-4, -1], dtype=np.float32),
        np.array([4, 1], dtype=np.float32),
        SMARTConfig(weights_path=str(settings().weights), device="cpu", greedy=True),
    )
    return SMARTController(planner, role)
