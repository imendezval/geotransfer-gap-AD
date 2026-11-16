"""Check exact late entry and initial movement in experimental C runtime."""
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--normal-termination', action='store_true', help="Use evaluator's INI termination mode")
    parser.add_argument('--eval-config', action='store_true', help="Use evaluator's INI and goal behavior")
    args = parser.parse_args()
    root = args.root.resolve()
    alias = Path('/tmp') / ('geo_scene_' + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    if not alias.exists():
        alias.symlink_to(root, target_is_directory=True)
    sys.path.insert(0, str(settings().bench))
    from geotransfer_gap.runtime import late_spawn_runtime
    runtime = late_spawn_runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.ocean.drive import binding
    ini_path = None
    if args.eval_config:
        ini_path = settings().bench / 'pufferlib/config/evaluation.ini'
    elif not args.normal_termination:
        ini_source = settings().bench / 'pufferlib/config/ocean/drive.ini'
        ini_text = ini_source.read_text()
        assert 'termination_mode = 1 #' in ini_text
        ini_path = Path('/tmp') / ('geo_spawn_ini_' + hashlib.sha256(ini_text.encode()).hexdigest()[:12] + '.ini')
        ini_path.write_text(ini_text.replace('termination_mode = 1 #', 'termination_mode = 0 #'))
    scenario = json.loads(next((root / 'testing').glob('ind_*.json')).read_text())
    births = {i: next((t for t, valid in enumerate(obj['valid']) if valid), None) for i, obj in enumerate(scenario['objects']) if not obj['valid'][0]}
    exits = {i: max((t for t, valid in enumerate(obj['valid']) if valid)) for i, obj in enumerate(scenario['objects']) if not obj['valid'][0]}
    results = {}
    for mode in ('dynamics', 'idm'):
        env = Drive(data_root=str(alias), split='testing', num_maps=1, num_agents=128, episode_length=91, map_id=0, action_type='continuous', control_mode='control_evaluation', goal_behavior=3 if args.eval_config else 4, collision_behavior=0, offroad_behavior=0, resample_frequency=0, **{'ini_file': str(ini_path)} if ini_path else {})
        try:
            env.reset()
            if mode == 'idm':
                binding.vec_set_movement_mode(env.c_envs, list(range(1, env.num_agents)), 1)
            binding.vec_set_movement_mode(env.c_envs, [0], 2)
            state = env.get_state()[0]
            initial = state['entities']
            slots = {entity_idx: slot for slot, entity_idx in enumerate(state['active_agent_indices'])}
            origins = [(obj['position'][0]['x'] - initial[i]['traj_x'][0], obj['position'][0]['y'] - initial[i]['traj_y'][0]) for i, obj in enumerate(scenario['objects'])]
            errors, heading_errors, velocity_errors, early, postexit, preentry_events, first_movement = ([], [], [], [], [], [], {})
            previous = {}
            goal_terminal_step = None
            for t in range(91):
                entities = env.get_state()[0]['entities']
                for i, birth in births.items():
                    e = entities[i]
                    if t < birth:
                        if e['x'] != -10000.0 or e['y'] != -10000.0:
                            early.append({'track': scenario['objects'][i]['id'], 'step': t})
                        slot = slots.get(i)
                        if e['collision_state'] or e['removed'] or e['stopped'] or (slot is not None and np.any(env.observations[slot])):
                            preentry_events.append({'track': scenario['objects'][i]['id'], 'step': t, 'kind': 'state_or_observation'})
                    elif t == birth:
                        expected = scenario['objects'][i]['position'][t]
                        errors.append(math.dist((e['x'] + origins[i][0], e['y'] + origins[i][1]), (expected['x'], expected['y'])))
                        heading_errors.append(abs((e['heading'] - scenario['objects'][i]['heading'][t] + math.pi) % (2 * math.pi) - math.pi))
                        expected_velocity = scenario['objects'][i]['velocity'][t]
                        velocity_errors.append(math.dist((e['vx'], e['vy']), (expected_velocity['x'], expected_velocity['y'])))
                        previous[i] = (e['x'], e['y'])
                    elif t == birth + 1:
                        first_movement[scenario['objects'][i]['id']] = math.dist(previous[i], (e['x'], e['y']))
                    if t > exits[i] and (e['x'] != -10000.0 or e['y'] != -10000.0):
                        postexit.append({'track': scenario['objects'][i]['id'], 'step': t})
                ego = entities[0]
                source_ego = scenario['objects'][0]
                source_position = source_ego['position'][t]
                goal = source_ego['goalPosition']
                if ego['removed'] and ego['collision_state'] == 0 and (math.dist((source_position['x'], source_position['y']), (goal['x'], goal['y'])) <= 2.1):
                    goal_terminal_step = t
                    break
                if t < 90:
                    env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
                    for i, birth in births.items():
                        slot = slots.get(i)
                        if t + 1 < birth and slot is not None and np.any(env.reward_components_raw[slot, :3]):
                            preentry_events.append({'track': scenario['objects'][i]['id'], 'step': t + 1, 'kind': 'reward'})
            results[mode] = {'late_tracks': {scenario['objects'][i]['id']: {'birth_step': t, 'type': scenario['objects'][i]['type'], 'controlled_slot': slots.get(i)} for i, t in births.items()}, 'observed_steps': t + 1, 'justified_goal_terminal_step': goal_terminal_step, 'post_goal_untested_birth_track_ids': [scenario['objects'][i]['id'] for i, birth in births.items() if birth > t], 'premature_appearances': early, 'postexit_appearances': postexit[:20], 'postexit_appearance_count': len(postexit), 'preentry_events': preentry_events, 'max_birth_position_error_m': max(errors, default=0.0), 'max_birth_heading_error_rad': max(heading_errors, default=0.0), 'max_birth_velocity_error_mps': max(velocity_errors, default=0.0), 'first_step_displacement_m': first_movement, 'birth_passed': not early and (not postexit) and (not preentry_events) and (max(errors, default=0.0) < 0.01) and (max(heading_errors, default=0.0) < 0.01) and (max(velocity_errors, default=0.0) < 0.01)}
        finally:
            env.close()
    report = {'binary_sha256': hashlib.sha256((root / 'testing/map_000000.bin').read_bytes()).hexdigest(), 'late_birth_count': len(births), 'test_termination_mode': 1 if args.normal_termination or args.eval_config else 0, 'test_goal_behavior': 3 if args.eval_config else 4, 'ini_sha256': hashlib.sha256(ini_path.read_bytes()).hexdigest() if args.eval_config else None, 'runtime': runtime, 'modes': results, 'passed': all((x['birth_passed'] for x in results.values()))}
    (root / ('testing/spawn_evaluation_validation.json' if args.eval_config else 'testing/spawn_validation.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['passed']:
        raise SystemExit(1)
if __name__ == '__main__':
    main()
