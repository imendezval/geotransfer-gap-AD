"""Convert and screen ranked moving-ego late-VRU windows."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
HERE = PROJECT_ROOT

def run(candidate):
    rec, ego, frame = (candidate[k] for k in ('recording', 'ego', 'first_frame'))
    name = f'r{rec:02d}_e{ego}_f{frame}'
    root = project_path('pilot/probes/vru_search') / name
    args = [sys.executable, str(project_path('pilot_ind.py')), '--recording', str(rec), '--ego', str(ego), '--first-frame', str(frame), '--static-crop-radius', '1000000', '--parked-as-static-expert', '--late-mode', 'runtime_spawn', '--output-root', str(root)]
    proc = subprocess.run(args, cwd=HERE, capture_output=True, text=True)
    result = {'scene': name, 'root': str(root), 'candidate': candidate}
    if proc.returncode:
        result['conversion_error'] = proc.stderr[-1200:]
        return result
    for script in ('audit_scene.py', 'audit_map_semantics.py'):
        proc = subprocess.run([sys.executable, str(project_path(script)), '--root', str(root)], cwd=HERE, capture_output=True, text=True)
        if proc.returncode:
            result[f'{script}_error'] = proc.stderr[-1200:]
            return result
    testing = root / 'testing'
    geo = json.loads((testing / 'map_audit.json').read_text())
    semantics = json.loads((testing / 'map_semantics_audit.json').read_text())
    validation = json.loads((testing / 'validation.json').read_text())
    result.update({'objects': validation['objects'], 'late_track_ids': validation['source_late_arriving_track_ids'], 'polygon_outside_samples': len(geo['ego_samples_outside_lanelet_polygons']), 'directed_route': geo['occupied_start_to_occupied_goal_reachable'], 'bad_successors': geo['successors_with_no_boundary_ids_shared'] + len(geo['successors_direction_reversed']), 'semantic_complete': semantics['semantic_transfer_complete_for_ego'], 'semantic_screen_pass': semantics['semantic_screen_pass'], 'ego_priority_relations': len(semantics['regulatory_elements_touching_ego_lanelets']), 'ego_crosses_crosswalk': semantics['ego_crosses_unencoded_crosswalk'], 'near_sign': semantics['ego_has_unencoded_sign_within_5m']})
    return result
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, default=project_path('pilot/audits/vru_candidates_0_10.json'))
    ap.add_argument('--limit', type=int, default=30)
    ap.add_argument('--offset', type=int, default=0, help='Skip this many unique ranked windows')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--output', type=Path, default=project_path('pilot/audits/vru_screen.json'))
    args = ap.parse_args()
    raw = json.loads(args.input.read_text())
    seen = set()
    selected = []
    for item in raw:
        key = (item['recording'], item['ego'], item['first_frame'])
        if key not in seen:
            selected.append(item)
            seen.add(key)
        if len(selected) >= args.offset + args.limit:
            break
    selected = selected[args.offset:]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, selected))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps([{k: v for k, v in row.items() if k not in ('candidate', 'root')} for row in results], indent=2))
