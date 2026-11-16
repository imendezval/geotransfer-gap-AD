"""Source-only task screen using physical path crossings and straight following.

Uses raw CSV tracks, never planner outcomes. Crossing centerlines and temporal
proximity are conservative search criteria, not evidence of driver causality
or final admission. Other task types remain in the deferred source queue.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import math
import hashlib
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
HERE = PROJECT_ROOT

def sample(track, frames):
    valid = (frames >= track[0, 0]) & (frames <= track[-1, 0])
    xy = np.column_stack([np.interp(frames, track[:, 0], track[:, i]) for i in (1, 2)])
    velocity = np.column_stack([np.interp(frames, track[:, 0], track[:, i]) for i in (4, 5)])
    heading = np.interp(frames, track[:, 0], np.unwrap(np.deg2rad(track[:, 3])))
    return (xy, velocity, heading, valid)

def screen(ego, actor, kind, ego_dimensions=None, actor_dimensions=None):
    ep, ev, eh, emask = ego
    ap, av, ah, amask = actor
    end = int(np.flatnonzero(np.linalg.norm(ep - ep[85], axis=1) <= 2)[0])
    times = np.arange(91)
    valid = emask & amask & (times >= 15) & (times <= min(end - 5, 70))
    es = np.linalg.norm(ev, axis=1)
    speed = np.linalg.norm(av, axis=1)
    if not valid.any():
        return None
    if kind not in ('car', 'truck_bus') and ego_dimensions and actor_dimensions:
        ef = np.column_stack((np.cos(eh), np.sin(eh)))
        en = np.column_stack((-np.sin(eh), np.cos(eh)))
        af = np.column_stack((np.cos(ah), np.sin(ah)))
        an = np.column_stack((-np.sin(ah), np.cos(ah)))
        delta = ap[None, :, :] - ep[:, None, :]
        el, ew = ego_dimensions
        al, aw = actor_dimensions
        overlap = np.ones((91, 91), dtype=bool)
        for axes, is_ego in ((ef, True), (en, True), (af, False), (an, False)):
            axis = axes[:, None, :] if is_ego else axes[None, :, :]
            separation = abs((delta * axis).sum(axis=2))
            er = 0.5 * el * abs((ef[:, None, :] * axis).sum(axis=2)) + 0.5 * ew * abs((en[:, None, :] * axis).sum(axis=2))
            ar = 0.5 * al * abs((af[None, :, :] * axis).sum(axis=2)) + 0.5 * aw * abs((an[None, :, :] * axis).sum(axis=2))
            overlap &= separation <= er + ar + 1e-06
        motion = av / np.maximum(speed[:, None], 1e-09)
        sine = abs(ef[:, None, 0] * motion[None, :, 1] - ef[:, None, 1] * motion[None, :, 0])
        te = times[:, None]
        ta = times[None, :]
        overlap &= (sine >= math.sin(0.5)) & (te >= 15) & (ta >= 15) & (te <= end - 5) & (ta <= end - 5) & (abs(te - ta) <= 30) & emask[:, None] & amask[None, :] & (speed[None, :] > 0.5)
        indices = np.argwhere(overlap)
        if len(indices) == 0:
            return None
        i, j = min(indices, key=lambda ij: (abs(int(ij[0]) - int(ij[1])), abs((int(ij[0]) + int(ij[1])) / 2 - 45)))
        return {'kind': 'pedestrian_crossing' if kind == 'pedestrian' else 'cyclist_crossing', 'ego_path_crossing_step': int(i), 'actor_path_crossing_step': int(j), 'source_crossing_time_gap_s': abs(int(i) - int(j)) / 10, 'source_goal_first_entry_step': end, 'source_conflict_geometry': 'sampled_oriented_source_footprints'}
    if kind not in ('car', 'truck_bus'):
        u = np.diff(ep, axis=0)
        v = np.diff(ap, axis=0)
        q = ap[None, :-1, :] - ep[:-1, None, :]
        det = u[:, None, 0] * v[None, :, 1] - u[:, None, 1] * v[None, :, 0]
        safe = np.where(abs(det) > 1e-10, det, 1.0)
        s = (q[:, :, 0] * v[None, :, 1] - q[:, :, 1] * v[None, :, 0]) / safe
        t = (q[:, :, 0] * u[:, None, 1] - q[:, :, 1] * u[:, None, 0]) / safe
        te = times[:-1, None] + s
        ta = times[None, :-1] + t
        lengths = np.linalg.norm(u, axis=1)[:, None] * np.linalg.norm(v, axis=1)[None, :]
        angle = np.abs(det) / np.maximum(lengths, 1e-12)
        hit = (abs(det) > 1e-10) & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1) & (angle >= math.sin(0.5)) & (te >= 15) & (ta >= 15) & (te <= end - 5) & (ta <= end - 5) & (abs(te - ta) <= 30)
        hit &= (emask[:-1] & emask[1:])[:, None] & (amask[:-1] & amask[1:])[None, :] & (speed[:-1] > 0.5)[None, :]
        indices = np.argwhere(hit)
        if len(indices) == 0:
            return None
        i, j = min(indices, key=lambda ij: abs(te[tuple(ij)] - ta[tuple(ij)]))
        return {'kind': 'pedestrian_crossing' if kind == 'pedestrian' else 'cyclist_crossing', 'ego_path_crossing_step': float(te[i, j]), 'actor_path_crossing_step': float(ta[i, j]), 'source_crossing_time_gap_s': float(abs(te[i, j] - ta[i, j]) / 10), 'source_goal_first_entry_step': end}
    delta = ap - ep
    along = delta[:, 0] * np.cos(eh) + delta[:, 1] * np.sin(eh)
    lat = -delta[:, 0] * np.sin(eh) + delta[:, 1] * np.cos(eh)
    hd = np.abs((ah - eh + np.pi) % (2 * np.pi) - np.pi)
    for t in np.flatnonzero(valid & (along > 3) & (along < 15) & (abs(lat) < 1.5) & (hd < 0.25)):
        start = max(10, t - 15)
        prior = start + int(es[start:t + 1].argmax())
        drop = float(es[prior] - es[t])
        turn = abs((eh[t] - eh[prior] + np.pi) % (2 * np.pi) - np.pi)
        if drop < 1.5 or turn > 0.2 or speed[t] > es[prior]:
            continue
        goal_ahead = (ap[t] - ep[end]) @ np.array([math.cos(eh[t]), math.sin(eh[t])])
        if speed[t] < 1 and goal_ahead > 0:
            continue
        return {'kind': 'lead_vehicle_braking_response', 'decision_step': int(t), 'ego_speed_drop_mps': drop, 'ego_heading_change_rad': float(turn), 'lead_speed_mps': float(speed[t]), 'source_goal_first_entry_step': end}
    return None

def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--selection', type=Path, default=project_path('pilot/audits/step2_oriented_source_selection.json'))
    ap.add_argument('--output', type=Path, default=project_path('pilot/audits/step2_source_task_selection.json'))
    args = ap.parse_args()
    source = args.selection
    raw = json.loads(source.read_text())
    rows = raw.get('source_pairs_before_dedup', raw['remaining_source_queue'])
    results = []
    rejected = []
    for rec in sorted({r['recording'] for r in rows}):
        todo = [r for r in rows if r['recording'] == rec]
        ids = {r[k] for r in todo for k in ('ego', 'actor')}
        df = pd.read_csv(settings().source / f'data/{rec:02d}_tracks.csv', usecols=['frame', 'trackId', 'xCenter', 'yCenter', 'heading', 'xVelocity', 'yVelocity'])
        df = df[df.trackId.isin(ids)]
        tracks = {int(i): g[['frame', 'xCenter', 'yCenter', 'heading', 'xVelocity', 'yVelocity']].to_numpy(dtype=float) for i, g in df.groupby('trackId', sort=False)}
        with (settings().source / f'data/{rec:02d}_tracksMeta.csv').open() as stream:
            metadata = {int(r['trackId']): r for r in csv.DictReader(stream)}

        def dimensions(tid):
            m = metadata[tid]
            defaults = (0.6, 0.6) if m['class'] == 'pedestrian' else (1.8, 0.6) if m['class'] == 'bicycle' else (4.5, 1.8)
            length = float(m['length'])
            width = float(m['width'])
            return (length if length > 0 else defaults[0], width if width > 0 else defaults[1])
        for row in todo:
            frames = row['first_frame'] + np.arange(91) * 2.5
            evidence = screen(sample(tracks[row['ego']], frames), sample(tracks[row['actor']], frames), row['actor_class'], dimensions(row['ego']), dimensions(row['actor']))
            if evidence:
                results.append(dict(row, task_evidence=evidence))
            else:
                rejected.append({'recording': rec, 'ego': row['ego'], 'first_frame': row['first_frame'], 'actor': row['actor'], 'reason': 'No qualifying physical crossing/straight-following response under the fixed source screen; other task claims require separate review.'})
        print('recording', rec, 'source task positives', len(results), flush=True)
    results.sort(key=lambda r: (r['location'], round(r['task_evidence'].get('source_crossing_time_gap_s', 3), 3), abs((r['task_evidence'].get('ego_path_crossing_step', r.get('source_nearest_step', 45)) + r['task_evidence'].get('actor_path_crossing_step', r.get('source_nearest_step', 45))) / 2 - 45), r['recording'], r['ego'], r['first_frame']))
    all_source_positive_pairs = list(results)
    unique = []
    seen_ego = set()
    seen_actor = set()
    for r in results:
        ek = (r['recording'], r['ego'])
        ak = (r['recording'], r['actor'])
        if ek in seen_ego or ak in seen_actor:
            continue
        unique.append(r)
        seen_ego.add(ek)
        seen_actor.add(ak)
    all_positive_count = len(results)
    results = unique
    cohort = []
    for location in (1, 2, 3, 4):
        for kind in ('pedestrian_crossing', 'cyclist_crossing', 'lead_vehicle_braking_response'):
            cohort.extend([r for r in results if r['location'] == location and r['task_evidence']['kind'] == kind][:12])
    report = {'schema_version': 1, 'source_selection_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'screen_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'selection': 'Oriented source-body path overlap with crossing angle>=0.5rad and actor speed>0.5m/s, both events steps15 through task-end-minus5, within3s; or aligned straight following with ego speed drop>=1.5m/s and no stopped-leader goal shortcut. First12 per location and task category, by source timing only; crossing-time gaps rounded to1ms for ranking and event midpoint preferred near45. All positive window variants retained for fidelity-screen fallbacks before final corpus deduplication; no planner outcomes.', 'source_positive_pairs_before_dedup': all_positive_count, 'source_positive_pairs': all_source_positive_pairs, 'eligible_task_candidates': len(results), 'jobs': cohort, 'remaining_source_queue': results, 'source_task_screen_rejections': rejected}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('task positives', len(results), 'cohort', len(cohort), 'types', dict(Counter((r['task_evidence']['kind'] for r in results))))
if __name__ == '__main__':
    main()
