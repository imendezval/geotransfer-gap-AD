"""Enumerate source-only 9 s inD windows without selecting on map semantics.

The stride is recorded.  Sliding search windows may overlap; accepted corpus
windows are made independent later. This is a candidate ledger, not admission.
"""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from geotransfer_gap.conversion.pilot_ind import SOURCE

def source_windows(output, minimum_motion=15.0, proximity=12.0, stride_frames=225, locations=None, minimum_displacement=10.0):
    rows = []
    for recording in range(33):
        stem = SOURCE / f'data/{recording:02d}'
        with (SOURCE / f'data/{recording:02d}_recordingMeta.csv').open() as f:
            location = int(next(csv.DictReader(f))['locationId'])
        if locations and location not in locations:
            continue
        with (SOURCE / f'data/{recording:02d}_tracksMeta.csv').open() as f:
            meta = {int(r['trackId']): r for r in csv.DictReader(f)}
        df = pd.read_csv(SOURCE / f'data/{recording:02d}_tracks.csv', usecols=['frame', 'trackId', 'xCenter', 'yCenter', 'heading'])
        tracks = {int(tid): group[['frame', 'xCenter', 'yCenter', 'heading']].to_numpy(dtype=float) for tid, group in df.groupby('trackId', sort=False)}
        for ego_id, track in tracks.items():
            m = meta[ego_id]
            if m['class'] not in ('car', 'truck_bus'):
                continue
            first, last = (int(track[0, 0]), int(track[-1, 0]))
            for start in range(first, last - 224 + 1, stride_frames):
                sample_frames = start + np.arange(91) * 2.5
                x = np.interp(sample_frames, track[:, 0], track[:, 1])
                y = np.interp(sample_frames, track[:, 0], track[:, 2])
                length = float(np.hypot(np.diff(x), np.diff(y)).sum())
                displacement = float(math.hypot(x[-1] - x[0], y[-1] - y[0]))
                h = np.interp(sample_frames, track[:, 0], np.unwrap(np.deg2rad(track[:, 3])))
                turn = float(abs((h[85] - h[0] + math.pi) % (2 * math.pi) - math.pi))
                goal_distance = np.hypot(x - x[85], y - y[85])
                first_goal_radius_step = int(np.flatnonzero(goal_distance <= 2.0)[0])
                motion_qualified = length >= minimum_motion and displacement >= minimum_displacement
                source_window_complete = sample_frames[-1] <= last
                reason = 'ego_source_track_incomplete' if not source_window_complete else 'insufficient_ego_motion' if not motion_qualified else 'early_goal_radius_entry' if first_goal_radius_step < 75 else None
                near = []
                if reason is None:
                    for actor_id, other in tracks.items():
                        if actor_id == ego_id or int(other[0, 0]) > sample_frames[-1] or int(other[-1, 0]) < start:
                            continue
                        valid = (sample_frames >= other[0, 0]) & (sample_frames <= other[-1, 0])
                        if not valid.any():
                            continue
                        ax = np.interp(sample_frames[valid], other[:, 0], other[:, 1])
                        ay = np.interp(sample_frames[valid], other[:, 0], other[:, 2])
                        distance = np.hypot(x[valid] - ax, y[valid] - ay)
                        nearest = float(distance.min())
                        actor_window_path_m = float(np.hypot(np.diff(ax), np.diff(ay)).sum())
                        moving = actor_window_path_m >= 1.0
                        if nearest <= proximity:
                            near.append({'track_id': actor_id, 'class': meta[actor_id]['class'], 'moving': moving, 'minimum_timed_center_distance_m': nearest, 'source_actor_window_path_m': actor_window_path_m, 'nearest_step': int(np.flatnonzero(valid)[int(distance.argmin())])})
                near.sort(key=lambda a: a['minimum_timed_center_distance_m'])
                rows.append({'recording': recording, 'location': location, 'ego_track_id': ego_id, 'first_frame': start, 'last_frame': start + 225, 'ego_source_last_frame': last, 'source_window_complete': bool(source_window_complete), 'ego_class': m['class'], 'ego_path_m': length, 'ego_displacement_m': displacement, 'turn_rad': turn, 'source_motion_qualified': motion_qualified, 'first_goal_radius_step': first_goal_radius_step, 'nearby_actor_count': len(near), 'nearby_moving_actor_count': sum((a['moving'] for a in near)), 'nearby_vru_count': sum((a['class'] in ('bicycle', 'pedestrian') for a in near)), 'nearest_actors': near, 'source_rejection': reason})
        print(f'recording {recording:02d}: {len(rows)} cumulative windows', flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'schema_version': 3, 'selection': {'window_source_frames': 225, 'stride_frames': stride_frames, 'minimum_ego_path_m': minimum_motion, 'minimum_ego_displacement_m': minimum_displacement, 'goal_sample_step': 85, 'goal_radius_m': 2.0, 'earliest_goal_radius_step': 75, 'timed_proximity_m': proximity, 'locations': sorted(locations) if locations else [1, 2, 3, 4]}, 'counts': dict(Counter((r['source_rejection'] or 'source_pass' for r in rows))), 'windows': rows}, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'counts': dict(Counter((r['source_rejection'] or 'source_pass' for r in rows))), 'location_counts': dict(Counter((r['location'] for r in rows if r['source_rejection'] is None)))}, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=project_path('pilot/audits/all_moving_windows.json'))
    ap.add_argument('--stride-frames', type=int, default=225)
    ap.add_argument('--locations', type=int, nargs='*')
    ap.add_argument('--minimum-path-m', type=float, default=15.0)
    ap.add_argument('--minimum-displacement-m', type=float, default=10.0)
    args = ap.parse_args()
    source_windows(args.output, stride_frames=args.stride_frames, locations=set(args.locations) if args.locations else None, minimum_motion=args.minimum_path_m, minimum_displacement=args.minimum_displacement_m)
