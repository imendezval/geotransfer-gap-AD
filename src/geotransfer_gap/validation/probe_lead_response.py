"""Compare IDM traffic with and without a synthetic ego vehicle in its lane.

This is a controller diagnostic, not a source-faithful planning scene.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np

def main():
    HERE = PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--track-id', type=int, required=True)
    ap.add_argument('--step', type=int, required=True)
    ap.add_argument('--ahead-m', type=float, default=12.0)
    args = ap.parse_args()
    root = args.root.resolve()
    alias = Path('/tmp') / ('geo_scene_' + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    scene = json.loads(next((root / 'testing').glob('ind_*.json')).read_text())
    target_idx = next((i for i, obj in enumerate(scene['objects']) if obj['id'] == args.track_id))
    ini = settings().bench / 'pufferlib/config/evaluation.ini'

    def run(place_ego):
        env = Drive(data_root=str(alias), split='testing', num_maps=1, num_agents=128, episode_length=91, map_id=0, action_type='continuous', control_mode='control_evaluation', goal_behavior=3, ini_file=str(ini), resample_frequency=0)
        try:
            env.reset()
            active = env.get_state()[0]['active_agent_indices']
            slots = {idx: slot for slot, idx in enumerate(active)}
            assert target_idx in slots and 0 in slots
            binding.vec_set_movement_mode(env.c_envs, [slots[0]], 2)
            binding.vec_set_movement_mode(env.c_envs, [slots[i] for i in slots if i != 0], 1)
            positions = []
            for t in range(91):
                if t == args.step and place_ego:
                    state = env.get_state()[0]['entities']
                    target = state[target_idx]
                    assert target['x'] != -10000.0 and (not target['removed'])
                    x = target['x'] + args.ahead_m * math.cos(target['heading'])
                    y = target['y'] + args.ahead_m * math.sin(target['heading'])
                    binding.vec_set_positions(env.c_envs, [slots[0]], [x], [y], [target['heading']])
                    binding.vec_set_movement_mode(env.c_envs, [slots[0]], 0)
                e = env.get_state()[0]['entities'][target_idx]
                positions.append({'step': t, 'x': e['x'], 'y': e['y'], 'heading': e['heading'], 'speed_mps': math.hypot(e['vx'], e['vy']), 'removed': bool(e['removed']), 'collision_state': int(e['collision_state'])})
                if t < 90:
                    env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
            return positions
        finally:
            env.close()
    baseline = run(False)
    injected = run(True)
    differences = []
    for a, b in zip(baseline, injected):
        if a['step'] < args.step or a['x'] == -10000.0 or b['x'] == -10000.0:
            continue
        differences.append({'step': a['step'], 'position_m': math.dist((a['x'], a['y']), (b['x'], b['y'])), 'speed_mps': b['speed_mps'] - a['speed_mps']})
    report = {'binary_sha256': hashlib.sha256((root / 'testing/map_000000.bin').read_bytes()).hexdigest(), 'evaluation_ini_sha256': hashlib.sha256(ini.read_bytes()).hexdigest(), 'runtime_source_sha256': runtime['runtime_source_sha256'], 'target_track_id': args.track_id, 'perturb_step': args.step, 'ahead_m': args.ahead_m, 'max_target_position_response_m': max((d['position_m'] for d in differences), default=0), 'max_target_speed_reduction_mps': max((-d['speed_mps'] for d in differences), default=0), 'target_removed_in_baseline': any((x['removed'] for x in baseline[args.step:])), 'target_removed_after_injection': any((x['removed'] for x in injected[args.step:])), 'first_response_samples': [d for d in differences if d['position_m'] > 0.01 or abs(d['speed_mps']) > 0.01][:10], 'diagnostic_only': True}
    (root / 'testing' / f'lead_response_track_{args.track_id}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    main()
