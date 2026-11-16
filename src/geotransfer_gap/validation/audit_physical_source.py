"""Audit source-scale actor boxes against Lanelet2 boundaries and each other."""
from geotransfer_gap.maps import lanelet
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from geotransfer_gap.validation.audit_parked_contacts import segment_hits_box

def corners(obj, t):
    pos = obj['position'][t]
    c, s = (math.cos(obj['heading'][t]), math.sin(obj['heading'][t]))
    return [(pos['x'] + a * obj['length'] / 2 * c - b * obj['width'] / 2 * s, pos['y'] + a * obj['length'] / 2 * s + b * obj['width'] / 2 * c) for a, b in ((-1, -1), (-1, 1), (1, 1), (1, -1))]

def boxes_overlap(a, b, t):
    ac, bc = (corners(a, t), corners(b, t))
    for poly in (ac, bc):
        for u, v in zip(poly, poly[1:] + poly[:1]):
            axis = (v[1] - u[1], u[0] - v[0])
            ap = [x * axis[0] + y * axis[1] for x, y in ac]
            bp = [x * axis[0] + y * axis[1] for x, y in bc]
            if max(ap) < min(bp) or max(bp) < min(ap):
                return False
    return True

def overlap_penetration_m(a, b, t):
    """Smallest translation that separates two overlapping source rectangles."""
    ac, bc = (corners(a, t), corners(b, t))
    penetration = float('inf')
    for poly in (ac, bc):
        for u, v in zip(poly, poly[1:] + poly[:1]):
            axis = (v[1] - u[1], u[0] - v[0])
            norm = math.hypot(*axis)
            ap = [x * axis[0] + y * axis[1] for x, y in ac]
            bp = [x * axis[0] + y * axis[1] for x, y in bc]
            penetration = min(penetration, (min(max(ap), max(bp)) - max(min(ap), min(bp))) / norm)
    return max(0.0, penetration)

def polygon_gap(a, b):
    """Minimum oriented-box separation; zero for contact or overlap."""
    for poly in (a, b):
        for u, v in zip(poly, poly[1:] + poly[:1]):
            axis = (v[1] - u[1], u[0] - v[0])
            ap = [x * axis[0] + y * axis[1] for x, y in a]
            bp = [x * axis[0] + y * axis[1] for x, y in b]
            if max(ap) < min(bp) or max(bp) < min(ap):
                break
        else:
            continue
        break
    else:
        return 0.0
    best = float('inf')
    for points, poly in ((a, b), (b, a)):
        for point in points:
            for u, v in zip(poly, poly[1:] + poly[:1]):
                dx, dy = (v[0] - u[0], v[1] - u[1])
                denom = dx * dx + dy * dy
                fraction = max(0.0, min(1.0, ((point[0] - u[0]) * dx + (point[1] - u[1]) * dy) / denom)) if denom else 0.0
                best = min(best, math.dist(point, (u[0] + fraction * dx, u[1] + fraction * dy)))
    return best

