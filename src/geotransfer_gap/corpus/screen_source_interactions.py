"""Catalog aerial-review dependencies and rank source-only interaction candidates.

This is a cheap screening queue, never scene admission. Relative-corridor
crossing is deliberately broad; turns/sidewalks require source review.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import json
import math
import hashlib
from pathlib import Path
import numpy as np
repo = PROJECT_ROOT
reviews = []
for path in sorted(project_path('pilot').rglob('*review*.json')):
    try:
        d = json.loads(path.read_text())
    except (ValueError, OSError):
        continue
    if not isinstance(d, dict):
        continue
    if not any((k in d for k in ('source_image', 'source_surface_evidence', 'pair_resolutions', 'decision', 'rule_resolutions'))):
        continue
    reg = path.parent / 'source_image_registration.json'
    try:
        r = json.loads(reg.read_text())
    except (ValueError, OSError):
        r = {}
    provider = r.get('schema_version') == 2 and r.get('registration_is_estimate') is False and (r.get('local_x_at_image_x0_m') == 0) and (r.get('local_y_at_image_y0_m') == 0)
    reviews.append({'review': str(path.relative_to(repo)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'decision': d.get('decision'), 'registration': 'provider_projection' if provider else 'historical_or_missing', 'status': 'current_projection_requires_contract_check' if provider else 'superseded_aerial_decision_pending_rereview', 'source_image': d.get('source_image')})
project_path('pilot/audits/step2_projection_review_backlog.json').write_text(json.dumps({'schema_version': 1, 'scope': 'All discovered pilot/*review*.json decision records; original evidence retained. All non-provider aerial decisions superseded, including exclusions.', 'reviews': reviews}, indent=2) + '\n')
ledger = json.loads(project_path('pilot/audits/step2_candidate_ledger.json').read_text())
results = []
for r in ledger:
    root = Path(r['root'])
    files = list((root / 'testing').glob('ind_*.json'))
    if len(files) != 1:
        continue
    scene = json.loads(files[0].read_text())
    ego = scene['objects'][0]
    ep = np.array([[p['x'], p['y']] for p in ego['position']])
    eh = np.array(ego['heading'])
    ev = np.array([[p['x'], p['y']] for p in ego['velocity']])
    es = np.linalg.norm(ev, axis=1)
    goal = np.array([ego['goalPosition'][k] for k in ('x', 'y')])
    hits = np.flatnonzero(np.linalg.norm(ep - goal, axis=1) <= 2)
    terminal = int(hits[0]) if len(hits) else 91
    if terminal < 75:
        continue
    events = []
    for a in scene['objects'][1:]:
        ap = np.array([[p['x'], p['y']] for p in a['position']])
        valid = np.array(a['valid'], dtype=bool) & np.array(ego['valid'], dtype=bool)
        dist = np.linalg.norm(ap - ep, axis=1)
        valid[:12] = False
        valid[terminal:] = False
        if not valid.any() or min(dist[valid]) > 12:
            continue
        speed = np.linalg.norm(np.array([[p['x'], p['y']] for p in a['velocity']]), axis=1)
        t = int(np.argmin(np.where(valid, dist, np.inf)))
        delta = ap - ep
        along = delta[:, 0] * np.cos(eh) + delta[:, 1] * np.sin(eh)
        lat = -delta[:, 0] * np.sin(eh) + delta[:, 1] * np.cos(eh)
        if a['type'] != 'vehicle':
            idx = np.arange(10, terminal)
            idx = idx[np.array(a['valid'], dtype=bool)[idx]]
            cross = len(idx) > 1 and min(lat[idx]) < -0.8 and (max(lat[idx]) > 0.8) and (max(speed[idx]) > 0.5) and any((0 < along[j] < 20 and abs(lat[j]) < 1 for j in idx))
            if cross and dist[t] < 9:
                events.append({'kind': a['type'] + '_crossing', 'actor': a['id'], 'step': t, 'center_gap_m': round(float(dist[t]), 2), 'lateral_range_m': [round(float(min(lat[idx])), 2), round(float(max(lat[idx])), 2)], 'ego_speed_mps': round(float(es[t]), 2), 'terminal_step': terminal})
        else:
            hd = np.abs((np.array(a['heading']) - eh + np.pi) % (2 * np.pi) - np.pi)
            candidates = np.flatnonzero(valid & (along > 3) & (along < 18) & (abs(lat) < 1.8) & (hd < 0.35))
            for q in candidates:
                drop = float(max(es[max(10, q - 15):q + 1]) - es[q])
                if drop >= 1.5 and dist[q] < 12:
                    gp = ep[terminal] if terminal < 91 else goal
                    ahead = float((ap[q] - gp) @ np.array([math.cos(eh[q]), math.sin(eh[q])]))
                    if speed[q] < 1 and ahead > 0:
                        continue
                    events.append({'kind': 'vehicle_following_response', 'actor': a['id'], 'step': int(q), 'center_gap_m': round(float(dist[q]), 2), 'ego_speed_drop_mps': round(drop, 2), 'actor_speed_mps': round(float(speed[q]), 2), 'terminal_step': terminal})
                    break
    if events:
        results.append({'root': str(root), 'recording': r['recording'], 'location': r['location'], 'ego': ego['id'], 'first_frame': r['first_frame'], 'events': events, 'binary_sha256': hashlib.sha256((root / 'testing/map_000000.bin').read_bytes()).hexdigest()})
results.sort(key=lambda x: (x['location'] == 4, x['location'], x['recording'], min((e['center_gap_m'] for e in x['events'])), x['ego'], x['first_frame']))
project_path('pilot/audits/step2_expansion_source_queue.json').write_text(json.dumps({'schema_version': 1, 'selection': 'Existing converted source windows; timed ego-corridor crossing or aligned following with source speed response and no stopped-leader goal shortcut. Queue is screening, not admission; stable location/recording/source-gap ordering; no planner outcomes.', 'review_backlog_sha256': hashlib.sha256(project_path('pilot/audits/step2_projection_review_backlog.json').read_bytes()).hexdigest(), 'candidates': results}, indent=2) + '\n')
from collections import Counter
print('review_backlog', len(reviews), Counter((x['registration'] for x in reviews)))
print('source_queue', len(results), Counter((x['location'] for x in results)), Counter((e['kind'] for x in results for e in x['events'])))
for r in results[:35]:
    print(Path(r['root']).name, 'loc', r['location'], r['events'])
