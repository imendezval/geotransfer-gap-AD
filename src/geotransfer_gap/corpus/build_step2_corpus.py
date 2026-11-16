"""Build a leakage-checked Step 2 manifest and candidate-to-admission flow."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import csv
import argparse
import json
from collections import Counter
from pathlib import Path
from geotransfer_gap.validation import scene_contract
HERE = PROJECT_ROOT
AUDITS = project_path('pilot/audits')

def read(path, default):
    return json.loads(path.read_text()) if path.is_file() else default

def split(location, recording):
    if location == 4:
        return 'heldout_location_4'
    return 'validation_recording' if recording % 5 == 0 else 'adaptation_recording'

def main(extra_roots, traffic_protocol):
    if traffic_protocol not in {'idm', 'hybrid_startup'}:
        raise ValueError(traffic_protocol)
    review_name = 'semantic_review.json' if traffic_protocol == 'idm' else 'semantic_review_hybrid_startup.json'
    admission_name = 'admission.json' if traffic_protocol == 'idm' else 'admission_hybrid_startup.json'
    output_suffix = '' if traffic_protocol == 'idm' else '_hybrid_startup'
    catalog_by_key = {}
    catalog_counts = {}
    for filename in ('all_moving_windows.json', 'all_moving_windows_loc23_stride50.json', 'all_moving_windows_loc1_stride50.json'):
        rows = read(AUDITS / filename, {'windows': []})['windows']
        catalog_counts[filename] = len(rows)
        catalog_by_key.update({(r['recording'], r['ego_track_id'], r['first_frame']): r for r in rows})
    catalog = list(catalog_by_key.values())
    preflight_by_key = {}
    preflight_counts = {}
    for filename in ('source_map_preflight.json', 'source_map_preflight_loc23_stride50.json', 'source_map_preflight_loc1_stride50.json'):
        rows = read(AUDITS / filename, {'windows': []})['windows']
        preflight_counts[filename] = len(rows)
        preflight_by_key.update({(r['recording'], r['ego_track_id'], r['first_frame']): r for r in rows})
    preflight = list(preflight_by_key.values())
    screens = []
    for filename in ('step2_first_screen.json', 'step2_map_screen.json', 'step2_map14_screen.json', 'step2_loc2_stride50_screen.json', 'step2_loc23_stride50_screen.json', 'step2_loc1_stride50_screen.json', 'step2_loc23_stride50_screen_v2.json', 'step2_remaining_interactive_screen.json'):
        screens.extend(read(AUDITS / filename, {'results': []})['results'])
    screening = {}
    duplicate_source_keys = {}
    for row in screens:
        key = (row['recording'], row['ego_track_id'], row['first_frame'])
        if key in screening:
            previous_root = screening[key].get('root') or str(project_path('pilot/corpus/candidates') / screening[key]['name'])
            current_root = row.get('root') or str(project_path('pilot/corpus/candidates') / row['name'])
            duplicate_source_keys.setdefault(str(key), [previous_root]).append(current_root)
            previous_review = read(Path(previous_root) / 'testing' / review_name, {})
            current_review = read(Path(current_root) / 'testing' / review_name, {})
            if previous_review.get('review_status') == 'complete' and current_review.get('review_status') != 'complete':
                continue
        screening[key] = row
    for root in extra_roots:
        root = root.resolve()
        validation = read(root / 'testing/validation.json', {})
        if not validation:
            raise ValueError(f'Missing validation.json in {root}')
        key = (validation['recording'], validation['ego_track'], validation['first_frame'])
        screening[key] = {'name': root.name, 'root': str(root), 'recording': key[0], 'location': validation['location'], 'ego_track_id': key[1], 'first_frame': key[2], 'source_nearby_moving_actors': None, 'source_nearby_vrus': None, 'conversion_pass': True, 'exclusion_reasons': []}
    keys = {(r['recording'], r['ego_track_id'], r['first_frame']): r for r in catalog}
    candidate_rows = []
    for key, row in sorted(screening.items()):
        root = Path(row.get('root') or project_path('pilot/corpus/candidates') / row['name'])
        admission = read(root / 'testing' / admission_name, None)
        current_contract = scene_contract.build(root, 'expert') if admission else None
        admission_current = bool(admission and admission.get('contract') == current_contract and (admission.get('traffic_protocol', 'idm') == traffic_protocol))
        scene_files = list((root / 'testing').glob('ind_*.json'))
        scene = read(scene_files[0], None) if len(scene_files) == 1 else None
        review = read(root / 'testing' / review_name, {})
        semantic = read(root / 'testing/rule_applicability_audit.json', {})
        objects = scene['objects'] if scene else []
        candidate_rows.append({'key': key, 'name': row['name'], 'root': str(root), 'traffic_protocol': traffic_protocol, 'recording': row['recording'], 'location': row['location'], 'ego_track_id': row['ego_track_id'], 'first_frame': row['first_frame'], 'last_frame': row['first_frame'] + 225, 'split': split(row['location'], row['recording']), 'source_path_m': keys.get(key, {}).get('ego_path_m'), 'source_window_complete': keys.get(key, {}).get('source_window_complete'), 'source_catalog_rejection': keys.get(key, {}).get('source_rejection'), 'ego_source_last_frame': keys.get(key, {}).get('ego_source_last_frame'), 'turn_rad': keys.get(key, {}).get('turn_rad'), 'source_nearby_moving_actors': row['source_nearby_moving_actors'], 'source_nearby_vrus': row['source_nearby_vrus'], 'conversion_pass': row.get('conversion_pass', True), 'full_gate_ever_run': admission is not None, 'full_gate_current': admission_current, 'actor_classes': dict(Counter((o['type'] for o in objects))), 'source_track_ids': sorted((o['id'] for o in objects)), 'moving_track_ids': sorted((o['id'] for o in objects if o['source_window_path_length_m'] >= 1.0)), 'rule_ids': [r['id'] for r in semantic.get('governing_regulatory_elements', [])], 'crosswalk_ids': [r['lanelet_id'] for r in semantic.get('ego_box_crosswalk_contacts', [])], 'sign_ids': [r['id'] for r in semantic.get('nearby_source_signs', [])], 'binary_sha256': current_contract['files']['scene_binary']['sha256'] if current_contract else None, 'source_tracks_sha256': current_contract['files']['source_tracks_csv']['sha256'] if current_contract else None, 'source_lanelet2_sha256': current_contract['files']['source_lanelet2_map']['sha256'] if current_contract else None, 'source_opendrive_sha256': current_contract['files']['source_opendrive_map']['sha256'] if current_contract else None, 'source_background_sha256': current_contract['files']['source_background_image']['sha256'] if current_contract else None, 'source_recording_meta_sha256': current_contract['files']['source_recording_meta_csv']['sha256'] if current_contract else None, 'evaluator_ini_sha256': current_contract['files']['evaluation_ini']['sha256'] if current_contract else None, 'technical_admitted': bool(admission_current and admission['technical_admitted']), 'research_admitted': bool(admission_current and admission['research_admitted']), 'eligible_interaction_types': review.get('eligible_interaction_types', []), 'interaction_opportunity': bool(review.get('interaction_opportunity')), 'interaction_actor_ids': review.get('interaction_actor_ids', []), 'rejection_reasons': row['exclusion_reasons'] or (admission['exclusion_reasons'] if admission_current else ['stale_admission_contract'] if admission else ['full_gate_not_run'])})
    accepted = []
    by_recording = {}
    for row in sorted((r for r in candidate_rows if r['research_admitted']), key=lambda r: (r['location'], r['recording'], r['first_frame'], r['ego_track_id'])):
        previous = by_recording.setdefault(row['recording'], [])
        if any((not (row['last_frame'] < x['first_frame'] or row['first_frame'] > x['last_frame']) or set(row['moving_track_ids']) & set(x['moving_track_ids']) for x in previous)):
            row['rejection_reasons'].append('independence_overlap_or_shared_moving_track')
            continue
        previous.append(row)
        accepted.append(row)
    flow = {'schema_version': 6, 'traffic_protocol': traffic_protocol, 'split_policy': 'location 4 held out; other whole recordings with number divisible by 5 reserved for validation; independent windows and moving actor tracks within a recording; stationary parked tracks may recur, with recording as an inference cluster', 'duplicate_source_keys': duplicate_source_keys, 'source_catalog_rows_by_file': catalog_counts, 'source_map_preflight_rows_by_file': preflight_counts, 'source_windows': len(catalog), 'source_motion_pass': sum((r.get('source_motion_qualified', r['source_rejection'] is None) for r in catalog)), 'source_track_complete_pass': sum((r.get('source_window_complete', True) for r in catalog)), 'source_goal_timing_pass': sum((r['source_rejection'] is None for r in catalog)), 'source_map_preflight_pass': sum((r['outside_sample_count'] == 0 and r['directed_route'] for r in preflight)), 'screened_unique_windows': len(candidate_rows), 'conversion_pass': sum((r['conversion_pass'] for r in candidate_rows)), 'full_gate_ever_run': sum((r['full_gate_ever_run'] for r in candidate_rows)), 'full_gate_current': sum((r['full_gate_current'] for r in candidate_rows)), 'technical_admitted': sum((r['technical_admitted'] for r in candidate_rows)), 'research_admitted_before_independence': sum((r['research_admitted'] for r in candidate_rows)), 'research_admitted_independent': len(accepted), 'independent_interaction_scenes': sum((r['interaction_opportunity'] for r in accepted)), 'interaction_scenes_by_location': dict(Counter((r['location'] for r in accepted if r['interaction_opportunity']))), 'accepted_by_location': dict(Counter((r['location'] for r in accepted))), 'accepted_by_split': dict(Counter((r['split'] for r in accepted))), 'rejection_counts': dict(Counter((reason for r in candidate_rows for reason in r['rejection_reasons'])))}
    (AUDITS / f'step2_selection_flow{output_suffix}.json').write_text(json.dumps(flow, indent=2) + '\n')
    (AUDITS / f'step2_candidate_ledger{output_suffix}.json').write_text(json.dumps(candidate_rows, indent=2) + '\n')
    fields = ['name', 'root', 'traffic_protocol', 'recording', 'location', 'ego_track_id', 'first_frame', 'last_frame', 'split', 'source_path_m', 'turn_rad', 'source_nearby_moving_actors', 'source_nearby_vrus', 'actor_classes', 'rule_ids', 'crosswalk_ids', 'sign_ids', 'eligible_interaction_types', 'interaction_opportunity', 'interaction_actor_ids', 'binary_sha256', 'source_tracks_sha256', 'source_lanelet2_sha256', 'source_opendrive_sha256', 'source_background_sha256', 'source_recording_meta_sha256', 'evaluator_ini_sha256']
    with (AUDITS / f'step2_research_manifest{output_suffix}.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        for row in accepted:
            writer.writerow({k: json.dumps(row[k]) if isinstance(row[k], (list, dict)) else row[k] for k in fields})
    print(json.dumps(flow, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--extra-root', type=Path, action='append', default=[])
    ap.add_argument('--traffic-protocol', choices=('idm', 'hybrid_startup'), default='idm')
    args = ap.parse_args()
    main(args.extra_root, args.traffic_protocol)