def audit(root):
    testing = root / 'testing'
    validation = json.loads((testing / 'validation.json').read_text())
    scene = json.loads(next(testing.glob('ind_*.json')).read_text())
    recording = validation['recording']
    with (settings().source / f'data/{recording:02d}_recordingMeta.csv').open() as f:
        meta = next(csv.DictReader(f))
    osm_path, _ = lanelet.map_paths(meta, recording)
    osm = ET.parse(osm_path).getroot()
    nodes = lanelet.project_nodes(osm, float(meta['xUtmOrigin']), float(meta['yUtmOrigin']))
    ways = {}
    for way in osm.findall('way'):
        tags = {tag.get('k'): tag.get('v') for tag in way.findall('tag')}
        if tags.get('type') not in ('road_border', 'curbstone'):
            continue
        coords = [nodes[int(n.get('ref'))] for n in way.findall('nd')]
        ways[int(way.get('id'))] = {'tags': tags, 'coords': coords}
    emitted = {road['id'] for road in scene['roads'] if road['type'] == 'road_edge'}
    contacts = defaultdict(list)
    for obj in scene['objects']:
        if obj['type'] != 'vehicle':
            continue
        for t, valid in enumerate(obj['valid']):
            if not valid:
                continue
            pos = obj['position'][t]
            center = (pos['x'], pos['y'])
            for wid in emitted:
                way = ways[wid]
                pts = way['coords']
                if not pts or min((x for x, _ in pts)) > center[0] + obj['length'] or max((x for x, _ in pts)) < center[0] - obj['length']:
                    continue
                if any((segment_hits_box(a, b, center, obj['heading'][t], obj['length'], obj['width']) for a, b in zip(pts, pts[1:]))):
                    contacts[str(obj['id'])].append({'step': t, 'edge_id': wid, 'type': way['tags'].get('type'), 'subtype': way['tags'].get('subtype')})
    overlaps = defaultdict(list)
    objects = scene['objects']
    for i, a in enumerate(objects):
        for b in objects[i + 1:]:
            if a['type'] != 'vehicle' and b['type'] != 'vehicle':
                continue
            for t in range(len(a['valid'])):
                if not a['valid'][t] or not b['valid'][t]:
                    continue
                pa, pb = (a['position'][t], b['position'][t])
                if math.dist((pa['x'], pa['y']), (pb['x'], pb['y'])) > (math.hypot(a['length'], a['width']) + math.hypot(b['length'], b['width'])) / 2:
                    continue
                if boxes_overlap(a, b, t):
                    overlaps[f"{a['id']}-{b['id']}"].append(t)
    pixel_scale_m = lanelet.background_pixel_scale(meta)
    overlap_details = {}
    ego = objects[0]
    for pair_id, steps in overlaps.items():
        a_id, b_id = map(int, pair_id.split('-'))
        a = next((obj for obj in objects if obj['id'] == a_id))
        b = next((obj for obj in objects if obj['id'] == b_id))
        ego_gaps = [min((polygon_gap(corners(ego, t), corners(obj, t)) for obj in (a, b))) for t in range(len(ego['valid'])) if ego['valid'][t] and a['valid'][t] and b['valid'][t]]
        stationary = all((obj['source_window_path_length_m'] <= 0.5 and obj['source_window_max_speed_mps'] <= 0.1 and obj['mark_as_expert'] for obj in (a, b)))
        depth = max((overlap_penetration_m(a, b, t) for t in steps))
        gap = min(ego_gaps) if ego_gaps else None
        overlap_details[pair_id] = {'track_ids': [a_id, b_id], 'maximum_penetration_m': depth, 'minimum_ego_box_gap_m': gap, 'both_stationary_expert': stationary, 'source_paths_m': [a['source_window_path_length_m'], b['source_window_path_length_m']], 'source_max_speeds_mps': [a['source_window_max_speed_mps'], b['source_window_max_speed_mps']], 'reviewable_annotation_overlap': bool(stationary and depth <= 3 * pixel_scale_m and (gap is not None) and (gap >= 3.0))}
    report = {'schema_version': 2, 'binary_sha256': hashlib.sha256((testing / 'map_000000.bin').read_bytes()).hexdigest(), 'lanelet_source_sha256': hashlib.sha256(osm_path.read_bytes()).hexdigest(), 'collision_scale': 1.0, 'source_background_pixel_scale_m': pixel_scale_m, 'stationary_overlap_tolerance_m': 3 * pixel_scale_m, 'emitted_boundary_types': dict(Counter((f"{ways[wid]['tags'].get('type')}:{ways[wid]['tags'].get('subtype')}" for wid in emitted))), 'source_box_boundary_contacts': {k: {'count': len(v), 'first': v[:10]} for k, v in contacts.items()}, 'source_box_actor_overlaps': {k: {'count': len(v), 'first_steps': v[:10]} for k, v in overlaps.items()}, 'source_box_actor_overlap_details': overlap_details}
    (testing / 'physical_source_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    audit(ap.parse_args().root.resolve())
