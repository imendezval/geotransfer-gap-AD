"""Trace source expert trajectories under the exact BehaviorBench evaluator INI."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from collections import Counter
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
    ini = settings().bench / 'pufferlib/config/evaluation.ini'
    env = Drive(data_root=str(alias), split='testing', num_maps=1, num_agents=128, episode_length=91, map_id=0, action_type='continuous', control_mode='control_evaluation', goal_behavior=3, ini_file=str(ini), resample_frequency=0)
    try:
        env.reset()
        initial = env.get_state()[0]
        binding.vec_set_movement_mode(env.c_envs, list(range(env.num_agents)), 2)
        offsets = [(obj['position'][0]['x'] - initial['entities'][i]['traj_x'][0], obj['position'][0]['y'] - initial['entities'][i]['traj_y'][0]) for i, obj in enumerate(scene['objects'])]
        first = {}
        counts = Counter()
        max_error = 0.0
        max_preterminal_error = 0.0
        justified_goal_terminal_step = None
        for t in range(91):
            entities = env.get_state()[0]['entities']
            for i, obj in enumerate(scene['objects']):
                if not obj['valid'][t]:
                    continue
                e = entities[i]
                absent = e['x'] == -10000.0
                src = obj['position'][t]
                error = None if absent else math.dist((e['x'] + offsets[i][0], e['y'] + offsets[i][1]), (src['x'], src['y']))
                if error is not None:
                    max_error = max(max_error, error)
                    if t < 90:
                        max_preterminal_error = max(max_preterminal_error, error)
                kind = 'missing' if absent else 'diverged' if error > 0.01 else None
                if kind:
                    counts[kind] += 1
                    first.setdefault(obj['id'], {'step': t, 'kind': kind, 'position_error_m': error, 'removed': e['removed'], 'stopped': e['stopped'], 'collision_state': e['collision_state'], 'source_type': obj['type'], 'source_valid_last_step': max((j for j, v in enumerate(obj['valid']) if v))})
            ego = scene['objects'][0]
            ego_entity = entities[0]
            if ego_entity['x'] == -10000.0 and ego['valid'][t] and ego_entity['removed'] and (ego_entity['collision_state'] == 0):
                goal = ego['goalPosition']
                source_position = ego['position'][t]
                if math.dist((source_position['x'], source_position['y']), (goal['x'], goal['y'])) <= 2.1:
                    justified_goal_terminal_step = t
                    break
            if t < 90:
                env.step(np.zeros((env.num_agents, 2), dtype=np.float32))
    finally:
        env.close()
    report = {'binary_sha256': hashlib.sha256((root / 'testing/map_000000.bin').read_bytes()).hexdigest(), 'evaluation_ini_sha256': hashlib.sha256(ini.read_bytes()).hexdigest(), 'runtime': runtime, 'first_issue_by_track': first, 'issue_counts': dict(counts), 'observed_steps': t + 1, 'justified_goal_terminal_step': justified_goal_terminal_step, 'post_goal_source_steps_not_evaluated': 90 - t if justified_goal_terminal_step is not None else 0, 'max_position_error_m': max_error, 'max_preterminal_position_error_m': max_preterminal_error, 'strict_expert_match': not first}
    report['premature_background_issues'] = {track: issue for track, issue in first.items() if track != scene['objects'][0]['id']}
    report['premature_ego_issue'] = first.get(scene['objects'][0]['id'])
    ego_issue = report['premature_ego_issue']
    ego = scene['objects'][0]
    if ego_issue and ego_issue['kind'] == 'missing' and (ego_issue['step'] > 0):
        prior = ego['position'][ego_issue['step'] - 1]
        goal = ego['goalPosition']
        report['ego_distance_to_goal_before_removal_m'] = math.dist((prior['x'], prior['y']), (goal['x'], goal['y']))
        current = ego['position'][ego_issue['step']]
        report['ego_source_distance_to_goal_at_removal_m'] = math.dist((current['x'], current['y']), (goal['x'], goal['y']))
    report['ego_goal_removal_consistent'] = ego_issue is None or (ego_issue['kind'] == 'missing' and ego_issue['collision_state'] == 0 and (report.get('ego_source_distance_to_goal_at_removal_m', float('inf')) <= 2.1))
    report['evaluation_traffic_replay_passed'] = not report['premature_background_issues'] and report['ego_goal_removal_consistent'] and (max_preterminal_error < 0.01)
    (root / 'testing/evaluation_replay_probe.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    main()
