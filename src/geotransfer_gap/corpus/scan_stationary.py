"""Scan source-rate 9-second vehicle windows for the static-expert rule."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from geotransfer_gap.conversion.pilot_ind import SOURCE

def scan_recording(recording):
    metadata = {int(r['trackId']): r for r in csv.DictReader((SOURCE / f'data/{recording:02d}_tracksMeta.csv').open())}
    vehicles = {tid for tid, row in metadata.items() if row['class'] in ('car', 'truck_bus')}
    windows = 0
    loose = 0
    strict = 0
    sampled_marked = 0
    sampled_false_static = []
    sampled_false_static_count = 0
    marginal = []
    temporary_stops = []
    marked_tracks = set()
    tid_current = None
    records = []

    def process(track_id, rows):
        nonlocal windows, loose, strict, sampled_marked, sampled_false_static_count
        if track_id not in vehicles or len(rows) < 226:
            return
        arr = np.asarray(rows, dtype=float)
        xy = arr[:, 1:3]
        speed = np.hypot(arr[:, 3], arr[:, 4])
        cumulative = np.r_[0, np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))]
        whole_path = float(cumulative[-1])
        for start in range(0, len(rows) - 225, 25):
            end = start + 225
            if arr[end, 0] - arr[start, 0] != 225:
                continue
            windows += 1
            path = float(cumulative[end] - cumulative[start])
            vmax = float(np.max(speed[start:end + 1]))
            is_loose = path < 0.5 and vmax < 0.1
            is_strict = path < 0.25 and vmax < 0.05
            samples = np.arange(91) * 2.5 + arr[start, 0]
            sx = np.interp(samples, arr[:, 0], arr[:, 1])
            sy = np.interp(samples, arr[:, 0], arr[:, 2])
            svx = np.interp(samples, arr[:, 0], arr[:, 3])
            svy = np.interp(samples, arr[:, 0], arr[:, 4])
            sampled_path = float(np.sum(np.hypot(np.diff(sx), np.diff(sy))))
            sampled_speed = float(np.max(np.hypot(svx, svy)))
            is_sampled = sampled_path < 0.5 and sampled_speed < 0.1
            loose += is_loose
            strict += is_strict
            sampled_marked += is_sampled
            if is_sampled and (not is_loose):
                sampled_false_static_count += 1
                if len(sampled_false_static) < 20:
                    sampled_false_static.append({'track_id': track_id, 'first_frame': int(arr[start, 0]), 'source_path_m': path, 'source_max_speed_mps': vmax, 'sampled_path_m': sampled_path, 'sampled_max_speed_mps': sampled_speed})
            if is_loose:
                marked_tracks.add(track_id)
                if whole_path > 5 and len(temporary_stops) < 20:
                    temporary_stops.append({'track_id': track_id, 'first_frame': int(arr[start, 0]), 'window_path_m': path, 'max_speed_mps': vmax, 'whole_track_path_m': whole_path})
            if is_loose != is_strict and len(marginal) < 20:
                marginal.append({'track_id': track_id, 'first_frame': int(arr[start, 0]), 'window_path_m': path, 'max_speed_mps': vmax})
    with (SOURCE / f'data/{recording:02d}_tracks.csv').open() as f:
        for row in csv.DictReader(f):
            tid = int(row['trackId'])
            if tid_current is not None and tid != tid_current:
                process(tid_current, records)
                records = []
            tid_current = tid
            if tid in vehicles:
                records.append((int(row['frame']), float(row['xCenter']), float(row['yCenter']), float(row['xVelocity']), float(row['yVelocity'])))
    if tid_current is not None:
        process(tid_current, records)
    return {'recording': recording, 'vehicle_tracks': len(vehicles), 'nine_second_windows': windows, 'marked_at_path_0_5m_speed_0_1mps': loose, 'marked_at_path_0_25m_speed_0_05mps': strict, 'marked_at_10hz_path_0_5m_speed_0_1mps': sampled_marked, 'sampled_false_static_count': sampled_false_static_count, 'sampled_false_static_examples': sampled_false_static, 'distinct_marked_tracks': len(marked_tracks), 'marginal_examples': marginal, 'temporary_stop_examples': temporary_stops}
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--recordings', type=int, nargs='+', default=[0, 4, 8, 13, 20, 21, 24, 28])
    ap.add_argument('--output', type=Path, default=Path(__file__).parent / 'pilot/audits/stationary_scan.json')
    args = ap.parse_args()
    result = [scan_recording(r) for r in args.recordings]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps([{k: v for k, v in x.items() if not k.endswith('examples')} for x in result], indent=2))
