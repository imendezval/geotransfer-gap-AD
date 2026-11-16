"""Run BehaviorBench on a one-map split without changing its source tree.

BehaviorBench's evaluator constructs Drive with its 100-map default. This small
wrapper sets num_maps=1 for the single-scene feasibility pilot.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import os
import sys
import hashlib
import json
from pathlib import Path

def main():
    here = PROJECT_ROOT
    bench = settings().bench
    actual_root = Path(os.environ.get('GEOTRANSFER_SCENE_ROOT', str(project_path('pilot')))).resolve()
    digest = hashlib.sha256(str(actual_root).encode()).hexdigest()[:12]
    scene_root = Path('/tmp') / f'geo_scene_{digest}'
    if not scene_root.exists():
        scene_root.symlink_to(actual_root, target_is_directory=True)
    elif scene_root.resolve() != actual_root:
        raise RuntimeError(f'Scene alias points elsewhere: {scene_root}')
    if os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1':
        validation = json.loads((actual_root / 'testing/validation.json').read_text())
        replay = json.loads((actual_root / 'testing/replay_validation.json').read_text())
        binary_sha256 = hashlib.sha256((actual_root / 'testing/map_000000.bin').read_bytes()).hexdigest()
        evaluation_ini_sha256 = hashlib.sha256((bench / 'pufferlib/config/evaluation.ini').read_bytes()).hexdigest()
        evaluation_replay = json.loads((actual_root / 'testing/evaluation_replay_probe.json').read_text())
        evaluation_replay_valid = bool(evaluation_replay.get('evaluation_traffic_replay_passed') and evaluation_replay.get('binary_sha256') == binary_sha256 and (evaluation_replay.get('evaluation_ini_sha256') == evaluation_ini_sha256) and (evaluation_replay.get('runtime', {}).get('runtime_source_sha256') == replay.get('runtime', {}).get('runtime_source_sha256')))
        late = bool(validation.get('late_arriving_objects'))
        map_report_path = actual_root / 'testing/map_audit.json'
        if map_report_path.exists():
            map_report = json.loads(map_report_path.read_text())
            from geotransfer_gap.conversion import pilot_ind
            from geotransfer_gap.validation import scene_contract
            current_contract = scene_contract.build(actual_root, 'expert')
            map_valid = not map_report['ego_samples_outside_lanelet_polygons'] and (not map_report['successors_direction_reversed']) and (map_report['successors_with_no_boundary_ids_shared'] == 0) and map_report['occupied_start_to_occupied_goal_reachable'] and (map_report.get('source_map_sha256') == current_contract['files']['source_lanelet2_map']['sha256'])
        else:
            map_valid = False
        spawn_valid = not late
        if late and os.environ.get('GEOTRANSFER_LATE_RUNTIME') == '1':
            spawn = json.loads((actual_root / 'testing/spawn_evaluation_validation.json').read_text())
            spawn_valid = bool(spawn.get('passed') and spawn.get('binary_sha256') == binary_sha256 and replay.get('runtime') and (spawn.get('ini_sha256') == evaluation_ini_sha256) and (spawn.get('test_termination_mode') == 1) and (spawn.get('test_goal_behavior') == 3) and (spawn.get('runtime', {}).get('runtime_source_sha256') == replay['runtime'].get('runtime_source_sha256')))
        crop_valid = True
        if validation.get('explicit_excluded_track_ids'):
            crop = json.loads((actual_root / 'testing/crop_audit.json').read_text())
            crop_valid = bool(crop.get('all_excluded_vehicles_stationary') and crop.get('all_excluded_bounding_circles_clear') and (not crop.get('retained_source_tracks_changed')) and ({x['track_id'] for x in crop['excluded']} == set(validation['explicit_excluded_track_ids'])))
        parked_valid = True
        if validation.get('parked_as_static_expert_track_ids'):
            if os.environ.get('GEOTRANSFER_LATE_RUNTIME') != '1':
                parked_valid = False
            else:
                parked = json.loads((actual_root / 'testing/parked_evaluation_validation.json').read_text())
                parked_valid = bool(parked.get('passed') and parked.get('test_termination_mode', 1) == 1 and (parked.get('ini_sha256') == evaluation_ini_sha256) and (parked.get('collision_shrink') == 1.0) and (parked.get('binary_sha256') == binary_sha256) and (parked.get('runtime', {}).get('runtime_source_sha256') == replay.get('runtime', {}).get('runtime_source_sha256')) and (set(parked.get('parked_track_ids', [])) == set(validation['parked_as_static_expert_track_ids'])))
        if not spawn_valid or not map_valid or (not crop_valid) or (not parked_valid) or (not evaluation_replay_valid) or (not validation.get('ego_goal_lane_reachable_by_successors')) or (not replay.get('replay_passed')) or (replay.get('test_termination_mode', 1) != 1) or (validation.get('binary_sha256') != binary_sha256) or (replay.get('binary_sha256') != binary_sha256):
            raise RuntimeError('Scene failed route, map, spawn, parked, evaluator-traffic, or current-binary replay validation')
    sys.path.insert(0, str(bench))
    if os.environ.get('GEOTRANSFER_LATE_RUNTIME') == '1':
        from geotransfer_gap.runtime import late_spawn_runtime
        runtime = late_spawn_runtime.load()
        if os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1' and late:
            if runtime['runtime_source_sha256'] != replay['runtime']['runtime_source_sha256']:
                raise RuntimeError('Late runtime differs from the validated C build')
        if os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1' and validation.get('parked_as_static_expert_track_ids'):
            if runtime['runtime_source_sha256'] != replay['runtime']['runtime_source_sha256']:
                raise RuntimeError('Parked runtime differs from the validated C build')
    semantic_path = actual_root / 'testing/map_semantics_audit.json'
    if not semantic_path.exists() and os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1':
        raise RuntimeError('Required map semantics audit is missing')
    if semantic_path.exists():
        semantic = json.loads(semantic_path.read_text())
        if semantic.get('binary_sha256') != hashlib.sha256((actual_root / 'testing/map_000000.bin').read_bytes()).hexdigest():
            raise RuntimeError('Map semantics audit does not match current binary')
        if os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1':
            if semantic.get('lanelet_source_sha256') != current_contract['files']['source_lanelet2_map']['sha256'] or semantic.get('opendrive_source_sha256') != current_contract['files']['source_opendrive_map']['sha256']:
                raise RuntimeError('Map semantics audit does not match current source maps')
        if not semantic.get('semantic_screen_pass', False):
            if os.environ.get('GEOTRANSFER_RESEARCH_SCORE') != '1':
                print('Map semantics screen requires per-scene review; this run is diagnostic.')
    if os.environ.get('GEOTRANSFER_ALLOW_UNVALIDATED') != '1':
        admission_path = actual_root / 'testing/admission.json'
        if not admission_path.is_file():
            raise RuntimeError('Scene admission report is missing')
        admission = json.loads(admission_path.read_text())
        if admission.get('contract') != current_contract or not admission.get('technical_admitted'):
            raise RuntimeError('Scene has no current technical admission')
        if os.environ.get('GEOTRANSFER_RESEARCH_SCORE') == '1' and (not admission.get('research_admitted')):
            raise RuntimeError('Scene has no current research admission')
    os.environ['DRIVE_BINARIES_DATA_ROOT'] = str(scene_root)
    os.environ['PUFFER_EXP_ROOT'] = str(scene_root / 'runs')
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/mpl-geotransfer')
    import pufferlib.evaluation.evaluator as evaluator
    import pufferlib.ocean.drive.drive as drive_module
    OriginalDrive = evaluator.Drive

    def one_map_drive(*args, **kwargs):
        kwargs['num_maps'] = 1
        kwargs.setdefault('data_root', str(scene_root))
        env = OriginalDrive(*args, **kwargs)
        if os.environ.get('GEOTRANSFER_TRACE_EGO_GOAL') == '1':
            import math
            trace = []
            original_step = env.step
            original_close = env.close

            def goal_row(state, label):
                entities = state[0]['entities']
                ego = entities[0]
                return {'label': label, 'x': ego['x'], 'y': ego['y'], 'goal_x': ego['goal_position_x'], 'goal_y': ego['goal_position_y'], 'distance_m': math.hypot(ego['goal_position_x'] - ego['x'], ego['goal_position_y'] - ego['y']), 'speed_mps': math.hypot(ego['vx'], ego['vy']), 'removed': bool(ego['removed']), 'reached_goal': bool(ego['reached_goal_this_episode'])}

            def traced_step(actions):
                before = goal_row(env.get_state(), 'before')
                result = original_step(actions)
                after = goal_row(env.get_state(), 'after')
                trace.append({'step': len(trace) + 1, 'before': before, 'after': after, 'ego_done': bool(result[2][0]), 'ego_truncated': bool(result[3][0]), 'observation_goal_distance_m': float((result[0][0, 0] ** 2 + result[0][0, 1] ** 2) ** 0.5 / 0.005)})
                return result

            def traced_close():
                (actual_root / 'testing/evaluator_goal_trace.json').write_text(json.dumps(trace, indent=2) + '\n')
                return original_close()
            env.step = traced_step
            env.close = traced_close
        return env
    evaluator.Drive = one_map_drive
    drive_module.Drive = one_map_drive
    from pufferlib.ocean.benchmark.eval import main
    if __name__ == '__main__':
        sys.argv = [sys.argv[0], '--eval.split', 'testing', '--map-ids', '0', *sys.argv[1:]]
        main()
if __name__ == '__main__':
    main()
