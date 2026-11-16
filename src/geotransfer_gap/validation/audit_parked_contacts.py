"""Find curb segments touching parked-car boxes at source step zero."""
from geotransfer_gap.config import PROJECT_ROOT, settings, project_path, tool_path
import argparse
import json
import math
from pathlib import Path

def segment_hits_box(a, b, center, heading, length, width):
    c, s = (math.cos(heading), math.sin(heading))

    def local(p):
        dx, dy = (p[0] - center[0], p[1] - center[1])
        return (dx * c + dy * s, -dx * s + dy * c)
    ax, ay = local(a)
    bx, by = local(b)
    dx, dy = (bx - ax, by - ay)
    low, high = (0.0, 1.0)
    for p, q in ((-dx, ax + length / 2), (dx, length / 2 - ax), (-dy, ay + width / 2), (dy, width / 2 - ay)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        elif p < 0:
            low = max(low, q / p)
        else:
            high = min(high, q / p)
    return low <= high

def audit(root, lost_ids):
    testing = root / 'testing'
    scene = json.loads(next(testing.glob('ind_*.json')).read_text())
    roads = [r for r in scene['roads'] if r['type'] == 'road_edge']
    rows = []
    for obj in scene['objects']:
        if obj['id'] not in lost_ids:
            continue
        pos = obj['position'][0]
        center = (pos['x'], pos['y'])
        contacts = []
        for road in roads:
            pts = [(v['x'], v['y']) for v in road['geometry']]
            if any((segment_hits_box(a, b, center, obj['heading'][0], obj['length'] * 0.7, obj['width'] * 0.7) for a, b in zip(pts, pts[1:]))):
                contacts.append(road['id'])
        rows.append({'track_id': obj['id'], 'source_length_m': obj['length'], 'source_width_m': obj['width'], 'collision_shrink': 0.7, 'touching_road_edge_ids': contacts})
    result = {'scene': str(root), 'lost_track_contacts': rows, 'all_lost_tracks_touch_road_edge': all((x['touching_road_edge_ids'] for x in rows))}
    (testing / 'parked_contact_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--lost-ids', type=int, nargs='+', required=True)
    a = ap.parse_args()
    audit(a.root.resolve(), set(a.lost_ids))
