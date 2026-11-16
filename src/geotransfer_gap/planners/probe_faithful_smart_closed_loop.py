"""Diagnostic SMART ego rollout with all observed actors; never grants admission."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch
HERE = PROJECT_ROOT
sys.path.insert(0, str(settings().bench))
from geotransfer_gap.runtime import late_spawn_runtime
from geotransfer_gap.runtime import hybrid_traffic
from pufferlib.prediction.binary_reader import read_binary_scenario

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--steps', type=int, default=91)
    ap.add_argument('--traffic', choices=('idm', 'hybrid_startup'), default='hybrid_startup')
    ap.add_argument('--require-admission', action='store_true')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--trace-output', type=Path)
    args = ap.parse_args()
    np.random.seed(0)
    torch.manual_seed(0)
    root = args.root.resolve()
    binary_path = root / 'testing/map_000000.bin'
    binary = read_binary_scenario(str(binary_path))
    if args.require_admission:
        from geotransfer_gap.validation import scene_contract
        gate_path = root / 'testing' / f'admission_smart_{args.traffic}.json'
        gate = json.loads(gate_path.read_text())
        if not gate.get('research_admitted') or gate.get('contract') != scene_contract.build(root, 'expert') or gate.get('gate_sha256') != hashlib.sha256(project_path('admit_smart_scene.py').read_bytes()).hexdigest() or any((not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest for path, digest in gate.get('evidence_sha256', {}).items())):
            raise RuntimeError('Missing or stale SMART admission')
    ego = binary['sdc_track_index']
    scene = {'metadata': {'sdc_track_index': ego}, 'objects': []}
    for obj in binary['objects']:
        scene['objects'].append({'id': obj['id'], 'type': {1: 'vehicle', 2: 'pedestrian', 3: 'cyclist'}[obj['type']], 'mark_as_expert': obj['mark_as_expert'], 'valid': obj['traj_valid'].tolist(), 'position': [{'x': float(x), 'y': float(y)} for x, y in zip(obj['traj_x'], obj['traj_y'])], 'velocity': [{'x': float(x), 'y': float(y)} for x, y in zip(obj['traj_vx'], obj['traj_vy'])]})
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    from pufferlib.planning.smart import SMARTConfig
    from geotransfer_gap.planners.faithful_smart import FaithfulSMARTPlanner
    alias = Path('/tmp') / ('geo_scene_' + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    env = Drive(data_root=str(alias), split='testing', num_maps=1, num_agents=128, episode_length=91, map_id=0, action_type='continuous', control_mode='control_evaluation', goal_behavior=3, goal_radius=2.0, goal_speed=20.0, ini_file=str(settings().bench / 'pufferlib/config/evaluation.ini'), resample_frequency=0)
    rows = []
    frames = []
    from geotransfer_gap.runtime.session import frame
    try:
        env.reset()
        planner = FaithfulSMARTPlanner(env, ego, np.array([-4, -1], dtype=np.float32), np.array([4, 1], dtype=np.float32), SMARTConfig(weights_path=str(settings().bench / 'weights/SMART_epoch_030.pt'), device='cpu', greedy=True))
        schedule = hybrid_traffic.release_schedule(scene)
        for step in range(min(args.steps, 91)):
            state = env.get_state()[0]
            if args.trace_output:
                frames.append(frame(state, binary, step))
            entity = state['entities'][ego]
            if entity['removed'] or entity['x'] == -10000.0:
                partner = entity.get('collided_with_index', -1)
                rows.append({'step': step, 'ego_terminal': True, 'collision_state': entity['collision_state'], 'collision_partner_binary_index': partner, 'collision_partner_source_id': scene['objects'][partner]['id'] if 0 <= partner < len(scene['objects']) else None})
                break
            slot = state['active_agent_indices'].index(ego)
            hybrid_traffic.apply(env, scene, schedule if args.traffic == 'hybrid_startup' else {}, step, binding)
            if step < 10:
                binding.vec_set_movement_mode(env.c_envs, [slot], 2)
                x, y, h, w, l, n, types = planner._get_agent_states()
                planner.history.append(x, y, h, w, l, n, types)
                rows.append({'step': step, 'observed_warmup': True})
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
                continue
            binding.vec_set_movement_mode(env.c_envs, [slot], 0)
            action = planner.plan(step, np.array(env.observations[slot], copy=True))
            if not np.isfinite(action).all():
                raise ValueError('Nonfinite SMART action')
            expected = {scene['objects'][i]['id'] for i, e in enumerate(state['entities'][:len(scene['objects'])]) if e['x'] != -10000.0 and (not e['removed'])}
            actual = {scene['objects'][int(i)]['id'] for i in planner._valid_agent_map}
            rows.append({'step': step, 'action': np.asarray(action).tolist(), 'prediction_refreshed': planner._prediction_step == step, 'identity_match': expected == actual, 'model_track_ids': sorted(actual), 'ego_collision_state': entity['collision_state']})
            actions = np.zeros((env.num_agents, 2), dtype=np.float32)
            actions[slot] = action
            env.step(actions)
    finally:
        env.close()
    report = {'schema_version': 1, 'diagnostic_only': True, 'binary_sha256': hashlib.sha256(binary_path.read_bytes()).hexdigest(), 'runtime': runtime, 'traffic_protocol': args.traffic, 'timeline': rows, 'seed': 0, 'admission_required': args.require_admission, 'warmup_steps': 10, 'evaluator_goal': {'radius_m': 2.0, 'max_speed_mps': 20.0}, 'protocol_sha256': {name: hashlib.sha256(project_path(name).read_bytes()).hexdigest() for name in ('faithful_smart.py', 'faithful_map.py', 'background_route_intent.py', 'hybrid_traffic.py', 'probe_faithful_smart_closed_loop.py', 'session.py')}}
    path = args.output or root / 'testing' / ('smart_all_actors_closed_loop_' + args.traffic + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    if args.trace_output:
        from geotransfer_gap.artifacts import write_json, reference
        write_json(args.trace_output, {'schema_version': 2, 'planner': 'smart', 'admission_required': args.require_admission, 'scene': reference(root), 'binary_sha256': report['binary_sha256'], 'runtime': runtime, 'protocol_sha256': report['protocol_sha256'], 'traffic_protocol': args.traffic, 'ego_binary_index': int(ego), 'frames': frames})
    print(json.dumps({'steps': len(rows), 'last': rows[-1], 'identity_failures_at_prediction': [r['step'] for r in rows if r.get('prediction_refreshed') and (not r['identity_match'])]}))
if __name__ == '__main__':
    main()
