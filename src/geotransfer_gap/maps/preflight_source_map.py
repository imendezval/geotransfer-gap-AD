"""Source-only lanelet occupancy and directed-route preflight for all catalog windows.

This is a fast search index.  Final admission still uses the independent
converter, geometry audit, source replay, and evaluator gate.
"""
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from matplotlib.path import Path as PolygonPath

def map_data(meta, recording):
    recording = recording
    osm_path, _ = lanelet.map_paths(meta, recording)
    osm = ET.parse(osm_path).getroot()
    nodes = lanelet.project_nodes(osm, float(meta['xUtmOrigin']), float(meta['yUtmOrigin']))
    ways = {int(w.get('id')): [nodes[int(n.get('ref'))] for n in w.findall('nd')] for w in osm.findall('way')}
    polygons = {}
    for relation in osm.findall('relation'):
        tags = {t.get('k'): t.get('v') for t in relation.findall('tag')}
        if tags.get('type') != 'lanelet' or tags.get('subtype') not in ('road', 'bus_lane'):
            continue
        refs = {m.get('role'): int(m.get('ref')) for m in relation.findall('member') if m.get('type') == 'way'}
        if 'left' in refs and 'right' in refs:
            polygons[int(relation.get('id'))] = PolygonPath(lanelet.lanelet_polygon(ways[refs['left']], ways[refs['right']]))
    roads, lanes = lanelet.make_roads(meta, recording)
    graph = {r['id']: r['exit_lanes'] for r in roads if r['type'] == 'lane'}
    return (polygons, graph, lanes)

def reachable(graph, start, goal):
    seen, pending = ({start}, [start])
    while pending:
        for nxt in graph[pending.pop()]:
            if nxt == goal:
                return True
            if nxt not in seen:
                seen.add(nxt)
                pending.append(nxt)
    return start == goal

def main(args):
    catalog = json.loads(args.catalog.read_text())
    selected = [r for r in catalog['windows'] if r['source_rejection'] is None]
    out = []
    for recording in range(33):
        rows = [r for r in selected if r['recording'] == recording]
        if not rows:
            continue
        meta = next(csv.DictReader((settings().source / f'data/{recording:02d}_recordingMeta.csv').open()))
        polygons, graph, lanes = map_data(meta, recording)
        needed_ids = {r['ego_track_id'] for r in rows}
        df = pd.read_csv(settings().source / f'data/{recording:02d}_tracks.csv', usecols=['frame', 'trackId', 'xCenter', 'yCenter'])
        df = df[df['trackId'].isin(needed_ids)]
        tracks = {int(tid): group[['frame', 'xCenter', 'yCenter']].to_numpy(dtype=float) for tid, group in df.groupby('trackId', sort=False)}
        for row in rows:
            track = tracks[row['ego_track_id']]
            frames = row['first_frame'] + np.arange(91) * 2.5
            if frames[0] < track[0, 0] or frames[-1] > track[-1, 0]:
                out.append({'recording': recording, 'location': row['location'], 'ego_track_id': row['ego_track_id'], 'first_frame': row['first_frame'], 'outside_sample_count': len(frames), 'nearest_start_lane': None, 'nearest_goal_lane': None, 'directed_route': False, 'source_track_complete': False, 'source_nearby_moving_actors': row['nearby_moving_actor_count'], 'source_nearby_vrus': row['nearby_vru_count'], 'turn_rad': row['turn_rad']})
                continue
            points = np.column_stack((np.interp(frames, track[:, 0], track[:, 1]), np.interp(frames, track[:, 0], track[:, 2])))
            occupied = np.zeros(len(points), dtype=bool)
            for poly in polygons.values():
                occupied |= poly.contains_points(points, radius=1e-08)
            start = min(lanes, key=lambda lid: lanelet.point_polyline_distance(tuple(points[0]), lanes[lid]['coords']))
            goal = min(lanes, key=lambda lid: lanelet.point_polyline_distance(tuple(points[85]), lanes[lid]['coords']))
            out.append({'recording': recording, 'location': row['location'], 'ego_track_id': row['ego_track_id'], 'first_frame': row['first_frame'], 'outside_sample_count': int((~occupied).sum()), 'nearest_start_lane': start, 'nearest_goal_lane': goal, 'directed_route': reachable(graph, start, goal), 'source_track_complete': True, 'source_nearby_moving_actors': row['nearby_moving_actor_count'], 'source_nearby_vrus': row['nearby_vru_count'], 'turn_rad': row['turn_rad']})
        print(f'recording {recording:02d}: {len(rows)} motion-qualified windows', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'schema_version': 2, 'method': 'all 91 sampled ego centers inside a road/bus lanelet polygon and nearest start-to-goal directed lane route', 'counts': dict(Counter((f"location_{r['location']}_map_{r['outside_sample_count'] == 0 and r['directed_route']}" for r in out))), 'windows': out}, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'counts': dict(Counter((f"location_{r['location']}_map_{r['outside_sample_count'] == 0 and r['directed_route']}" for r in out)))}, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--catalog', type=Path, default=project_path('pilot/audits/all_moving_windows.json'))
    ap.add_argument('--output', type=Path, default=project_path('pilot/audits/source_map_preflight.json'))
    main(ap.parse_args())
