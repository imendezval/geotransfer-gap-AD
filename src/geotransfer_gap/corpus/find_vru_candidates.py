"""Rank recorded late-VRU windows with a moving, nearby vehicle ego."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from geotransfer_gap.conversion.pilot_ind import SOURCE

def candidates(recording):
    meta = list(csv.DictReader((SOURCE / f'data/{recording:02d}_tracksMeta.csv').open()))
    cars = [r for r in meta if r['class'] in ('car', 'truck_bus')]
    vrus = [r for r in meta if r['class'] in ('pedestrian', 'bicycle')]
    pairs = []
    for vru in vrus:
        birth = int(vru['initialFrame'])
        for ego in cars:
            start = max(int(ego['initialFrame']), birth - 50)
            if start + 225 <= int(ego['finalFrame']) and start + 5 <= birth <= start + 190:
                pairs.append((int(ego['trackId']), int(vru['trackId']), start, birth))
    target_ids = {i for ego, vru, _, _ in pairs for i in (ego, vru)}
    tracks = {i: [] for i in target_ids}
    with (SOURCE / f'data/{recording:02d}_tracks.csv').open() as f:
        for row in csv.DictReader(f):
            tid = int(row['trackId'])
            if tid in tracks:
                tracks[tid].append((int(row['frame']), float(row['xCenter']), float(row['yCenter'])))
    arrays = {i: np.asarray(rows) for i, rows in tracks.items() if rows}
    rows = []
    for ego, vru, start, birth in pairs:
        e, v = (arrays[ego], arrays[vru])
        ep = lambda f: (float(np.interp(f, e[:, 0], e[:, 1])), float(np.interp(f, e[:, 0], e[:, 2])))
        vp = lambda f: (float(np.interp(f, v[:, 0], v[:, 1])), float(np.interp(f, v[:, 0], v[:, 2])))
        move = math.dist(ep(start), ep(start + 225))
        near = math.dist(ep(birth), vp(birth))
        if move < 15 or near > 55:
            continue
        rows.append({'recording': recording, 'ego': ego, 'first_frame': start, 'vru': vru, 'vru_class': next((x['class'] for x in vrus if int(x['trackId']) == vru)), 'birth_frame': birth, 'birth_step_approx': (birth - start) / 2.5, 'ego_displacement_m': move, 'ego_vru_distance_at_birth_m': near})
    return rows
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--recordings', type=int, nargs='+', default=list(range(33)))
    ap.add_argument('--output', type=Path, default=Path(__file__).parent / 'pilot/audits/vru_candidates.json')
    args = ap.parse_args()
    found = []
    for rec in args.recordings:
        found.extend(candidates(rec))
    found.sort(key=lambda x: (x['ego_vru_distance_at_birth_m'], -x['ego_displacement_m']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(found, indent=2) + '\n')
    print(json.dumps({'candidate_pairs': len(found), 'top_20': found[:20]}, indent=2))
