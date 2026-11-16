"""Restart-task regression fixtures, including a real queue-goal negative."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from geotransfer_gap.corpus.screen_source_restarts import restart
HERE = PROJECT_ROOT

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--negative-root', type=Path, default=project_path('pilot/oriented_v3/r15_e332_f25626'))
    ap.add_argument('--moving-root', type=Path, default=project_path('pilot/oriented_v3/r00_e321_f21017'))
    args = ap.parse_args()
    times = np.arange(91)
    valid = np.ones(91, dtype=bool)
    heading = np.zeros(91)
    ep = np.column_stack((np.maximum(0, times - 44) * 0.35, np.zeros(91)))
    ev = np.column_stack((np.where(times > 44, 3.5, 0), np.zeros(91)))
    lp = np.column_stack((5 + np.maximum(0, times - 30) * 0.3, np.zeros(91)))
    lv = np.column_stack((np.where(times >= 30, 3.0, 0), np.zeros(91)))
    ego = (ep, ev, heading, valid)
    leader = (lp, lv, heading, valid)
    cases = []

    def case(name, e, a, expected):
        evidence = restart(e, a, 4.5, 4.5, 1.8, 1.8)
        cases.append({'case': name, 'expected': expected, 'passed': (evidence is not None) == expected, 'evidence': evidence})
    case('stopped_leader_restarts_goal_cannot_end_before_it', ego, leader, True)
    parallel = lp.copy()
    parallel[:, 1] = 3
    case('adjacent_lane_is_not_a_leader', ego, (parallel, lv, heading, valid), False)
    case('stationary_leader_never_restarts', ego, (np.column_stack((np.full(91, 5), np.zeros(91))), np.zeros((91, 2)), heading, valid), False)
    turn = np.clip((times - 60) / 20, 0, 1) * 0.5
    turn_velocity = np.column_stack((np.cos(turn), np.sin(turn))) * np.where(times > 44, 3.5, 0)[:, None]
    turn_xy = np.cumsum(turn_velocity * 0.1, axis=0)
    case('later_turn_keeps_a_real_stop_restart_task', (turn_xy, turn_velocity, turn, valid), leader, True)
    early_turn = heading.copy()
    early_turn[:30] = 0.6
    case('unmatched_heading_at_stop_is_not_following', (ep, ev, early_turn, valid), leader, False)
    scene_path = next((args.negative_root / 'testing').glob('ind_*.json'))
    scene = json.loads(scene_path.read_text())
    e = scene['objects'][0]
    a = next((o for o in scene['objects'] if o['id'] == 324))

    def arrays(o):
        return (np.asarray([[v['x'], v['y']] for v in o['position']]), np.asarray([[v['x'], v['y']] for v in o['velocity']]), np.asarray(o['heading']), np.asarray(o['valid'], dtype=bool))
    evidence = restart(arrays(e), arrays(a), e['length'], a['length'], e['width'], a['width'])
    cases.append({'case': 'recorded_queue_control_goal_before_leader', 'expected': False, 'passed': evidence is None, 'evidence': evidence})
    evidence = restart(arrays(e), arrays(a), e['length'], a['length'], e['width'], a['width'], moving_queue=True)
    cases.append({'case': 'moving_queue_label_cannot_bypass_goal_before_leader', 'passed': evidence is None})
    cases.append({'case': 'stationary_restart_is_not_relabelled_as_creeping', 'passed': restart(ego, leader, 4.5, 4.5, 1.8, 1.8, moving_queue=True) is None})
    invalid = ep.copy()
    invalid[15, 0] = np.nan
    cases.append({'case': 'nonfinite_source_is_rejected', 'passed': restart((invalid, ev, heading, valid), leader, 4.5, 4.5, 1.8, 1.8) is None})
    moving_path = next((args.moving_root / 'testing').glob('ind_*.json'))
    moving_scene = json.loads(moving_path.read_text())
    e = moving_scene['objects'][0]
    a = next((o for o in moving_scene['objects'] if o['id'] == 317))
    evidence = restart(arrays(e), arrays(a), e['length'], a['length'], e['width'], a['width'], moving_queue=True)
    cases.append({'case': 'recorded_constrained_following_source_positive', 'passed': evidence is not None, 'evidence': evidence})
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    out = {'screen_sha256': sha(project_path('screen_source_restarts.py')), 'probe_sha256': sha(Path(__file__)), 'recorded_negative_sha256': sha(scene_path), 'recorded_moving_positive_sha256': sha(moving_path), 'cases': cases, 'passed': all((c['passed'] for c in cases))}
    project_path('pilot/audits/source_restart_screen_regressions.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({'passed': out['passed'], 'cases': len(cases)}))
    if not out['passed']:
        raise SystemExit(1)
if __name__ == '__main__':
    main()
