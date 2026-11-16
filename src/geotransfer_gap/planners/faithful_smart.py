"""Experimental SMART ego adapter including expert background actors.

Uses evaluator state and the source velocity at an observed actor birth.
Source future positions are never supplied to SMART.
Actor identity follows binary order for both US and converted scenes.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import numpy as np
from pathlib import Path
from pufferlib.planning.smart import SMARTPlanner
from pufferlib.prediction.binary_reader import read_binary_scenario
from geotransfer_gap.planners.faithful_map import tokenize_roads
PROTOCOL_VERSION = 'smart_all_actors_observed_history_dense_map_v4'

class FaithfulSMARTPlanner(SMARTPlanner):

    def _load_map(self):
        if self._map_loaded:
            return
        env = self.env
        index = self.map_env_index
        map_id = int(env.map_ids[index]) if hasattr(env, 'map_ids') and len(env.map_ids) > index else 0
        scenario = read_binary_scenario(str(Path(env.data_root) / env.split / f'map_{map_id:06d}.bin'))
        self.map_data = tokenize_roads(scenario['roads'], self.map_codebook)
        self._scenario_objects = scenario['objects']
        self._map_loaded = True
        if self.map_data is None:
            raise ValueError('SMART requires an encoded map')
        entities = self._state()['entities']
        anchor = next((i for i, o in enumerate(self._scenario_objects) if o['traj_valid'][0]))
        obj, entity = (self._scenario_objects[anchor], entities[anchor])
        self.input_frame_origin = np.array([float(obj['traj_x'][0]) - entity['traj_x'][0], float(obj['traj_y'][0]) - entity['traj_y'][0]])
        position = self.map_data['pt_token']['position'].clone()
        origin = position.new_tensor(self.input_frame_origin)
        position[:, :2] -= origin
        self.map_data['pt_token']['position'] = position
        self.map_data['map_save']['traj_pos'] = self.map_data['map_save']['traj_pos'].clone() - origin

    def plan(self, current_step=0, obs=None, extract_trajectories=False):
        self._observed_step = current_step
        return super().plan(current_step, obs, extract_trajectories)

    def prepare_step(self, current_step):
        self._observed_step = current_step
        return super().prepare_step(current_step)

    def _load_ground_truth_history(self):
        x, y, heading, width, length, n, types = self._get_agent_states()
        speed = np.zeros(n, dtype=np.float32)
        self._bootstrap_speeds_from_state(speed, n)
        for t in range(self.config.num_historical_steps - 1):
            dt = (self.config.num_historical_steps - 1 - t) * self.config.dt
            hx = np.where(width > 0, x - speed * np.cos(heading) * dt, -10000.0)
            hy = np.where(width > 0, y - speed * np.sin(heading) * dt, -10000.0)
            self.history.append(hx, hy, heading, width, length, n, types)

    def _load_ground_truth_predictions(self):
        raise RuntimeError('Source future predictions are forbidden in this adapter')

    def _state(self):
        state = self.env.get_state()
        return state[self.map_env_index] if isinstance(state, list) else state

    def _get_active_agent_indices(self):
        return list(range(len(self._scenario_objects)))

    def _get_agent_states(self):
        self._load_map()
        entities = self._state()['entities']
        objects = self._scenario_objects
        n = len(objects)
        if n > self.history.max_agents:
            raise ValueError('SMART actor capacity exceeded')
        x = np.full(n, -10000.0, dtype=np.float32)
        y = x.copy()
        h = np.zeros(n, dtype=np.float32)
        width = np.zeros(n, dtype=np.float32)
        length = width.copy()
        types = np.zeros(n, dtype=np.int32)
        for i, obj in enumerate(objects):
            entity = entities[i]
            if entity['x'] == -10000.0 or entity.get('removed'):
                continue
            valid = np.flatnonzero(obj['traj_valid'])
            if not len(valid):
                continue
            t = int(valid[0])
            x[i], y[i] = (entity['x'], entity['y'])
            if abs(x[i]) >= 9000 or abs(y[i]) >= 9000:
                raise ValueError("Scene exceeds SMART's safe local coordinate range")
            h[i] = entity['heading']
            width[i], length[i] = (entity['width'], entity['length'])
            types[i] = entity['type']
            if not np.isfinite([x[i], y[i], h[i], width[i], length[i]]).all():
                raise ValueError(f'Nonfinite present actor state at binary index {i}')
        return (x, y, h, width, length, n, types)

    def _bootstrap_speeds_from_state(self, cur_speeds, num_agents):
        for i, entity in enumerate(self._state()['entities'][:num_agents]):
            if entity['x'] != -10000.0 and (not entity.get('removed')):
                cur_speeds[i] = np.hypot(entity['vx'], entity['vy'])
                obj = self._scenario_objects[i]
                valid = np.flatnonzero(obj['traj_valid'])
                if entity.get('movement_mode') == 2 and len(valid):
                    birth = int(valid[0])
                    if getattr(self, '_observed_step', -1) == birth and np.hypot(entity['x'] - entity['traj_x'][birth], entity['y'] - entity['traj_y'][birth]) < 0.0001:
                        cur_speeds[i] = np.hypot(obj['traj_vx'][birth], obj['traj_vy'][birth])
