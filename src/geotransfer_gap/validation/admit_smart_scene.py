"""Planner-specific SMART admission over the mandatory technical scene gate."""
from geotransfer_gap.conversion import binary
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
from geotransfer_gap.artifacts import sha256 as sha
import argparse
import csv
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np
from geotransfer_gap.validation import scene_contract
from geotransfer_gap.maps.audit_rule_applicability import polygon_of, box_distance, box_path_clearance
from geotransfer_gap.validation.audit_physical_source import corners
from geotransfer_gap.maps.audit_task_rule_scope import stop_scope
from geotransfer_gap.corpus.screen_source_restarts import restart
from geotransfer_gap.maps.audit_following_scope import audit as following_scope, heuristic_flags
from geotransfer_gap.maps.audit_directed_rule_scope import audit as directed_rule_scope
from geotransfer_gap.maps.audit_source_route_sequence import audit as source_route_sequence
HERE = PROJECT_ROOT

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--us-root', type=Path, required=True)
    ap.add_argument('--traffic-protocol', choices=('idm', 'hybrid_startup'), default='hybrid_startup')
    args = ap.parse_args()
    root, us = (args.root.resolve(), args.us_root.resolve())
    testing = root / 'testing'
    checks, details = ({}, {})

    def check(name, ok, detail=None):
        checks[name] = bool(ok)
        if detail is not None:
            details[name] = detail

    def read(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
    current = scene_contract.build(root, 'expert')
    suffix = '' if args.traffic_protocol == 'idm' else '_hybrid_startup'
    base_path = testing / f'admission{suffix}.json'
    base = read(base_path)
    check('technical_gate_current', base.get('contract') == current and base.get('technical_admitted'))
    check('rule_audit_current', base.get('checks', {}).get('rule_audit_current'))
    lateral_path = project_path('pilot/audits/source_lane_change_native_oracle.json')
    lateral = read(lateral_path)
    check('legal_lane_change_oracle_current', lateral.get('passed') and lateral.get('lane_change_tool_sha256') == sha(project_path('source_lane_changes.py')) and (lateral.get('converter_sha256') == sha(project_path('pilot_ind.py'))) and any((r.get('source_sha256') == current['files']['source_lanelet2_map']['sha256'] for r in lateral.get('maps', []))))
    check('interaction_audit_current', base.get('checks', {}).get('interaction_audit_current'))
    binary_hash = current['files']['scene_binary']['sha256']
    probe_path = testing / 'smart_map_transfer_all_actors_probe.json'
    us_probe_path = us / 'testing/smart_map_transfer_all_actors_probe.json'
    probe, us_probe = (read(probe_path), read(us_probe_path))
    paths = {'adapter': project_path('faithful_smart.py'), 'probe': project_path('probe_smart_map_transfer.py'), 'map_preprocessing': project_path('faithful_map.py'), 'smart_planner': settings().bench / 'pufferlib/planning/smart.py', 'tokenizer': settings().bench / 'pufferlib/prediction/map_tokenizer.py', 'training_dataset': settings().bench / 'pufferlib/prediction/dataset.py', 'map_codebook': settings().bench / 'pufferlib/prediction/smart/tokens/map_traj_token5.pkl', 'motion_codebook': settings().bench / 'pufferlib/prediction/smart/tokens/cluster_frame_5_2048.pkl', 'evaluation_ini': settings().bench / 'pufferlib/config/evaluation.ini'}
    hashes = {k: sha(v) for k, v in paths.items()}
    weights_hash = sha(settings().bench / 'weights/SMART_epoch_030.pt')
    traffic_evidence = []
    if args.traffic_protocol == 'hybrid_startup':
        parity_path = project_path('pilot/audits/hybrid_protocol_us_parity.json')
        parity = read(parity_path)
        us_source = Path(parity.get('us_source_json', '/missing'))
        us_binary = Path(parity.get('us_binary_path', '/missing'))
        check('traffic_us_mechanics_current', parity.get('mechanical_parity_pass') and us_source.is_file() and us_binary.is_file() and (parity.get('us_source_sha256') == sha(us_source)) and (parity.get('us_binary_sha256') == sha(us_binary)) and (parity.get('runtime_source_sha256') == current['runtime_source_sha256']) and (parity.get('evaluator_ini_sha256') == hashes['evaluation_ini']) and (parity.get('hybrid_protocol_sha256') == sha(project_path('hybrid_traffic.py'))))
        traffic_evidence = [parity_path, us_source, us_binary]
    for name, report, scene_binary in [('german', probe, testing / 'map_000000.bin'), ('us', us_probe, us / 'testing/map_000000.bin')]:
        check(name + '_input_probe_current', report.get('protocol_file_sha256') == hashes and report.get('checkpoint_sha256') == weights_hash and (report.get('maps', {}).get('german', {}).get('binary_sha256') == sha(scene_binary)) and (report.get('runtime_source_sha256') == current['runtime_source_sha256']))
        rows = report.get('rollout', [])
        boot = report.get('prepare_step_bootstrap', {})
        features = report.get('source_feature_audit', {})
        check(name + '_source_features_faithful', len(set(features.get('steps', []))) >= 20 and features.get('presence_mismatches') == 0 and (features.get('class_mismatches') == 0) and (features.get('max_position_error_m', math.inf) < 0.01) and (features.get('max_local_position_error_m', math.inf) < 0.01) and (features.get('max_heading_error_rad', math.inf) < 0.01) and (features.get('max_evaluator_velocity_error_mps', math.inf) < 0.01) and (features.get('max_dimension_error_m', math.inf) < 0.01), features)
        check(name + '_input_probe_pass', report.get('future_mutation_invariant_at_reset') and report.get('warmup_steps') == 10 and (report.get('evaluator_goal') == {'radius_m': 2.0, 'max_speed_mps': 20.0}) and (report.get('planner_config') == {'history_steps': 11, 'prediction_interval_steps': 5, 'dt': 0.1, 'greedy': True, 'device': 'cpu'}) and (report.get('map_frame_position_error_m', math.inf) < 0.01) and (report.get('perturbed_ego_input_error_m', math.inf) < 0.01) and report.get('inference_finite') and (report.get('nonfinite_smart_input_headings') == 0) and boot.get('ready') and (boot.get('history_steps') == 11) and boot.get('current_positions_match') and boot.get('finite_headings') and (len(rows) >= 10) and all((row.get('finite_action') for row in rows)) and all((row.get('identity_match') for row in rows if row.get('prediction_refreshed'))))
    check('us_german_distinct', sha(us / 'testing/map_000000.bin') != binary_hash)
    audit = read(testing / 'rule_applicability_audit.json')
    interaction = read(testing / ('interaction_fidelity_audit.json' if args.traffic_protocol == 'idm' else 'interaction_fidelity_audit_hybrid_startup.json'))
    review_path = testing / f'semantic_review_smart_{args.traffic_protocol}.json'
    review = read(review_path)
    expected = {'regulatory_element': {x['id'] for x in audit.get('governing_regulatory_elements', [])}, 'crosswalk': {x['lanelet_id'] for x in audit.get('ego_box_crosswalk_contacts', [])}, 'sign': {x['id'] for x in audit.get('nearby_source_signs', [])}, 'omitted_marking': {x['id'] for x in audit.get('nearby_omitted_markings', [])}}
    resolutions = review.get('rule_resolutions', [])
    represented = {x.get('source_id') for x in resolutions if x.get('kind') == 'crosswalk' and x.get('resolution') == 'represented_in_planner'}
    meta_path = Path(current['files']['source_recording_meta_csv']['path'])
    with meta_path.open() as stream:
        meta = next(csv.DictReader(stream))
    osm = ET.parse(current['files']['source_lanelet2_map']['path']).getroot()
    nodes = lanelet.project_nodes(osm, float(meta['xUtmOrigin']), float(meta['yUtmOrigin']))
    ways = {int(w.get('id')): [nodes[int(n.get('ref'))] for n in w.findall('nd')] for w in osm.findall('way')}
    rels = {int(r.get('id')): r for r in osm.findall('relation')}
    binary = binary.read_binary(testing / 'map_000000.bin')
    roads = {r['id']: r for r in binary['roads'] if r['type'] == 8}
    sys.path.insert(0, str(settings().bench))
    from pufferlib.prediction.map_tokenizer import load_map_codebook
    from geotransfer_gap.planners.faithful_map import tokenize_roads, PROTOCOL_VERSION as MAP_ENCODING_PROTOCOL
    from geotransfer_gap.planners.faithful_smart import PROTOCOL_VERSION as PLANNER_PROTOCOL
    check('shared_map_encoding_protocol', probe.get('map_encoding_protocol') == us_probe.get('map_encoding_protocol') == MAP_ENCODING_PROTOCOL)
    codebook = load_map_codebook()
    coverage = {}
    for rid in represented:
        road = roads.get(rid)
        poly = polygon_of(rels[rid], ways) if rid in rels else None
        encoded = list(zip(road['polyline_x'], road['polyline_y'])) if road else []
        correct = bool(poly and len(poly) == len(encoded) and all((math.dist(a, b) < 0.01 for a, b in zip(poly, encoded))))
        tokens = tokenize_roads([road], codebook)['pt_token']['type'] if road else []
        coverage[str(rid)] = bool(correct and len(tokens) > 0 and all((int(t) == 8 for t in tokens)))
    check('represented_crosswalks_reach_smart', all(coverage.values()) and represented <= expected['crosswalk'], coverage)
    check('actual_planner_map_tokens', probe.get('actual_planner_crosswalk_tokens') == probe.get('maps', {}).get('german', {}).get('crosswalk_tokens'))
    unsupported = base.get('details', {}).get('source_supported_irrelevance_plausible', [])
    remaining = [x for x in unsupported if not any((x.startswith(f'crosswalk_{rid}_vru_') for rid in represented))]
    scope = stop_scope(root)
    scope_path = testing / 'source_task_rule_scope.json'
    scope_path.write_text(json.dumps(scope, indent=2) + '\n')
    reviewed_stop_ids = set(review.get('stop_rules_outside_task', []))
    scoped_stop_ids = {r['rule_id'] for r in scope['rules'] if r['stop_obligation_outside_task']}
    scope_bound = not reviewed_stop_ids or (reviewed_stop_ids <= scoped_stop_ids and review.get('task_rule_scope_sha256') == sha(scope_path))
    check('stop_scope_review_bound', scope_bound, scope)
    if scope['rules'] and scope_bound and (reviewed_stop_ids == {r['rule_id'] for r in scope['rules']}) and (reviewed_stop_ids == scoped_stop_ids):
        remaining = [x for x in remaining if x != 'ego_stop_sign_requires_stop_even_without_conflicting_traffic']
    reviewed_following = set(review.get('same_route_following_actor_ids', []))
    following = following_scope(root, reviewed_following)
    following_path = testing / 'source_following_scope.json'
    following_path.write_text(json.dumps(following, indent=2) + '\n')
    flags = heuristic_flags(audit)
    certified = {x['actor_id'] for x in following['actors'] if x['same_route_following']}
    following_bound = not reviewed_following or (reviewed_following <= certified and reviewed_following <= set(flags.values()) and (review.get('following_scope_sha256') == sha(following_path)))
    check('following_scope_review_bound', following_bound, following)
    if following_bound:
        remaining = [x for x in remaining if not (x in flags and flags[x] in reviewed_following)]
    directed = directed_rule_scope(root)
    directed_path = testing / 'source_directed_rule_scope.json'
    directed_path.write_text(json.dumps(directed, indent=2) + '\n')
    reviewed_directed = set(review.get('non_ego_yield_rule_ids', []))
    certified_directed = {r['rule_id'] for r in directed['rules'] if r['overlap_only_non_ego_yield_approach']}
    directed_bound = not reviewed_directed or (reviewed_directed <= certified_directed and review.get('directed_rule_scope_sha256') == sha(directed_path))
    check('directed_rule_scope_review_bound', directed_bound, directed)
    if directed_bound:
        remaining = [x for x in remaining if not any((x.startswith(f'rule_{rid}_priority_') for rid in reviewed_directed))]
    check('no_unrepresented_applicable_rules', not remaining, remaining)
    image = testing / review.get('source_image', 'missing')
    reg = read(testing / 'source_image_registration.json')
    check('manual_review_current', review.get('binary_sha256') == binary_hash and review.get('rule_audit_sha256') == sha(testing / 'rule_applicability_audit.json') and image.is_file() and (review.get('source_image_sha256') == sha(image)) and (review.get('interaction_source_digest') == interaction.get('source_evidence_digest')) and (reg.get('schema_version') == 2) and (reg.get('registration_is_estimate') is False) and (reg.get('binary_sha256') == binary_hash) and (reg.get('background_sha256') == current['files']['source_background_image']['sha256']) and (reg.get('local_x_at_image_x0_m') == 0) and (reg.get('local_y_at_image_y0_m') == 0) and math.isclose(reg.get('pixel_scale_m', -1), lanelet.background_pixel_scale(meta), abs_tol=1e-10))
    complete = review.get('schema_version') == 2 and review.get('decision') == 'admit' and (review.get('review_status') == 'complete') and (review.get('scope') == 'recorded_window_and_tested_interaction') and (review.get('ego_track_id') == current['ego_track_id']) and all(({r.get('source_id') for r in resolutions if r.get('kind') == kind} == ids for kind, ids in expected.items())) and (len(resolutions) == sum((len(ids) for ids in expected.values()))) and all((len(r.get('source_evidence', '')) >= 80 and r.get('source_steps') and (r.get('resolution') == 'source_supported_irrelevance' or (r.get('kind') == 'crosswalk' and r.get('resolution') == 'represented_in_planner')) for r in resolutions)) and (set(review.get('reviewed_boundary_way_ids', [])) == {x['way_id'] for x in audit.get('ego_lanelet_boundaries', [])}) and (len(review.get('source_surface_evidence', '')) >= 100) and (len(set(review.get('source_surface_steps', []))) >= 3) and (len(review.get('boundary_and_lane_change_evidence', '')) >= 80)
    check('manual_review_complete', complete)
    geometry = read(testing / 'map_audit.json')
    lateral_required = not geometry.get('occupied_start_to_occupied_goal_reachable_following_only', False)
    sequence_path = testing / 'source_route_sequence.json'
    if lateral_required:
        sequence = source_route_sequence(root)
        sequence_path.write_text(json.dumps(sequence, indent=2) + '\n')
        used = {(r['source'], r['target'], r['shared_boundary_way']) for r in sequence['used_lane_changes']}
        reviewed = {(r['source'], r['target'], r['shared_boundary_way']) for r in review.get('reviewed_source_lane_changes', [])}
        lateral_review = sequence['source_path_legal'] and bool(used) and (used == reviewed) and (review.get('source_route_sequence_sha256') == sha(sequence_path))
    else:
        lateral_review = True
    check('source_lateral_route_review_bound', lateral_review)
    ids = review.get('interaction_actor_ids', [])
    opportunities = {x['track_id']: x for x in interaction.get('actor_opportunities', [])}
    observed = interaction.get('idm_observed_steps', 0)
    decision_steps = review.get('interaction_decision_steps', [])
    crossing_evidence = []
    if review.get('interaction_opportunity') and any(('crossing' in t for t in review.get('eligible_interaction_types', []))):
        scene = json.loads(next(testing.glob('ind_*.json')).read_text())
        ego = copy.copy(scene['objects'][0])
        goal = ego['goalPosition']
        end = next((t for t, pt in enumerate(ego['position']) if ego['valid'][t] and math.hypot(pt['x'] - goal['x'], pt['y'] - goal['y']) <= 2.0), 90)
        ego['valid'] = [int(bool(v) and 10 <= t <= end) for t, v in enumerate(ego['valid'])]
        for obj in scene['objects']:
            if obj['id'] not in ids:
                continue
            actor = copy.copy(obj)
            actor['valid'] = [int(bool(v) and 10 <= t <= end) for t, v in enumerate(obj['valid'])]
            evidence = box_path_clearance(ego, actor) if any(actor['valid']) else {}
            crossing_evidence.append({'actor_id': obj['id'], **evidence})
    check('crossing_claim_has_source_path_conflict', not crossing_evidence or all((e.get('minimum_spatial_box_gap_m', math.inf) < 0.01 for e in crossing_evidence)), crossing_evidence)
    shortcuts = []
    restart_bounds = []
    if review.get('interaction_opportunity') and any((t.startswith('lead_vehicle_') for t in review.get('eligible_interaction_types', []))):
        scene = json.loads(next(testing.glob('ind_*.json')).read_text())
        ego = scene['objects'][0]
        objects = {o['id']: o for o in scene['objects']}
        goal = ego['goalPosition']
        if any((k in review.get('eligible_interaction_types', []) for k in ('lead_vehicle_stop_and_restart', 'lead_vehicle_constrained_following'))):

            def observed_arrays(obj):
                return (np.asarray([[v['x'], v['y']] for v in obj['position']]), np.asarray([[v['x'], v['y']] for v in obj['velocity']]), np.asarray(obj['heading']), np.asarray(obj['valid'], dtype=bool))
            for actor_id in ids:
                actor = objects.get(actor_id)
                evidence = restart(observed_arrays(ego), observed_arrays(actor), ego['length'], actor['length'], ego['width'], actor['width'], moving_queue='lead_vehicle_constrained_following' in review.get('eligible_interaction_types', [])) if actor and actor['type'] == 'vehicle' else None
                restart_bounds.append({'actor_id': actor_id, 'source_restart_evidence': evidence})
        entry = next((t for t, point in enumerate(ego['position']) if ego['valid'][t] and math.hypot(point['x'] - goal['x'], point['y'] - goal['y']) < 2.0), None)
        for actor_id in ids:
            actor = objects.get(actor_id)
            step = opportunities.get(actor_id, {}).get('source_box_step')
            if not actor or actor['type'] != 'vehicle' or step is None or (entry is None):
                continue
            velocity = actor['velocity'][step]
            if math.hypot(velocity['x'], velocity['y']) >= 1.0:
                continue
            h = ego['heading'][step]
            delta = abs((actor['heading'][step] - h + math.pi) % (2 * math.pi) - math.pi)
            if delta >= 0.35:
                continue
            if abs((ego['heading'][entry] - h + math.pi) % (2 * math.pi) - math.pi) >= 0.35:
                continue
            candidate = ego['position'][entry]
            ahead = (actor['position'][step]['x'] - candidate['x']) * math.cos(h) + (actor['position'][step]['y'] - candidate['y']) * math.sin(h)
            gap = box_distance(corners(ego, entry), corners(actor, step))
            if ahead > 0 and gap > 0:
                shortcuts.append({'actor_id': actor_id, 'source_step': step, 'source_goal_entry_step': entry, 'goal_completion_box_gap_m': gap, 'reason': 'A collision-free goal completion exists before the stopped leader; no lead-response claim is justified.'})
    check('longitudinal_goal_requires_claimed_response', not shortcuts, shortcuts)
    if 'lead_vehicle_stop_and_restart' in review.get('eligible_interaction_types', []):
        check('restart_goal_region_bound', len(restart_bounds) == len(ids) and all((x['source_restart_evidence'] is not None and x['source_restart_evidence']['goal_disk_beyond_stopped_leader_collision_interval_m'] > 0 for x in restart_bounds)), restart_bounds)
    if 'lead_vehicle_constrained_following' in review.get('eligible_interaction_types', []):
        check('constrained_following_task_bound', len(restart_bounds) == len(ids) and all((x['source_restart_evidence'] is not None for x in restart_bounds)), restart_bounds)
    check('claimed_actors_reach_model_at_encounter', all((any((row.get('prediction_refreshed') and abs(row['step'] - opportunities.get(actor, {}).get('source_box_step', -1000)) <= 5 and (actor in row.get('model_track_ids', [])) for row in probe.get('rollout', []))) for actor in ids)))
    check('interaction_supported', bool(review.get('eligible_interaction_types')) and isinstance(ids, list) and (bool(ids) and len(review.get('interaction_decision_evidence', '')) >= 120 and (len(set(decision_steps)) >= 2) and all((isinstance(t, int) and 0 <= t < observed for t in decision_steps)) and all((opportunities.get(i, {}).get('preserved_for_claimed_interaction') and any((abs(t - opportunities[i]['source_box_step']) <= 10 for t in decision_steps)) for i in ids)) if review.get('interaction_opportunity') else ids == [] and all((t.startswith('uncontested_') for t in review.get('eligible_interaction_types', [])))))
    context_failures = []
    source_scene = json.loads(next(testing.glob('ind_*.json')).read_text())
    source_ego = source_scene['objects'][0]
    source_objects = {o['id']: o for o in source_scene['objects']}
    goal = source_ego['goalPosition']
    end = next((t for t, pt in enumerate(source_ego['position']) if math.hypot(pt['x'] - goal['x'], pt['y'] - goal['y']) <= 2), 90)
    for actor_id, opportunity in opportunities.items():
        if opportunity['preserved_for_claimed_interaction'] or opportunity['source_close_steps_after_warmup'] == 0:
            continue
        actor = source_objects[actor_id]
        step = opportunity['source_box_step']
        if actor['type'] != 'vehicle':
            continue
        h = source_ego['heading'][step]
        ep = source_ego['position'][step]
        ap = actor['position'][step]
        ahead = (ap['x'] - ep['x']) * math.cos(h) + (ap['y'] - ep['y']) * math.sin(h)
        lateral = abs(-(ap['x'] - ep['x']) * math.sin(h) + (ap['y'] - ep['y']) * math.cos(h))
        angle = abs((actor['heading'][step] - h + math.pi) % (2 * math.pi) - math.pi)
        if ahead <= 0 or lateral >= 1.5 or angle >= 0.35:
            continue
        blocked = [t for t in range(max(10, step), end + 1) if box_distance(corners(source_ego, t), corners(actor, step)) < 0.01]
        if blocked:
            context_failures.append({'actor_id': actor_id, 'source_reference_step': step, 'blocked_source_route_steps': blocked, 'reason': 'An unpreserved preceding vehicle occupies the required source route before goal completion.'})
    check('essential_leading_context_preserved', not context_failures, context_failures)
    result = {'schema_version': 1, 'gate_sha256': sha(Path(__file__)), 'planner_protocol': PLANNER_PROTOCOL, 'map_encoding_protocol': MAP_ENCODING_PROTOCOL, 'traffic_protocol': args.traffic_protocol, 'evaluator_goal': probe.get('evaluator_goal'), 'warmup_steps': 10, 'planner_config': probe.get('planner_config'), 'contract': current, 'research_admitted': all(checks.values()), 'checks': checks, 'details': details, 'evidence_sha256': {str(path): sha(path) for path in [base_path, probe_path, us_probe_path, review_path, testing / 'rule_applicability_audit.json', testing / 'source_image_registration.json', image, testing / ('interaction_fidelity_audit.json' if args.traffic_protocol == 'idm' else 'interaction_fidelity_audit_hybrid_startup.json'), us / 'testing/map_000000.bin', settings().bench / 'weights/SMART_epoch_030.pt', project_path('probe_faithful_smart_closed_loop.py'), project_path('audit_task_rule_scope.py'), project_path('screen_source_restarts.py'), project_path('screen_source_tasks.py'), project_path('audit_following_scope.py'), project_path('audit_directed_rule_scope.py'), directed_path, project_path('source_lane_changes.py'), lateral_path, project_path('audit_source_route_sequence.py'), sequence_path, scope_path, following_path, *traffic_evidence, *paths.values()] if path.is_file()}, 'exclusion_reasons': [key for key, value in checks.items() if not value]}
    (testing / f'admission_smart_{args.traffic_protocol}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'research_admitted': result['research_admitted'], 'exclusion_reasons': result['exclusion_reasons']}))
    if not result['research_admitted']:
        sys.exit(1)
if __name__ == '__main__':
    main()
